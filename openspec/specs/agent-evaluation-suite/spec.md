# agent-evaluation-suite Specification

## Purpose
TBD - created by archiving change add-toolcall-evaluation. Update Purpose after archive.
## Requirements
### Requirement: 工具调用轨迹提取

评估链路 SHALL 从 Langfuse trace 提取工具调用序列（工具名/参数/耗时/成败/重试次数）作为评估输入。

#### Scenario: 轨迹提取

- **WHEN** 评测样本为 quick 模式 trace 且含工具调用
- **THEN** 输出结构化调用序列，含失败与重试标注

### Requirement: 工具调用评估维度

工具选择正确性维度的合法工具集合 SHALL 从权威工具注册（`finance_agent.tool_registry.AGENT_TOOL_NAMES`）派生，评估器 SHALL NOT 各自硬编码一份允许集；`agent_factory` 注册工具名 SHALL 引用同一注册表常量。允许集 SHALL 仍可被评估调用方覆盖（如历史快照评估），但默认值 SHALL 与当前注册表一致。

(Previously: 允许集在 `evals/toolcall/measure.py` 硬编码 `DEFAULT_ALLOWED_TOOLS`，与 agent 实际工具注册可能漂移。)

#### Scenario: 默认与注册表一致

- **WHEN** 评估器使用默认允许集
- **THEN** 默认允许集 SHALL 等于 `tool_registry.AGENT_TOOL_NAMES`
- **AND** agent_factory 注册的工具名 SHALL 均 ∈ 注册表（注册表为准，防止评估漏注册）

#### Scenario: 覆盖保留

- **WHEN** 调用方显式传入 allowed 集合（历史快照/特定场景）
- **THEN** 以显式值生效，覆盖不改变注册表

#### Scenario: 合法集合断言

- **WHEN** 样本声明了合法工具集合且实际调用落在集合内
- **THEN** 工具选择维度通过，不因与 golden 序列不同而误判失败

#### Scenario: 循环调用检测

- **WHEN** 同一工具以相同参数连续调用超过配置上限
- **THEN** 调用效率维度扣分并在报告标注

### Requirement: 工具调用门禁

工具调用维度 SHALL 纳入评测门禁（回归阈值），@live nightly 防漂移。

#### Scenario: 回归拦截

- **WHEN** 工具调用维度均分跌破基线阈值
- **THEN** 门禁失败并输出退化样本清单

### Requirement: 事实性 claim 抽取

评估链路 SHALL 从最终报告抽取可验证 claim（数值型：价格/涨跌幅/财务指标；事实型：事件/日期/主体）。

#### Scenario: claim 抽取

- **WHEN** 评测样本含最终报告文本
- **THEN** 输出结构化 claim 列表，每条标注类型与文中位置

### Requirement: 证据校验与幻觉率

系统 SHALL 将 claim 对照证据源（K 线/财报真实数据 + 检索内容）判定 supported/contradicted/unverifiable；`hallucination_rate` = contradicted / 可验证 claim 总数，unverifiable 单列不进分子。

#### Scenario: 矛盾识别

- **WHEN** 报告中数值 claim 与真实数据矛盾（超出容差）
- **THEN** 计为 contradicted 并计入幻觉率分子

#### Scenario: 合理推断不惩罚

- **WHEN** claim 无法从证据源证实亦不矛盾
- **THEN** 计为 unverifiable 单列，不影响幻觉率

### Requirement: 幻觉率门禁

幻觉率上限 SHALL 纳入评测门禁并 nightly 追踪趋势。

#### Scenario: 超限拦截

- **WHEN** hallucination_rate 超过配置上限
- **THEN** 门禁失败并输出 contradicted claim 清单

### Requirement: 性能度量采集

评估链路 SHALL 从 Langfuse trace 聚合每次分析的端到端时延、节点时延分解、token 用量与折算成本，quick/deep 分开统计；模型单价表配置化。

#### Scenario: 度量聚合

- **WHEN** 评测运行完成
- **THEN** 报告含性能一节：两种模式的时延/token/成本汇总与节点分解

### Requirement: 基线对比与回归门禁

系统 SHALL 在 docs/evals/ 维护性能基线档案，评测对比基线；时延或成本超基线配置百分比即告警或失败。

#### Scenario: 回归拦截

- **WHEN** 端到端时延或成本超基线阈值
- **THEN** 门禁按配置告警或失败，报告标注退化维度

### Requirement: 趋势追踪

nightly 运行 SHALL 沉淀性能时序数据，识别单次不超阈值但趋势向上的缓慢劣化。

#### Scenario: 趋势识别

- **WHEN** 连续 N 轮（配置化）指标单调劣化且累计幅度超阈值
- **THEN** 报告标注趋势告警，即使单轮未触发门禁

### Requirement: 在线 hosted evaluator

