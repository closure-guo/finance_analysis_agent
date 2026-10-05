# Delta for citation-verification

## ADDED Requirements

### Requirement: 同值跨期次歧义消解

校验器 SHALL 构建「数值→期次锚点」索引：遍历 state 序列型指标段（`profitability_metrics` / `solvency_metrics` / `efficiency_metrics` / `cashflow_metrics` 的按期次字典，及 `quarterly_trend` 的单季序列），按现有数值归一化口径将每个数值映射到其出现的期次段集合。当某 claim 的 `stated_value` 匹配到的锚点期次段基数 ≥ 2（同值出现在 ≥2 个不同期次）时，该 claim 触发消歧义务：interpretation 的期次标记集合 SHALL 包含 field_ref 溯源期次（经 `normalize_period` 归一后比对）。interpretation 无任何期次标记时 SHALL 判 FAIL 并归入独立桶（`ambiguous_value_undisambiguated`）；标记集合存在但不含 field_ref 期次时 SHALL 判 FAIL 并归入 `semantic_period_mismatch`。期次标记检查 SHALL 不依赖值歧义独立生效：interpretation 含期次标记但不认领 field_ref 期次即拦，无论该值是否撞车。唯一锚点的 claim 与 interpretation 无期次标记的唯一锚点 claim SHALL NOT 受消歧义务约束。比较型 claim 的历史基期标记 SHALL NOT 触发拦截——校验只要求 field_ref 期次被显式认领，不禁止提及别的期次。歧义桶 SHALL NOT 进入确定性单点修复白名单，按桶分流走定向重试。

#### Scenario: 期次标记错配被拦截（41.69% 撞车实例）

- **GIVEN** 41.69 同时存在于 `profitability_metrics.毛利率.2024`（年报序列）与 `quarterly_trend.gross_margin` 的 2026Q1 锚点（单季序列）
- **WHEN** claim 的 field_ref 为 `profitability_metrics.毛利率.2024`、period 申报 2024，interpretation 为「2026Q1 单季毛利率 41.69%」
- **THEN** 判 FAIL，桶为 semantic_period_mismatch（标记集合 {2026Q1} 不含 field_ref 溯源期次 2024）

#### Scenario: 歧义值无期次标记被拦截

- **GIVEN** 同上撞车 state
- **WHEN** claim 引用 41.69 且 interpretation 为「毛利率 41.69%，处于低位」——不含任何期次标记
- **THEN** 判 FAIL，桶为 ambiguous_value_undisambiguated（消歧义务未履行）

#### Scenario: 显式认领期次放行

- **GIVEN** 同上撞车 state
- **WHEN** claim 的 field_ref 指向 2024 年报键，interpretation 为「2024 年报毛利率 41.69%」
- **THEN** PASS（标记集合含 field_ref 期次，消歧完成）

#### Scenario: 唯一锚点不触发消歧义务

- **GIVEN** 34.95 仅存在于 2025 年报锚点
- **WHEN** claim 引用 34.95 且 interpretation 无期次标记
- **THEN** PASS（不误伤；消歧义务仅由期次锚点基数 ≥2 的值承担）

#### Scenario: 标记错配检查独立于值歧义

- **GIVEN** 34.95 仅存在于 2025 年报锚点（值不撞车）
- **WHEN** claim 的 field_ref 指向 2025 年报键，interpretation 为「2026Q1 单季毛利率 34.95%」
- **THEN** 判 FAIL，桶为 semantic_period_mismatch

#### Scenario: 比较型 claim 历史基期标记不误伤

- **GIVEN** 45.2 仅存在于 2025 年报锚点
- **WHEN** 比较型 claim 的 field_ref 指向 2025 年报键，interpretation 为「较 2024 年的 30.1 提升至 45.2」
- **THEN** PASS（标记集合 {2024, 2025} 含 field_ref 期次；历史基期标记不触发拦截）

#### Scenario: 单季序列撞车样本回归

- **WHEN** 运行既有 citation 语料（tests/data/citation_r2_claims.json、citation_r4_claims.json）全量回归
- **THEN** 零新增 FAIL（既有 PASS 样本不因消歧义务误伤）
