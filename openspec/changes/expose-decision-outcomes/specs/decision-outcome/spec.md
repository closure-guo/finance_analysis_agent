# Delta for decision-outcome

## ADDED Requirements

### Requirement: 决策查询 API

系统 SHALL 提供只读查询端点，将 `decision_log` 中的决策记录与结算结果暴露给前端。列表端点 `GET /api/decisions` SHALL 支持按 `ticker` 与 `status` 过滤，默认按决策时间倒序返回；统计端点 `GET /api/decisions/stats` SHALL 返回聚合战绩。两个端点 SHALL NOT 触发任何写操作，查询失败 SHALL 返回结构化错误而非 500 堆栈。

#### Scenario: 返回决策列表

- **WHEN** 前端请求 `GET /api/decisions`
- **THEN** 系统 SHALL 返回 `decision_log` 全部记录，按 `timestamp` 倒序
- **AND** 每条记录含 decision_id / session_id / timestamp / ticker / name / action / entry_price / stop_loss / target_price / confidence / status / settled_at / settle_price / hold_days / decision_return / benchmark_return / decision_excess

#### Scenario: 按状态过滤

- **WHEN** 请求 `GET /api/decisions?status=hit_target`
- **THEN** 系统 SHALL 只返回 `status=hit_target` 的记录
- **AND** status 取值限定为 open / hit_stop / hit_target / expired，非法取值 SHALL 返回 422

#### Scenario: 按股票过滤

- **WHEN** 请求 `GET /api/decisions?ticker=600519`
- **THEN** 系统 SHALL 只返回该 ticker 的决策记录
- **AND** ticker 与 status 过滤条件 SHALL 可组合（AND 语义）

#### Scenario: 聚合战绩统计

- **WHEN** 前端请求 `GET /api/decisions/stats`
- **THEN** 系统 SHALL 返回：总决策数、open 数、各结算状态计数、已结算决策的胜率（`decision_return > 0` 占比）、平均 `decision_return`、平均 `decision_excess`
- **AND** 胜率与均值 SHALL 只基于已结算记录（open 不计入）
- **AND** `decision_excess` 为 null 的记录 SHALL 从超额均值中剔除（不当作 0）

#### Scenario: 空表与无已结算记录

- **GIVEN** `decision_log` 为空或无任何已结算记录
- **WHEN** 请求 stats 端点
- **THEN** 计数类字段 SHALL 返回 0
- **AND** 胜率与均值字段 SHALL 返回 null（而非 0 或报错），由前端展示为「暂无数据」

### Requirement: 决策战绩页面

系统 SHALL 在前端提供「决策战绩」页面，顶部展示战绩汇总卡，下方展示决策列表，支持按股票与状态过滤。每条已结算决策 SHALL 以可读格式展示收益与基准超额（百分比、正负着色）。用户 SHALL 能从一条决策跳转到产生它的来源会话。页面数据 SHALL 来自决策查询 API，不使用前端硬编码或 mock 数据。

#### Scenario: 页面展示汇总与列表

- **GIVEN** 数据库已有若干 open 与已结算决策
- **WHEN** 用户从侧边栏进入「决策战绩」页面
- **THEN** 页面 SHALL 展示汇总卡（总决策数、胜率、平均收益、平均超额）
- **AND** 列表逐行展示每条决策的名称/代码、action、状态、入场价、结算价、持有天数、收益与超额

#### Scenario: 状态与收益的可读呈现

- **WHEN** 列表渲染一条已结算决策
- **THEN** 状态 SHALL 以中文标签呈现（open=持有中 / hit_stop=止损 / hit_target=达标 / expired=超期）
- **AND** 正收益与正超额 SHALL 以涨色着色、负值以跌色着色（A 股红涨绿跌约定）
- **AND** 字段为 null（如未结算的收益）SHALL 展示为占位符「—」

#### Scenario: 前端过滤联动

- **WHEN** 用户在页面选择某状态或输入股票代码过滤
- **THEN** 列表 SHALL 通过 API 过滤参数刷新，仅展示匹配记录
- **AND** 无匹配记录时 SHALL 展示空态提示而非空白区域

#### Scenario: 跳转来源会话

- **WHEN** 用户点击某条决策的来源入口
- **THEN** 前端 SHALL 导航到该决策 `session_id` 对应的会话视图
- **AND** 若会话已不存在，SHALL 展示提示而非报错崩溃

#### Scenario: 结算后页面可见新结果

- **GIVEN** 某决策刚被日批任务结算（status 由 open 转为 hit_target）
- **WHEN** 用户刷新决策战绩页面
- **THEN** 该决策 SHALL 以新状态与结算数据展示
- **AND** 汇总卡的胜率与均值 SHALL 反映最新结算结果