系统 SHALL 对生产 trace 启用 Langfuse managed evaluator（采样率配置化，默认 10%），维度对齐离线评测口径；自托管版本不支持时降级为轮询脚本方案。

#### Scenario: 采样打分

- **WHEN** 生产 trace 到达且命中采样
- **THEN** hosted evaluator 输出分数，与离线评分入同一分数命名空间并可按来源区分

### Requirement: 口径对齐验证

系统 SHALL 抽样比对 hosted 与离线 judge 对同一 trace 的打分差异，差异超阈值时告警。

#### Scenario: 口径漂移告警

- **WHEN** 同 trace 两套打分 MAE 超配置阈值
- **THEN** 报告标注口径漂移，提示统一裁判口径

### Requirement: 在线质量告警

hosted 均分跌破阈值 SHALL 触发告警（Langfuse webhook 或轮询脚本）；evaluator 模板作为 prompt 纳入版本管理与部署纪律。

#### Scenario: 均分告警

- **WHEN** 滑动窗口内 hosted 均分低于配置阈值
- **THEN** 产生告警并输出低分 trace 清单

### Requirement: 人工标注工具

系统 SHALL 提供标注脚本：从 Langfuse 抽样 trace 导出评判表（维度 × 人工 1-5 分），支持多轮标注与仲裁，样本集落 tests/fixtures/。

#### Scenario: 抽样导出

- **WHEN** 运行标注导出脚本并指定抽样规模与模式（quick/deep）
- **THEN** 生成含 trace 摘要与空人工评分列的标注表

### Requirement: judge-人工一致性指标

系统 SHALL 计算 judge 分 vs 人工分的 Spearman 相关、MAE、方向一致率，输出校准报告至 reports/。

#### Scenario: 一致性报告

- **WHEN** 标注完成并运行一致性计算
- **THEN** 报告给出三项指标，低于配置阈值时标记需修订 judge prompt

### Requirement: 校准触发与归档

judge prompt 变更后 SHALL 必跑一致性校准；校准结论归档至 docs/evals/。

#### Scenario: 变更后强制校准

- **WHEN** judge prompt 经部署管线发布新版本
- **THEN** 下一轮评测强制附带一致性校准，结论归档

### Requirement: 评估材料优先展示分析师可读结论

评估材料（judge 输入变量 `analyst_reports` 的拼装、人工标注导出表的 agent 摘要）SHALL 优先使用分析师报告的 `plain_conclusion`（普通人可读的结论+解释）；旧 trace 报告对象无该字段时 SHALL 回退现状（`summary` 拼贴），不得报错或中断评估。评估材料 SHALL NOT 以「正文前 N 字符」截取的方式充当该层摘要（与原文重复、无信息量）。

#### Scenario: 新报告展示可读结论

- **GIVEN** 分析师报告对象含非空 `plain_conclusion`
- **WHEN** 拼装 analyst_reports judge 变量或生成标注材料 agent 摘要
- **THEN** 该 agent 的展示文本 SHALL 取自 `plain_conclusion`
- **AND** `summary` 不再作为该 agent 的默认展示文本

#### Scenario: 旧 trace 回退

- **GIVEN** 分析师报告对象缺 `plain_conclusion`（旧版本产出）
- **WHEN** 拼装评估材料
- **THEN** SHALL 回退使用 `summary`（或 `conclusion`），不报错、不中断评估

#### Scenario: 禁止截取式摘要

- **WHEN** 生成人工标注材料
- **THEN** 评估材料 SHALL NOT 用「正文前 N 字符」充当该层摘要
- **AND** 分析师节以「各 agent 的 plain_conclusion（或回退 summary）」分行展示

### Requirement: 报告结论 judge 变量取分析综合

judge 变量 `report_conclusion` SHALL 优先取 `state["focus_summary"]`（report 节点无条件生成的研究聚焦综合摘要）；该字段缺失时（历史 trace）SHALL 回退现有 `extract_conclusion(final_report)` 提取。consistency 维度材料中【最终报告结论章节】的语义 SHALL 因此为「分析综合结论」，而非「基金经理审批复述」。

#### Scenario: 新 trace 取研究聚焦

- **WHEN** trace 的 state 含非空 `focus_summary` 且构建 consistency judge 变量
- **THEN** `report_conclusion` SHALL 等于 `focus_summary` 文本
- **AND** SHALL NOT 为「基金经理决策」章节的复述

#### Scenario: 历史 trace 无 focus_summary 时回退

- **WHEN** trace 的 state 无 `focus_summary` 字段
- **THEN** `report_conclusion` SHALL 回退为 `extract_conclusion(final_report)` 的提取结果（现行行为）

### Requirement: 研究聚焦无条件生成

report 节点 SHALL 无条件生成研究聚焦综合摘要（LLM），写入 `state["focus_summary"]`；focus 为空时 SHALL 使用固定提示词（不带关注点引导）综合各层产出。研究聚焦的生成 SHALL NOT 依赖 focus 是否非空。

