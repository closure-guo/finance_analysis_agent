# Delta for track-record

## ADDED Requirements

### Requirement: 当前观点只读接口

系统 SHALL 提供只读接口 `GET /api/v1/track-record/current`：按标的返回其最新一条 `status='open'` 的观点（当前立场视图，每标的至多一行，按 `created_at` 倒序）。行结构 SHALL 与观点日志行一致（含 `source_type`/`symbol`/`symbol_name`/`direction`/`entry_price`/`horizon_days`/`status`/`created_at` 等）。`duplicate_of_day`、已结算（`resolved_*`/`avoidance`）与 `unresolvable` 行 SHALL NOT 出现在本接口响应中。接口 SHALL 支持可选 `source` 查询参数（按 `source_type` 过滤；缺省不过滤，但每行 SHALL 携带 `source_type` 供回测/实盘区分，SHALL NOT 产出无法区分口径的合并视图）。响应 SHALL 带 `as_of` 与 `disclaimer`。本接口为纯展示视图：SHALL NOT 改变任何统计口径（胜率/样本量/NAV/IC 分母仍按 `add-prediction-pool-integrity` 日主规则），SHALL NOT 执行任何写操作。

#### Scenario: 每标的仅返回最新一条 open

- **GIVEN** 同一标的存在多条 `status='open'` 的跨日观点（如 601058.SH 有 8 条 open）
- **WHEN** 请求 `/api/v1/track-record/current`
- **THEN** 该标的 SHALL 仅返回 `created_at` 最新的一条
- **AND** 台账中该标的其余 open 行 SHALL NOT 出现在响应中

#### Scenario: 无 open 观点的标的不出现

- **GIVEN** 某标的全部观点均已结算或关闭
- **WHEN** 请求 `/api/v1/track-record/current`
- **THEN** 响应 SHALL NOT 含该标的任何行

#### Scenario: 已关闭行不进入立场视图

- **GIVEN** 某标的最新落库的一条观点为 `duplicate_of_day` 或已结算状态
- **WHEN** 请求 `/api/v1/track-record/current`
- **THEN** 该标的 SHALL 返回其最新一条 `status='open'` 的观点（若存在）
- **AND** SHALL NOT 返回任何已关闭行

#### Scenario: 回测实盘分离

- **WHEN** 请求 `/api/v1/track-record/current` 不带 `source` 参数
- **THEN** 每行 SHALL 携带 `source_type` 字段供区分
- **AND** 请求携带 `source=live` 时 SHALL 仅返回 `source_type='live'` 的行

#### Scenario: 响应带 as_of 与免责声明

- **WHEN** 请求 `/api/v1/track-record/current`
- **THEN** 响应 SHALL 含 `as_of` 与 `disclaimer` 字段

## MODIFIED Requirements

### Requirement: 战绩页面（总览 + 观点日志）

系统 SHALL 在前端提供战绩页面：总览区（胜率、平均超额、样本量、as_of、**回避正确率（含样本数）、当前判定口径（caliber_horizon）、存量旧口径计数（legacy_settled）**）+ **当前观点区（每股最新一条 open 观点的立场视图）** + 观点日志列表。当前观点区 SHALL 位于总览区与观点日志之间：每标的一行，展示标的名称与代码、方向、建立日期、入场价、判定窗口（该观点自带 `horizon_days`，如 T+20）与状态（进行中），并注明该区口径说明（每股仅显示最新一条进行中观点，历史逐条记录见观点日志）；行点击 SHALL 导航至该观点详情页（与观点日志行同一详情页）；无任何 open 观点时 SHALL 展示空态文案而非隐藏区块或以 0 值冒充。当前观点区为展示层收敛：观点日志台账 SHALL 不受其影响，仍逐条展示全部状态记录（含同股跨日多条 open）。回避正确率 SHALL 与胜率同门槛（settled < 10 不展示，展示「样本积累中」而非 0 值）；口径与存量计数 SHALL 常驻展示（二者为口径披露，不受样本门槛限制）。页面 SHALL 固定展示风险提示「历史业绩不代表未来表现」，不可关闭；观点日志默认视图 SHALL 包含 loss 记录（不可隐藏）；进行中观点 SHALL 展示当前浮动收益并标注「未结算」；状态标签以颜色区分（命中=绿、未中=红、中性=灰、进行中=蓝、不可判定=灰斜杠、**回避=灰**——neutral 观点的回避终态 `status="avoidance"`，标签文本「回避」）。

