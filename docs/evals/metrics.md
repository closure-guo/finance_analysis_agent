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
| citation_surgical_repaired | 跟踪 | 单点修复成功回填条数（稀疏 value_mismatch，同一分析师同轮 <3 处触发）；已计入 `analyst_true_fail`，单独计数用于观测修复触发/成功率——修复失败时无重试回退（自动重试已关），失败即标记阻断 |
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

| r8 09-13 21:32Z | cdca5b1+027+v7 | 基线重建轮（三变量：v7 rubric / 派生指标喂回 / 027 价位校验回路激活）；dg 3.56 系 v7 归属+解读失当扣分生效（契约抽验 4 条低分全中 v7 规则）；blocked 4/9 | 5.0 | 4.22 | 3.56 | 4.89 | 0.556（blocked 4/9） | 0.835 | 4/9｜1.22/条｜5.33/条 | 0 |
| r9 09-14 00:37Z | afd9d1f+v8 | 混合变量轮（材料升级：consistency 补 Trader 方案节 + debate 收敛骨架行；rubric v8 三版本两判例）；审计：dg 归属扣分全为真错安（判例无误放）、Trader→RJ 静默推翻核对首次可判、debate 5 分档仍漏判 ≥3 行（v9 候选：强制枚举）；blocked 6/9 | 5.0 | 4.67 | 3.44 | 4.67 | 0.333（blocked 6/9） | 0.843 | 6/9｜1.44/条｜6.33/条 | 0 |

人工校准：round8 盲标环节改为**维护者代裁**（owner 拒绝再投入标注时间；非盲审计口径，不能当独立 MAE）——41 行逐条核对：36 行一致、5 行分歧全部 ±1 档且方向均为 judge 偏严/规则执行不一致、无虚高，维护者口径 MAE 0.122 / 方向一致率 100%。**judge 自 round7 起可用结论维持**；两条 v8 候选改动见下方待决策。详见 [2026-09-13-round8-维护者代裁报告.md](2026-09-13-round8-维护者代裁报告.md)。
## 2.2 round8 预登记（基线重建轮，2026-09-13 启动）

- 实验：`round8-v7-rubric`（dataset a-share-analysis-v1），HEAD 含 rubric v7 + 两个 delta 实现 + incident 027 修复
- **三变量混合轮（不可纯归因 v7）**：① rubric v7（dg 三层判法归属/组合claim规则/解读失当强制核对 + debate 5 分收紧）；② 派生指标喂回风险辩论 context（deterministic-derived-metrics）；③ incident 027 修复激活价位校验 fail→打回回路（trader 行为可能变化）。对比 round7 时按桶归因，不把任何差异直接记到 v7 头上
- 收口动作：健康检查 → 契约抽验（v7 生效：judge 是否开始扣归属层/解读失当）→ 导出盲标表 → ~~owner 标注 → measure 合并~~（**实际路径**：owner 拒绝标注，改为维护者代裁审计，见上）
- 附加观察：trader 价位申报率（E2E 3/3 次 None，价位为 buy/sell 承重参数，考虑必填化评估；**round9 追加证据**：宁德 04baff5c 为 buy 决策仍 entry/stop/target 三价全 null，止损仅以散文「近期前低下方」描述——连续 4 轮 0 申报，report-render-operational-params 4.2 真实报告核对持续被堵，价位必填化建议升级为独立 delta）；derived_metrics 真实数据路径补核（E2E 未覆盖）

## 2.3 round9 预登记（混合变量轮，2026-09-13 立项，delta upgrade-judge-material-v8-rubric）

