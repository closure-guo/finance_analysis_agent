# judge 校准复盘：从 round5 人工标注到 r3——指标状态、人机对比与问题发现链

日期：2026-09-10 ～ 2026-09-11
范围：LLM-as-judge 四维度（report_relevance / debate_quality / decision_grounding / consistency）的校准工作；数据集 `a-share-analysis-v1`（17 item：9 deep + 5 quick + 3 有意跳过）；judge = 方舟 deepseek-v4-flash；管线 LLM = glm-5.3。
关联：`docs/evals/2026-09-10-judge校准round5报告.md`（起点）、delta `openspec/changes/harden-decision-report-semantics/`（全部修复归口）。

---

## 1. 起点：round5 人工盲标 vs judge（2026-09-10）

53 行盲标（v6 表，owner 单人标注），与 judge 分数对比：

| 维度 | n | Spearman | MAE | 方向一致率 | 人工均 | judge 均 |
|---|---|---|---|---|---|---|
| report_relevance | 20 | -0.35 | 2.90 | 25% | 2.20 | 4.80 |
| debate_quality | 11 | 0.19 | 1.36 | **0%** | 2.91 | 4.27 |
| decision_grounding | 11 | -0.23 | 0.64 | 54.5% | 3.64 | 4.09 |
| consistency | 11 | -0.18 | 1.45 | 54.5% | 3.18 | 3.73 |
| 整体 | 53 | -0.36 | 1.81 | 32% | — | — |

全线未达阈值（Spearman≥0.5 / MAE≤1.0 / 方向一致率≥0.7）。judge 系统性高于人工 1–2.6 分。

**人工标注过程中（标注人边标边贴材料）暴露的材料缺陷**——这些是分数分歧的直接来源，而非人工噪声：

1. 材料 350 字符截断：consistency 只见 technical 分析师；RM 节被切；report_relevance 的分析报告只剩开头
2. extract 层 4096 字节「挖心」截断：fundamental 整段丢失、辩论记录【bear】标签被挖掉——debate_quality 方向一致率 0% 的根因（人按「交锋不可核」打 ≤3，judge 对同样残缺输入给 >3）
3. report 变量 = 报告全文挖心：图表路径占头部 → judge 只见标题就打 5（4f58faf7 平安银行：18933 字节分析内容被挖，judge 对图片路径 + 审批章打 5 分）——report_relevance 恒 5 的根因
4. consistency rubric v1 未定义 approve 的批准对象 → judge 把「watch + approve」误判冲突（7/11 低分）
5. 【最终报告结论章节】= FM 审批章复述，与 FM 节逐字重复，无独立信号
6. report_relevance 口径分歧：judge 按「主题相关」给 5，人工按「问题解答」给 1（quick 报告覆盖维度但不回答「能不能买」）
7. decision_grounding 材料缺【多空辩论记录】，evidence_refs 里 debate_bear 来源的 claim 无法核对（rubric 要求核对一份未提供的材料）
8. 材料可读性：转义 JSON、agent 摘要与正文重复、术语多，非专业标注人难读

**方法论上的错误（已承认）**：让标注在材料仍在修的过程中继续进行，而不是先冻结材料、通读、修完再标。标注人的原话「给 judge 的信息不全，还有继续标的意义？」是对的。由此确立原则：**先修 judge 输入，再标注**。

## 2. 修复批次：delta `harden-decision-report-semantics`（D1–D5）

- 截断策略：per-agent / per-message 边界截断替代整体挖心；论点骨架行前置
- report 变量结构化拼装（研究聚焦 + 分析师摘要 + RM + 交易方案 + FM），剔除图片引用
- rubric：report_relevance v3（切题 = 回答了用户的问题）、consistency v2/v3（approve 批准对象语义）、decision_grounding v5（加辩论记录）、全维度输出 confidence（材料不充分 MUST 降低）
- 结构化决策契约：FM 输出 action/confidence（approve 必填）、RM JSON 评级前置、辩论 rebuttal_to 交锋引用 + 覆盖率指标、focus 意图贯穿辩论/风控层、【最终报告结论章节】改为聚焦摘要
- golden 门禁 T8 反义逃逸修复；judge 端点切方舟

