# Evaluation Specification

## Purpose

定义管线产出的评估能力域。评估以 langfuse dataset experiment 为核心执行（`evals/run.py`：`run_experiment` 是实验唯一入口，无 langfuse 时显式报错不降级），输出四个 judge 维度（report_relevance / debate_quality / decision_grounding / consistency）加确定性指标（section_coverage / ticker_match）。交易决策的论据可追溯性由 `evidence_refs` 结构化引用支撑，使 judge 可核对「决策论据 → 来源」而非仅凭自由文本推断。
## Requirements
### Requirement: 交易决策论据结构化引用

系统 SHALL 让 Trader 的决策输出包含结构化论据引用 `evidence_refs`：每条引用含 `claim`（论据）与 `source`（来源，枚举 technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager）。Trader prompt SHALL 强制「reasoning 中的每条例据对应一条 evidence_ref，且数值与来源一致」，使决策论据可被机器/评估器核对。

#### Scenario: 决策输出带论据引用

- **GIVEN** Trader 基于分析师报告做出决策
- **WHEN** 输出 TradeDecision
- **THEN** JSON SHALL 包含 `evidence_refs` 列表（每项 `{claim, source}`）
- **AND** `reasoning` 的主要论据 SHALL 能在 `evidence_refs` 中找到对应项

#### Scenario: 解析与序列化兼容

- **WHEN** 下游（risk_judge、报告生成、judge 变量提取）消费 TradeDecision
- **THEN** `evidence_refs` SHALL 被 Pydantic 解析并随 `_serialize_decision` 输出
- **AND** 既有字段（action/confidence/reasoning/position_size 等）行为不变

#### Scenario: Risk Judge 回显引用

- **GIVEN** Risk Judge 与 Trader 共用 TradeDecision schema，且 judge 变量 `trade_decision` 取 `final_trade_decision`（Risk Judge 输出）
- **WHEN** Risk Judge 输出最终决策
- **THEN** 采纳自交易方案的论据 SHALL 原样保留其 `evidence_refs`（claim 与 source 不变）
- **AND** SHALL 不虚构来源；无可对应来源的论据可不引用（`evidence_refs` 允许为空数组）

### Requirement: decision_grounding 评估

系统 SHALL 在 decision_grounding judge 中输入 TradeDecision 的 `evidence_refs`，并让 judge 可核对「决策论据是否在对应 source 中有出处」。judge 输入 `trade_decision` SHALL 包含 evidence_refs；`analyst_reports` 输入 SHALL 保留关键数值（不被摘要抹掉核对所需信息）。

#### Scenario: 有引用可核对

- **GIVEN** TradeDecision 含 evidence_refs（如 `{claim: "ROE 3.4%", source: "fundamental"}`）
- **WHEN** 运行 decision_grounding judge
- **THEN** judge SHALL 按「evidence_refs 的 claim 与 source 是否对得上、reasoning 是否全部有引用」给分
- **AND** 全部对得上 → 高分（4-5）；source 缺失或数值不符 → 低分（1-2）

#### Scenario: 无引用降级

- **WHEN** TradeDecision 无 evidence_refs（旧格式/解析失败）
- **THEN** judge SHALL 按原 rubric 从自由文本推断（不因缺字段报错）

### Requirement: 确定性评估器

系统 SHALL 提供零 token 成本的确定性评估器，对结构化 / 可重算维度打分，可进 CI、可重复执行。至少包含 `section_coverage`（必备章节覆盖率）与 `ticker_match`（标的解析正确性）；已有 `citation_pass` 同属此类。确定性评估器 SHALL NOT 调用 LLM。

#### Scenario: section_coverage 评估

- **GIVEN** Dataset item 的 `expected_output.must_cover` 列出必备章节（如 `["偿债能力", "盈利能力", "技术面", "风险提示"]`）
- **WHEN** 运行 section_coverage 评估器
- **THEN** SHALL 返回 `{name: "section_coverage", value: <0-1 覆盖率>, comment: <缺失章节或 null>}`
- **AND** 章节命中 SHALL 经同义词词典匹配（非裸字符串 `in`），覆盖中文表述差异

#### Scenario: ticker_match 评估

- **GIVEN** `expected_output.ticker` 指定预期标的代码
- **WHEN** 运行 ticker_match 评估器
- **THEN** SHALL 返回 `{name: "ticker_match", value: 1.0 | 0.0}`

#### Scenario: expected 缺省时跳过

- **GIVEN** item 无 `must_cover` 或无 `ticker`
- **THEN** 对应评估器 SHALL 返回 null（不计入该维度），不报错

#### Scenario: 不调用 LLM

- **WHEN** 确定性评估器执行
- **THEN** SHALL NOT 发起任何 LLM 调用

### Requirement: LLM-as-Judge 评估器与 rubric 标准

