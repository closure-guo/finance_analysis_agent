# Proposal: remove-evals-local-nonlangfuse-path

## Why

`evals/run.py` 的 `--local` 本地循环路径（`run_local` / `_local_scores`）是「无 langfuse 时绕开 `run_experiment` 的降级执行」，但：

1. **spec 未定义此路径**：`agent-evaluation-suite/specs/evaluation/spec.md`「实验回归工作流」Requirement 只定义了 `evals/run.py "<实验名>"` 走 `run_experiment`（langfuse）；本地循环是非契约的代码内实现细节。
2. **它绕过 langfuse 观测**：本地路径不建 dataset、不落 trace、不挂 item，与「实验结果可对比基线、prompt 版本可追溯、judge 独立核算成本」的 spec 意图相悖——等于一套偷偷运行、不可审计的实验。
3. **它掩盖环境故障**：langfuse 未配置/未启动时，`--local` 让实验「看似跑了」，produces 的分数无法与基线对比，误导「实验通过」判断。

## What Changes

- **移除 `evals/run.py` 的 `--local` 参数与本地循环**：删除 `argparse --local`、`run_local`、`_local_scores`、`main()` 中「无 langfuse → 本地循环」分支；无 langfuse 时改为**显式报错退出**（返回非零退出码 + 明确提示），不再静默降级。
- **配套清理**：删除测试 `tests/evals/test_run.py::TestLocalRun.test_local_run_produces_rows`（`run_local` 不再存在）；`_mean_rows` 保留（`run_experiment` 路径仍用）；更新 `evals/dataset_seed.py` / `evals/evaluators.py` 中提及 `--local` 的注释。
- **`load_items` / `dataset_seed.seed` 保留**：`load_items` 仍被 `seed()` 与测试使用，不随本地路径删除。

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**: `evaluation`（MODIFIED Requirement「实验回归工作流」：明确 run_experiment 为唯一入口，无 langfuse 时显式报错；REMOVED 无——spec 本就无本地循环条目，仅澄清）

## Impact

- `evals/run.py`（删 ~60 行）、`tests/evals/test_run.py`（删 1 用例）、`evals/dataset_seed.py` / `evals/evaluators.py`（注释）
- 无 langfuse 环境（CI 未配 key）跑 evals 将从「本地循环出分数」变为「显式报错」——CI 依赖方需提供 langfuse key（spec Requirement「业务代码零侵入」下 evals 本就是 langfuse 实验的一等公民）