## 3. r1（修复后首轮，2026-09-10 13:13Z）与它暴露的问题

健康检查：16/17 完成，37/37 judge 分数落库，confidence 100% 落库（0.40–0.95），judge_failures=0。
均值：report_relevance 5.0 / debate_quality 4.38 / decision_grounding 2.75 / consistency 3.63。

**发现链（按发现顺序）：**

| # | 问题 | 怎么发现的 | 根因 |
|---|---|---|---|
| 1 | Item 0（分析平安）整条崩 | 汇总表 17→16 行；日志开头 `Item 0 failed: ValidationError`；grep SDK 源码确认「丢弃 item、无重试」 | FM 首答 approve 缺 action/confidence，`model_validate` 抛错无重试 |
| 2 | **FM 从未看到交易方案**（2026-07-04 首次提交即有） | 契约抽验「FM 含操作定性」6/8，两条未过是 reject 属合规；但 reject **理由原文**写「仅有风控指标输入，无交易方案」；拉 Langfuse fund_manager 节点 user 正文：4/4 无「交易决策」段 | `risk.py` 写 TradeDecision 对象进 state，`fund_manager.py` 用 `isinstance(dict)` 守卫静默跳过；旧测试 fixture 用 dict 喂 state 绕过生产路径 |
| 3 | decision_grounding 2.75 的主因是量尺对不上被测对象 | 8 条 judge 理由归类：5 条「风控数字无出处」、3 条「中性方/保守方论据无出处」；2 分行 confidence 全 ≤0.5 | 被评对象是 Risk Judge 裁决（依赖风控指标 + 三方风险辩论），材料却只给 Trader 的证据基础 |
| 4 | 分析师解析失败兜底「数据缺失」覆盖好报告（中芯 fundamental） | 全量复盘：material 里 fundamental 写「基本面数据缺失」，但辩手引用了营收 +16.5%；Langfuse 显示 fundamental 生成 3 次，前两次完整，第 3 次 JSON 因未转义内嵌引号 `"呈"低盈利"格局"` 解析失败 → 兜底覆盖 | 解析器不容忍内嵌引号；兜底文案撒谎；引用重试重跑不做 keep-best |
| 5 | 交锋覆盖率 8 条 trace 全「4/8」 | 第三关「整齐得可疑」；合成数据复现：bear 回应 bull 全部 8 条却报 4/8 | 去重键只用（角色, 单条内序号），多轮的①合并 |
| 6 | 降级/节点元数据全打到根 span 互相覆盖 | 按 span 元数据统计降级：每条 trace 只剩 1 个 `degradation`、agent=None；根 span 上 citation_coverage 是中间轮次残留 | 分析师节点无独立 span，`update_current_span` 落根，单键覆盖 |
| 7 | 置信度是常数 | RM 6/8 = 0.55，RJ 0.50–0.60，FM approve 6/6 watch 0.6–0.7；对照 prompt 示例值（RM 0.6、RJ 0.6、FM watch/0.55） | 模型抄输出示例（FM 全 watch 另有盲审批混杂） |
| 8 | section_coverage「风险提示」6/8 缺失 | 全部 6 条缺的是同一章；report.py 无顶层风险提示章（只在 deep_mode 摘要 prompt 里） | must_cover 期望与报告模板不匹配（决策项） |
| 9 | 引用重试无收益且有害 | 7/8 trace fundamental+macro 各生成 3 次，citation_pass 仍 0；routing 注释早已记录同类教训 | value_mismatch / coverage-gap 重试打满 3 轮不收敛（见 §6） |
| 10 | 汇总表不标 skip；茅台 Risk Judge JSON 残缺 | rows 的 skipped 硬编码 None；`_serialize_decision` 后再被 `_trunc` 挖心 | — |

## 4. r2（2026-09-11 00:16Z）与三道关审计

均值：report_relevance 4.86 / debate_quality 4.33 / decision_grounding 3.89 / consistency 4.67；17/17 完成，judge_failures=0。环境注意：运行期间机器网络抖动（35 次 AKShare 终态 ConnectionError、LiteLLM DNS 失败），deep 数据由缓存承接未受损（8/8 risk_metrics 存在、零兜底）。Docker Desktop 守护进程在此前一小时曾无故退出。