系统 SHALL 提供 LLM-as-Judge 评估器，对主观质量维度按 rubric 打分，至少包含 `report_relevance`（报告切题度）、`debate_quality`（辩论实质交锋）、`decision_grounding`（决策论据前文支撑）、`consistency`（跨层结论一致性）。每个 Judge SHALL 由明确 rubric 驱动，输出 JSON `{score, reason}`，裁判模型 SHALL 使用 `deepseek-chat`（非生成模型），裁判调用 SHALL 出现在 Langfuse trace 中并以 `langfuse-llm-as-a-judge` 环境标记独立核算成本。rubric SHALL 显式声明"不以长度论优劣"以抑制冗长偏置。

#### Scenario: report_relevance 评估

- **GIVEN** 用户查询 `{{query}}` 与最终报告 `{{report}}`
- **WHEN** 运行 report_relevance Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 完全切题，1 = 完全答非所问）
- **AND** 输出 JSON `{score, reason}`

#### Scenario: debate_quality 评估

- **GIVEN** 辩论记录 `{{debate_history}}`（依赖 delta `agent-trace-content-fidelity` 的 span 内容保真）
- **WHEN** 运行 debate_quality Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 双方逐条交锋且引证据，1 = 单方输出或空洞）

#### Scenario: decision_grounding 评估

- **GIVEN** 分析师结论 `{{analyst_reports}}`、辩论结论 `{{research_manager_decision}}`、交易决策 `{{trade_decision}}`
- **WHEN** 运行 decision_grounding Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 决策论据均有前文出处，1 = 与前文矛盾或无中生有）

#### Scenario: consistency 评估

- **GIVEN** 各层结论 `{{analyst_reports}}` / `{{research_manager_decision}}` / `{{risk_judgment}}` / `{{fund_manager_decision}}` / `{{report_conclusion}}`
- **WHEN** 运行 consistency Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 各层完全一致，1 = 明显自相矛盾）
- **AND** 特别检查 Fund Manager 结论与 Risk Judge 裁决的一致性、报告结论与分析师章节的一致性

#### Scenario: Judge 输出解析失败容错

- **WHEN** Judge 返回非 JSON 或解析失败
- **THEN** SHALL 重试一次；仍失败则该维度记 score=null
- **AND** 不阻塞实验，但计入 judge 失败率

#### Scenario: 裁判成本独立核算

- **WHEN** Judge 调用发起
- **THEN** Langfuse trace 的 generation SHALL 标 `langfuse-llm-as-a-judge` 环境
- **AND** 成本在 Dashboard 可独立查看

### Requirement: 评估 Dataset 与覆盖矩阵

系统 SHALL 维护一个评估 Dataset（命名如 `a-share-analysis-v1`），含 15-20 条覆盖矩阵用例（deep 典型 5-6 / deep 边界 2-3 / quick 3-4 / follow_up 2-3 / 意图澄清 1-2）。每条 item SHALL 含 `input`（query / mode / session_id）与 `expected_output`（仅断言结构性字段，不断言时效数值）。Dataset SHALL 可从历史 trace 捞取并幂等重建。

#### Scenario: Item Schema

- **WHEN** Dataset item 定义
- **THEN** `input` SHALL 含 `query`、`mode`（deep/quick/follow_up）、可选 `session_id`
- **AND** `expected_output` 可含 `ticker`、`must_cover`、`should_clarify`，均为可选
- **AND** `metadata` 含 `category` 与 `source`

#### Scenario: 幂等建库

- **WHEN** `dataset_seed.py` 重复执行
- **THEN** SHALL 不产生重复 item（以 input.query + mode 为去重键）
- **AND** 已存在 item 不被覆盖

#### Scenario: expected 不含时效数值

- **GIVEN** 某 deep 典型 case
- **THEN** `expected_output` SHALL NOT 含具体财务数值（如净利润 X 亿）
- **AND** 只含结构性断言（章节、ticker）

### Requirement: 实验回归工作流

系统 SHALL 提供 `evals/` 目录（与 src 平级，不侵入业务代码）与 `run_experiment` 入口，对全 Dataset 跑一遍，关联所用 prompt 版本，产出可对比基线的实验结果。实验 SHALL 支持"改 prompt / 模型 → 跑 → 对比基线 → 决策"闭环。`run_experiment`（经 Langfuse dataset）SHALL 是实验的唯一执行入口：不提供绕过 Langfuse 的本地循环降级；Langfuse 未配置/不可达时，实验入口 SHALL 显式报错并给出非零退出码，不得静默产出不可对比的分数。

#### Scenario: run_experiment 一键执行

- **WHEN** 执行 `evals/run.py "<实验名>"`
- **THEN** SHALL 对 Dataset 全量 item 跑 `run_analysis_task`
- **AND** 对每个 item 应用全部确定性 + Judge 评估器
- **AND** 产出含各 Score 均值与 per-item 明细的结果表