- **变量声明（混合轮，按桶归因，不把差异单一归因）**：① judge 材料升级——consistency 加【Trader 方案】节（trader_plan，Trader 原始方案 ≠ final_trade_decision）、debate 材料加收敛信号骨架行（确定性统计，标注「供参考」）；② rubric v8 三版本递增（debate 3→4 论点标头定性判例 / dg 7→8 多来源归属判例 / consistency 3→4 静默推翻核对）
- 对照基线：round8（judge 分 + 代裁 41 行审计，非盲口径见代裁报告）
- **定向验证点（round8 代裁误判样本是否被 v8 纠正）**：① 比亚迪 3e316c01 型「多来源同判归属」不再误扣（dg 4 分档是否上移）；② 美的 41a90c99 / 宁德 6b3d5e05 型「论点标头纯定性论点」是否被降 4（debate 5 分是否收敛至 ≤1 条/9）
- 预期方向：dg 均值小幅上移（4 分档收窄）、debate 均值小幅下移（5 分档收紧）、consistency 材料完整性提升后均值不变或微调——三者均为 rubric 判例的预期效果，非能力变化
- 收口动作：健康检查 → 契约抽验（判例生效证据）→ runs.jsonl + 时间线 → 代裁审计（重点两条判例）→ metrics.md 记录
- 排除项：材料骨架行升级（辩论收敛 + Trader 方案）与 rubric v8 不改变 5 层流水线行为，citation 链路与 golden gate 不受影响
- **收口结果（2026-09-14）**：17/17 行齐、judge_failures=0。定向验证：① dg 多来源归属判例达标（比亚迪 dg=3 三处扣分逐条复核全为真错安，判例无误放；平安 dg=5 干净证据链正常给满）；② consistency Trader 方案节达标（茅台 d46e0942 首次核出「RJ 将 Trader light 修正为 none 且已说明」，宁德/中芯参数演进被正确定性）；③ debate 5 分档判例**未达标**——4 分档严格引用判例语言，但 5 分档抽查 3 行（宁德/美的/平安银行）论点标头均含纯定性论点被漏判，与 round8 同构 → v9 候选。详见 [2026-09-14-round9-v8审计.md](2026-09-14-round9-v8审计.md)。citation_pass 0.556→0.333（blocked 6/9）为新生成方差（citation 链路无变更），follow-up 观察不处置

## 2.4 round10 预登记（debate rubric v5 单变量离线重判，2026-09-14）

- **单变量**：仅 debate_quality rubric v4→v5（加强制枚举动作：评分前逐条标注论点标头「数据/事实」或「纯定性」，任一纯定性即封顶 4）。dg/consistency/report_relevance rubric 与全部 judge 材料、5 层流水线均不变
- **方法（纯归因，不重跑管线）**：对 round9 的 9 条 deep trace，从 Langfuse 取落库的 debate judge 输入材料（同一批辩论内容），用 v5 rubric 离线 run_judge 重评（tests/scripts/rejudge_debate_v5.py）。同内容 + 仅 rubric 变 = 分数差异可纯归因到 v5
- **定向验证点（round9 审计漏判样本是否被 v5 纠正）**：宁德 04baff5c / 美的 20712f2a / 平安银行 a163494e 三行 v4=5（标头含纯定性论点被漏判）→ v5 应降 4；其余 6 行 v4 分应基本稳定（4 分档已正确执行判例，不应因 v5 进一步下压）
- 判定：v5 满分行数 ≤1/9 且三条漏判样本全部降 4 → 判例达标；若仍漏判 → 强制枚举模式对 debate 无效，需换机制（如 judge 输出结构化枚举字段后程序校验）
- 收口：重判结果落 jsonl + 本节追加结果 + runs.jsonl（标记 offline-rejudge，非全量实验）
- 排除项：不重跑 pipeline、不写业务 score（dry-run），Langfuse 仅可选 --write 落 v5 对照分
- **收口结果（2026-09-14，8/9 行）**：茅台现金流 5f179e87 因 Docker Desktop 停机未能拉取材料（其 v4=4，不影响判定）。**未达预登记达标线**（满分 2 行 >1；宁德 04baff5c v5 仍 5——「价格战加速产能出清利好龙头份额集中」漏判），但净效果显著正向：对照审计 ground truth（8 行全应得 4），准确率 v4 2/8 → v5 6/8（美的/比亚迪/平安银行/中芯/茅台 5 行 5→4 纠正），均值 4.75→4.25（方向=收紧）。**一个回归**：招行 53448e4b v4=4（曾正确抓住「银行股破位速度快」定性论断）→ v5=5 漏判——LLM 自我枚举是随机的，不是确定性的。**结论**：prompt 内强制枚举降低但不消除 5 分边界漏判，触发预登记 fallback——后续候选=judge 输出结构化枚举字段 + 程序封顶（代码强制 cap，不依赖 LLM 自律），已登记待决策。v5 保留（当前最优版），残留漏判如实记录

## 3. 待终裁 / 待决策

