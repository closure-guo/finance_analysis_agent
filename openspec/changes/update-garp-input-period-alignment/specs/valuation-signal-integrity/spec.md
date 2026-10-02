# Delta for valuation-signal-integrity

## ADDED Requirements

### Requirement: GARP 判定输入期次对齐

GARP 筛选的输入 SHALL 按指标性质取正确报告期：**负债率为时点指标**，SHALL 优先取 `latest_period_snapshot.资产负债率`（最新披露报告期期末值——中报/季报披露后年报口径即过时）；快照缺失或字段缺失时 SHALL 回落年报口径并在 details 标注回落。**ROE 为全年化指标**（阈值 15% 为年度口径语义），SHALL 取最新年报值，MUST NOT 用半年度/季度累计值直接比较。GARP details SHALL 标注负债率与 ROE 的期次来源（`负债率_期次`/`ROE_期次` 键），使判定依据的报告期可观测、可与正文口径对账。

#### Scenario: 中报披露后负债率取最新期

- **GIVEN** 拓荆科技最新年报 2025 资产负债率 64.11%，`latest_period_snapshot` 含 2026-06-30 中报资产负债率 47.85%
- **WHEN** GARP 筛选执行
- **THEN** 负债率判定 SHALL 用 47.85%（< 60% 阈值，不产生「负债率 >= 60%」failure）
- **AND** details SHALL 标注 `负债率_期次` 为中报来源（含报告日）

#### Scenario: 快照缺失回落年报并标注

- **GIVEN** `latest_period_snapshot` 缺失或不含资产负债率字段，年报资产负债率 64.11%
- **WHEN** GARP 筛选执行
- **THEN** 负债率判定 SHALL 回落年报口径 64.11%（≥ 60%，产生 failure）
- **AND** details 的 `负债率_期次` SHALL 标注为年报口径（回落可见，不伪装成最新期）

#### Scenario: ROE 维持全年口径并标注期次

- **GIVEN** 最新年报 ROE 22.5%，`latest_period_snapshot` 为 2026 中报累计口径
- **WHEN** GARP 筛选执行
- **THEN** ROE 判定 SHALL 用年报 22.5%（MUST NOT 用半年度累计值与 15% 年度阈值比较）
- **AND** details SHALL 标注 `ROE_期次` 为年报年份
