## Why

当前系统的 LLM 调用封装边界太薄、入口太多、能力判断靠模型名猜测（`_is_deepseek(model)` 字符串分支散布在 `llm.py` 与 `harness/litellm_client.py`）。2026-08-16 将管线从 DeepSeek 切换到方舟 GLM-5.2 + opencode judge 后，评估跑批连环暴露 7 个独立 bug（incident 016/017 及 5 个后续修复，PR #74），其中 5 个正是《[LLM Provider Gateway 设计档案](../../../docs/design/LLM%20Provider%20Gateway%20设计档案.md)》§1 预判的根因类别：

- provider 字段语义相反（DeepSeek 要求回传 `reasoning_content`、方舟拒收该字段）
- `tool_calls[].function.arguments` 非法 JSON（GLM 自己输出单引号 Python 字面量，原样回传被方舟严格校验 400）
- reasoning 与正文共享 max_tokens 配额导致截断/空正文（`finish_reason=length` 无独立处理）
- 结构化输出解析失败直接炸管线节点（citation 裸 `float(dict)`）
- judge 配置半套漂移（JUDGE_* 回退 LLM_* 打错网关）

另有 3 个档案未覆盖、由实战暴露的缺口，一并纳入本 delta：

1. **litellm 库自身平台性 bug 无防护**：litellm 1.85.1 流式 logging 全局线程池在 Windows/Py3.14 socketpair 竞态死锁（incident 016，100 worker 全灭、进程挂死）——与协议无关，adapter 边界挡不住，需要运行时开关与泄漏守护的统一收口。
2. **评估链路无输出合同**：judge 输入变量（debate_history 等）静默为空时照常打分（对空辩论打 1 分混入真实分数），「自信但失真」。
3. **「强制 thinking」无 capability 字段承载**：方舟 GLM thinking 强制开启不可关（`disabled` 被 400 拒），直接影响 max_tokens 预算策略，现有 Capability 草案没有此字段。

## What Changes

- 新建 `src/finance_agent/llm/` gateway 包：`types`（Capability/ModelProfile/CanonicalRequest/CanonicalEvent）、`registry`（provider 能力表）、`resolver`（唯一配置解析入口）、`gateway`（complete/stream/with_tools）、`errors`（typed errors）、`contracts`（结构化输出合同）、`probes`（能力探测）、`adapters/litellm_adapter`（唯一允许 import litellm 的地方）
- Capability 显式化：废弃全代码库 `_is_deepseek(model)` 类判断，改为 `capability.reasoning_field` / `capability.reasoning_forced` / `capability.tools` 等契约字段；新增 `reasoning_forced` 承载「thinking 强制开启不可关」
- 消息序列化规则收口 adapter：`reasoning_content` 仅在 `reasoning_must_echo_on_tool` 为真时回传；模型下发的 `arguments` 字符串回传前规范化为合法 JSON（不限于自己序列化的场景）
- `finish_reason` 归一化处理：`length/content_filter/empty/unknown` 分类，`length` 触发 max_tokens 复核或 repair，`content_filter` 不盲目重试，空输出抛 `EmptyLLMOutput`
- 结构化输出合同统一：所有「LLM 文本 → json.loads/Pydantic/进管线/进评估」的路径走 `extract_json → validate → repair(1-2次) → fallback → typed error`；judge 输入变量增加非空断言，杜绝静默空输入打分
- litellm 运行时防护归口 adapter 初始化：`disable_streaming_logging`、请求级 timeout、线程/端口泄漏守护测试统一在 adapter 层设置与验证，业务代码不再各自设置
- 连通性测试升级为五项 capability probe（non_stream/stream/tool_call/tool_followup/json_output），前端设置页展示能力矩阵与 warnings，区分「能聊天」与「能跑 Agent」
- 合同测试 `tests/llm_contracts/`：每个启用 profile 跑同一组用例；未通过 tool_call+followup 的 profile 不得用于生产深度模式
- 旧 `llm.py.call_llm*` 与 `harness/litellm_client.py` 保留薄壳转调 gateway（deprecation warning），CI grep 门禁禁止 adapters 外 import litellm

## Capabilities

### New Capabilities

- `llm-provider-gateway`: LLM Provider Gateway 防腐层——能力契约（Capability/ModelProfile）、唯一配置解析入口（ProfileResolver）、adapter 收口（litellm 仅存在于 adapters/ 内，消息序列化/错误归一化/finish_reason 分类/litellm 运行时防护）
- `llm-output-contract`: 结构化输出合同——所有 LLM 文本消费路径（管线节点/ReAct/evals judge 输入）统一 extract→validate→repair→fallback→typed error，禁止裸 parse 炸管线或静默空值污染
- `llm-capability-probe`: provider 能力探测与合同测试——五项 probe、能力矩阵展示、profile 门禁（未过工具合同的 profile 禁入深度模式）、litellm/模型升级触发合同测试

### Modified Capabilities

- `trace-observability`: LLM 调用 trace 新增 profile/provider/capability/finish_reason/repair_count/fallback_from 字段；litellm 运行时防护事件（死锁开关命中、泄漏守护触发）写入 trace

## Impact

- **后端代码**：
  - 新建 `src/finance_agent/llm/` 包（types/registry/resolver/gateway/errors/contracts/probes/adapters）
  - [llm.py](../../../src/finance_agent/llm.py) — 三入口转调 gateway 薄壳；DeepSeek 特判、`disable_streaming_logging` 设置移入 adapter
  - [harness/litellm_client.py](../../../src/finance_agent/harness/litellm_client.py) — 迁移为 adapter 流式实现；`_sanitize_messages_for_openai_compat`/`_normalize_arguments_str` 逻辑收口 adapter
  - [harness/loop.py](../../../src/finance_agent/harness/loop.py) — ReAct 循环消费 CanonicalEvent；action 文本协议兜底
  - [nodes/_llm_utils.py](../../../src/finance_agent/nodes/_llm_utils.py) — `parse_json_response`/`call_llm_for_json` 并入 contracts
  - [agent_factory.py](../../../src/finance_agent/agent_factory.py) — 按 profile 构建 Agent，purpose 决定档位不决定 provider
  - [api.py](../../../src/finance_agent/api.py) — `/api/llm-config/test` 升级五项 probe
  - [citation.py](../../../src/finance_agent/citation.py) — 数值校验过 contracts typed error
  - `evals/judges.py` / `evals/extract.py` — judge 输入变量非空断言
- **前端代码**：设置页 probe 结果展示（能力矩阵 + warnings）、capability 不满足时禁用对应模式入口
- **测试**：新增 `tests/llm_contracts/`；litellm 泄漏守护测试迁入 adapter 测试；CI grep 门禁
- **依赖**：不新增三方依赖；litellm 版本升级须过合同测试（§15 门禁）
- **迁移**：分四阶段（止血 P0 → 收口 → 合同化 → 治理），旧 API 兼容薄壳保证渐进迁移，P0 六项立即修复中已被 PR #74 覆盖的部分（超时/消息清洗/arguments 规范化）作为既有事实并入
