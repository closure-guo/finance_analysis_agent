# ADR-0001: Data Preparation Node (Strategy C)

## Status: Accepted

## Context

财务分析 Agent 和投资分析 Agent 存在大量共享数据需求：

- **三大报表**：财务 Agent 用于计算指标，投资 Agent 用于 DCF 估值（算 FCF）
- **PE/PB/ROE**：两个 Agent 都需要
- **同业公司数据**：财务 Agent 用于同业对比，投资 Agent 用于可比估值

如果两个 Agent 各自独立拉取数据（Strategy A），会导致 API 调用翻倍、计算结果可能不一致。如果用共享缓存（Strategy B），时序耦合导致无法真正并行。

## Decision

在 Supervisor 路由之前插入一个**数据准备子图**（check_cache → fetch_data → validate_financials → compute_metrics），统一负责所有数据拉取、校验和计算，结果写入 LangGraph State。

数据准备子图实现为 LangGraph 子图，包含条件边：

- HIT → 报表持久化命中 + 行情未过期，跳过 fetch，走 validate → compute
- MISS → 首次分析，执行 fetch（拉取 + 持久化报表 + 缓存行情）→ validate → compute
- validate FAIL → 硬等式校验失败，短路终止到 END

两条路径都继续走 Route → Agent，因为分析报告不缓存，LLM 每次重新生成。

fetch_data 内部分两步（MVP）：

- Step 1：并行拉取 L1 + L2 无依赖数据（三大报表 + 行情 + 行业归属 + 预计算指标）
- Step 2：拉取同业数据（需要 Step 1 的行业归属）

## Consequences

- 两个 Agent 可以真正并行执行，零时序依赖
- API 调用不冗余，数据一致性有保证
- 数据准备节点较重，但逻辑集中好维护
- 需要提前知道所有数据需求，不支持"分析中发现需要新数据"的场景
