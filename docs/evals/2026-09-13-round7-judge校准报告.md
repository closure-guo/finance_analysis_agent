# round7 Judge 人工校准报告（2026-09-13，终裁后终版）

**status**: active

数据：`judge-sample-round7-blind-v2.xlsx` × `judge-sample-round7-judge.jsonl`（r3 运行时落库，已冻结），41/41 行完整；按 [metrics.md §2.1 预登记分析计划](../metrics.md) 口径执行，含 2026-09-13 owner 终裁（[终裁材料](../../tests/validation/round7-校准终裁材料.md)）后的人工改分。

## 结论

1. **全维度达标，round7 起 judge 可用**：整体 MAE **0.342** / 方向一致率 **97.6%**（阈值 1.0 / 0.7）；四维度分别满足「MAE≤1.0 且方向≥0.7」。
2. **与 round5 对照（预登记：只比方向）**：方向一致率 32% → **97.6%**，系统性偏差从「judge 高 1–2.6 分」收敛到「≤1 分」。
3. **终裁修正后 dg MAE 减半**（0.889 → 0.444）：owner 确认 4 行为 judge 正确的 source 归属扣分（人工 5→4），1 行 judge 误判（维持人工 5），1 行灰区（人工维持 5）。
4. **剩余人机分歧全部是系统性口径差，无一处无中生有**：debate 6×Δ1（judge 恒 5 宽松）、consistency 2×Δ1（judge 扣表述差异）、dg 1×Δ1（组合 claim 灰区）+ 1×Δ2（解读失当漏检）、report 1×Δ1。全部进 rubric v7 改动清单。
5. Spearman 不可作结论：report/debate judge 恒 5 零方差；dg 仅 {4,5} 两档 + n=9（预登记已声明不单独下结论，round8 合并判）。

## 指标总表（终裁后）

| 维度 | n | Spearman | MAE | 方向一致率 | 预登记判定 |
|---|---|---|---|---|---|
| consistency | 9 | — | 0.222 | 1.000 | ✓ |
| debate_quality | 9 | —（judge 恒 5 零方差） | 0.667 | 1.000 | ✓ |
| decision_grounding | 9 | -0.116（不具结论力） | 0.444 | 0.889 | ✓ |
| report_relevance | 14 | —（judge 恒 5 零方差） | 0.143 | 1.000 | ✓ |
| **整体** | 41 | 0.223 | **0.342** | **0.976** | ✓ |

## 健康检查

- 41/41 行人工分齐备（`5f41a49a` 由 owner 终裁补填 5）；judge 41/41 出分，无 parse 失败。
- judge confidence 0.80–1.00，无 <0.5 低置信信号。
- 人工 confidence 按维护者此前给的 3 档制填写（与 0-1 契约不一致），相关不可算——**责任在维护者口径未统一**；口径卡已补「confidence 填 0-1 小数」说明。

## 终裁结果（2026-09-13，详见[终裁材料](../../tests/validation/round7-校准终裁材料.md)）

| 项 | 裁决 | 处置 |
|---|---|---|
| 1a d7e48a92 | judge 成立（36% 标 fundamental 实出 sentiment、打折主张标 conservative 实为 neutral，真错安×2） | 人工 5→4 |
| 1b d477972f | judge 成立（264亿标 fundamental 实出 sentiment） | 人工 5→4 |
| 1c 5e9b09e3 | judge 成立（「应分批减仓」标 risk_aggressive，与激进方立场相反） | 人工 5→4 |
| 1d 4758fdb7 | 灰区可接受（数字+他方解读合体，标签取数字来源） | 维持 5 |
| 1e ce66d316 | judge 的 4 分不成立（ref2 GARP 实出 fundamental，judge 误判） | 维持 5 |
| 1f 8bbe659a | judge 对（neutral 里有同表述，非无中生有） | 人工 5→4 |
| 终裁2 1caf1f7b | 单向解读扣分成立（judge 漏检解读失当） | 维持 3 |
| 终裁3 7e6bc8bc | 改 4（基本切题但无总结性结论） | 人工 3→4 |
| 终裁4 5f41a49a | 5 分回填 | 14/14 完整 |

**关键口径发现**：人工与 judge 的尺差不在「数字找不找得到」，在「source 归属精确性」与「解读方向」——前者 owner 终裁确认按三层判法计分，后者确认 judge 漏检。

## rubric v7 改动清单（终裁确定，合并一次 bump）

1. **debate 5 分措辞收紧**：judge 恒 5 宽松偏置（6×Δ1）——5 改为「所有论点均有数据/事实支撑」，个别纯定性论点降 4。
2. **dg source 归属精确性按三层判法计分**：1a/1b/1c 确认归属层破 = 扣 1 分；数字在他源存在不豁免。
3. **dg 组合 claim 归属规则**（1d 灰区裁定）：数字+他方解读合体时标签可取数字来源，但解读为主张重心时 MUST 标解读来源。
4. **dg 解读失当强化**（终裁2）：judge 逐条复述 source 原文并与 claim 方向比对，单向解读/反向证据忽略 SHALL 降档。

变更后 bump RUBRIC_VERSIONS 并重校准（预登记单变量原则：与 round8 材料版本改动分开跑）。
