# Proposal: add-golden-set-assertion-types

## Why

校验基准 claim_benchmark v12 全部为构造标签（rule_derived），实测 F1=1.0 零误差，属「构造性一致」——只验证「实现没改坏」，测不出「校验器对真实 claim 对不对」（真实实验 citation_pass=0.125 与 F1=1.0 直接矛盾）。同时 golden set 对照八大类型（GoldenSet 设计文档）缺 T6 拒答、T8 合规红线、T8 事故回归、T2 计算推理——而这些恰是防幻觉、合规与防复发的高价值确定性判定。需要建立「真实来源优先」的断言级金标准集，并把 v12 降级为算法回归探针。

## What Changes

- 新增断言级金标准集（`evals/golden/`）：schema 含 `as_of_date` / `origin` / `annotator` / `tier`，判定优先 deterministic（对照数据快照），`rule_derived` 仅限 pilot
- 首批真实来源样本：T8 事故回归（从 incidents 001/002/006 沉淀真实 bad case claim）、T6 拒答边界（未披露财报→不可得声明+无逃逸数字）、T8 合规红线（怂恿性问句→不得收益承诺+必须风险提示）
- `rule_derived` v12 身份降级：CI 门禁输出带「回归探针」声明确认，不构成真实准度声明；准度改由真实来源样本担纲
- CI 接线：golden 集 deterministic gate（零 token、进 CI）

## Capabilities

### New Capabilities

- `assertion-golden-set`: 断言级金标准集（schema/分层/判定/标注/来源纪律）

### Modified Capabilities

- `evaluation`: 校验器准度门禁附加「真实准度由真实来源+人工标注样本声明，构造集仅为回归探针」的披露要求

## Impact

- 新增 `evals/golden/`（schema.py / gates.py / 样本 JSONL / 判定器）
- `evals/claim_benchmark/measure.py`：输出加身份声明字段
- `.github/workflows/ci.yml`：golden gate 步骤
- 测试：`tests/evals/golden/`；标注流程复用 `compute_kappa`（首现真实 κ）
- 数据源：incidents 001/002/006 抽真实 claim + 人工构造 T6/T8 样本（待人工标注确认标签）