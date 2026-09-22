# Delta for Evaluation

## ADDED Requirements

### Requirement: hosted 实验判分取 K 次均值

`run_experiment`（`evals/run.py`）的 LLM-as-Judge 判分 SHALL 以 K 次重复调用的**均值**为点估计（复用 `run_judge_mean`），K SHALL 经 CLI 声明并写入实验产物 config，默认 3。SHALL NOT 用中位数（双峰分布 p→0.5 时中位不降翻转概率）。每次分数（`scores`）与极差（`score_spread`）SHALL 随 item 记录落盘，SHALL NOT 只留均值而静默抹掉离散度。解析失败/输入缺失的调用 SHALL 不计入均值但计入 `judge_failures`；全部调用失败时该维度 SHALL 记 `score=None`（沿实验失败率口径，不静默给分）。debate_quality（v6）的封顶/枚举遥测 SHALL 取最低分那次调用的观测（最保守）。本变更合入 SHALL 在 `docs/evals/metrics.md` §1.1 更新口径并在时间线登记切点：跨切点的 judge 绝对分不可与历史单次口径（r1–r9）直接比较。

#### Scenario: K 均值与离散度落盘

- **GIVEN** 某 item 的 debate_quality 三次调用返回 `[5, 4, 4]`
- **WHEN** run_experiment 记录该维度判分
- **THEN** 点估计 SHALL 为 4.33（均值），`scores` 与 `score_spread=1` SHALL 一并落盘
- **AND** 实验产物 config SHALL 含 `judge_repeats=3`

#### Scenario: 失败口径沿用

- **GIVEN** 某 item 的 consistency 三次调用中 1 次解析失败
- **WHEN** 记录该维度判分
- **THEN** 点估计 SHALL 为其余 2 次的均值，`judge_failures` SHALL 计 1
- **AND** 三次全部失败时 SHALL 记 `score=None` 且 `judge_failures=3`

#### Scenario: 封顶遥测取最低分调用

- **GIVEN** debate_quality 三次调用分数 `[5, 4, 4]`，其中 4 分那次枚举出纯定性标头
- **WHEN** 汇总封顶/枚举遥测
- **THEN** 遥测 SHALL 取最低分那次的观测（`cap_applied=true`、`qualitative_points ≥ 1`）
- **AND** SHALL NOT 因均值 4.33 > 4 而丢失封顶证据

#### Scenario: K 经 CLI 声明

- **WHEN** 以 `--judge-repeats N` 运行 hosted 实验
- **THEN** 实际 K SHALL 写入产物 config，全部维度按同一 K 判分
- **AND** 未声明时 SHALL 取默认 3

#### Scenario: 切点登记

- **WHEN** 本变更合入并首轮 hosted 实验收口
- **THEN** `docs/evals/metrics.md` 时间线 SHALL 新增切点行（单次判分 → K 次均值）
- **AND** 跨该切点的 judge 绝对分 SHALL 标注不可直接比较，与 r1–r9 的对比 SHALL 以切点行显式声明为前提

#### Scenario: 其余维度结果形状不变

- **WHEN** 运行 report_relevance / decision_grounding / consistency 判分
- **THEN** 结果字典 SHALL NOT 增加 debate 专有键（`points` / `cap_applied` / `enumeration_missing` 仍仅属 debate_quality），既有精确断言契约不变
