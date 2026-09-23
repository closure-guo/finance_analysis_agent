# Design: switch-hosted-judge-to-k-mean

## Approach

复用消融路径已落地的 `run_judge_mean`（`evals/judges.py`），hosted 侧只做三件事：① `evals/run.py` 的判分调用替换 + `--judge-repeats` CLI 透传（写入产物 config）；② item 记录塑形补 `scores` / `score_spread`（`judge_failures` 口径函数内既有）；③ 台账与时间线切点登记。遥测聚合（最低分调用的封顶观测）若 `run_judge_mean` 已实现则直接继承，不重复实现。

## Alternatives Considered

- **维持单次判分 + 报告内披露噪声区间**：不解决根因（单次调用是从双峰分布随机抽样一次，r 系列要检测的回归效应与噪声同阶），披露只是把问题写下来。
- **K 次取中位数**：round11 已论证双峰 p≈0.5 下中位不降翻转概率，均值才无偏且方差随 K 收缩——与消融路径同结论。
- **只对 debate_quality 加 K**（其他维度单次）：极差>0 的行 5/8 不止 debate；且「哪些维度需要 K」会成为新的口径分叉，违背一次收口的目的。

## Risks

- **成本 ×K**：每轮 judge 调用约 68 → 204（K=3）。对策：K 可 CLI 调低（如 smoke 轮 K=1 显式声明）；成本在 Langfuse `langfuse-llm-as-a-judge` 环境标记下仍可独立核算。
- **与历史报告绝对分不可比**：以时间线切点行显式声明（本项目既有惯例：debate 锚点材料切点、决策契约切点同款）；runs.jsonl 后续行 notes 带切点标注。
- **Langfuse 服务端托管 Evaluator 不在本变更范围**（服务端配置非本地代码路径）：服务端单次判分若启用，其口径分叉在启用时单独处理，本变更不假装覆盖它。
