# Tasks: improve-decision-grounding

参考：`specs/evaluation/spec.md`（行为契约）。测试按 TDD「先红后绿」。

## 1. TradeDecision 模型 + prompt

- [x] 1.1 `models.py::TradeDecision` 新增 `evidence_refs: list[dict] = []`（每项 `{claim: str, source: str}`；source 枚举 technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager 用 Literal 或宽松 str + validator 归一）。TDD：解析含/不含 evidence_refs 的 JSON 均通过；非法 source 清洗或降级
- [x] 1.2 `prompts/trader.md` + `prompts/risk_judge.md`：输出示例加 `evidence_refs`；trader 要求「reasoning 每条例据对应一条引用、数值与来源一致」；risk_judge 要求「采纳自交易方案的论据原样保留引用、不虚构来源」（judge 变量 `trade_decision` 取自 `final_trade_decision`，risk_judge 不回显则 judge 无引用可核对）。TDD：prompt 文本断言（含 evidence_refs 示例与要求）
- [x] 1.3 `_llm_utils._STUB_TRADE_DECISION` 补 `evidence_refs: []`（stub 管线合法）。TDD：stub 决策可解析

## 2. 序列化 + judge 输入

- [x] 2.1 `evals/extract.py::_serialize_decision` 输出含 evidence_refs；`trade_decision` judge 变量透传。TDD：序列化含 evidence_refs、judge 变量含引用
- [x] 2.2 `_summarize_analyst_reports` 保留关键数值（或 trade_decision 侧附完整来源）：确保 judge 能核对 claim 数值。TDD：摘要不再抹掉数值断言
- [x] 2.3 `evals/judges.py` decision_grounding rubric 增加「evidence_refs 可核对 → 高分；缺失/不符 → 低分」规则。TDD：rubric 文本含新规则

## 3. 回归与验证

- [x] 3.1 `uv run pytest tests/ -m "not live"` 全绿（重点 test_models/trader 节点/evals extract/judges）
- [x] 3.2 `uv run ruff check` / `uv run mypy` 通过
- [x] 3.3 `openspec validate improve-decision-grounding` 通过
- [x] 3.4 提交

> 真实实验对比（可选，数据源可达时）：重跑 evals 对比 decision_grounding 均值（基线 1.57）——作为 delta 收益证据落 `tests/validation/`。