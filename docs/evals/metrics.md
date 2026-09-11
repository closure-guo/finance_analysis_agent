# 评估指标台账

唯一查询入口：口径定义看这里，历史看时间线表，机器可读摘要看 [`metrics/runs.jsonl`](runs.jsonl)。
分工：Langfuse Scores = 逐 trace 明细真源；`reports/evals/*.json` = 单次实验全量产物（本地）；本文件 = 跨 run 台账。每次实验收口时更新一行，并注明当时的 git HEAD。

**基线切点**：incident 026（`docs/incidents/026-citation-gate-misattribution-20260911.md`）之前，`citation_pass` 把校验器误报算在分析师头上（r2 终裁：FAIL 桶 100% 误报），不可与 r4 起的拆报指标直接比较。

---

## 1. 口径定义

### 1.1 judge 维度（LLM-as-judge，rubric 见 `evals/judges.py`，人工对照见 `evals/judge_calibration/`）

| 指标 | 口径 | rubric 版 | 备注 |
|---|---|---|---|
| report_relevance | 切题 = 回答了用户的问题（非主题相关） | v3 | quick/deep 均评 |
| debate_quality | 辩论交锋质量（含交锋覆盖率对照锚点） | v2 | deep only |
| decision_grounding | 决策论据逐条核对 evidence_refs ↔ source | v5 | deep only；材料 v6 含风控指标+风险辩论 |
| consistency | 各层方向一致性（approve 语义：批准对象是 Risk Judge 方案） | v3 | deep only |
| judge confidence | judge 对评分依据充分性的自报把握；材料不足 MUST <0.5 | — | 以 `[conf=x.xx]` 前缀落 Scores.comment |

### 1.2 确定性指标（零 token，`evals/evaluators.py` / `evals/sections.py`）

| 指标 | 口径 |
|---|---|
| ticker_match | 标的解析正确性 |
| section_coverage | 报告必备章节覆盖（must_cover；「风险提示」章口径待决策 #6） |
| citation_coverage | 报告正文数字被 claim 认领比例（警告线 0.90） |

### 1.3 citation 门禁拆报（r4 起，delta `rework-citation-gate-attribution`；定义=incident 026）

| 指标 | 层 | 口径 |
|---|---|---|
| citation_blocked | 阻断 | 归一后残余 FAIL > 0 |
| citation_analyst_true_fail | 阻断/拆报 | 残余 FAIL + 单点修复回填数（修复会把真错藏进 PASS，必须计入） |
| citation_verifier_normalized | 跟踪 | 归一后由 FAIL 转 PASS 的计数（unit/percent/echo）＝校验器此前解析债的量化 |
| citation_unverifiable_text | 跟踪 | 文本 claim（entity/regulatory/event）分型排除，不计阻断分母 |
| citation_unverifiable_unregistered | 跟踪 | 未注册/空值 UNVERIFIABLE（目标：注册后趋零） |
| citation_coverage_warn | 警告 | coverage < 0.90 报警不阻断 |
| auto_claims | 跟踪 | 正文数字唯一匹配 state 条目自动合成的 claim 数 |

### 1.4 校准指标（`evals/judge_calibration/measure.py`）

Spearman / MAE / 方向一致率（>3 分界）/ Cohen's κ；阈值 Spearman≥0.5、MAE≤1.0、方向一致率≥0.7。judge 分零方差的维度 Spearman 不可计算，以 MAE/方向一致率为主。

---

## 2. 时间线（每轮一行，收口时追加）

| run | HEAD@启动 | 关键变更 | report_rel | debate_q | dg | consistency | citation_pass¹ | citation_cov | blocked/真错/归一² | judge_fail |
|---|---|---|---|---|---|---|---|---|---|---|
| r1 09-10 13:13Z | e92129a+judge端点 | delta 实施后首轮 | 5.0 | 4.38 | 2.75 | 3.63 | 0.25 | 0.861 | 未拆报 | 0 |
| r2 09-11 00:16Z | d621acb | FM 审批对象+重试校验+d_g v6+JSON 完整 | 4.86 | 4.33 | 3.89 | 4.67 | 0.111 | 0.919 | 未拆报 | 0 |
| r3 09-11 02:08Z | 4f0db3f | 覆盖率并行语义+预算放宽+evidence 逐条 | 5.0 | 5.0 | 4.22 | 4.78 | 0.111 | 0.918 | 未拆报 | 0 |
| r4 09-11（跑中） | 322ce18 | 阶段 0–5 全量：重试停用+校验器归一+分型回声+auto-claim+三层拆报 | — | — | — | — | — | — | 待填 | — |

¹ r1–r3 的 `citation_pass` 是旧口径（FAIL=0，含校验器误报），与 r4 起 `citation_blocked` 不可直接比较。
² 拆报四项（blocked / analyst_true_fail / verifier_normalized / unverifiable_text+unregistered）自 r4 起记录。

人工校准：round5（53 行）全线未达标（整体 Spearman -0.36 / MAE 1.81 / 方向一致率 32%）→ 材料与 rubric 修复多轮 → round7（41 行，r3）待 owner 标注。

---

## 3. 待终裁 / 待决策

**待 owner 终裁**：r2 非 PASS 137 条归因对照表 `tests/validation/citation-r2-nonpass-归因对照表.md`——34 条机器归因为校验器误报、82 条结构不可验（分型/注册处理），**22 条标「待终裁」必须人工过目**（16 条空值申报类、6 条无日期/季度形态的路径失败）。

**待决策**：
- #2 surgical 单点修复（<3 处失败真值回填）与重试准入的关系：回填算「分析师真错已修复」，须保留在 analyst_true_fail 中
- #4 置信度锚定（RM/RJ/FM 扎堆示例值 0.50–0.60；r3 FM 动作已有多样性，确认后改示例或加校准指令）
- #6 「风险提示」章：报告加顶层章 vs 改 must_cover 期望
- 分析师节点独立 span（根 span 元数据覆盖的根治方案，当前以 `degradation.{agent}.r{n}` 键止血）
- 覆盖率指标在「逐条回应成常态」后无区分度（r3 全 4/4、5/5），是否保留进 judge 材料
- mypy 全仓 75 个既有错误（本次触碰文件为 0），是否立清理任务
