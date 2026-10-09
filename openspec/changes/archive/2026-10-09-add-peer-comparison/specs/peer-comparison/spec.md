# Delta for peer-comparison

## ADDED Requirements

### Requirement: 点名多标的对比请求识别

入口 Agent（deep 模式）SHALL 识别用户在同一输入中点名两只及以上明确标的的对比请求（如「对比 A 和 B」「A 和 B 哪个好」），并解析为唯一主标的 + 1–3 只对标股：以用户语义的被分析主体为主标的；无法判定语义核心时 SHALL 取点名顺序的第一只为主标的，并在应答中明确告知可更换主视角。对比请求 SHALL 以单次 `run_deep_analysis` 调用完成（主标的 + `peer_codes`），MUST NOT 为多标的串行或并行发起多条完整管线。主标的与对标股的名称 SHALL 先经 `search_stock` 解析为 6 位代码后再调用工具。

#### Scenario: 点名两只标的对比

- **GIVEN** 用户输入「对比一下贵州茅台和五粮液」
- **WHEN** 入口 Agent 完成意图分类
- **THEN** SHALL 以语义主体（或第一只）为主标的发起单次 `run_deep_analysis`，另一只为 `peer_codes`
- **AND** SHALL NOT 发起第二次完整管线调用

#### Scenario: 点名标的超过上限

- **GIVEN** 用户一次点名 4 只及以上标的
- **WHEN** 入口 Agent 解析对标股
- **THEN** 对标股 SHALL 截断至 3 只
- **AND** 应答 SHALL 告知截断结果与被舍弃的标的

#### Scenario: 主视角歧义告知

- **GIVEN** 对比请求无法从语义判定主标的
- **WHEN** 入口 Agent 发起分析
- **THEN** SHALL 以点名第一只为主标的
- **AND** 应答 SHALL 明确说明「已以 X 为主视角」，并告知回复可换另一只为主视角重跑

### Requirement: run_deep_analysis 对标股参数

`run_deep_analysis` 工具 SHALL 接受可选 `peer_codes` 参数（1–3 个 6 位 A 股代码），由入口 LLM 在识别对比意图后传入。无效代码（search_stock 解析失败或格式非法）SHALL 剔除后继续分析，并在应答中告知剔除结果；SHALL NOT 因单个无效对标股阻断主标的分析。HTTP 请求级闭包注入的 `peer_codes`（AnalyzeRequest 既有路径）SHALL 保留；LLM 显式传参与闭包并存时 SHALL 以 LLM 传参为准。

#### Scenario: LLM 传参生效

- **GIVEN** 入口 LLM 调用 `run_deep_analysis(stock_code="600519", peer_codes=["000858"])`
- **WHEN** 管线 initial_state 构建
- **THEN** `state.peer_codes` SHALL 为 `["000858"]`
- **AND** fetch 层 SHALL 触发同业抓取

#### Scenario: 无效对标股剔除

- **GIVEN** `peer_codes` 含一个无法解析的名称和一个合法代码
- **WHEN** 入口 Agent 处理参数
- **THEN** 合法代码 SHALL 进入管线，无效项 SHALL 被剔除
- **AND** 应答 SHALL 告知用户被剔除的标的，分析 SHALL 继续

#### Scenario: 显式传参优先于闭包

- **GIVEN** HTTP 请求闭包注入 `peer_codes=["A"]` 且 LLM 显式传参 `peer_codes=["B"]`
- **WHEN** 工具执行
- **THEN** 管线 SHALL 使用 `["B"]`

### Requirement: 同业指标格式化注入

compute 层 SHALL 提供同业指标格式化器：将 `state.peer_financials` 渲染为结构化文本材料（标的×指标对照表，主标的置于首行并标注），写入 `state.peer_comparison` 注入基本面分析师 context（替换现标志位占位，关闭 Issue #4）。请求未携带 `peer_codes` 时 SHALL 省略注入，与既有 optional 降级语义一致；对比请求成立但 `peer_financials` 全部降级为 None 时 SHALL 注入同业数据缺失声明（对齐「报告同业对比段呈现」R4）。财务字段组降级时 SHALL 在材料中以缺失标记如实呈现对应字段，MUST NOT 静默省略整列。

#### Scenario: 完整 peer 数据注入

- **GIVEN** `peer_financials` 含 2 只对标股的估值组与财务组字段
- **WHEN** compute 层执行格式化
- **THEN** `state.peer_comparison` SHALL 含三行（主标的 + 2 对标股）× 全字段的对照材料
- **AND** 基本面分析师 context SHALL 包含该材料

#### Scenario: 财务字段组降级如实标注

- **GIVEN** 对标股财务字段组抓取全失败、估值组成功
- **WHEN** 格式化器渲染材料
- **THEN** 对照材料 SHALL 含估值组字段
- **AND** 财务字段 SHALL 以缺失标记呈现（如「—」），MUST NOT 删除该列或虚构数值

#### Scenario: 无对标股不注入

- **GIVEN** 请求未携带 peer_codes
- **WHEN** compute 层执行
- **THEN** SHALL NOT 写入 `state.peer_comparison`
- **AND** 基本面分析师行为与现状一致

### Requirement: 报告同业对比段呈现

当同业材料注入存在时，基本面分析师产出与报告基本面章节 SHALL 包含同业对比段：主标的与各对标股的关键指标对照（估值组必有，财务组按可得呈现）+ 相对估值结论，并 SHALL 标注数据口径（行情快照时点 / 财务指标报告期）。对比段所有数值 SHALL 可溯源至注入材料（对齐 agent-prompt-contracts「摘要仅基于输入材料」），MUST NOT 引入材料外的同业数据。peer 数据缺失时报告对应位置 SHALL 以缺失声明呈现，MUST NOT 编造对比结论。

#### Scenario: 完整数据呈现对照表

- **GIVEN** 同业材料含完整估值组与财务组
- **WHEN** 报告基本面章节生成
- **THEN** SHALL 含主标的与各对标股的指标对照与相对估值结论
- **AND** SHALL 标注行情快照时点与财务指标报告期口径

#### Scenario: 对比段数值溯源

- **GIVEN** 报告含同业对比段
- **WHEN** 人工核验对照表数值
- **THEN** 每个数值 SHALL 能在注入材料（`state.peer_comparison`）中找到出处

#### Scenario: peer 缺失如实声明

- **GIVEN** 对比请求成立但同业抓取全部降级（`peer_financials` 为 None）
- **WHEN** 报告生成
- **THEN** 基本面章节 SHALL 含同业数据缺失声明
- **AND** MUST NOT 出现无数据支撑的对比结论
