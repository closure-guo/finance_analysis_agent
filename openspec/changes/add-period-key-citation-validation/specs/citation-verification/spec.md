# Delta for citation-verification

## ADDED Requirements

### Requirement: 同值跨期次歧义消解

校验器 SHALL 构建「数值→期次锚点」索引：遍历 state 序列型指标段（`profitability_metrics` / `solvency_metrics` / `efficiency_metrics` / `cashflow_metrics` 的按期次字典，及 `quarterly_trend` 的单季序列），按现有数值归一化口径将每个数值映射到其出现的期次段集合。当某 claim 的 `stated_value` 匹配到的锚点期次段基数 ≥ 2（同值出现在 ≥2 个不同期次）时，该 claim 触发消歧义务：interpretation 的期次标记集合 SHALL 包含 field_ref 溯源期次（经 `normalize_period` 归一后比对）。有期次标记但标记集合不含 field_ref 期次时 SHALL 判 FAIL 并归入 `semantic_period_mismatch`；无任何期次标记时 SHALL 判 FAIL 并归入独立桶（`ambiguous_value_undisambiguated`）。消歧义务 SHALL 仅对撞车值生效：唯一锚点值（含「自 2021 年 X 缓慢下行」类历史参照期次表述）SHALL NOT 被认领检查拦截。降级边界：比较型 claim（field_ref_b / claim_type=comparative）豁免——interpretation 必然含基期期次标记，两值两期次语义由双端申报结构承担；interpretation 为空（旧格式 claim）SHALL 跳过消歧检查——义务针对正文标注，正文缺席不判；撞车值但 field_ref 锚点期次解析不出时按覆盖缺口降级。歧义桶 SHALL NOT 进入确定性单点修复白名单，按桶分流走定向重试。

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

#### Scenario: 显式认领外加历史参照标记放行

- **GIVEN** 同上撞车 state
- **WHEN** claim 的 field_ref 指向 2024 年报键，interpretation 为「2024 年报毛利率 41.69%，低于 2026Q1 修复水平」
- **THEN** PASS（只要求 field_ref 期次被认领，不禁止提及别的期次）

#### Scenario: 唯一锚点不触发消歧义务

- **GIVEN** 34.95 仅存在于 2025 年报锚点
- **WHEN** claim 引用 34.95 且 interpretation 无期次标记
- **THEN** PASS（不误伤；消歧义务仅由期次锚点基数 ≥2 的值承担）

#### Scenario: 唯一锚点历史参照表述不拦

- **GIVEN** 34.95 仅存在于 2025 年报锚点（值不撞车）
- **WHEN** claim 的 field_ref 指向 2025 年报键，interpretation 为「2026Q1 单季毛利率 34.95%」或「自 2021 年 4.30 次缓慢下行」类含历史期次表述
- **THEN** PASS（认领检查仅撞车档生效；002412 真实语料实证）

#### Scenario: 空正文旧格式 claim 降级

- **GIVEN** 撞车值（如合成基准 state 中资产负债率 2022 与 2024 同为 40.0）
- **WHEN** claim 的 interpretation 为空串（旧格式）
- **THEN** 跳过消歧检查（义务针对正文标注，正文缺席不判），不判 FAIL

#### Scenario: 比较型 claim 历史基期标记不误伤

- **GIVEN** 45.2 仅存在于 2025 年报锚点
- **WHEN** 比较型 claim 的 field_ref 指向 2025 年报键，interpretation 为「较 2024 年的 30.1 提升至 45.2」
- **THEN** PASS（比较型整体豁免；历史基期标记不触发拦截）

#### Scenario: 单季序列撞车样本回归

- **WHEN** 运行既有 citation 语料（tests/data/citation_r2_claims.json、citation_r4_claims.json）全量回归
- **THEN** 零新增 FAIL（既有 PASS 样本不因消歧义务误伤）
