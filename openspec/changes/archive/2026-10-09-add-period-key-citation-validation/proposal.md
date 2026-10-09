# Proposal: add-period-key-citation-validation

## Why

第七轮人工评审（2026-10-05，拓荆 688072 v4 vs v7 跨版本比对）发现同一数值 41.69% 的期次归属随 LLM 采样漂移。回查原始财报终裁：**两版都没错**——2024 年报累计毛利率与 2026Q1 单季毛利率恰好都是 41.69%。快照的年报序列（`profitability_metrics`）与单季序列（`quarterly_trend`）同时携带该值，现有校验器全部通过：值存在性校验只查数值是否存在于 state（两处都存在），`_check_period` 只比对 claim 声明期次与 field_ref 溯源期次（claim 自报时两者天然一致），interpretation 中的期次标记（"2026Q1 单季"）与 field_ref 期次（2024 年报）错配无人检查。Q1 单季 ≈ 上年年报是财报常见现象，此类撞车必然复发。

## What Changes

- 新增「数值→期次锚点」索引：遍历 state 序列型指标段，将数值映射到其出现的期次段集合
- 新增同值跨期次歧义消解校验：当 stated_value 匹配 ≥2 个不同期次锚点时，claim 触发消歧义务——interpretation 的期次标记集合必须包含 field_ref 溯源期次；无标记判 FAIL（新桶 `ambiguous_value_undisambiguated`），标记集合不含 field_ref 期次判 FAIL（复用 `semantic_period_mismatch` 桶）
- interpretation 期次标记检查不依赖值歧义独立生效：标记存在但不认领 field_ref 期次即拦（v4 案例的标记错配路径）
- 分析师提示词补期次标注纪律：引用多期次并存的数值时正文必须显式标注期次
- 不误伤边界：唯一锚点 claim 不受消歧义务约束；比较型 claim 的历史基期标记不触发拦截（只要求 field_ref 期次被认领，不禁止提及别的期次）；歧义桶不进确定性修复白名单，走定向重试

## Capabilities

- **Modified Capabilities**: `citation-verification`（新增同值跨期次歧义消解 Requirement）、`agent-prompt-contracts`（期次标注纪律并入）

## Impact

- `src/finance_agent/citation.py`：新增索引构建 + `_check_period` 扩展（标记集合比对与消歧义务判定）
- `src/finance_agent/prompts/fundamental_analyst.md` 等 4 个分析师 prompt：期次标注纪律一行
- `src/finance_agent/nodes/citation_repair.py`：歧义桶明确排除出修复白名单（如需显式化）
- 测试：`tests/test_citation*.py` 新增撞车样本；r2/r4 语料零回归是硬验收
- 关联 issue #231；关联 #191（毛利率多口径对账前科）
