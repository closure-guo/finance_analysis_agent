# Proposal: improve-decision-grounding

## Why

真实实验（2026-08-24，全链路就绪）8 条 deep 的 `decision_grounding` 平均 **1.57/5**（5 条 = 1.0 最低分）。judge 定义为「交易决策的论据是否有前文支撑」（`evals/judges.py:64-73`）。根因：

1. **trader 决策只有自由文本 `reasoning`**（`prompts/trader.md:11`），无结构化「论据 → 来源」引用。模型写理由时不显式锚定「这条依据来自技术分析师/辩论结论」，judge 无从核对出处；
2. **judge 能看到的前文被摘要化**：`_summarize_analyst_reports`（`evals/extract.py:50-73`）把分析师报告压成摘要、`_trunc` 截断——即使 trader 引用了正确来源，judge 看到的来源也残缺，判低分；
3. trader 的 `reasoning` 常含摘要里没有的数值（如精确 PE/ROE），judge 判「无中生有」。

## What Changes

- **trader 决策 JSON 增加 `evidence_refs` 字段**（结构化论据引用，改 `src/finance_agent/models.py::TradeDecision` + `prompts/trader.md`）：每条 = `{claim, source}`，`source` 枚举 `technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager`；prompt 强制「reasoning 的每条例据必须对应一条 evidence_ref，且数值必须与对应来源一致」。
- **judge 输入增强**：`evals/extract.py` 的 `trade_decision` 变量附上 `evidence_refs`；`analyst_reports` 摘要**保留关键数值**（或至少在 `trade_decision` 侧透传完整来源），使 judge 能实际核对引用是否成立。
- **judge rubric 微调**（可选）：在 rubric 中增加「若 evidence_refs 的 source 与 claim 数值可对上，判高分；source 缺失或对不上判低分」的显式规则，对齐 TradeDecision 新字段。

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**: `evaluation`（MODIFIED：decision_grounding judge 输入含 evidence_refs，规则对齐结构化引用）

## Impact

- **核心**：`models.py`（TradeDecision + evidence_refs）、`prompts/trader.md`（强制引用）、`evals/extract.py`（judge 变量透传）
- **注意**：`TradeDecision` 增加必填/可选字段影响解析（trader/risk_judge 共用该 schema，`_STUB_TRADE_DECISION` 也要补）；`_serialize_decision` 序列化新字段给 judge
- **收益**：把「决策论据可追溯性」从 judge 主观猜变成结构化可核对；预期 decision_grounding 从 1.57 显著提升
- **风险**：prompt 改动可能影响决策质量/格式；需回归既有 trade 决策测试与 evals 基线对比