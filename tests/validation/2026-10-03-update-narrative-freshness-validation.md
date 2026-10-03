# 验证报告: update-narrative-freshness

**日期**: 2026-10-03
**分支**: `update-narrative-freshness`
**关联 delta**: openspec/changes/update-narrative-freshness/（agent-prompt-contracts ADDED「论据期次新鲜度」）
**关联 issue**: #189
**变更类型**: 非交互类（prompt 契约）→ 不适用 E2E 门禁

## 变更内容

①bear_debater prompt 增「论据期次新鲜度（强制）」段——负面论据 MUST 用最新披露期口径，趋势被最新期反转时 MUST 同论点并列呈现反转事实；②研究聚焦摘要生成器（report.py `_build_focus_summary`）system 文案增「最新期次引用 + 反转并列、禁止单边半句」约束；③契约断言 2 用例。

## 验证结果

| 验证项 | 证据 | 结果 |
|---|---|---|
| bear prompt 契约断言（最新披露 + 并列呈现） | `test_prompt_contracts.py::TestNarrativeFreshnessContract::test_bear_prompt_requires_latest_period_and_reversal_pairing` | ✅ |
| 摘要生成器契约断言（最新期次 + 并列 + 单边禁止） | `::test_focus_summary_builder_requires_pairing` | ✅ |
| prompts 部署一致性 | `deploy_prompts.py` 执行（production 标签） | ✅ |
| 既有 prompt/渲染零回归 | prompt_contracts + report_render 91 passed | ✅ |

## 门禁命令

ruff 全过；全量 pytest 由滞回 PR（#208）同基线背书（本 PR 仅 prompt 文案 + 断言，无运行时逻辑变更，受影响面 91 passed 已覆盖）。

## 结论
[x] 全部通过
