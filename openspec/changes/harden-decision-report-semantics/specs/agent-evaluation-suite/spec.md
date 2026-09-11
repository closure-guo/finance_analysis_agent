# Delta for agent-evaluation-suite

## ADDED Requirements

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
