## Context

完整设计依据见《[LLM Provider Gateway 设计档案](../../../docs/design/LLM%20Provider%20Gateway%20设计档案.md)》（含目录结构、数据模型、P0 修复清单、迁移计划），本文件只记录 delta 范围内的关键决策与该档案的差异增补。

现状：LLM 调用散布在 `llm.py`（三入口 + DeepSeek thinking 特判）、`harness/litellm_client.py`（ReAct 流式客户端 + 自有 DeepSeek 分支 + 消息清洗）、`agent_factory.py`（按 mode 构建）、`nodes/_llm_utils.py`（parse/retry 收口）、`react_agent.py`/`nlp.py`（各自 JSON 提取）。2026-08-16 换方舟 GLM + opencode judge 后实测 7 个 bug（PR #74 七个 commit 已修复其表层），本 delta 是根治性架构收口。

已落地事实（PR #74，作为迁移起点而非重做）：请求级 timeout、`_sanitize_messages_for_openai_compat`（剥 reasoning_content + arguments 规范化）、`call_llm_for_json`（解析/服务错误重试）、`litellm.disable_streaming_logging` 双入口、citation 容错、evals 提取 pydantic 兼容。

## Goals / Non-Goals

**Goals:**
- 业务代码不感知 provider 细节：不出现模型名字符串分支，不直接 import litellm
- 新增 provider 只改 profile + adapter 映射 + 合同测试，不改 Agent 核心
- 换 provider 从「全身手术」变为受控配置变更，且有合同测试证明可用

**Non-Goals:**
- 不追求所有 provider 行为一致；能力缺失时降级、观测、可回滚即可
- 不自研替代 litellm 协议细节；litellm 是 adapter 内的实现选择
- 第一阶段不做成本优化与多模型博弈路由
- 不含前端 profile 管理重构（沿用 add-custom-llm-api 已有 profile 概念，仅升级 probe 展示）

## Decisions

1. **渐进迁移而非一次性重写**：旧 `llm.py.call_llm*` 与 `harness/litellm_client.py` 保留薄壳转调 gateway（deprecation warning），管线节点与 ReAct 循环分批切换。理由：主链路刚被 PR #74 修复稳定，一次性替换风险高于收益。
2. **Capability 增加 `reasoning_forced` 字段**（超出设计档案 §6）：方舟 GLM 实测 `thinking.type=disabled` 被 400 拒、`reasoning_effort` 不透传——该事实决定 max_tokens 预算策略（reasoning 与正文共享配额），必须显式建模，resolver 依据它派生预算而非全局写死。
3. **arguments 规范化范围扩展到「模型下发」**（超出档案 §8 硬性修正）：档案只约束自己序列化 `json.dumps`；实战证明模型自己输出的 arguments 就可能是单引号 Python 字面量（GLM），回传前必须规范化。已实现于 `_normalize_arguments_str`，迁入 adapter。
4. **litellm 运行时防护是 adapter 的初始化职责**（档案未覆盖）：`disable_streaming_logging`、timeout 等开关统一在 adapter 首次初始化设置并一次性记 trace；泄漏守护（线程数/本地监听端口稳定性）进合同测试。理由：incident 016 证明库级平台 bug 与协议无关，业务模块各自设置必然漂移。
5. **评估链路纳入输出合同**（档案未覆盖）：judge 输入变量提取兼容 dict/pydantic + 关键维度非空断言（空输入记 `input_missing` 跳过，不出正常分数）。理由：r5 校准实测「静默空辩论打 1 分」污染均值且不可察觉——输出合同原则必须延伸到评估管道。
6. **finish_reason 分类在 adapter 归一化**：`length/content_filter/empty/unknown` 分型，`length` 触发预算复核或 repair（当前 16384 硬编码升级为按 capability.max_output + reasoning_forced 派生），`content_filter` 不重试。理由：截断表现为下游 JSONDecodeError 的根因是没有分型。
7. **probe 以运行时事实修正静态能力表**：registry 静态表是默认值，probe 结果是事实；冲突以 probe 为准并写 warning。合同测试门禁（未过工具合同的 profile 禁入深度模式）在 CI 强制。
8. **evals judge 配置走 resolver**：JUDGE_* 环境变量纳入 profile 解析（judge 作为独立 purpose），根治「import 时序固化 + 回退漂移」类问题（PR #74 已做调用时读取的表层修复，本 delta 收口为结构修复）。

## Risks / Trade-offs

- **迁移期双路径并存**：薄壳与 gateway 并存期间行为可能漂移；用合同测试对拍（同一组用例跑薄壳与 gateway 路径）收敛后删除薄壳。
- **能力表维护成本**：静态表会过期（如 provider 行为随版本变化）；靠 probe 校准 + 合同测试 canary 缓解，接受「表是默认、probe 是事实」的折中。
- **repair 增加延迟**：结构化节点允许 1-2 次 repair，超过走 fallback；不在关键路径做无限修复。
- **action 文本协议冗长**：比 native tools 多耗 token，仅作无工具 provider 的兜底，不默认启用。
- **范围大、周期长**：按档案四阶段推进（止血→收口→合同化→治理），本 delta 的 tasks 分阶段可独立交付；P0 六项中已被 PR #74 覆盖的不再重复实施。