#### Scenario: 无 Langfuse 时显式报错

- **WHEN** 执行实验且 Langfuse 未配置或不可达
- **THEN** SHALL 打印明确错误（说明需要配置 Langfuse）并以非零退出码终止
- **AND** SHALL NOT 以本地循环降级产出分数

#### Scenario: prompt 版本关联

- **WHEN** 实验运行
- **THEN** SHALL 经 `langfuse.get_prompt(name, label="production")` 取 prompt
- **AND** prompt 名与版本记到 trace，UI 可回答"哪个 prompt 版本分数高"

#### Scenario: 业务代码零侵入

- **GIVEN** `evals/` 目录存在
- **THEN** 业务代码（`src/finance_agent/`）SHALL NOT 因评估被修改
- **AND** `evals/` 仅通过既有 graph 入口调用系统

### Requirement: Judge 校准门禁

Judge 评估器 SHALL NOT 在未校准情况下用于线上决策（如阻塞 PR）。上线前 SHALL 经 Annotation Queue 人工按同一 rubric 打分，judge 与人工一致性 ≥ 80% 方可定稿 rubric；定稿后每月抽检一次防漂移。

#### Scenario: 上线前校准

- **WHEN** 首版 rubric 完成、首轮实验产出
- **THEN** SHALL 抽 20-30 条进 Annotation Queue 人工打分（NUMERIC 1-5）
- **AND** judge 分与人工分一致性 < 80% 时 SHALL 调整 rubric 措辞并重校准
- **AND** 一致性 ≥ 80% 方可定稿

#### Scenario: 系统性偏置检测

- **WHEN** 校准发现 judge 系统性偏高 / 偏低（如对长报告偏宽松）
- **THEN** SHALL 在 rubric 强化对应措辞后重跑

#### Scenario: 月度抽检

- **GIVEN** rubric 已定稿上线
- **THEN** 此后每月 SHALL 抽检一次 judge 与人工一致性
- **AND** 漂移超标时触发 rubric 迭代

### Requirement: 线上托管 Evaluator

第二阶段，系统 SHALL 在 Langfuse 服务端配置线上托管 Evaluator，与线下实验用同一套 rubric 与裁判模型，按采样率（初值 10-20%）对生产 trace 自动评估，结果作为 Monitors 告警信号。quick 模式无辩论，仅跑 `report_relevance`。

#### Scenario: 采样评估

- **GIVEN** 线上 trace 产生
- **WHEN** 命中采样率
- **THEN** 托管 Evaluator SHALL 按同 rubric 自动跑 Judge
- **AND** Score 附着到该 trace

#### Scenario: 模式过滤

- **GIVEN** trace 的 `mode=quick`
- **THEN** 托管 Evaluator SHALL 仅跑 `report_relevance`，跳过 `debate_quality`

#### Scenario: 漂移告警

- **WHEN** 某 Judge Score 均值在窗口内骤降
- **THEN** Monitors SHALL 触发告警（webhook）

### Requirement: 断言级校验基准集

系统 SHALL 维护断言级校验基准集（claim benchmark）：从历史报告抽样 30-50 份，每份抽取 20-30 条 claim，人工标注每条 claim 的应有裁决（PASS / FAIL / UNVERIFIABLE）。标注 SHALL 双人背对背进行、分歧仲裁，并报告一致性系数（Cohen's κ）。基准集 SHALL 随生产 bad case 滚动补库，SHALL NOT 一次建成后冻结。

#### Scenario: 基准集构建

- **WHEN** 构建或扩充校验基准集
- **THEN** 每条 claim SHALL 有两名标注者的独立标注与仲裁后的最终标签
- **AND** 数据集元信息 SHALL 记录标注者一致性 κ 与版本号

#### Scenario: 滚动补库

- **WHEN** 生产中发现校验器误判的 bad case（人工复核确认）
- **THEN** 该 claim SHALL 以人工裁决为标签补入基准集下一版本

### Requirement: 校验器准度测量与门禁

系统 SHALL 提供校验器准度测量：对基准集运行 `verify_claims`，输出整体 Precision / Recall / F1，以及两个对抗子集的分项召回——(a) 擦边子集：stated_value 在真值 ±5% 以内的对抗 claim；(b) hedged 措辞子集：含"约""可能""接近"等模糊措辞的 claim。校验器整体 F1 ≥ 0.90 为可信门禁；擦边子集召回 SHALL 单独显式披露（不设硬门禁），以暴露近边界盲区。

#### Scenario: 准度达标

- **GIVEN** 基准集标注完成
- **WHEN** 运行准度测量
- **THEN** 报告 SHALL 含整体 P/R/F1（带 95% CI）与两个对抗子集的分项召回
- **AND** 整体 F1 ≥ 0.90 时校验器准度状态为"可信"，否则其下游 FAIL 判定 SHALL 在评估报告中标注"校验器自身准度未达标"

