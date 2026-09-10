# Delta for evaluation

## MODIFIED Requirements

### Requirement: 评估 Dataset 与覆盖矩阵

系统 SHALL 维护评估 Dataset（命名如 `a-share-analysis-v1`），每条 item SHALL 含 `input`（query / mode / session_id）与 `expected_output`（仅断言结构性字段，不断言时效数值），metadata SHALL 含 `category`、`source` 与 `pool`。Dataset 条目按 pool 分两组：`baseline` 池为固定可比集合（跨实验配对对比的对象，不得随轮次变动）；`rotating` 池为轮换候选池，每轮实验 SHALL 从池中按标的分组随机抽样（seed 可复现），防对固定标的过拟合。Dataset SHALL 可从历史 trace 捞取并幂等重建。

(Previously: Dataset 条目只按 category 分类，无 pool 区分；重复执行实验始终跑同一批 16 条 items，标的固定无轮换。)

#### Scenario: Item Schema

- **WHEN** Dataset item 定义
- **THEN** `input` SHALL 含 `query`、`mode`（deep/quick/follow_up）、可选 `session_id`
- **AND** `expected_output` 可含 `ticker`、`must_cover`、`should_clarify`，均为可选
- **AND** `metadata` 含 `category` 与 `source`

#### Scenario: 幂等建库

- **WHEN** `dataset_seed.py` 重复执行
- **THEN** SHALL 不产生重复 item（以 input.query + mode 为去重键）
- **AND** 已存在 item 不被覆盖

#### Scenario: expected 不含时效数值

- **GIVEN** 某 deep 典型 case
- **THEN** `expected_output` SHALL NOT 含具体财务数值（如净利润 X 亿）
- **AND** 只含结构性断言（章节、ticker）

#### Scenario: baseline 池固定可比

- **GIVEN** 两次实验均使用 baseline 池
- **WHEN** 运行实验
- **THEN** 两次实验的 item 集合 SHALL 完全一致（配对 bootstrap 可比前提）
- **AND** rotating 池条目 SHALL NOT 混入 baseline 实验

#### Scenario: rotating 池按标的分组抽样

- **WHEN** 以 `--pool rotating --rotating-sample N --rotating-seed S` 建库
- **THEN** SHALL 随机抽取 N 个标的，每个标的的全部条目（deep/quick）一并入池
- **AND** 相同 seed 抽取结果 SHALL 完全一致（可复现），不同 seed 应倾向不同标的组合
- **AND** rotating 条目 SHALL 建于独立 dataset（如 `a-share-analysis-v1-rot-<seed>`），不污染 baseline 的可比集合

#### Scenario: 确定性断言覆盖

- **WHEN** 定义 quick/deep 条目
- **THEN** 能明确对应单一标的的条目 SHALL 提供 `expected_output.ticker`（供 ticker_match 确定性评分）
- **AND** 无单一标的的行业类查询（如「银行股现在估值贵吗」）可留空，但须在 metadata 标注原因

#### Scenario: 出分条目占比

- **WHEN** 审视 Dataset 设计
- **THEN** 非 skipped 条目（可出分）SHALL 占条目总数 ≥ 80%
- **AND** follow_up / 意图澄清等首版跳过条目合计 SHALL NOT 超过 3 条

## ADDED Requirements

### Requirement: deep 边界歧义解析样本

deep 边界类别 SHALL 覆盖至少一个「模糊名称无代码」的歧义解析样本（如「分析平安」→ 期望解析到具体标的或触发反问），用于加压 ticker 解析与意图澄清路径。

#### Scenario: 歧义样本加压

- **GIVEN** dataset 含「分析平安」这类无代码模糊 query
- **WHEN** 运行实验
- **THEN** 该条目 SHALL 期望解析到确定标的（ticker_match 打分）或经 `should_clarify` 触发反问
- **AND** 两种预期均在 expected_output 中显式声明