观点日志表格 SHALL 新增「建立日期」列，展示观点创建日期，并作为可排序列之一。表格列头 SHALL 支持点击切换升/降序，可排序列 SHALL 包含建立日期/标的/方向/状态/入场价/结算价/区间收益/基准超额，当前排序 SHALL 有可见指示。表格上方 SHALL 提供过滤控件：关键字输入框（匹配代码/名称/方向/状态）与起止日期选择（按创建日，到日，含两端）；提交过滤后 SHALL 重新向后端拉取，并在服务端分页。表格 SHALL 提供分页控件以浏览过滤/排序后的完整结果。
(Previously: 页面仅「总览区 + 观点日志台账」单视图，无每股当前立场的收敛视图，用户无法从页面直接得知系统对每只股票的当前立场。)

#### Scenario: 页面渲染总览与观点日志

- **GIVEN** 已有若干不同状态观点
- **WHEN** 用户进入战绩页
- **THEN** SHALL 展示总览指标与观点日志列表
- **AND** 页面固定展示风险提示文案

#### Scenario: 默认视图不可隐藏 loss

- **WHEN** 用户打开观点日志默认视图
- **THEN** SHALL 同时展示 win 与 loss 记录
- **AND** SHALL NOT 存在「只看好单」类预设筛选

#### Scenario: 回避终态标签渲染

- **GIVEN** 存在 `status="avoidance"` 的 neutral 终态观点
- **WHEN** 战绩页观点日志渲染该行
- **THEN** 状态标签 SHALL 显示「回避」文本（由前端 `predictionStatus.ts` 的单一状态映射产出）
- **AND** SHALL NOT 渲染为空白标签

#### Scenario: 展示建立日期列

- **WHEN** 用户查看观点日志
- **THEN** 表格 SHALL 展示每条观点的建立日期（`created_at` 的日期部分）
- **AND** 该列 SHALL 可参与排序

#### Scenario: 按列排序交互

- **WHEN** 用户点击某可排序列头（如「区间收益」）
- **THEN** 表格 SHALL 按该列重新排序并显示升/降序指示
- **AND** 再次点击 SHALL 切换排序方向

#### Scenario: 关键字过滤交互

- **WHEN** 用户在关键字输入框输入「平安」并提交
- **THEN** 表格 SHALL 仅展示标的代码/名称/方向/状态匹配的记录
- **AND** 空关键字或清空后 SHALL 恢复全量视图

#### Scenario: 时间段过滤交互

- **WHEN** 用户选择起止日期（如 2026-09-01 至 2026-09-30）并提交
- **THEN** 表格 SHALL 仅展示创建日期落在区间内（含两端）的记录

#### Scenario: 过滤后分页浏览

- **WHEN** 过滤结果超过单页条数
- **THEN** 表格 SHALL 提供分页控件，可在过滤后的结果中翻页浏览

#### Scenario: 空态与样本不足

- **GIVEN** 无观点或样本量 < 10
- **WHEN** 渲染总览
- **THEN** SHALL 显示「样本积累中」与已有样本数进度，不显示 0 值冒充数据

#### Scenario: 数据缺口不伪造

- **WHEN** 行情存在缺口日
- **THEN** 图表 SHALL 断点处理，不插值伪造

#### Scenario: 回避正确率披露

- **GIVEN** 回避判定已结算样本 ≥ 10
- **WHEN** 渲染总览
- **THEN** SHALL 展示回避正确率与其样本数（win/(win+loss) 口径）
- **AND** 样本 < 10 时 SHALL 展示「样本积累中」而非 0 值或空白

#### Scenario: 口径与存量计数披露

- **WHEN** 渲染总览
- **THEN** SHALL 展示当前判定口径（如「T+20 交易日」）与存量旧口径计数（如「另有 n 条 252 日口径历史未计入」）
- **AND** 存量计数为 0 时 SHALL 明示「无存量」而非隐藏该披露

#### Scenario: 当前观点区每股一行

- **GIVEN** 同一标的存在多条 open 观点（跨日）
- **WHEN** 用户进入战绩页
- **THEN** 当前观点区该标的 SHALL 仅展示最新一条 open 观点
- **AND** 区块 SHALL 注明口径说明（每股仅显示最新一条进行中观点）

#### Scenario: 当前观点区空态

- **WHEN** 无任何标的持有 open 观点
- **THEN** 当前观点区 SHALL 展示空态文案（如「暂无进行中观点」）
- **AND** SHALL NOT 隐藏区块结构或以 0 值冒充数据

#### Scenario: 当前观点行点击进详情

- **WHEN** 用户点击当前观点区某行
- **THEN** SHALL 导航至该观点的详情页（与观点日志行一致）

#### Scenario: 台账不受立场视图影响

- **WHEN** 用户查看观点日志
- **THEN** 台账 SHALL 仍逐条展示全部状态记录（含同股跨日多条 open）
- **AND** SHALL NOT 因当前观点区存在而收敛、过滤或隐藏台账行
