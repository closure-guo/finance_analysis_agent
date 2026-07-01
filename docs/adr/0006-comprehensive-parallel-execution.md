# ADR-0006: Comprehensive 模式并行执行架构

## Status: Superseded by [ADR-0011](0011-five-layer-architecture.md)

> **Superseded**: FA/IA 双 Agent 并行已被 ADR-0011 的 4 个分析师并行替代。Send API 并行模式被继承，但应用对象从 fa_analyze/ia_analyze 变为 macro/fundamental/technical/sentiment 4 个分析师。

## Context

Comprehensive 分析需要同时运行财务分析（FA）和投资分析（IA）两个 Agent。初始实现使用条件边返回列表 `["fa_analyze", "ia_analyze"]`，但 LangGraph 默认顺序执行这些节点，导致 comprehensive 模式总耗时 ≈ 2.5× 单 Agent 模式（5 次串行 LLM 调用）。

改用 LangGraph `Send` API 从 `compute_metrics` 节点直接并行派发 `fa_analyze` 和 `ia_analyze`。两个 Agent 节点各自执行完毕后都路由到 `merge`，LangGraph 自动等待所有并行分支完成后才触发 merge。

## 为什么选 Send API

考虑过四种方案：

| 方案 | 实现复杂度 | comprehensive 耗时 | 风险 |
|------|-----------|-------------------|------|
| A. 串行 | 无改动 | ~5 次 LLM | 用户体验差 |
| **B. Send API** | 改 3 行 | ~3 次 LLM | 低 |
| C. 全节点并行 | 拆 4 个节点 | ~1 次 LLM | 破坏双阶段生成内聚性 |
| D. async call_llm | 改调用层 | 不确定 | LangGraph 同步执行器下收益有限 |

B 是收益/风险比最优的：只改 graph 拓扑（routing.py + graph.py），不改节点内部逻辑。两个 Agent 写不重叠的 state key（`financial_*` vs `investment_*`），天然线程安全。
