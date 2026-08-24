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