三道关（第一关程序查在不在；第二关跨层一致性；第三关整齐度）结果：

- 第二关通过：FM 输入 9/9 含交易决策段（bug 2 修复在线生效）；FM action 与 RJ 裁决 9/9 一致
- 第三关新发现：
  - 覆盖率仍全 ~50%：真实 rebuttal_to 显示辩论图**按轮扇出并行**（`route_to_debate_r1/r2` 各派两个 Send），同轮互不可见、R2 只能回应对方 R1、R2 论点无人可回应——旧实现「上一条发言 = 对方」在扇出下不成立，分母又含不可回应的末轮论点，上限被压到 50%
  - consistency【Risk Judge 裁决】9/9 原始 JSON：`risk_judgment` = 裁决 JSON + 风险辩论尾部 > 4096，外层 `_trunc` 挖掉闭合括号
  - 人读化把 evidence_refs 压成来源分布，**标注人看不到任何 claim**，而 judge 所见 JSON 每条都在——decision_grounding 人/judge 材料不等价
  - Risk Judge 输出枚举外来源 `risk_bull/risk_bear`
- 子代理通读 41 行另发现：consistency 末节泄漏评测指令「先明确决策语义(评分前必读)」（尾部锚点缺项）；分析师/辩论段 800 字节中段截断切出残句、丢期间标签造成「+36% vs +228%」假矛盾；judge 6/41 条理由抱怨「截断无法核对」并压低置信度

**用户决策**：截断预算一律放宽（分析师/辩论单段 800→6000，变量上限 4096→32768，裁决 reasoning 2400→6000，展示上限 5000→40000）。

## 5. r3（2026-09-11 02:08Z）——当前状态

均值：report_relevance **5.0（14/14）** / debate_quality **5.0（9/9）** / decision_grounding 4.22 / consistency 4.78；17/17，judge_failures=0。

三道关：第一关 41/41 全过（零截断标记 40/41、零指令泄漏、零 JSON 碎片、零兜底、Risk Judge 全部人读化、风险辩论无全零覆盖行、evidence 逐条列出）；第二关沿用 r2 结论；第三关：FM 动作出现 buy/hold/watch/sell 分布且与裁决 9/9 一致；置信度仍扎堆 0.50–0.60；覆盖率全部 100%（辩手逐条回应了对方全部首轮论点）。

**需要标注人知道的两点**：

1. report_relevance 与 debate_quality 的 judge 分零方差。材料补全后 judge 没有「截断」可归咎，5 分是它的真实判定；人工若给出分歧，测到的是 rubric 宽严问题而非材料问题——这正是本轮盲标要回答的。零方差意味着这两维的 Spearman 不可计算，以 MAE 与方向一致率为主。
2. 材料变长（中位数 11KB，最大 34KB），这是放宽预算的代价。

round7 盲标表：`evals/judge_calibration/data/judge-sample-round7-blind.xlsx`（41 行 / 14 trace，锁定 r3）。

## 6. citation 门禁失败成因（r2 专项，565 条 claim）

PASS 428（76%）、UNVERIFIABLE 98、FAIL 39；`citation_pass` = FAIL 为零 → 8/9 不过。

- **39 个 FAIL 没有一个是数字写错**：path_unresolvable 24（日期显示 `2025-12-31` vs 存储 `20251231`；季度用标签 `2026Q2` 而校验器要位置索引）、value_mismatch 5（亿/万 vs 元）、semantic_term_mismatch 5（照抄真实列名「归属于母公司的净利润」被词表拒绝）、direction_mismatch 5（LLM 把「低于荣枯线」填成 negative，对恒正的水平量比符号无意义）
- **98 个 UNVERIFIABLE 中 75 个是舆情文本 claim**（news_list 61/61、key_events 14/14）：校验器只做数值比对
- **重试白烧**：触发桶 value_mismatch + direction_mismatch 全是误报，加 coverage-gap 补 claim 重跑，分析师重写表述不变 → 停滞前打满 → 75 次生成；顺带制造 §3-4 的降级覆盖事故
- 纠正：并非「上下文里没有真实键名」——context 标了 state 键、prompt 写了语法，LLM 是照抄它看到的形态；错位在「显示形态 ≠ 校验器解析形态」。修法在校验器侧做归一（日期/季度/单位/词表别名、符号校验只对有符号量生效），不需要 NLI：真正的语义忠实性由 decision_grounding judge（rubric v6 逐条核对）与人工盲标承担

