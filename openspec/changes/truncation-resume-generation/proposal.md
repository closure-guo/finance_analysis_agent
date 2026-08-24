## Why

A 股深度分析（deep 模式）的 LLM 生成频繁触发 `finish_reason=length` 截断：方舟 GLM 的 reasoning 与正文共享 `max_tokens` 配额，长 JSON 报告在 16384 配额下 reasoning 一长正文就被掐断。当前处理是「完整重试 + 预算翻倍（16384→32768）」，但重试会重新生成已完成的 reasoning/正文，长节点在 32768 下仍大概率再截（本次 evals 批跑 7 条 deep 全部 `finish_reason=length` 即证）。结果是节点级失败/残缺报告静默进入下游，evals 整条 item 作废。

## What Changes

- **断点续写（拼接式）**：`finish_reason=length` 时不重试完整 prompt，而是以「已生成的正文 + 续写指令」发起一次新请求，只生成缺失的尾部，与前半段拼接成完整输出。Reasoning 不参与续写拼接（正文续写即可满足下游 JSON 解析）。
- **统一在 gateway 层实现**：`complete_text` / `complete_stream` / `complete_stream_async` 三个公共入口共享同一续写逻辑，管线节点、ReAct harness、evals 批跑自动继承，调用方无需改。
- **续写预算与上限**：续写请求沿用剩余输出预算（按剩余配额派生）；续写仍截断则停止（不再无限续写），按既有 `OutputTruncatedError` 语义上抛，但 trace 记录截断段数。
- **可追溯增强**：续写发生/续写仍截断/最终拼接，均写入 generation 观测 metadata（`resume_count`、`truncated=true`），下游可据此识别「这份报告由续写完成」。
- **导入者行为兼容**：不改变成功路径行为；未发生截断时续写逻辑零开销。

## Capabilities

### New Capabilities
- `llm-output-resume`: 覆盖 LLM 输出截断后的断点续写行为——触发条件、续写请求构造、拼接语义、预算边界、截断上限、trace 标记。

### Modified Capabilities
<!-- 无：现有 trace-observability / pipeline-events 的既有 Requirement 不改变，仅新增独立能力。

## Impact

- **核心代码**：`src/finance_agent/llm/gateway.py`（三个 complete 入口）、`src/finance_agent/llm/adapters/litellm_adapter.py`（续写请求构造、`classify_outcome` 联动）、`src/finance_agent/llm/errors.py`（截断上限相关标记）。
- **间接获益方**：`_llm_utils.call_llm_streaming`（节点层不再依赖 32768 加倍重试兜底）、harness ReAct（quick 模式长输出）、evals 批跑（deep item 不再因单次截断作废）。
- **观测**：generation observation metadata 追加 `resume_count`/`truncated` 字段（langfuse；符合既有预算/错误元数据契约）。
- **风险**：续写请求多一次 LLM 调用（成本/延迟 +1 次）；拼接边界需防重复/断词——正文续写以「不重复已给内容」指令 + 尾部原样拼接实现，spec 中锁定拼接契约。