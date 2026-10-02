# 验证报告: fix-decision-price-check-false-positives

**日期**: 2026-10-02
**分支**: `fix-decision-price-check-false-positives`
**关联 delta**: openspec/changes/fix-decision-price-check-false-positives/（price-level-tooling MODIFIED）
**变更类型**: 非交互类（纯后端校验规则）→ 不适用 E2E 门禁
**关联 incident**: [034](../docs/incidents/034-decision-price-check-false-positives-20261002.md)

## 变更内容

修复决策价位校验器两个实证误报（688072 重跑被门禁误拦的根因）：①`_NON_PRICE_KEYWORDS` 增加 `var`/`在险价值`——VaR95 等风险度量语境的数字不再被当股价；②`_BREAKDOWN_WORDS` 增加「回撤至/回调至」+ `_check_snippet` 复合回踩豁免（同条目同数值 down+up 方向共现 → 跳过空洞判定，预扫不做量纲过滤）。spec 场景 1 例子更正（原「95 vs 570」例子即误报案例）。

## 验证结果

| 验证项 | 证据位置 | 结果 |
|---|---|---|
| 缺陷 A：VaR95 不再误报（688072 reasoning 原文） | `tests/metrics/test_decision_price_check.py::TestFalsePositiveFix688072::test_var95_not_misread_as_price` | ✅ |
| VaR(95% / 在险价值95 变体形态不误报 | `::test_var_percent_and_chinese_forms_not_misread` | ✅ |
| 缺陷 B：gen1 复合回踩触发（回撤至610…站稳610）不判空洞 | `::test_compound_retest_trigger_gen1_not_empty` | ✅ |
| 缺陷 B：gen2 复合回踩触发（跌破610后站稳610之上）不判空洞 | `::test_compound_retest_trigger_gen2_not_empty` | ✅ |
| 护栏：单上破无下破语境照常判空洞（豁免不扩大化） | `::test_simple_breakout_still_empty` | ✅ |
| 护栏：真幻觉裸价位（无 var 语境）照常报偏差 | `::test_real_hallucinated_price_still_reported` | ✅ |
| 既有行为零回归（22.61 空洞 / 22.94 直通 / 18.35% 不误报等 20 项） | `tests/metrics/test_decision_price_check.py` 26 passed | ✅ |
| 门禁回路/路由/阻断终态零回归 | tests/nodes/ + routing + api 阻断套件 223 passed | ✅ |

## 门禁命令（全量，本 worktree 实测）

| 命令 | 结果 |
|---|---|
| `uv run ruff check` | All checks passed! |
| `uv run mypy src/finance_agent` | 81 errors ≡ main 基线 81（零新增） |
| `uv run pytest`（全量） | **3930 passed, 1 failed, 7 skipped**（672s）。唯一失败为既有 @live 环境项 `test_fm_decision_live`（incident 034 时代已确认与本变更零交集） |

## 实施备注

- TDD 红绿证据：gen1 用例在首版实现下红（`1 failed, 25 passed`）——根因为预扫描做了量纲过滤，「回撤」关键词误杀「回撤至610」的下破方向使 down+up 共现判定缺一半（已在 incident 034 根因 B 中记录该第二层坑）；修正预扫后全绿
- 预扫描量纲豁免的设计依据：方向检测与量纲分类正交，预扫结果仅用于豁免判定、不产生 anomaly

## 结论

[x] 全部通过——两个误报缺陷修复且护栏锁定（豁免不扩大化、真幻觉仍报）；可进入 archive 流程