## 7. 方法论沉淀

1. **「测试全过 ≠ 行为正确」的具体形态**：契约清单从 delta 需求反推，只验这次改的东西——FM 盲审批是 delta 之前的老 bug，不在清单上；5.2 live 验证 7/7 通过也是同一原因。
2. **存在性检查 ≠ 可信度检查**：覆盖率行 8/8 都在、格式全对就打勾，但 8 条全 50% 本身就是红旗。整齐得可疑的数字（全 5 分、全 0.55、全 4/8）必须先解释再放行。
3. **LLM 在理由里抱怨输入缺失，比分数更强的信号**：FM 写「无交易方案」、judge 写「风控数字无出处」「记录有截断」——每一条都指向一个真实的材料缺口。
4. **先修 judge 输入，再标注**（用户原则，两轮验证）：r1、r2 都在导出后发现材料缺陷，若按原节奏交表都会浪费一轮人工。
5. **交付前三道关**：逐行通读（程序查在不在、人查可不可信）；跨层一致性（FM 看到的 = RJ 裁的、judge 变量 = state、材料数字可溯源）；整齐度解释。r3 是第一份按此标准交付的表。
6. **观测数据本身会撒谎**：根 span 元数据被覆盖、兜底文案谎称「数据缺失」——排查时必须回到节点原始输入/输出。
7. **指标低 ≠ 能力差：必须先分桶归因，逐条人工终裁，再定处置。** 把「citation_pass 低」直接当幻觉率，是这个体系里典型的未归因误读——39 个 FAIL 逐条看完，数字写错的是零，全是校验器的形态/单位/词表/符号误报。同一形态的误读在两天内出现三次：round5 把 debate_quality 方向一致率 0% 读成 judge 打不准（实为输入残缺）；r1 把 FM「无交易方案」读成 FM 幻觉（实为 FM 没收到方案）；r2 把 citation_pass 1/9 读成分析师引用不可靠（实为校验器认不出正确表述）。更要紧的是系统自己把这个误读写进了代码：routing 把 value_mismatch 桶当「分析师写错值」自动触发重跑——一个没有归因就执行、且每轮自动执行的处置，直接导致 75 次无效生成和降级覆盖事故。规则：任何聚合指标进入「处置」（重试、改 prompt、判定 agent 缺陷、写进报告结论）之前，必须有分桶表和逐条终裁记录；自动化处置只允许挂在经过人工终裁确认为「真错误」的桶上。

## 8. 提交清单与待决策

commit：`907e78e`（FM 审批对象 + approve 重试）、`d4b39b1`（解析保真 + 覆盖率 + 降级键）、`8a0d62b`（decision_grounding v6 + Risk Judge 来源，prompt 已 deploy）、`d621acb`（JSON 合法 + skipped）、`a420d24`（覆盖率并行语义 + risk_judgment 完整 + evidence 逐条）、`838ab71`（risk_bull/bear 别名）、`4f0db3f`（预算放宽 + 尾部锚点 + 逐块人读化）。门禁 2204 passed。

待决策：
- citation 校验器五项归一（日期/季度路径、单位量级、词表别名、有符号量 signed 注册、舆情回声匹配）+ 关停 value_mismatch/coverage-gap 重试
- 置信度锚定（RM/RJ/FM 扎堆示例值附近；改示例还是加校准指令）
- 「风险提示」章：给报告加顶层章，还是改 must_cover 期望
- 分析师节点独立 span（根治元数据覆盖，改 trace 拓扑）
- 覆盖率指标在「逐条回应」成为常态后已无区分度，是否保留进 judge 材料
