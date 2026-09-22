# Proposal: add-causal-observation-battery

## Why

v2 因果消融框架产出的三个已校准读数——grounding 无源断言率（校准一致率 1.000）、B1 风险点吸收率（校准 0.875）、B2 交锋修正率（校准 0.906）——目前只在实验批内出现；2026-09-20 观测轮（p2-batch-20260920）已手工示范「固定快照 × 新生产栈 → 三读数对照」的用法（grounding 0/79、B1 0.833、B2 0.138），证明这套读数对 prompt/模型栈变更敏感且成本可控（材料腿 393 次调用）。但该流程无契约、无入口、无触发规则，每次都要手工拼装。judge 四维对这类变更的观测面窄（report_relevance 零方差、debate v6 取值域压缩），已校准的因果系读数是更有效的常规观测面。

## What Changes

- 新增**常规观测电池**（standing observation battery）驱动入口：对固定材料快照（P1 快照 20 标的）以当前生产栈跑材料腿，产出 grounding 无源率 / B1 吸收率 / B2 修正率三读数，一键执行
- 观测电池 SHALL 固定快照 digest（跨轮可比），沿用因果消融的校准门控（rubric 变更须重过 0.80 门才可进电池读数）
- 观测轮**不作层增量裁决**（无两臂对照），读数为趋势观测：与上轮对照人工解读，不产出层间结论句
- 触发约定：生产 prompt / 模型栈变更（`deploy_prompts.py` 发布或模型切换）后运行；读数落 `runs.jsonl` + `metrics.md` 时间线
- 成本披露：材料腿调用数与判定调用数随产物落盘

## Capabilities

### New Capabilities

（无——观测电池是 causal-ablation 能力域内的新需求）

### Modified Capabilities

- `causal-ablation`: 新增「常规观测电池」需求——三读数（grounding / B1 / B2）从实验批专用升格为可重复执行的常规观测，附固定快照、校准门控沿用、不作层增量三条边界

## Impact

- 代码：`evals/causal_ablation/` 新增观测驱动（复用 `bear_grounding.py` / `family_b*.py` 判定实现，不重复实现判定逻辑）；CLI 入口
- 台账：`docs/evals/metrics.md` §1 口径登记观测电池条目；§2 时间线按轮追加
- 边界：B5c 与 A 族注入法**保持实验态**（需要两臂/注入构造），不进观测电池——本提案显式不做
- 成本：每轮观测电池 ≈ 材料腿 400 次调用 + 判定腿（grounding ~80 / B1 ~250 / B2 ~110 单元），按 09-20 观测轮实测外推
