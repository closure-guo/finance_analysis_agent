# Tasks: remove-evals-local-nonlangfuse-path

参考：`specs/evaluation/spec.md`（行为契约）。测试统一放 `tests/evals/`，按 TDD「先红后绿」。

## 1. 移除本地循环路径

- [x] 1.1 在 `evals/run.py` 删除 `--local` 参数、`run_local`、`_local_scores` 与 `main()` 的「无 langfuse → 本地循环」分支；无 langfuse 时改为打印明确错误（提示配置 Langfuse）并 `sys.exit(非零)`。`_mean_rows` / `_write_report` 保留（run_experiment 路径仍用）。TDD：先写失败测试（无 langfuse 时报错退出）→ 删除旧路径实现 → 通过
- [x] 1.2 更新 `evals/dataset_seed.py` 与 `evals/evaluators.py` 中提及 `--local` 的注释（改为「本地文件读取/实验经 run_experiment」）

## 2. 测试更新

- [x] 2.1 删除 `tests/evals/test_run.py::TestLocalRun.test_local_run_produces_rows` 与 `run_local` import（`_mean_rows` 用例保留）
- [x] 2.2 新增失败测试：无 langfuse（get_langfuse 返回 None）时 `main()` 报错并用非零退出码终止、不产出分数；有 langfuse 时不走本地分支

## 3. 验证收尾

- [x] 3.1 `uv run pytest tests/evals/ -q` 全绿；`uv run ruff check evals/ tests/evals/` 零告警
- [x] 3.2 `openspec validate --change remove-evals-local-nonlangfuse-path` 通过；`openspec validate --strict` 全库无回归
- [x] 3.3 提交