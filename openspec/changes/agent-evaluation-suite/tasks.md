# Tasks: agent-evaluation-suite

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出至 `docs/superpowers/plans/`，不在此处。

## 前置

- [ ] delta `agent-trace-content-fidelity` 已落地（Judge 输入依赖 span 内容保真）

## 验收项

- [ ] `evals/` 目录建立（与 src 平级），业务代码零侵入（git diff 确认未改 `src/finance_agent/`）
- [ ] 确定性评估器 `section_coverage`（同义词词典匹配）+ `ticker_match` 落地，零 LLM 调用
- [ ] 4 个 LLM-as-Judge（`report_relevance`/`debate_quality`/`decision_grounding`/`consistency`）rubric 落地，裁判 `deepseek-chat`，rubric 含「不以长度论优劣」声明，输出 JSON `{score, reason}`
- [ ] Dataset `a-share-analysis-v1` 建库（15-20 条覆盖矩阵：deep 典型/边界、quick、follow_up、意图澄清），`dataset_seed.py` 幂等
- [ ] `run_experiment` 一键执行全 Dataset，关联 `langfuse.get_prompt(label="production")` 版本，产出含均值的结果表
- [ ] Judge 裁判调用标 `langfuse-llm-as-a-judge` 环境，成本 Dashboard 可独立核算
- [ ] Judge 校准：首轮实验抽 20-30 条进 Annotation Queue 人工打分，一致性 ≥ 80% 才定稿 rubric（校准报告落 `tests/validation/`）
- [ ] 线上托管 Evaluator 配置（第二阶段：同 rubric 采样 10-20%，Monitors 告警）
- [ ] `uv run pytest` 全过（`@live` 评估用例 nightly 跑）、`uv run ruff check` 无错误、`uv run mypy` 无错误
- [ ] `openspec validate agent-evaluation-suite --strict` 通过
- [ ] 人工验证报告落 `tests/validation/`（基线实验结果 + 校准一致性 + 成本核算 < 5%）
