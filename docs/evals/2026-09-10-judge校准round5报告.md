# Judge 校准 Round5 报告（2026-09-10）

**status**: active

## 配置

- 样本：53 行（20 trace × 4 维度；report_relevance 20 / debate_quality 11 / decision_grounding 11 / consistency 11）
- 人工标注：单盲标（v6 表，材料为 judge 同口径落库输入；标注人=系统 owner，非金融专业视角）
- judge 分：deepseek-v4-flash（方舟端点；consistency 11 条为 rubric v2 重评分，其余为 round5 原评分）
- 指标：Spearman / MAE / 方向一致率（>3 分界）

## 结果

| 维度 | n | Spearman | MAE | 方向一致率 | 人工均 | judge 均 |
|---|---|---|---|---|---|---|
| report_relevance | 20 | -0.35 | 2.90 | 25% | 2.20 | 4.80 |
| debate_quality | 11 | 0.19 | 1.36 | **0%** | 2.91 | 4.27 |
| decision_grounding | 11 | -0.23 | 0.64 | 54.5% | 3.64 | 4.09 |
| consistency | 11 | -0.18 | 1.45 | 54.5% | 3.18 | 3.73 |
| **整体** | 53 | -0.36 | 1.81 | 32% | — | — |

**全线未达阈值（Spearman≥0.5 / MAE≤1.0 / 方向一致率≥0.7）。**

## 归因（裸指标不可直接采信的原因）

1. **report_relevance 13 条 Δ4 分歧全部为「人工 1 vs judge 5」**。judge 理由呈模板化（「全面覆盖…紧扣…无无关内容」），其中 4f58faf7（平安银行）经实证为**幻觉评分**：judge 输入被 4096 挖心后仅见图表路径与审批章（18933 字节分析内容缺失），judge 从章节标题脑补「全面覆盖」。report_relevance 恒 5 分（消融期 96%）由此而来。
2. **人工口径揭示 rubric 语义分歧**：quick 报告（如「茅台现在能买吗」「比亚迪和特斯拉哪个更值得买」）judge 以「主题相关」给 5 分，人工以「问题解答」口径打 1——报告覆盖了维度但**未回答用户的问题**（不给买/不买的结论，以「不构成投资建议」收尾）。两种口径中「问题解答」更符合 report_relevance 的定义意图；rubric 下一版须明确。
3. **debate_quality 方向一致率 0%（11 条全部反向）**：judge 与人工看的是同一份残缺辩论输入（4096 挖心，【bear】标签丢失）。人工按「交锋不可核」打 ≤3，judge 对同样的残缺输入系统性给 >3——证明 judge 在残缺输入上虚高，非人工噪声。
4. **decision_grounding MAE 0.64 为最优**：judge 输入缺辩论记录（已知缺口，evidence_refs 引用 debate_bear 的 claim 无法核对），两侧均未因此重罚。
5. 截断材料行（42 条）平均 Δ1.64 vs 完整材料行（11 条）Δ2.45——完整行更差由 quick 报告（口径分歧）构成，非「材料完整反而更差」的一般结论。

## 结论

1. **当前 judge 评分不可作为质量依据**——根因排序：①judge 输入残缺（report 挖心+幻觉、debate 挖心、consistency 9/11 截断、decision_grounding 缺辩论）；②rubric 语义歧义（report_relevance 的「切题」口径、consistency 的 approve 语义已修 v2）；③judge 对残缺输入系统性虚高而非保守。
2. 本轮校准的主要产出是**诊断**：发现并修复/立项 8 项系统缺陷（两层材料截断、辩论论点丢弃、consistency rubric v2、report 变量幻觉输入、decision_grounding 缺辩论、report_relevance 口径歧义、FM 语义缺失、材料可读性），全部收敛于 delta `harden-decision-report-semantics` 与已直接修复项。
3. **第二轮校准前置条件**：delta 实施（judge 输入修复）→ 重跑 dataset 实验 → 新抽样重标。修复前 judge 分数仅可作参考信号，禁止用于 CI 门禁、层间对比、回归判定。

## 后续

- delta 实施后：consistency / decision_grounding / report_relevance 全量重评（rubric v4 连同 debate 记录补充）；
- report_relevance rubric 需明确「切题=回答了用户的问题」口径，并处理「安全规则回避直接结论」与「回答用户问题」的张力（系统 Safety 要求不给买卖建议 vs 用户明确问能不能买——如实说明约束即为回答）；
- 双标注员（或 owner 复标）以测量人工参照系自身的 κ，建立噪声基线。