#### Scenario: 擦边盲区披露

- **WHEN** 生成准度报告
- **THEN** 擦边子集召回 SHALL 单独成行披露，SHALL NOT 被整体指标掩盖

### Requirement: 实验对比统计显著性

`run_experiment` 的基线对比 SHALL 使用配对 bootstrap（B=10,000，按 dataset item 重采样）报告差值的 95% 置信区间。当 CI 含 0 时，结论 SHALL 只能表述为"无显著差异"，SHALL NOT 用语义化措辞包装点估计差异。本条适用于全部确定性评估器与 judge 分数的对比报告。

#### Scenario: 显著改进

- **GIVEN** 新 prompt 版本与基线各跑完全量 dataset
- **WHEN** 分数差值的 95% CI 不含 0 且为正
- **THEN** 报告 SHALL 判定"显著改进"并给出 CI 区间

#### Scenario: 差异不显著

- **WHEN** 分数差值的 95% CI 含 0
- **THEN** 报告 SHALL 输出"无显著差异"，并 SHALL NOT 出现"略有提升""整体更好"等无统计支撑的结论性措辞

### Requirement: 数据对齐消融实验

系统 SHALL 支持数据对齐消融：构造三个架构变体——(a) 单分析师直出、(b) 分析师 + Bull/Bear 辩论、(c) 完整 5 层——所有变体接收**完全相同**的 state 快照（fetch_data / compute_metrics 输出重放），仅 Agent 编排不同。每变体 × 每标的 SHALL 重复运行 3 次取中位数。消融报告 SHALL 以 citation_pass 率与 judge 分数（带 CI）衡量各层增量价值，SHALL NOT 用单变体单次运行下结论。

#### Scenario: 变体输入对齐

- **WHEN** 执行消融实验
- **THEN** 三个变体的数据输入 SHALL 来自同一 trace 的 state 快照重放，差异只可归因于编排架构

#### Scenario: 消融结论

- **WHEN** 消融完成
- **THEN** 报告 SHALL 给出每个新增层级的增量效果及 95% CI
- **AND** 对 CI 含 0 的层级，报告 SHALL 明确标注"该层价值未获统计支持"，供成本裁剪决策参考

### Requirement: 基准集 v1.1 构造规则

校验基准集 v1.1 SHALL 重构 near_miss 子集：篡改幅度改为 ±{0.3%, 0.5%, 0.7%, 1%} 四档（探容差边界而非远离边界），且其中 50% 为 should_pass 样本（篡改幅度在容差内，标签为 PASS），使子集同时测量漏检与误报。v1.1 SHALL 新增 semantic_mismatch 子集：数值与 field_ref 正确但术语或期次张冠李戴（如毛利率写作净利率、年报值描述为季度值），标签为 FAIL。子集检出率 SHALL 在准度报告中单独披露。

#### Scenario: 边界双向探测

- **WHEN** 生成 v1.1 near_miss 子集
- **THEN** 样本覆盖容差两侧（0.3%/0.5% 档多为 should_pass，0.7%/1% 档多为 should_fail）
- **AND** 报告分别披露"过线检出率"与"线内误报率"，不接受单一汇总检出率

#### Scenario: 语义子集验收新规则

- **GIVEN** 术语一致性校验规则已上线
- **WHEN** 对 semantic_mismatch 子集运行准度测量
- **THEN** 该子集检出率 SHALL ≥ 90% 并在准度报告中单独成行

### Requirement: 覆盖率纳入实验指标

run_experiment 的实验报告 SHALL 增加 `citation_coverage` 指标（按 dataset item 聚合均值与 95% CI），与 citation_pass 并列展示；覆盖率变化的显著性判断沿用配对 bootstrap 契约。

#### Scenario: 实验报告含覆盖率

- **WHEN** 对比两个 prompt 版本的实验结果
- **THEN** 报告 SHALL 含 citation_coverage 的均值差与 CI，CI 含 0 时表述为"无显著差异"

### Requirement: judge rubric 扩展语义核对

decision_grounding judge 的 rubric SHALL 扩展：核对 interpretation/报告表述中的指标术语、期次、方向与所引用数值的语义一致性（如数值下降却表述"改善"）。rubric 变更 SHALL 递增版本号，并按 Judge 校准门禁契约重新校准（与人工一致性 ≥80%）后方可上线。

#### Scenario: 解读失当被扣分

- **GIVEN** 报告将行业垫底的 45.2% 毛利率表述为"行业领先"，且 evidence_refs 指向该值
- **WHEN** 运行 decision_grounding judge
- **THEN** judge SHALL 按 rubric 对解读失当扣分（不得仅因数值有出处给高分）

