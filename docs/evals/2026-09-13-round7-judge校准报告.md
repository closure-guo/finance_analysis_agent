# round7 Judge 人工校准报告（2026-09-13）

数据：`judge-sample-round7-blind-v2.xlsx`（人工 40/41 行）× `judge-sample-round7-judge.jsonl`（r3 运行时落库，已冻结）；按 [metrics.md §2.1 预登记分析计划](../metrics.md) 口径执行。

## 结论

1. **全维度达标，round7 起 judge 可用**：整体 MAE 0.475 / 方向一致率 95%（阈值 1.0 / 0.7）；四个维度分别满足「MAE≤1.0 且方向一致率≥0.7」。
2. **与 round5 对照（预登记：只比方向）**：方向一致率 32% → **95%**，系统性偏差从「judge 高 1–2.6 分」收敛到「≤1 分」。材料三道关 + rubric v6 + 预算放宽的修复链生效。
3. **Spearman 不可作为结论**：report_relevance / debate_quality judge 恒 5（零方差）不可算；decision_grounding 的 -0.43 出自 judge 仅 {4,5} 两档 + n=9，正是预登记预测的形态——n=9 维度不单独下结论，待 round8 合并判。
4. **本轮最有价值的口径发现**：dg 的 6 行 Δ1 全部是 judge 因「source 标注不精确」扣分而人工给 5——judge 在 v6 下自发执行了三层判法的「归属层」核对（数字真实存在但 source 标错节），而人工标注时重点在「数字可溯源」、没把 source 归属精确性当扣分项。**人工与 judge 的尺差不在「找不找得到」，在「归属精确性」。**

## 指标总表

| 维度 | n | Spearman | MAE | 方向一致率 | 预登记判定 |
|---|---|---|---|---|---|
| consistency | 9 | —（judge 仅 {4,5}，n 小） | 0.222 | 1.000 | ✓ 达标 |
| debate_quality | 9 | —（judge 恒 5 零方差） | 0.667 | 1.000 | ✓ 达标 |
| decision_grounding | 9 | -0.425（不具结论力，见上） | 0.889 | 0.889 | ✓ 达标 |
| report_relevance | 13 | —（judge 恒 5 零方差） | 0.231 | 0.923 | ✓ 达标 |
| **整体** | 40 | -0.179 | **0.475** | **0.950** | ✓ 达标 |

## 健康检查

- 人工标注 40/41（`5f41a49a` report_relevance 未填，judge=5 待补）；judge 41/41 出分，无 parse 失败。
- judge confidence 0.80–1.00，无 <0.5 低置信信号（材料健康，无「缺料却高分」的幻觉形态）。
- 人工 confidence 按维护者此前给的 3 档制填写（39 行=3，1 行=2），与 judge 侧 0-1 契约不一致 → 预登记的「人工×judge confidence 相关」不可算。**责任在维护者口径未统一，非标注人误用**；round8 口径卡补「confidence 填 0-1 小数」填写说明，此前口径指引一并修正。

## 分桶：系统性偏差结构（全部 ≤1 分，方向无一处反转）

| 桶 | 行数 | 形态 | 归因 | 处置 |
|---|---|---|---|---|
| debate_quality 宽松偏置 | 6×Δ1（judge5/human4） | judge 满足「逐条+有数据」即给 5；human 对个别纯定性论点（如 bull②/bear②）保留 4 | rubric 5 的门槛锚定差 | 良性；rubric v7 候选：收紧 5 措辞为「所有论点均有数据/事实支撑」 |
| consistency 严格偏置 | 2×Δ1（judge4/human5） | judge 扣「分析师与最终方向表述差异」 | 严格侧，方向无冲突 | 良性，不动 |
| dg source 归因 | 6×Δ1（judge4/human5） | judge 逐条指出 source 标错节：中报 36% 标 fundamental 实出 sentiment、beta 解读标 risk_metrics 实出 neutral、分批减仓建议标 risk_aggressive 实为中性方表述等 | judge 执行归属层核对；人工未把归属精确性当扣分项 | **待终裁**（见下） |
| dg 解读失当盲区 | 1×Δ2（judge5/human3，1caf1f7b） | human 扣「利率支撑资产质量系单向解读」，judge 称语义一致 | judge 对「解读失当」不敏感（v6 有此条款未执行） | **待终裁**；rubric v7 强化检查的证据 |
| report_relevance | 1×Δ2（judge5/human3，7e6bc8bc） | 宁德时代「今日股价表现」查询，judge 认为直接回答 | 待 owner 终裁报告是否切题 | **待终裁** |

## 待终裁清单（逐条人工过目后更新本报告）

1. **dg source 归因 6 行**（d7e48a92 / d477972f / ce66d316 / 8bbe659a / 5e9b09e3 / 4758fdb7）：逐条核被 judge 点名的 source 是否真错安——真错安 → judge 对，人工按三层判法改分并重跑 measure；数字两节都有、两可 → 记口径灰区，rubric v7 写明判定规则。
2. **dg 1caf1f7b（Δ2）**：确认「单向解读」扣分是否成立 → 若成立，v7 需给 judge 增加逐条复述核对解读方向的强制动作。
3. **report_relevance 7e6bc8bc（Δ2）**：owner 重读报告与查询，裁决切题归属。
4. **5f41a49a 补填**（1 分钟）：补填后重跑 measure 刷新 report_relevance（13 行完整）。

## round8 建议

- rubric v7 三处候选改动**合并一次 bump**：① debate 5 分措辞收紧；② dg 写明「source 归属精确性按三层判法计分」；③ dg 强化解读失当检查。改动后重校准（依赖预登记：单变量原则）。
- 口径卡补 confidence 0-1 填写说明（round7 实测：维护者给的 3 档制与 judge 侧 0-1 契约不一致，统一为 0-1）。
- 口径卡已随本次提交新增「人工标注操作指引」章节（5465481），round8 导出自带。
