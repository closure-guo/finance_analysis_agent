# Tasks: agent-evaluation-suite

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出至 `docs/superpowers/plans/`，不在此处。

## 前置

- [x] delta `agent-trace-content-fidelity` 已落地（Judge 输入依赖 span 内容保真）

## 验收项

- [x] `evals/` 目录建立（与 src 平级），业务代码零侵入（git diff 确认未改 `src/finance_agent/`）
- [x] 确定性评估器 `section_coverage`（同义词词典匹配）+ `ticker_match` 落地，零 LLM 调用
- [x] 4 个 LLM-as-Judge（`report_relevance`/`debate_quality`/`decision_grounding`/`consistency`）rubric 落地，裁判 `deepseek-chat`，rubric 含「不以长度论优劣」声明，输出 JSON `{score, reason}`
- [x] Dataset `a-share-analysis-v1` 建库（15-20 条覆盖矩阵：deep 典型/边界、quick、follow_up、意图澄清），`dataset_seed.py` 幂等
- [x] `run_experiment` 一键执行全 Dataset，关联 `langfuse.get_prompt(label="production")` 版本，产出含均值的结果表
- [x] Judge 裁判调用标 `langfuse-llm-as-a-judge` 环境，成本 Dashboard 可独立核算
- [x] Judge 校准首轮：**以跨模型一致性代理门禁完成**（2026-09-07，人工标注延后至 backlog）——
      抽样 30 trace × 4 维度 = 90 对，deepseek-v4-flash（原 judge）↔ qwen3.8-flash ↔ k3-256k
      三模型交叉重评（脚本 tests/scripts/judge_cross_model_rerun.py）；整体 Spearman 0.63 /
      MAE 0.48 / 方向 81%；decision_grounding 方向 50%（qwen 严格读法，k3 7/10 站 deepseek），
      结论与 rubric v3 增补建议见 reports/judge-cross-model-report-20260907.md 与
      tests/validation/2026-09-07-cross-model-calibration-validation.md。
      **延后项**：spec「人工标注工具/judge-人工一致性指标」要求的人工 ≥80% 一致性校验仍开放
      （exporter 与 measure.py 工具链已就绪，见 add-judge-human-calibration 归档）
- [x] 线上托管 Evaluator 配置（第二阶段：同 rubric 采样 10-20%，Monitors 告警）——由子 delta
      `enable-hosted-evaluator` 完成（2026-09-07 归档）：4 个 evaluator 上线 + configId 快照回填
      docs/evals/hosted-evaluator-template.md + 实证打分=4（见 tests/validation/2026-09-07-hosted-evaluator-e2e-validation.md）；
      降级路径 poll.py + 阈值告警 + 口径比对齐备
- [x] `uv run pytest` 全过（`@live` 评估用例 nightly 跑）、`uv run ruff check` 无错误、`uv run mypy`（基线对比）无新增错误
- [x] `openspec validate agent-evaluation-suite --strict` 通过
- [x] 人工验证报告落 `tests/validation/`（基线实验结果 + 校准一致性 + 成本核算 < 5%）
