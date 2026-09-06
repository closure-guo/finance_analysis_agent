# price-level-tooling Specification

## Purpose
TBD - created by archiving change toolize-price-levels. Update Purpose after archive.
## Requirements
### Requirement: 价位预算工具

系统 SHALL 由 K 线以确定性工具计算价位参考（`price_levels`）：近期高低点、ATR、
支撑/阻力参考带、建议止损带与目标参考带，供 Trader 解读与引用；Trader 产出的
entry/stop/target SHALL 经过该工具数据支撑，不得无依据产出。

#### Scenario: 价位参考注入 trader context

- **WHEN** Trader 节点构建 context
- **THEN** SHALL 包含 price_levels JSON（参考带而非单点指令）
- **AND** Trader 保留决策权（可偏离参考带，但受 sanity 校验约束）

### Requirement: 交易价位 sanity 校验

系统 SHALL 在 Trader 产出后运行确定性校验：long 须 stop<entry<target（short 对
称）；entry 距最新收盘偏差 ≤ 配置上限（默认 15%）；stop/target 落在工具参考带内
（±2ATR 放宽带）。校验 SHALL NOT 由 LLM 执行。

#### Scenario: 首次不合法打回

- **GIVEN** Trader 首次产出的价位不通过校验
- **WHEN** 路由判定
- **THEN** SHALL 携带失败原因与 price_levels 参考带打回 Trader 重出（上限 1 次）

#### Scenario: 二次不合法工具修正

- **GIVEN** 打回后产出的价位仍不通过校验
- **WHEN** 路由判定
- **THEN** 系统 SHALL 按工具参考带修正价位
- **AND** 置 `price_level_corrected=true` 与修正原因（报告与 trace 可观测，不静默）

#### Scenario: 合法价位直通

- **WHEN** 价位通过全部校验
- **THEN** SHALL 原样放行，不产生修正标注

### Requirement: quick 模式行情快照

quick 模式的 search_stock 工具结果 SHALL 附带现价与涨跌幅快照（工具计算），
LLM 对价格事实的陈述 SHALL 以快照为据。

#### Scenario: 查股附带快照

- **WHEN** quick 模式调用 search_stock 命中标的
- **THEN** 结果 SHALL 含 price 与 pct_change 字段（数据缺失时如实标注缺失）

### Requirement: 分析师派生值预生成

系统 SHALL 由工具预计算常用派生值（5/20/60 日区间涨跌幅、距 250 日高点回撤、
距 250 日低点反弹）并随 technical_indicators 注入技术面分析师 context；分析师
对上述派生值的陈述 SHALL 引用预生成值而非自行计算。

#### Scenario: 派生值注入

- **WHEN** 技术面分析师 context 构建
- **THEN** SHALL 包含派生值表（带 field_ref 可引用）
- **AND** 数据不足的派生项 SHALL 如实标注缺失