#### Scenario: focus 为空仍生成聚焦摘要

- **WHEN** 用户未提供 focus 且 report 节点运行
- **THEN** state SHALL 含非空 `focus_summary`（基于各层产出的通用综合摘要）
- **AND** final_report SHALL 含「研究聚焦」章节

#### Scenario: 聚焦摘要仅基于各层材料

- **WHEN** 生成研究聚焦摘要
- **THEN** 提示词 SHALL 约束摘要仅基于所提供各层材料组织，不引入材料外数值或推测（与现行 `_build_focus_summary` 约束一致）

### Requirement: report judge 变量结构化拼装

deep 报告的 judge 变量 `report` SHALL 由结构化拼装构成（研究聚焦 + 各分析师摘要 + RM 结论 + 交易决策要点 + FM 决策），SHALL NOT 对 final_report 全文做整体 head/tail 截断；拼装内容 SHALL 剔除图片 markdown 引用（judge 无法读取本地图片，路径为纯噪声）。历史实证：报告全文约 2 万字符，4096 字节头尾截断后 judge 仅见图表路径与审批章（18933 字节分析内容被挖），judge 从章节标题幻觉推断「全面覆盖」恒给 5 分——report_relevance 恒 5 分天花板由此而来。

#### Scenario: 拼装变量含可读分析内容

- **WHEN** deep 管线构建 report_relevance 的 judge 变量
- **THEN** 变量 SHALL 包含研究聚焦与各分析师摘要的可读文本
- **AND** 变量 SHALL NOT 包含 `![…](本地路径)` 形式的图片引用

#### Scenario: 幻觉评分输入条件消除

- **WHEN** judge 评估 report_relevance
- **THEN** 其输入 SHALL 含足够判断「是否回答用户查询」的实质分析文本（非标题与路径集合）

### Requirement: decision_grounding judge 变量含辩论记录

decision_grounding 的 judge 输入 SHALL 包含多空辩论记录（`{{debate_history}}`，按消息边界截断）：`TradeDecision.evidence_refs` 的 source 枚举包含 `debate_bull`/`debate_bear`，rubric 要求逐条核对 claim 在对应 source 中找到出处——要求核对一个未提供的材料自相矛盾。material 标注配置（DIMENSION_SECTIONS）SHALL 同步补充【多空辩论记录】节。rubric 变更 SHALL 递增版本号并对 decision_grounding 已评 trace 重评。

#### Scenario: debate 来源的 claim 可核对

- **WHEN** 交易决策的 evidence_refs 含 `source: "debate_bear"` 的 claim 且 judge 评估 decision_grounding
- **THEN** judge 输入中 SHALL 存在该轮辩论发言的内容（含论点骨架），使 claim 出处可核对

#### Scenario: 标注材料同步含辩论节

- **WHEN** 导出 decision_grounding 维度的标注材料
- **THEN** 材料小节 SHALL 含【多空辩论记录】（与 judge 输入同口径）

### Requirement: decision_grounding judge 变量含裁决证据基础

decision_grounding 评估的交易决策取 `final_trade_decision`（Risk Judge 裁决，回退 `trader_plan`）。Risk Judge 在三方风险辩论之后裁决，其理由建立在风控指标与风险辩论上——judge 输入 SHALL 包含【风控指标】（`{{risk_metrics}}`，人读格式：最大回撤/年化波动率/VaR(95%)/beta 等）与【风险辩论记录】（`{{risk_debate_history}}`，按消息边界截断，含 aggressive/conservative/neutral 标签）；rubric 的 source 枚举 SHALL 含 `risk_aggressive`/`risk_conservative`/`risk_neutral`/`risk_metrics`。material 标注配置 SHALL 同步补充两节。rubric 变更 SHALL 递增版本号（v6）。

依据：r1 复盘 8 条 decision_grounding 理由中 5 条判「风控数字（beta/VaR/回撤）无出处」、3 条判「中性方/保守方论据无出处」，四个 2 分的 judge 置信度均 ≤0.5——是材料缺口而非决策缺陷。

#### Scenario: 风控指标与风险辩论进入 judge 输入

- **WHEN** state 含 `risk_metrics` 与 `risk_debate_history` 且 judge 评估 decision_grounding
- **THEN** judge 输入 SHALL 含【风控指标】一行人读文本与【风险辩论记录】各方发言，使裁决中「beta 1.96」「中性方指出…」类论据可核对
- **AND** 二者缺失时变量为空串，维度不因此记 input_missing（核心变量仍是分析师结论与 RM 结论）

#### Scenario: 标注材料同步含两节

- **WHEN** 导出 decision_grounding 维度的标注材料
- **THEN** 材料小节 SHALL 含【风控指标】与【风险辩论记录】（与 judge 输入同口径）
