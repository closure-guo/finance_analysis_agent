# Proposal: add-toolcall-evaluation

## Why

快速模式（ReAct）的核心能力是工具调用，但评估体系目前只评最终文本质量（引用、多视角等维度），对「调了什么工具、参数对不对、顺序合不合理、失败恢复如何」完全无评估。parse-ark-text-tool-call 等历史事故说明工具调用链路脆弱且无回归护栏。

## What Changes

- 轨迹采集：从 Langfuse trace 提取工具调用序列（工具名、参数、耗时、成败、重试次数）
- 评估维度：工具选择正确性（该搜时搜了吗）、参数合法性、调用效率（冗余/循环调用检测）、失败恢复（一次失败后是否换策略）
- 评测集：构造带工具调用预期的 quick 模式样本（golden tool sequence 或合法集合断言）
- 门禁：工具调用维度纳入评测门禁（回归阈值），@live nightly 防漂移

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增工具调用维度（轨迹提取、评估指标、门禁断言）

## Impact

- 依赖：quick 模式 ReAct trace 结构（langfuse-trace-agent-attribution 已建）；评估样本集新增
- 与 add-hallucination-rate-metric 有数据复用（工具返回内容是事实校验的证据源）
- 约束：断言必须容忍合理的策略差异（合法集合而非唯一序列），避免脆性门禁
