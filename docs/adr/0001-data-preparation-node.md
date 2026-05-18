# ADR-0001: Data Preparation Node (Strategy C)

## Status: Accepted

## Context

财务分析 Agent 和投资分析 Agent 存在大量共享数据需求：

- **三大报表**：财务 Agent 用于计算指标，投资 Agent 用于 DCF 估值（算 FCF）
- **PE/PB/ROE**：两个 Agent 都需要
- **同业公司数据**：财务 Agent 用于同业对比，投资 Agent 用于可比估值

如果两个 Agent 各自独立拉取数据（Strategy A），会导致 API 调用翻倍、计算结果可能不一致。如果用共享缓存（Strategy B），时序耦合导致无法真正并行。

## Decision

在 Supervisor 路由之前插入一个**数据准备子图**（check_cache → fetch_data → compute_metrics），统一负责所有数据拉取和计算，结果写入 LangGraph State。

数据准备子图实现为 LangGraph 子图，包含条件边：
- FULL_HIT → 跳过 fetch 和 compute，直接进入 Route
- RAW_HIT → 跳过 fetch，只执行 compute
- PARTIAL_MISS / FULL_MISS → 执行 fetch → compute

fetch_data 内部分三步：
- Step 1：并行拉取 L1 + L2 无依赖数据
- Step 2：拉取依赖 Step 1 结果的数据（Tavily 搜索需要行业名称）
- Step 3：拉取同业数据（需要 Layer 1 的行业归属）

## Consequences

- 两个 Agent 可以真正并行执行，零时序依赖
- API 调用不冗余，数据一致性有保证
- 数据准备节点较重，但逻辑集中好维护
- 需要提前知道所有数据需求，不支持"分析中发现需要新数据"的场景
