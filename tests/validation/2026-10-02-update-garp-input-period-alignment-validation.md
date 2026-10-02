# 验证报告: update-garp-input-period-alignment

**日期**: 2026-10-02
**分支**: `update-garp-input-period-alignment`（commit c2e91994）
**关联 delta**: openspec/changes/update-garp-input-period-alignment/（valuation-signal-integrity ADDED「GARP 判定输入期次对齐」）
**变更类型**: 非交互类（compute 层取数规则）→ 不适用 E2E 门禁
**触发**: 第三轮评审「GARP 判定期次残留」（正文期次成对标注但判定挂年报 64.11%）

## 变更内容

`_try_garp` 负债率取数优先级改为「latest_period_snapshot.资产负债率(%)（最新披露期，时点指标）→ 年报回落（标注回落）」；GARP details 新增 `负债率_期次`/`ROE_期次` 透传标注；ROE 维持 latest_year 全年口径（年度阈值语义，显式标注）。`calc_garp` 纯比较逻辑与 failures 文案零改动（citation-verification 的 failures 集合比对契约不受影响）。

## 验证结果

| 验证项 | 证据位置 | 结果 |
|---|---|---|
| 快照中报 47.85% 优先 → 不产生负债率 failure + 期次标注含报告日 | `TestGarpDebtPeriodAlignment::test_snapshot_debt_wins_and_passes_threshold` | ✅ |
| 快照缺失 → 回落年报 64.11% → failure 产生 + 回落标注可见 | `::test_snapshot_missing_falls_back_to_annual_with_note` | ✅ |
| 快照在但缺字段（部分快照）→ 同回落语义 | `::test_snapshot_field_missing_falls_back` | ✅ |
| ROE 全年口径维持 + 期次标注 | `::test_roe_stays_annual_with_period_note` | ✅ |
| 既有 GARP/估值行为零回归 | tests/nodes/ + tests/metrics/ 557→全量 3934 passed | ✅ |

## 门禁命令（全量，本 worktree 实测）

| 命令 | 结果 |
|---|---|
| `uv run ruff check` | All checks passed! |
| `uv run mypy src/finance_agent/nodes/compute.py` | 4 errors ≡ stash 基线 4（零新增） |
| `uv run pytest`（全量） | **3934 passed, 1 failed, 7 skipped**——唯一失败为既有 @live 环境项（与历轮相同，非回归） |

## TDD 证据

4 用例先红（`TypeError: unexpected keyword 'latest_period_period'` 形态与目标断言红）→ 实现后绿（47 passed 含既有）。

## 结论

[x] 全部通过——判定与正文期次矛盾消除（拓荆案：中报 47.85% < 60% 阈值，负债率 failure 不再出现）；可 archive
