# Proposal: switch-hosted-judge-to-k-mean

## Why

hosted 实验路径（`evals/run.py` 的 `run_experiment`，产出 r 系列时间线与 `reports/evals/*.json`）的 judge 判分仍是**单次调用**，而 round11 实测同一材料同一 rubric 的单次调用在 4/5 边界**双峰翻转**（宁德 04baff5c，n=13 次：4 分 7 次 / 5 分 6 次），且 K=3 中极差>0 的行占 5/8——该调用级噪声与 r 系列要检测的回归效应同阶，跨实验比较只能按「同噪声下的相对差异」解读。消融路径已切换 K 次均值（delta `judge-enumeration-cap-and-ablation-materials`），hosted 路径是口径分叉的最后残留（`docs/evals/metrics.md` §3 待决策登记项「hosted 实验路径仍是单次判分」）。

## What Changes

- hosted `run_experiment` 的 judge 判分由 `run_judge`（单次）切换为 `run_judge_mean`（K 次均值），K 经 CLI 声明并写入产物 config，默认 3（与消融路径一致）
- 判分结果落盘口径：点估计 = K 次均值；每次分数（`scores`）与极差（`score_spread`）随行落盘；解析失败/输入缺失的调用不计入均值但计入 `judge_failures`，全部失败记 `score=None`
- debate_quality（v6）的封顶/枚举遥测取**最低分那次**调用的观测（与消融口径一致，任一次找到纯定性标头则封顶证据不丢）
- `docs/evals/metrics.md` §1.1 口径先行更新（点估计=K 次均值），时间线登记**口径切点**：跨切点的 judge 绝对分不可与 r1–r9 历史单次口径直接比较
- 成本影响如实披露：judge 调用次数 ×K（17 item × 4 维 × K）；Langfuse 服务端托管 Evaluator 不受影响（服务端配置，非本路径）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `evaluation`: 新增「hosted 实验判分取 K 次均值」需求——`run_experiment` 的 judge 分数契约从单次调用升级为 K 次均值 + 离散度落盘 + 切点登记

## Impact

- 代码：`evals/run.py`（判分调用与结果塑形）、`evals/judges.py`（如需 CLI 透传）；测试同步
- 台账：`docs/evals/metrics.md` §1.1 口径行 + §2 时间线切点行；`runs.jsonl` 后续行的 means 口径不变（仍为均值），新增 spread 类字段可选
- 历史可比性：**跨切点不可直接比较**（r1–r9 单次 vs 切点后 K 均值），以切点行显式声明；切点前的相对差异解读纪律（「同噪声下的相对差异」）随之退役
- 成本：每轮 hosted 实验 judge 调用 ×K（默认 ×3）
