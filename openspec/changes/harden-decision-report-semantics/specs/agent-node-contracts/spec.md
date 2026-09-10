# Delta for agent-node-contracts

## ADDED Requirements

### Requirement: Fund Manager 操作性结论字段

`FundManagerDecision` SHALL 新增 `action`（枚举同 `TradeDecision.action`）与 `confidence`（0-1 浮点）可选字段；`decision` 为 `"approve"` 时两者 SHALL 必填（模型校验，缺失中断管线），`"reject"`/`"return"` 时 SHALL 允许为 None。FM 的 action 是对 Risk Judge 裁决后最终方案的操作定性，MUST NOT 被硬拦截为管线异常（与裁决方向相悖时交由报告展示与一致性评估披露）。

#### Scenario: approve 决策必含操作定性与置信度

- **WHEN** FM 输出 `decision` 为 `"approve"` 但缺少 `action` 或 `confidence`
- **THEN** `FundManagerDecision.model_validate` SHALL 抛出 ValidationError 中断管线（不静默降级）

#### Scenario: reject/return 允许无操作定性

- **WHEN** FM 输出 `decision` 为 `"reject"` 或 `"return"` 且不含 `action`/`confidence`
- **THEN** 校验 SHALL 通过（字段为 None），管线照常路由

#### Scenario: approve 的 action 与裁决方向相悖不硬拦截

- **WHEN** FM `decision` 为 `"approve"` 且 `action` 与 `final_trade_decision.action` 方向不同
- **THEN** 管线 SHALL 正常继续（保留 FM 仲裁权）
- **AND** 报告与 judge 材料中 SHALL 并排展示 FM action 与裁决 action，使矛盾可见

#### Scenario: FM 决策进 judge 变量

- **WHEN** `extract_judge_vars` 序列化 FM 决策
- **THEN** 变量文本 SHALL 包含 `action` 与 `confidence`（存在时），使 judge 与标注人无需从理由推断操作定性

### Requirement: 报告基金经理决策章节展示操作定性

report 节点拼装「基金经理决策」章节时，SHALL 在决策标注旁展示 FM 的 `action` 与 `confidence`（存在时），与裁决 action 并排，使「批准的是什么方案」直接可见。

#### Scenario: 报告展示 approve 的操作定性

- **WHEN** FM approve 且 `action`/`confidence` 非空
- **THEN** 「基金经理决策」章节 SHALL 同时呈现 FM action/confidence 与最终裁决 action
- **AND** 审批标注（审批通过/未通过审批/退回重评）SHALL 保留（ADR-0011 语义不变）

### Requirement: Research Manager 结构化评级输出

Research Manager SHALL 输出结构化 JSON：`reasoning`（多空概括与判断依据）、`rating`（看多/看空/中性枚举）、`confidence`（0-1）。JSON 键序 SHALL 为 reasoning 在前、rating 在后（保持「先推理后结论」的生成顺序）；消费端（state 结论字符串、报告章节、judge 变量）SHALL 由代码把 rating/confidence 前置到 reasoning 之前（倒金字塔展示）。JSON 解析失败时 SHALL 降级为现行自由文本行为（原文作 conclusion，rating/confidence 置 None），MUST NOT 中断管线。

#### Scenario: RM 结构化输出与结论前置

- **WHEN** RM 正常输出结构化 JSON
- **THEN** `state["research_manager_conclusion"]` SHALL 以「评级：<rating>（置信度 <confidence>）」行开头，reasoning 全文随后
- **AND** `state` SHALL 另存 `research_manager_rating` / `research_manager_confidence` 供战绩结算与 judge 变量直取

#### Scenario: 生成顺序保持先推理后结论

- **WHEN** RM prompt 模板定义 JSON 输出
- **THEN** reasoning 键 SHALL 位于 rating 键之前（LLM 按键序生成，推理先于结论）

#### Scenario: 解析失败降级不中断

- **WHEN** RM 输出无法解析为结构化 JSON
- **THEN** 管线 SHALL 以自由文本原文作为 conclusion 继续（rating/confidence 为 None）
- **AND** 降级 SHALL 可观测（parse_degraded 类标记，对齐分析师降级语义）

#### Scenario: Trader 上下文与 judge 变量自动前置

- **WHEN** Trader context 或 judge 变量 `research_manager_decision` 引用 RM 结论
- **THEN** 所见文本 SHALL 为评级前置后的拼装（无需各自解析原文）

### Requirement: 辩论交锋结构化引用

Bull/Bear 辩论 SHALL 以既有 `key_arguments` 为编号锚点建立显式交锋引用：辩论 context 中各历史发言 SHALL 以编号列出对方论点（如「对方(R1) 论点: ①…②…」）；`DebateMessage` SHALL 新增可选字段 `rebuttal_to: list[int]`（本轮回应的对方上一轮论点编号，首轮开场为空），辩论 prompt 要求 content 中逐条标注「回应对方N」；交锋覆盖率（被回应论点并集 / 对方论点总数）SHALL 可由代码直接计算（确定性指标，不依赖 judge）。风险辩论三方为同构扩展，SHALL 在 Bull/Bear 落地验证后跟进。

#### Scenario: context 呈现对方论点编号

- **WHEN** 构建第 2 轮辩论 context
- **THEN** 对方第 1 轮发言 SHALL 以「论点: ①…②…」编号形式呈现（取自 key_arguments）
- **AND** 辩论历史仍保留发言正文（编号行前置）

#### Scenario: rebuttal_to 结构化引用

- **WHEN** 辩论方输出第 2 轮及以后发言
- **THEN** `DebateMessage` SHALL 支携带 `rebuttal_to`（回应的对方论点编号列表）；`rebuttal_to` 为空 SHALL 不视为解析失败（首轮开场/纯补充立场时合法）

#### Scenario: 交锋覆盖率代码可算

- **WHEN** 一场辩论结束
- **THEN** 「对方论点被回应的比例」SHALL 可由各轮 `rebuttal_to` 并集直接计算（零 LLM 调用）
- **AND** 该覆盖率 SHALL 进入 debate_quality 的 judge 材料与评估记录（作为 judge 打分的确定性对照锚点）

#### Scenario: 引用曲解可检测

- **WHEN** 某轮发言的 content 标注「回应对方N」但所述与对方论点 N 原文明显不符（曲解/弱化）
- **THEN** judge 材料中 SHALL 并排呈现论点 N 原文与该轮回应，使曲解可被人工/judge 识别

