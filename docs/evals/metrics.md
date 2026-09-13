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
| r4 09-11 07:36Z | 322ce18+容忍补丁 | 阶段 0–5 全量：重试停用+校验器归一+分型回声+auto-claim+三层拆报 | 4.93 | 5.0 | 4.0 | 4.89 | 0.333（blocked 6/9） | 0.837¹ | 6/9｜1.89/条｜5.22/条 | 0 |
| r5 09-12 03:17Z | fa9f72b | 6.2 重评全量重跑（fa9f72b 渲染修复生效：辩论预算 24000）；东财数据源当日大面积不可用（百度+腾讯回退），对比含环境混淆 | 5.0 | 5.0 | 4.22 | 5.0 | 0.556（blocked 4/9） | 0.879 | 4/9｜0.78/条｜8.0/条 | 0 |

¹ r1–r3 的 `citation_pass` 是旧口径（FAIL=0，含校验器误报），与 r4 起 `citation_blocked` 不可直接比较。
² 拆报四项自 r4 起记录：verifier_normalized 5.22/条（echo 34+percent 13，校验器解析债）、unverifiable text 3.11 + unregistered 4.0（每条 deep）。r4 收口详见 [2026-09-11-citation门禁整改r4收口报告.md](2026-09-11-citation门禁整改r4收口报告.md)。
¹ r4 coverage 0.837 为重试停用后的真实首轮值（r2/r3 的 0.92 含 2–3 轮补 claim 重跑），不可直接对比。

人工校准：round5（53 行）全线未达标（整体 Spearman -0.36 / MAE 1.81 / 方向一致率 32%）→ 材料与 rubric 修复多轮 → **round7（41 对终裁后终值，r3）全维度达标：整体 MAE 0.342 / 方向一致率 97.6%，judge 自 round7 起可用**（终裁：4 行 judge 的 source 归属扣分成立改 4、1 行 judge 误判维持人工 5、1 行灰区维持 5；详见 [2026-09-13-round7-judge校准报告.md](2026-09-13-round7-judge校准报告.md)。rubric v7 四项改动已定稿待 bump：debate 5 分收紧 / source 归属三层判法 / 组合 claim 归属规则 / 解读失当强化）。

---

## 2.1 round7 预登记分析计划（标注前锁定，防事后口径漂移）

- 数据：`judge-sample-round7-blind.xlsx`（人工 human_score + confidence）× `judge-sample-round7-judge.jsonl`（judge 分，r3 运行时落库，已冻结）
- 每维计算：MAE、方向一致率（>3 分界）、judge 分有方差的维度另算 Spearman（report_relevance / debate_quality judge 全 5，Spearman 不计）；整体 MAE / 方向一致率
- 判定：MAE ≤ 1.0 且方向一致率 ≥ 0.7 视为该维 judge 可用；Spearman ≥ 0.5 为加强项。n=9 的维度**不单独下结论**，与 round8 合并后判
- 附加：人工 confidence 与 judge confidence 的相关；人工低置信行单独列出复核
- 与 round5 对照：只比方向（是否从「judge 系统性高 1–2.6 分」收敛），不比绝对值（材料/rubric 不同口径）

## 3. 待终裁 / 待决策

**待 owner 终裁**：r2 非 PASS 137 条归因对照表 `tests/validation/citation-r2-nonpass-归因对照表.md`——34 条机器归因为校验器误报、82 条结构不可验（分型/注册处理），**22 条标「待终裁」必须人工过目**（16 条空值申报类、6 条无日期/季度形态的路径失败）。

**待 owner 终裁（round7 校准，2026-09-13）**：~~已完成~~——4 行 judge source 归属扣分成立（人工改 4）、1 行 judge 误判（维持人工 5）、1 行灰区（维持 5）、1caf1f7b 单向解读成立（维持 3）、7e6bc8bc 改 4、5f41a49a 补填 5。终值：整体 MAE 0.342 / 方向一致率 97.6%。rubric v7 四项改动清单已定稿（见校准报告）。

**待决策**：
- #2 surgical 单点修复（<3 处失败真值回填）与重试准入的关系：回填算「分析师真错已修复」，须保留在 analyst_true_fail 中
- #4 置信度锚定（RM/RJ/FM 扎堆示例值 0.50–0.60；r3 FM 动作已有多样性，确认后改示例或加校准指令）
- #6 「风险提示」章：报告加顶层章 vs 改 must_cover 期望
- 分析师节点独立 span（根 span 元数据覆盖的根治方案，当前以 `degradation.{agent}.r{n}` 键止血）
- 覆盖率指标在「逐条回应成常态」后无区分度（r3 全 4/4、5/5），是否保留进 judge 材料
- consistency / decision_grounding 材料缺【Trader 方案】节——Trader→Risk Judge 的转向是否静默推翻无法核对（round8 材料版本落地，本轮 round7 口径：只评 RM→RJ→FM→报告四层）
- mypy 全仓 75 个既有错误（本次触碰文件为 0），是否立清理任务
