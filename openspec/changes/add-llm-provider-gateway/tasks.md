## 1. 阶段一：gateway 骨架与能力契约

- [x] 1.1 新建 `src/finance_agent/llm/` 包：`types.py` 定义 Capability（含 `reasoning_forced`）/ ModelProfile / CanonicalRequest / CanonicalEvent / typed errors，TDD 先行（tests/llm/test_types.py）
- [x] 1.2 `registry.py` 内置最小能力表（DeepSeek 官方 / OpenAI / Anthropic / Gemini / Ollama-vLLM / 自定义 OpenAI 兼容），静态表数据驱动测试
- [x] 1.3 `resolver.py` 唯一配置解析入口：请求级 → profile → 环境变量 → 默认的优先级、半套配置显式报错、`openai/<model>` 前缀规则、judge purpose 纳入解析；覆盖 PR #74 的「调用时读环境」语义
- [x] 1.4 `adapters/litellm_adapter.py` 初始化收口：迁移 `disable_streaming_logging`、请求级 timeout、litellm-langfuse 兼容补丁到 adapter；泄漏守护测试（线程/端口稳定性）迁入
- [x] 1.5 CI grep 门禁：`src/finance_agent/**` 除 `llm/adapters/**` 与薄壳外禁止 `import litellm`（先允许存量、按阶段收紧）

## 2. 阶段二：adapter 行为合同

- [x] 2.1 消息序列化收口：`_sanitize_messages_for_openai_compat` + `_normalize_arguments_str`（含「模型下发 arguments」规范化）迁入 adapter，按 `capability.reasoning_must_echo_on_tool` 决定 reasoning 字段回传
- [x] 2.2 finish_reason 归一化：`length/content_filter/empty/unknown` 分型 → OutputTruncated / ContentFiltered / EmptyLLMOutput typed errors；`length` 触发预算复核钩子
- [x] 2.3 max_tokens 预算派生：按 `capability.max_output` + `reasoning_forced` 派生（替换 16384 硬编码），trace 标记派生来源
- [x] 2.4 错误归一化：AuthError / RateLimitError / TimeoutError / ModelNotFound / ContextOverflow / ContentFiltered / UnsupportedCapability / UnknownLLMError 映射与可重试分类（含 PR #74 的服务错误重试语义）
- [x] 2.5 关键参数不静默丢弃：移除全局 `drop_params=True` 直通（adapter 白名单化），不支持的关键参数抛 UnsupportedCapabilityError

## 3. 阶段三：输出合同统一

- [ ] 3.1 `contracts.py`：extract_json（fence/噪声/平衡对象/尾逗号清理）+ Pydantic validate + repair prompt（schema+错误+原输出）重试 1-2 次 + OutputContractError(raw_excerpt)
- [ ] 3.2 并入现有收口：`parse_json_response` / `call_llm_for_json` 的能力并入 contracts（保持对外函数签名兼容或迁移调用点），管线六节点与 citation 数值校验走合同
- [ ] 3.3 ReAct action 文本协议兜底：`<action>`/`<observation>` 协议、CanonicalToolCall 归一、capability.tools=none 时启用，trace 记 degradation
- [ ] 3.4 评估链路输入合同：judge 输入变量提取非空断言，空维度记 `input_missing`（score=null + 原因），pydantic 兼容用例迁移；judge 配置改走 resolver
- [ ] 3.5 ReAct loop 消费 CanonicalEvent：harness/loop.py 改造为消费归一事件流（reasoning/tool delta 合并移入 adapter）

## 4. 阶段四：probe、前端与门禁

- [ ] 4.1 `probes.py` 五项探测（non_stream/stream/tool_call/tool_followup/json_output）+ 能力表修正（probe 事实覆盖静态默认 + warnings）
- [ ] 4.2 `/api/llm-config/test` 升级：返回 effective 配置 + capability 矩阵 + warnings；前端设置页展示能力矩阵，capability 不满足时禁用对应模式入口
- [ ] 4.3 `tests/llm_contracts/` 合同测试组（12 用例模板）接入 CI：litellm 升级 / 模型 alias 变更 / prompt 变更触发；未过工具合同的 profile 禁入深度模式（下拉过滤或标红）
- [ ] 4.4 trace 契约字段：generation metadata 增加 profile/provider/purpose/capability/finish_reason/repair_count/fallback_from/degradation；judge 独立 environment 审计（维度/输入断言/分数）

## 5. 阶段五：迁移收尾与治理

- [ ] 5.1 旧路径切薄壳：`llm.py` 三入口与 `harness/litellm_client.py` 转调 gateway（deprecation warning），合同测试对拍双路径一致后收紧 grep 门禁
- [ ] 5.2 端到端验证：全量 pytest + 一轮 evals 跑批（方舟 GLM + opencode judge）比对 r6 基线（judge_failures=0、四 rubric 有意义分布不回退）
- [ ] 5.3 文档：架构文档更新（docs/architecture.md 增 gateway 层）、incident 016/017 补「根治指向」链接；@live 用例改为读 resolver 配置（修方舟 404 环境性失败）
- [ ] 5.4 人工验证报告落 `tests/validation/`（设置页 probe 交互 + 换 provider 演练），走 sync + archive
