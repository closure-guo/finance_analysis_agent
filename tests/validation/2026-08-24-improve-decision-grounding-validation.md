# 人工验证报告: improve-decision-grounding

**日期**: 2026-08-24
**验证人**: 开发管线（控制器 + SDD 审查）—— 非交互类纯后端变更，无真实浏览器人工抽查（project-workflow §5 触发条件不适用）
**关联 delta**: openspec/changes/improve-decision-grounding/
**E2E 门禁**: 不适用（纯后端：models + prompts + evals extract/judges，无前端 UI / SSE / 会话切换 / 状态流转）
**分支**: feat/add-report-export
**实现提交**: fd1260e（提案）→ 00422c9（计划+spec 修正）→ ba3d117（Task1）→ d63a0cc（Task2）→ 663e002（tasks 全勾）→ cc0b9c9（final review 修复）

## 验证结果

| 验证项 | 证据 | 结果 |
|---|---|---|
| TradeDecision.evidence_refs 解析（含/不含/None/畸形条目） | `tests/test_models.py::TestTradeDecisionEvidenceRefs`（7 用例，含 scrub 2 例） | ✅ |
| source 归一（别名/大小写/空白，未知值宽松保留） | `test_source_aliases_normalized` + `test_unknown_source_lenient` | ✅ |
| trader.md / risk_judge.md 强制 evidence_refs + 枚举漂移守卫 | `tests/test_trade_decision_prompts.py`（8 用例，含 `TRADE_EVIDENCE_SOURCES` 全量对比） | ✅ |
| risk_judge 上下文透传交易方案（pydantic 实例，含 evidence_refs）| `tests/nodes/test_risk.py::TestRiskContextCarriesTraderPlan`（final review F1 回归） | ✅ |
| judge 变量 trade_decision 含 evidence_refs；analyst_reports 保留 claims 数值 | `tests/evals/test_extract.py`（7 用例，含 `_format_claims` 5 分支直测） | ✅ |
| decision_grounding rubric 结构化核对 + 无引用降级 | `tests/evals/test_judges.py`（16 用例绿，含 rubric 文本断言） | ✅ |
| 全量回归 | `uv run pytest tests/ -m "not live" -q` → **1207 passed, 2 skipped, 8 deselected, 0 failed**（基线 1197 + 10 新增） | ✅ |
| 静态检查 | ruff：tracked 树全绿；mypy：delta 涉及文件（models/extract/judges/risk/_llm_utils）Success, no issues | ✅ |
| delta 校验 | `openspec validate improve-decision-grounding --strict` → valid | ✅ |
| 生产链路不回归 | TESTING=1 stub 全 5 层 graph 运行通过（final reviewer 实证）；report 渲染 / decision_log 持久化不受新字段影响 | ✅ |
| 双 review 门禁 | Task1/Task2 spec ✅ + quality Approved；最终全分支审查 2 个 Important 修复后复审 ✅ | ✅ |

## 遗留（archive 前待办）

1. **真实实验对比（delta 收益证据，可选但建议）**：重跑 langfuse evals，对比 decision_grounding 均值（基线 1.57/5）。期望 evidence_refs + rubric 对齐后显著提升；这是「决策论据可追溯性」主观项的人工验证，E2E/单测无法替代。数据源不可达时按 tasks.md 3.4 视为可选。
2. **LLM 实际输出合规性**：trader/risk_judge 是否真实产出结构良好的 evidence_refs（真模型行为，需 @live 或实验观察）。
3. 修复遗留：`scripts/` 未跟踪目录（`evals_gated_run.py` / `observe_langfuse_experiments.py` 11 个 ruff 错）属前 delta 工作产物，与本 delta 无关，未纳入提交（纳入 `docs/incidents/` 或后续清理任务处理）。

## 结论

- [x] 静态验证全部通过，实现完成，可进入实验验证/archive 前阶段
- [ ] 存在待验证项（真实实验对比），完成后可 archive

## 附: final review 修复的核心影响

审查发现并修复两处生产断链：① trader 的 pydantic `TradeDecision` 在 LangGraph state 不转 dict，`_build_risk_context` 原 `isinstance(plan, dict)` 判 False 导致 risk_judge 看不到交易方案（evidence_refs 无从回显）→ 已加 model_dump 分支；② `evidence_refs: null` 或畸形条目会 ValidationError 炸整条管线 → 已加 `_scrub_evidence_refs` before-validator。两者均为「LLM 输出抖动不炸管线」全局约束的必要实现。