# Tasks: add-causal-observation-battery

- [x] docs/evals/metrics.md §1 口径先行登记观测电池条目（三读数定义引用既有行、固定快照 digest、触发约定、不作层增量边界）——§1.8
- [x] 失败测试先行：观测驱动对固定快照 digest 不一致显式失败（复用快照核验既有实现，不静默混轮）
- [x] 观测驱动实现：材料腿（复用 family_b_materials）+ 三判定（复用 bear_grounding / family_b 判定）+ 汇总落盘（读数含分母行数与解析失败数、llm_calls 分腿申报）——evals/causal_ablation/observation.py
- [x] provisional 派生逻辑：rubric 版本 × 校准记录核验（CALIBRATION_REGISTRY），未过门读数标记且不与历史轮对照
- [x] CLI 入口（python -m evals.causal_ablation.observation）
- [x] 首轮（第 1 轮）观测执行（2026-09-22，HEAD ec3122b）：grounding 0.049（4/82，vs 第 0 轮 0/79 回退待归因）/ B1 0.848（212/250）/ B2 0.082（122/1,487 全量首读）；runs.jsonl 追加第 30 行 + metrics.md 时间线登记（B2 跨口径披露已写入）
- [x] 全量测试通过（uv run pytest：3118 passed / 2 skipped，2026-09-22）
