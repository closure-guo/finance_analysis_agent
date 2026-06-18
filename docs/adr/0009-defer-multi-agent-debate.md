# ADR-0009: Defer Multi-Agent Debate, Prioritize Tool-Use Refactor

**Status**: Accepted
**Date**: 2026-06-17

## Context

本项目作为 Agent 开发岗位作品集，需要展示真实的 Agent 架构能力。当前架构（ADR-0002 的「纯 LLM 消费者」模型）在代码层面存在一个根本问题：

`fa_analyze` / `ia_analyze` 调用 `call_llm(prompt, system)`，**`call_llm` 没有任何 `tools` 参数**（见 `src/finance_agent/llm.py`）。这意味着：

1. LLM **无法主动查询数据** — 所有上下文由 `_build_context` 在调用前一次性格式化塞入 prompt
2. LLM **无法动态决策** — 看到数据不足时无法发起工具调用补取，只能编造或写「数据缺失」
3. Agent 节点本质是「按固定模板调一次 LLM」，**不是真正的 Agent**

这是作品集面试时被问到「你的 Agent 和普通 LangChain Chain 有什么区别」时会暴露的核心缺陷。

## Decision

**延后多 Agent 辩论机制，第一优先级做工具使用重构。**

辩论机制（FA/IA 双 Agent 对抗，或 Bull/Bear 立场辩论）作为 Phase 2 或更晚的功能。引入辩论的**触发条件**：Worker（fa_analyze 等）已经具备工具调用能力。

### FinDebate 论文评估

参考 [FinDebate (arXiv:2509.17395)](https://arxiv.org/abs/2509.17395)，论文验证了两个关键设计选择：

1. **单轮辩论优于多轮**：多轮辩论会导致观点趋同（collapse），单轮 + 立场锁定更稳。
2. **锁定初始立场**：Bull/Bear Agent 各自坚持初始观点不退缩，避免共识妥协。

但论文的 Agent 都是 **RAG-grounded** — 每个论点必须由检索到的文档支持。本项目的 Worker 不是。

### 决策依据

| 维度 | 多 Agent 辩论（先做） | 工具使用重构（先做） |
|------|---------------------|---------------------|
| 基础前提 | Worker 需有外部知识 grounding | 无前置依赖 |
| 工程成本 | 中（编排 + 协调器） | 低（litellm tools API 已支持） |
| 面试可解释性 | 强（时髦关键词） | 强（直击「Agent vs Chain」核心区别） |
| 无 grounding 的风险 | 高（两个 LLM 互相编故事） | 低（工具返回真实数据） |
| 复用现有代码 | 低（需重写 Agent 子图） | 高（在 `call_llm` 加 tools 参数即可） |

工具使用是辩论机制的**前置依赖**。在 Worker 没有工具调用能力之前上辩论，等于让两个不会查数据的 LLM 互相对抗 — 用对抗掩盖幻觉，不是用对抗消除幻觉。

## Consequences

- **延后项**：多 Agent 辩论机制（Bull/Bear、Reviewer、Moderator）进入 backlog，待工具使用落地后再评估
- **新建项**：ADR-0010 将详细设计工具使用重构（query_metric / compare_with_peers / flag_anomaly 等工具集 + ReAct 循环）
- **设计保留**：FinDebate 的「单轮 + 立场锁定」安全协议作为未来辩论机制的默认设计基线，避免再次论证
- **评估基础**：工具使用落地后，可通过「Agent 是否发起了预期数量的工具调用」作为评估指标，让 Agent 行为可度量
- **作品集叙事**：本 ADR 本身是面试核心素材 — 展示对「Agent 真正价值」的判断力，不堆砌时髦架构词

## References

- [FinDebate: Multi-Agent-Based Financial Debate System](https://arxiv.org/abs/2509.17395) — 安全协议参考
- Du et al. 2023, *Improving Factuality and Reasoning in Language Models through Multiagent Debate* — 多轮辩论原论文
- Liang et al. 2024, *Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate* — 立场锁定机制
- [ADR-0002](0002-pure-llm-agents.md) — Agent 节点作为纯 LLM 消费者的初始决策（本 ADR 修正其「纯 LLM」被解读为「无工具」的偏差）