**r2 非 PASS 137 条归因**：~~待终裁~~ **已闭合（2026-09-13，维护者代裁，证据链齐备）**。对照表 `tests/validation/citation-r2-nonpass-归因对照表.md` 机器分桶：81 结构不可验→分型 + 34 校验器误报 + 22 待终裁；22 条决策单 `tests/validation/citation-22条待终裁决策单.md`（✅ 终裁完成）：**全部「非幻觉」**——13 行 r4 同族全 PASS（新规则吸收）、8 行混合族残余全落已知结构不可验形态（比较/解读句 + quarterly_trend 期段路径）、2 条列名单位后缀缺口已修复（metric_vocab 补「加权每股收益(元)」别名）。owner 如需可对决策单抽查；副产品 follow-up 两条见下段。

**待 owner 终裁（round7 校准，2026-09-13）**：~~已完成~~——4 行 judge source 归属扣分成立（人工改 4）、1 行 judge 误判（维持人工 5）、1 行灰区（维持 5）、1caf1f7b 单向解读成立（维持 3）、7e6bc8bc 改 4、5f41a49a 补填 5。终值：整体 MAE 0.342 / 方向一致率 97.6%。rubric v7 四项改动清单已定稿（见校准报告）。

**校验器 follow-up（2026-09-13，22 条终裁副产品）**：① 比较型差值重算——~~开放~~ **已落地（2026-09-14）**：数值差值申报走双端重算 + 符号校验（方向未申报显式计覆盖缺口）；② quarterly_trend 期段定位补全——**已落地**（ff26b71）。派生键注册补齐 8 键 + 两条门禁（引用覆盖 `test_recompute_registry_covers_all_compute_outputs`、图通道 `TestNodeOutputChannels`）随 delta `close-citation-coverage-gaps` 落地（见 `tests/validation/2026-09-14-close-citation-coverage-gaps-validation.md`）。

**待决策**：
- ~~#2 surgical 单点修复（<3 处失败真值回填）与重试准入的关系~~ **已落地（2026-09-14）**：真错口径含修复回填（`citation_analyst_true_fail = 残余 FAIL + value_mismatch_repaired`，`citation_node.py:411`）；修复数单独入拆报 `citation_surgical_repaired`；授权与三条护栏固化进规范（`citation-verification`「单点修复的自动处置授权与边界」，delta `2026-09-14-document-surgical-repair-policy`）
- #4 置信度锚定（RM/RJ/FM 扎堆示例值 0.50–0.60；r3 FM 动作已有多样性，确认后改示例或加校准指令）
- #6 「风险提示」章：报告加顶层章 vs 改 must_cover 期望
- 分析师节点独立 span（根 span 元数据覆盖的根治方案，当前以 `degradation.{agent}.r{n}` 键止血）
- 覆盖率指标在「逐条回应成常态」后无区分度（r3 全 4/4、5/5），是否保留进 judge 材料
- consistency / decision_grounding 材料缺【Trader 方案】节——Trader→Risk Judge 的转向是否静默推翻无法核对（round8 材料版本落地，本轮 round7 口径：只评 RM→RJ→FM→报告四层）
- **v8 候选（round8 代裁发现，2026-09-13）**：① debate 5 分档执行不稳定——「个别定性论点降 4」在 4 分档执行严格，但美的/宁德两行漏判纯定性论点给 5，建议 5 分判例进 rubric few-shot；② dg 归属层对「同一评判在多来源出现」判定偏机械——claim 在 debate_bear 与 research_manager 均有原话时 judge 只认单源（比亚迪 ref7 误扣），v8 补「任一真实来源即合法」判例
- **debate 5 分边界可靠性（round9 审计发现 → round10 验证，2026-09-14）**：v4 判例 4 分档严格但 5 分档漏判 ≥3 行 → v5 强制枚举（prompt 内逐条标注）离线重判 8 行：准确率 2/8→6/8 但仍漏判宁德、且招行回归（LLM 自我枚举随机）→ **prompt 机制已到顶，候选换机制**：judge 输出结构化枚举字段（每条论点标注 data/qualitative）+ 代码强制封顶 4，不依赖 LLM 自律——需开新 delta 改 judge 输出契约
- mypy 全仓 75 个既有错误（本次触碰文件为 0），是否立清理任务
