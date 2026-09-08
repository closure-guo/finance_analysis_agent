# citation-verification Specification

## Purpose
引用校验契约：`field_ref` 的解析语义与分析师 context 的一致性要求，确保 citation 校验结果可靠（不因索引错位误报）。

## ADDED Requirements

### Requirement: field_ref 的 list index 相对 state 完整列表

citation 校验 SHALL 将 `field_ref`（如 `macro_indicators.cpi.0.全国-同比增长`）中的 list index 解析为 **state 中完整列表的索引**（`cpi[0]` = 最新一期，遵循 data-fetching 契约），ground-truth 取自该元素。

#### Scenario: 解析完整列表索引

- **WHEN** 校验 `field_ref` 含 list index（如 `macro_indicators.cpi.0.全国-同比增长`）
- **THEN** 系统 SHALL 从 `state["macro_indicators"]["cpi"][0]["全国-同比增长"]` 解析 ground-truth，而非从分析师 context 的子集解析

### Requirement: 分析师 context 从 index 0 开始展示

系统 SHALL 使分析师看到的时间序列子集从 index 0 开始（取 `[:N]`），保证分析师引用的 `field_ref` 索引与校验方解析的索引对齐；SHALL NOT 使用从非 0 索引开始的子集（`[-N:]`）作为分析师 context。

#### Scenario: context 子集从 index 0 开始

- **WHEN** 构建分析师 context（如 `_build_macro_context` / `_build_fundamental_context`）展示时间序列子集
- **THEN** 子集 SHALL 取列表的前 N 个元素（`[:N]`，index 0 = 最新一期），而非后 N 个（`[-N:]`）

#### Scenario: 引用一致

- **WHEN** 分析师报告包含 `field_ref` 引用某索引，且校验方解析同一 `field_ref`
- **THEN** 两者 SHALL 指向同一数据元素（索引语义一致），数值比对结果反映真实准确性而非索引错位

### Requirement: 校验算法不变

citation 校验的数值比较规则（绝对容差 0.01、相对容差 0.5%）、状态语义（PASS/FAIL/UNVERIFIABLE）与 ground-truth 来源（state）SHALL 保持不变；本 delta 仅修正数据排序与索引对齐，不改变校验判定逻辑。

#### Scenario: 算法语义不回归

- **WHEN** 校验判定执行
- **THEN** 容差与状态规则与修复前一致，仅 ground-truth 因数据排序修正而正确
