## MODIFIED Requirements

### Requirement: decision_grounding 评估

系统 SHALL 在 decision_grounding judge 中输入 TradeDecision 的 `evidence_refs`，并让 judge 可核对「决策论据是否在对应 source 中有出处」。judge 输入 `trade_decision` SHALL 包含 evidence_refs；`analyst_reports` 输入 SHALL 保留关键数值（不被摘要抹掉核对所需信息）。rubric（v8 起）SHALL 显式声明归属判例：同一评判在多个来源（如 debate_bear 与 research_manager）均有原话时，evidence_refs 引用任一真实来源即合法，judge SHALL NOT 因未选「最早」或「主要」来源而按归属错安扣分。

#### Scenario: 有引用可核对

- **GIVEN** TradeDecision 含 evidence_refs（如 `{claim: "ROE 3.4%", source: "fundamental"}`）
- **WHEN** 运行 decision_grounding judge
- **THEN** judge SHALL 按「evidence_refs 的 claim 与 source 是否对得上、reasoning 是否全部有引用」给分
- **AND** 全部对得上 → 高分（4-5）；source 缺失或数值不符 → 低分（1-2）

#### Scenario: 无引用降级

- **WHEN** TradeDecision 无 evidence_refs（旧格式/解析失败）
- **THEN** judge SHALL 按原 rubric 从自由文本推断（不因缺字段报错）

#### Scenario: 多来源同判归属合法

- **GIVEN** evidence_refs 某条 claim（如「多方环比修复拐点论尚缺同比转正证据」）在 debate_bear 与 research_manager 的结论中均有原话
- **WHEN** 该条 source 标注为其中任一真实来源
- **THEN** judge SHALL 视为归属合法，SHALL NOT 扣分
- **AND** 仅当 claim 在所有被标来源中均无原话时，才按归属错安处理（降 1 档、不高于 4）

### Requirement: LLM-as-Judge 评估器与 rubric 标准

系统 SHALL 提供 LLM-as-Judge 评估器，对主观质量维度按 rubric 打分，至少包含 `report_relevance`（报告切题度）、`debate_quality`（辩论实质交锋）、`decision_grounding`（决策论据前文支撑）、`consistency`（跨层结论一致性）。每个 Judge SHALL 由明确 rubric 驱动，输出 JSON `{score, reason}`，裁判模型 SHALL 使用 `deepseek-chat`（非生成模型），裁判调用 SHALL 出现在 Langfuse trace 中并以 `langfuse-llm-as-a-judge` 环境标记独立核算成本。rubric SHALL 显式声明"不以长度论优劣"以抑制冗长偏置。rubric 版本号 SHALL 随判例或档位语义变更递增（v8 起：debate_quality v4、decision_grounding v8），并记录于 `RUBRIC_VERSIONS`。

judge 输入材料 SHALL 满足：debate_quality 的 `debate_history` SHALL 在原始辩论发言之前附骨架行——交锋覆盖统计（各方论点被回应数 N/M）与收敛信号摘要（第二轮起双方立场靠拢/共识点/核心分歧保留项）；consistency 的材料 SHALL 含【Trader 方案】节（TradeDecision 的 action / position_size / 价位与触发条件的结构化渲染），使「Trader 方案 → Risk Judge 裁决」是否静默推翻可核对。

#### Scenario: report_relevance 评估

- **GIVEN** 用户查询 `{{query}}` 与最终报告 `{{report}}`
- **WHEN** 运行 report_relevance Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 完全切题，1 = 完全答非所问）
- **AND** 输出 JSON `{score, reason}`

#### Scenario: debate_quality 评估

- **GIVEN** 辩论记录 `{{debate_history}}`（含交锋覆盖骨架行与收敛信号摘要；依赖 delta `agent-trace-content-fidelity` 的 span 内容保真）
- **WHEN** 运行 debate_quality Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 双方逐条交锋且引证据，1 = 单方输出或空洞）
- **AND** v4 起 5 分档 SHALL 执行判例：论点列表（R1/R2 标头）中任一条为纯定性表述（无数据/事实支撑的断言，含「历史上……」类无样本论据）即降 4，即使该回应其余部分数据密集

#### Scenario: decision_grounding 评估

- **GIVEN** 分析师结论 `{{analyst_reports}}`、辩论结论 `{{research_manager_decision}}`、交易决策 `{{trade_decision}}`
- **WHEN** 运行 decision_grounding Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 决策论据均有前文出处，1 = 与前文矛盾或无中生有）

#### Scenario: consistency 评估

- **GIVEN** 各层结论 `{{analyst_reports}}` / `{{research_manager_decision}}` / `{{trade_decision}}`（Trader 方案节）/ `{{risk_judgment}}` / `{{fund_manager_decision}}` / `{{report_conclusion}}`
- **WHEN** 运行 consistency Judge
- **THEN** SHALL 按 1-5 rubric 打分（5 = 各层完全一致，1 = 明显自相矛盾）
- **AND** 特别检查 Fund Manager 结论与 Risk Judge 裁决的一致性、Risk Judge 裁决相对 Trader 方案是否有未说明的方向/参数推翻、报告结论与分析师章节的一致性

#### Scenario: Judge 输出解析失败容错

- **WHEN** Judge 返回非 JSON 或解析失败
- **THEN** SHALL 重试一次；仍失败则该维度记 score=null
- **AND** 不阻塞实验，但计入 judge 失败率

#### Scenario: 裁判成本独立核算

- **WHEN** Judge 调用发起
- **THEN** Langfuse trace 的 generation SHALL 标 `langfuse-llm-as-a-judge` 环境
- **AND** 成本在 Dashboard 可独立查看
