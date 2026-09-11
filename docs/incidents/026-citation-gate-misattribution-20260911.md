# Incident 026 — citation 门禁把校验器解析缺陷记成分析师引用错误，并据此自动重跑分析师

- **日期**: 2026-09-11（r2 专项归因；现象自门禁上线起持续）
- **状态**: 阶段 0–5 已实施（delta `rework-citation-gate-attribution`，commits `4de9d3f`/`15f65ef`/`04aa075`/`9229ea6`）：重试停用、校验器四类归一、派生字段注册、文本分型回声、auto-claim、门禁三层分置与拆报；137 条离线归因表落 `tests/validation/citation-r2-nonpass-归因对照表.md`（34 误报 / 82 结构不可验 / 22 待终裁——终裁待 owner）。r4 验证：FAIL 39→16（归一后残余约 3 条真错）、PASS 76%→85.6%、verifier_normalized 47/轮、analyst_true_fail 1.89/条首次可观测，详见 `docs/evals/2026-09-11-citation门禁整改r4收口报告.md`；22 条终裁待 owner
- **影响面**: 全部 deep 分析；每次 deep 多烧约 4 次分析师 LLM 调用（r2 九条 deep 分析师生成 75 次，fundamental 25 次）；重跑用解析失败的降级版覆盖正常报告（r1 中芯，见 `docs/evals/2026-09-11-judge校准复盘-round5到r3问题发现链.md` §3-4）；实验报告中 `citation_pass` 1/9 被读作「引用可靠性」。

## 现象

> 关联：[020](020-citation-contract-diseases-20260828.md) 已记录同类「考卷与答案册不同源」病；本次是其复发，新形态为日期显示格式、季度标签、单位量级、direction 符号字段。020 当时离线重判「残量全为真幻觉」的结论在本轮样本上不成立——FAIL 桶抽样无一真错。

- `citation_pass` 长期 ≤ 1/9，`citation_coverage` 0.69–0.78；routing 注释早在 citation-retry-policy 时已记录「重试零收益、每轮全量重跑白烧 ~40 分钟」，但 D6 coverage-gap 重试路径重现同一模式。
- r2 逐 claim 归因（565 条）：PASS 428、UNVERIFIABLE 98、FAIL 39。**39 个 FAIL 抽样归因无一为数字写错**（待逐条终裁）。

## 根因（按桶）

| 桶 | n | 真实原因 |
|---|---|---|
| path_unresolvable | 24 | context 里报告日经 `render_date` 显示为 `2025-12-31`，校验器按单元格原值 `20251231` 匹配；季度 LLM 照抄标签 `2026Q2`，校验器要位置索引 `[idx]` |
| value_mismatch | 5 | 分析师写「583.95 亿元」，数据存元；校验器不做量级归一 |
| semantic_term_mismatch | 5 | LLM 照抄真实列名「归属于母公司的净利润」，词表规范名是「归母净利润」 |
| direction_mismatch | 5 | `direction` 是 LLM 申报的符号字段；LLM 把「PMI 49.8 低于荣枯线」填成 negative，校验器对恒正水平量比符号 |
| UNVERIFIABLE | 98 | 75 条舆情文本 claim（news_list 61/61、key_events 14/14）只能数值比对；23 条计算型字段（garp_result、anomalies 等）未注册 |

**放大器**：定向重试只盯 value_mismatch + direction_mismatch 两个桶（全为误报）+ coverage-gap 补 claim → 重跑分析师不改变表述 → 停滞判定前打满 3 轮；重跑结果不做 keep-best（已修，`d4b39b1`）。

**误读**：`citation_pass` = FAIL 为零，把校验器的解析债算在分析师头上；实验报告把它当引用质量指标呈现。

## 指标必须拆开报

- 分析师真幻觉率：0/565（本轮样本，抽样归因，待逐条终裁）
- 校验器误报率：39/467（FAIL 桶 100% 误报）
- 结构不可验占比：98/565 ≈ 17%（契约设计问题）

## 处置（按杠杆排序）

0. **立刻停掉错误的重试**（配置级）：value_mismatch / direction_mismatch / coverage-gap 三条自动重试下线；加停滞保护「重写后文本不变即停」；重试准入 = 经代码复核确认的真 FAIL。
1. **修校验器 39 条误报**（纯代码）：日期/季度路径双向归一；单位换算（亿/万/元）在容差前归一；报表域列名词表从 DataFrame 列动态生成；指标注册 `signed` 属性，符号校验只对有符号量生效，`direction` 字段改名/加注释。清零后**必须做注入式故障演练**（故意写错一个数字须 FAIL），全绿不是庆祝信号。
2. **计算型字段注册**：garp_result / anomalies 等由代码从快照算出，校验器用同一份代码重算即可核对（23 条 UNVERIFIABLE → 可验）。
3. **文本 claim 分型**：不新增字段，用既有 `claim_type`（entity/temporal）+ `source_type`（event）分流——不计入 FAIL=0 分母，先加回声匹配（标题子串命中即 PASS），NLI 作第二层备选；交易决策引用舆情的语义核对由 decision_grounding judge v6 承担。
4. **auto-claim 补覆盖缺口**：正文数字唯一匹配 state 结构化条目时自动生成 claim（注意同值多字段歧义）。

**门禁定义重写**（需 delta，涉及 `harden-citation-semantic-coverage` / `citation-retry-policy` 规范）：阻断门禁 = 真 FAIL（终裁后）= 0；警告线 = coverage < 0.90 报警不阻断；跟踪指标 = UNVERIFIABLE 占比。现有 `citation_minor_fail` 降级放行是这套三层分置的临时替代，随之退役。

## 经验

- **处置对象必须匹配归因桶**：契约病修契约、解析病修解析器、真幻觉才修分析师。任何聚合指标进入处置（重试/改 prompt/判定 agent 缺陷/写进报告）前必须有分桶表与逐条终裁记录；自动化处置只允许挂在人工终裁确认为真错误的桶上。
- 聚合指标低 ≠ 某个 agent 能力差。同一误读两天内三次：round5 debate 方向一致率 0%（实为输入残缺）、r1 FM「无交易方案」（实为 FM 没收到方案）、r2 citation_pass 1/9（实为校验器认不出正确表述）。
- 系统性问题的分桶 + 终裁流程应固化为 SOP：FAIL 桶再出现时第一反应是终裁归因，不是触发重跑。
