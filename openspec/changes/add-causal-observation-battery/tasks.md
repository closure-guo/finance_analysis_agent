# Tasks: add-causal-observation-battery

- [x] docs/evals/metrics.md §1 口径先行登记观测电池条目（三读数定义引用既有行、固定快照 digest、触发约定、不作层增量边界）——§1.8
- [x] 失败测试先行：观测驱动对固定快照 digest 不一致显式失败（复用快照核验既有实现，不静默混轮）
- [x] 观测驱动实现：材料腿（复用 family_b_materials）+ 三判定（复用 bear_grounding / family_b 判定）+ 汇总落盘（读数含分母行数与解析失败数、llm_calls 分腿申报）——evals/causal_ablation/observation.py
- [x] provisional 派生逻辑：rubric 版本 × 校准记录核验（CALIBRATION_REGISTRY），未过门读数标记且不与历史轮对照
- [x] CLI 入口（python -m evals.causal_ablation.observation）
- [ ] 首轮（第 1 轮）观测执行：runs.jsonl 追加行 + metrics.md 时间线登记（以 09-20 观测轮为第 0 轮基线对照）
- [x] 全量测试通过（uv run pytest：3118 passed / 2 skipped，2026-09-22）
