# Proposal: toolize-price-levels

## Why

2026-09-04 数值计算工具化审计发现：管线 PREP 层（fetch/勾稽校验/compute_metrics）与
风控/FM/报告组装已完全工具化（LLM 只解读预算好的指标 JSON），但 **Trader 的
`entry_price`/`stop_loss`/`target_price` 三个价位字段由 LLM 直接产出**——
`_build_trader_context` 只喂分析师报告摘要 + 辩论史，`metrics/technical.py` 无
支撑阻力/ATR/近期高低点等价位计算，产出后亦无 sanity 校验（无节点检查
stop<entry<target、entry 距现价偏差）。LLM 在做数值决策计算，幻觉无护栏。
次要缺口：quick 模式无行情工具（LLM 对搜索片段数字自由发挥）；分析师报告的
派生数字（区间涨跌幅/距高点回撤）由 LLM 心算，未进 claims 的无人校验。

## What Changes

- **新增 PREP 工具 `calc_price_levels`**（metrics/levels.py）：由 K 线计算
  近期高低点/ATR/支撑阻力参考区间 → 建议止损带/目标参考带，写入 state
  `price_levels`，注入 trader context
- **新增 trader 后置 sanity 校验**（确定性节点）：价格关系（stop<entry<target，
  short 对称）、entry 距现价偏差超限、价位落在近期区间外 → 打回 trader 重出
  （限 1 次，同 FM return 模式）；仍不合法则按工具参考带修正并标注
  `price_level_corrected=true`（可观测，不静默）
- **quick 模式行情快照注入**：search_stock 结果附带现价/涨跌幅快照（工具数据，
  供 LLM 解读而非心算）
- **分析师派生值预生成**：technical_indicators 附带区间涨跌幅/距高点回撤等
  常用派生表（工具算好，LLM 直接引用）
- LLM 职责边界不变：规划（决策方向/仓位/逻辑）+ 解读；数值计算全部工具化

## Capabilities

### New Capabilities

- `price-level-tooling`: 价位预算工具、trader sanity 校验、quick 行情快照、
  分析师派生值注入

### Modified Capabilities

（无——既有需求不变，纯增量）

## Impact

- 代码：`metrics/levels.py`（新）、`nodes/fetch.py` 或 `compute.py`（挂载）、
  `nodes/trader.py`（context 注入）、`graph.py` + `routing.py`（sanity 节点与
  打回路由）、`nodes/analysts.py`（派生值注入）、`react_agent.py`/`agent_factory.py`
  （quick 快照）
- 前置：无需 LLM 余额即可实施与单测（价位计算/校验全离线）；E2E 走既有 stub
- 风险：打回循环需上限（1 次）+ 修正可观测，防止管线卡死或静默改写
