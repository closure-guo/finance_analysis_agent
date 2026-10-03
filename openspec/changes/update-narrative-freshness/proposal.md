# Proposal: update-narrative-freshness

## Why

回归评审 P1（issue #189）：数据层期次对齐修复后，**叙事层未完全同步**——空方主论据仍以「毛利率连续三年下滑」展开而不附「最新中报回升至 41.0%，趋势已被打破」限定（期次错位从数据缺失降级为叙事权重失衡）；负债率引用年报 64.11% 旧口径。根因：bear 辩论 prompt 与研究聚焦摘要生成器均无论据新鲜度约束。

## What Changes

- **bear prompt 论据新鲜度规则**：引用财务数据的负面论据 MUST 使用最新披露期；当负面趋势被最新期反转（如年报连续下滑但中报回升）MUST 并列呈现反转事实，MUST NOT 拿过期年报口径当当前论据
- **研究聚焦摘要生成约束**：摘要引用财务数据时使用材料中的最新期次；最新期次与历史趋势方向相反时 MUST 并列呈现（单边半句禁止）
- **契约**：agent-prompt-contracts ADDED「论据期次新鲜度」requirement

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-prompt-contracts`: ADDED「论据期次新鲜度」

## Impact

- `src/finance_agent/prompts/bear_debater.md`（deploy_prompts 同步）
- `src/finance_agent/nodes/report.py` `_build_focus_summary` 的 system 文案
- `tests/test_prompt_contracts.py`：新增契约断言
- 非交互类 → 不适用 E2E 门禁
