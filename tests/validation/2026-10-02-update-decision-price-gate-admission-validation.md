# 验证报告: update-decision-price-gate-admission

**日期**: 2026-10-02
**分支**: `update-decision-price-gate-admission`（commit 2b1b9f00）
**关联 delta**: openspec/changes/update-decision-price-gate-admission/（price-level-tooling MODIFIED——门禁准入恶化判据分层）
**变更类型**: 非交互类 → 不适用 E2E 门禁
**授权**: incident 034 遗留 owner 终裁（2026-10-02 晚「都批」）

## 变更内容

risk_judge 门禁回路打回重试后的判定改为恶化分层：残留 anomaly 与首次比较（source_text 集合 + 条数）——同源未恶化（残留 ⊆ 首次且条数不增）→ pass + note「打回后残留 N 条未清零（未恶化，放行待人工终裁）」，残留照落 trace；恶化（新增 source 或条数增加）→ fail 阻断（note 含恶化语义）。路由/报告/API 链路零改动（读 result 不读 note）。

## 验证结果

| 验证项 | 证据 | 结果 |
|---|---|---|
| 同源残留放行 + note 待终裁 | `TestGateAdmissionLayering::test_same_source_residue_passes_with_note` | ✅ |
| 残留新增 source（重试引入新错误）→ fail | `::test_new_source_residue_fails_gate` | ✅ |
| 残留条数增加 → fail | `::test_more_residues_fails_gate` | ✅ |
| 残留减少且剩余同源（有改善）→ pass | `::test_shrunk_same_source_residue_passes` | ✅ |
| 既有 stub 同输出用例迁移到新语义 | `TestDecisionPriceGate::test_anomaly_persists_same_source_after_retry_passes` | ✅ |
| 既有集成用例（601066 空洞形态）迁移 | `test_decision_price_check.py::TestRiskJudgeIntegration` | ✅ |
| 受影响面零回归 | nodes/metrics/routing/api/factory 737 passed | ✅ |

## 门禁命令

| 命令 | 结果 |
|---|---|
| `uv run ruff check` | All checks passed! |
| `uv run mypy src/finance_agent/nodes/risk.py` | no issues |
| `uv run pytest`（全量） | **3938 passed, 1 failed（既有 @live 环境项）, 7 skipped** |

## TDD 证据

4 分层用例先红后绿；实施中一度 4 用例红于错误路径（`[_BAD_TRIGGER]` 嵌套列表致 validator 清空 triggers、走了 reeval 打回）——以最小复现用例定位为测试自身 bug 后修复（此坑记录：`_BAD_TRIGGER` 已是 list，组合用 `+` 不再包 `[]`）。

## 结论

[x] 全部通过——未恶化放行/恶化阻断分层生效，incident 034 终裁落地；可 archive
