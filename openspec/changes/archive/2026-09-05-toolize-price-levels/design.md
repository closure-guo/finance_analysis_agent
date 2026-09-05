# Design: toolize-price-levels

## Context

数值计算工具化审计（2026-09-04）确认：PREP 层 fetch → validate_financials（硬等
式 FAIL 短路）→ compute_metrics（metrics/ 全模块）已完全工具化；分析师 context
注入预算好的指标 JSON（负索引约定）；风控辩论/FM 只解读 JSON；报告组装模板化。
唯一 LLM 直接产出数值的环节 = Trader 的 entry/stop/target 三价位字段，且无工具
预算、无后置校验。

## Goals / Non-Goals

- Goals：价位计算工具化（calc_price_levels）；trader 产出 sanity 校验 + 打回/修正；
  quick 行情快照；分析师派生值注入。LLM 输出中不再有「无工具依据、无校验」的数值。
- Non-Goals：不改变 trader 的决策职责（方向/仓位/逻辑仍是 LLM 规划）；不做
  quick 链路 claim 校验（另行评估）；不改报告组装。

## Decisions

### D1 价位计算放 metrics/levels.py，由 compute_metrics 编排

与 risk/technical 同构：`calc_price_levels(kline)` → 近 N 日高低点、ATR(14)、
支撑/阻力参考（近期摆动高低点聚类）、建议止损带（entry ± k*ATR 的参考带，非单点）、
目标参考带。写入 state `price_levels`。选 compute_metrics 挂载（kline 已就绪），
fetch 保持单职责。

### D2 sanity 校验为独立节点 + 打回 1 次 + 工具修正兜底

`validate_trade_prices` 节点（trader 之后）：确定性规则——
1. 价格关系：long 须 stop<entry<target（short 对称）
2. entry 距最新收盘偏差 ≤ 配置上限（默认 15%，防止 LLM 报无关价位）
3. stop/target 落在 [近期低点-2ATR, 近期高点+2ATR] 参考带内（放宽带，非硬约束）

失败路由（after_validate_trade_prices）：首次失败 → 打回 trader（context 附带
失败原因 + price_levels 参考带，复用 FM return 的 return_count 模式，上限 1）；
二次失败 → 按工具参考带中值**修正**并置 `price_level_corrected=true` +
`price_level_correction_reason`（报告可观测，不静默）。选节点而非 post-validator
函数：打回需要图路由，且与 ADR-0011 分层一致。

### D3 quick 行情快照：search_stock 结果扩展，不新增工具

search_stock 已有 AKShare 查价路径——结果 dict 附带 `price`/`pct_change` 快照
字段（工具数据）。不新增 quote 工具（避免 LLM 需要学会第二个调用时机；快照随
查随得）。

### D4 分析师派生值预生成

`metrics/technical.py` 增加 `calc_derived_series(kline)`：区间涨跌幅（5/20/60 日）、
距 250 日高点回撤、距 250 日低点反弹——随 technical_indicators 一并注入 technical
analyst context（工具算好，LLM 引用不心算）。基本面派生（财报增长率等）已由
compute_metrics 覆盖，不动。

## Risks / Trade-offs

- 打回循环成本：上限 1 次 + 修正兜底，最坏多一次 trader LLM 调用
- 修正非 LLM 意见：`price_level_corrected` 标注进报告与 trace，人工可审计
- 参考带放宽（±2ATR）：避免把合理策略价位误杀；硬规则只有价格关系与偏差上限
