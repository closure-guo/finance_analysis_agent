# 人工验证报告: agent-evaluation-suite

**日期**: 2026-08-12
**验证人**: [待填]
**关联 delta**: openspec/changes/agent-evaluation-suite/
**E2E 门禁**: 不适用(纯后端评估基建,非交互类变更,§2 判别)

## 验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 确定性评估器零 LLM | section_coverage/ticker_match 不调 LLM,同义词命中 | 单测锁定(test_deterministic_evaluators_never_call_llm 等 12 例) | ✅ |
| Judge rubric 契约 | 4 rubric 含 JSON 约束 + 不以长度论优劣 | 单测锁定(test_rubrics_have_json_constraint_and_no_length_bias) | ✅ |
| Judge 容错 | 非 JSON 重试一次后 score=None,不阻塞 | 单测锁定(test_parse_failure_retries_once_then_null) | ✅ |
| Dataset 幂等 | 重复 seed 0 created | 单测锁定(test_idempotent_on_rerun) | ✅ |
| 业务零侵入 | git diff 无 src/ 改动 | 全分支 diff 审查 | ✅ |
| seed 真实建库 | langfuse UI 可见 a-share-analysis-v1 16 条 | [待人工:配好 langfuse 后跑 `uv run python -m evals.dataset_seed`] | ⬜ |
| 基线实验 | `uv run python -m evals.run baseline-v1` 全 Dataset 跑通,产出 reports/evals/ JSON | [待人工:真 LLM,约 1-2 小时] | ⬜ |
| Judge 校准 | 抽 20-30 条人工打分,一致性 ≥ 80% | [待人工:用实验 JSON + Annotation Queue;校准报告回填本节] | ⬜ |
| judge 环境标记 | Langfuse 按 environment=langfuse-llm-as-a-judge 过滤可见裁判 generation | [待人工:实验后 UI 核对] | ⬜ |
| quick item trace 亲子链 | 真实 langfuse 跑批 quick item 时,LLM span 挂在 item trace 父节点下(Task 4 `_await_sync` contextvars 修复的验证) | [待人工:基线实验后 UI 核对 quick item trace 层级] | ⬜ |
| 托管 Evaluator | 按 evals/hosted_evaluator_setup.md 配置,采样 10-20% | [待人工:第二阶段,校准定稿后] | ⬜ |

## 异常记录
[待填]

## 结论
[x] 存在待人工确认项(seed/基线实验/校准/quick trace 亲子链/托管配置)
[ ] 全部通过,可 archive
