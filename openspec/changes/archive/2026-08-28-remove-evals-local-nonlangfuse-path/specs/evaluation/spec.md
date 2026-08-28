# Delta for Evaluation

## MODIFIED Requirements

### Requirement: 实验回归工作流

系统 SHALL 提供 `evals/` 目录（与 src 平级，不侵入业务代码）与 `run_experiment` 入口，对全 Dataset 跑一遍，关联所用 prompt 版本，产出可对比基线的实验结果。实验 SHALL 支持"改 prompt / 模型 → 跑 → 对比基线 → 决策"闭环。`run_experiment`（经 Langfuse dataset）SHALL 是实验的唯一执行入口：不提供绕过 Langfuse 的本地循环降级；Langfuse 未配置/不可达时，实验入口 SHALL 显式报错并给出非零退出码，不得静默产出不可对比的分数。
(Previously: 系统 SHALL 提供 `evals/` 目录与 `run_experiment` 入口，对全 Dataset 跑一遍，关联所用 prompt 版本，产出可对比基线的实验结果。实验 SHALL 支持"改 prompt / 模型 → 跑 → 对比基线 → 决策"闭环。未定义无 Langfuse 时的行为。)

#### Scenario: run_experiment 一键执行

- **WHEN** 执行 `evals/run.py "<实验名>"`
- **THEN** SHALL 对 Dataset 全量 item 跑 `run_analysis_task`
- **AND** 对每个 item 应用全部确定性 + Judge 评估器
- **AND** 产出含各 Score 均值与 per-item 明细的结果表

#### Scenario: 无 Langfuse 时显式报错（新增）

- **WHEN** 执行实验且 Langfuse 未配置或不可达
- **THEN** SHALL 打印明确错误（说明需要配置 Langfuse）并以非零退出码终止
- **AND** SHALL NOT 以本地循环降级产出分数

#### Scenario: prompt 版本关联

- **WHEN** 实验运行
- **THEN** SHALL 经 `langfuse.get_prompt(name, label="production")` 取 prompt
- **AND** prompt 名与版本记到 trace，UI 可回答"哪个 prompt 版本分数高"

#### Scenario: 业务代码零侵入

- **GIVEN** `evals/` 目录存在
- **THEN** 业务代码（`src/finance_agent/`）SHALL NOT 因评估被修改
- **AND** `evals/` 仅通过既有 graph 入口调用系统