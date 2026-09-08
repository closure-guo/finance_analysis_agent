# track-record Specification

## Purpose
TBD - created by archiving change add-track-record. Update Purpose after archive.
## Requirements
### Requirement: 观点数据模型（append-only + 快照冻结）

系统 SHALL 建立 `predictions` 表记录每条观点（Agent 一次可判定输出的最小单元：标的、方向、时间窗口，缺任一要素不进入统计）。表含 `source_type`（backtest/live，回测实盘分离）、`direction`（long/short/neutral）、`confidence`（0-1，校准用）、`rationale_snapshot`（完整分析原文 + 引用数据快照）、`entry_price`（参考价）、`horizon_days`（默认 252，上限 1 年）。观点快照（rationale_snapshot/direction/entry_price/created_at）写入后 SHALL 冻结，禁止任何接口修改；判定结果由系统计算，只允许状态流转（open → resolved_* / unresolvable）。

#### Scenario: 观点写入即冻结

- **WHEN** 一条观点写入 predictions
- **THEN** rationale_snapshot SHALL 含当时完整分析原文与引用数据
- **AND** 后续任何接口（含服务端内部接口）尝试修改 direction/entry_price/rationale_snapshot/created_at SHALL 失败并留记录

#### Scenario: 回测实盘分离

- **WHEN** 任何对外接口返回战绩数据
- **THEN** 响应 SHALL 按 `source_type` 区分 backtest 与 live
- **AND** SHALL 不存在合并 backtest 与 live 的服务端接口

#### Scenario: 缺要素观点不入统计

- **GIVEN** 一条观点缺标的、方向或时间窗口任一要素
- **WHEN** 写入
- **THEN** SHALL 存档但不进入战绩统计

### Requirement: 观点全量记录

系统 SHALL 落库 Agent 发出的**每一条**观点（P1），不再只记被批准（approve）的决策：reject、hold/watch、neutral 方向的观点 SHALL 同样写入 predictions。不允许删除观点记录，只允许状态流转。

#### Scenario: reject 观点同样落库

- **WHEN** Fund Manager 产出 reject 决策
- **THEN** 该观点 SHALL 写入 predictions（direction 由交易决策的 action 映射：buy→long、sell→short、hold/watch→neutral）

#### Scenario: 记录不可删除

- **WHEN** 通过任何接口尝试删除 predictions 记录
- **THEN** SHALL 失败并留记录

### Requirement: 判定规则（Outcome Resolution）

系统 SHALL 按统一规则判定观点：默认判定窗口 T+252 交易日（观点自带 `horizon_days` 则以自带为准，上限 1 年）；对同一标的发出方向相反或目标价不同的新观点时，旧观点 SHALL 立即以当前价结算（superseded）。方向判定：long 观点区间超额收益 > +2% → resolved_win；< −2% → resolved_loss；±2% 区间内 → resolved_neutral（计入总数但不计入胜率分子分母）；short 对称。中性带 ±2% 为全局配置项。停牌/退市/长期无行情 SHALL 标记 unresolvable，计入样本量，不计入胜率，UI 单独标识。

#### Scenario: 到期判定

- **GIVEN** 某 long 观点到达 horizon 终点
- **WHEN** 判定任务结算
- **THEN** 按区间超额收益判定 resolved_win / resolved_loss / resolved_neutral

#### Scenario: 中性带判定

- **GIVEN** 某 long 观点区间超额收益为 +1.5%（在中性带 ±2% 内）
- **WHEN** 判定
- **THEN** 该观点 SHALL 为 resolved_neutral
- **AND** 计入总数但不计入胜率分子分母

#### Scenario: 提前结算（观点变更）

- **WHEN** 对同一标的发出方向相反或目标价不同的新观点
- **THEN** 旧观点 SHALL 立即以当前价格结算判定
- **AND** resolution_rule SHALL 记录为 superseded

#### Scenario: 不可判定

- **GIVEN** 标的停牌 / 退市 / 长期无行情
- **WHEN** 判定任务处理
- **THEN** 该观点 SHALL 标记 unresolvable
- **AND** 计入样本量，不计入胜率

### Requirement: 基础统计（胜率 + 平均超额 + 显著性门槛）

系统 SHALL 计算并返回胜率与平均超额收益。胜率 = resolved_win / (resolved_win + resolved_loss)，neutral 与 unresolvable 不进分母。显著性门槛 SHALL 约束展示：样本量 < 10 不展示胜率与评级（仅展示样本数与「样本积累中」）；样本量 10–29 展示胜率并标注「样本较少」；样本量 ≥ 30 完整展示。评级（0–5 星）属后续增量（阶段 A 不做）。

#### Scenario: 胜率口径

- **GIVEN** 10 条观点（4 win / 4 loss / 2 neutral）
- **WHEN** 计算胜率
- **THEN** win_rate SHALL 为 0.5

#### Scenario: 样本量门槛

- **GIVEN** 某 Agent 已判定观点数为 9
- **WHEN** 请求总览
- **THEN** 响应 SHALL 不返回胜率与评级
- **AND** SHALL 返回样本数与「样本积累中」标注

#### Scenario: 空库

- **GIVEN** 无观点记录
- **WHEN** 请求总览
- **THEN** 计数类字段 SHALL 返回 0，胜率与超额 SHALL 返回 null

### Requirement: track-record 只读 API

系统 SHALL 提供统一前缀 `/api/v1/track-record` 的只读接口：总览（核心指标 + 样本量 + as_of）与观点日志列表（分页，默认时间倒序，包含全部状态）。写入接口仅服务端内部调用（Agent 编排层），SHALL 带鉴权，服务端生成权威 created_at。所有接口响应 SHALL 带 `as_of` 与 `disclaimer: "历史业绩不代表未来表现"`。

观点日志列表 `GET /api/v1/track-record/predictions` SHALL 支持可选查询参数进行排序与过滤（缺省保持全部状态、`created_at DESC`，不传任何参数时行为不变）：

- 排序：`sort_by`（可取值 `created_at`/`symbol`/`direction`/`status`/`entry_price`/`exit_price`/`raw_return`/`excess_return`）+ `sort_dir`（`asc`/`desc`，默认 `desc`）。
- 关键字：`keyword`，大小写不敏感，匹配标的代码 `symbol`、标的名称 `symbol_name`，或方向中文标签（看多/看空/中性）与状态中文标签（进行中/命中/未中/中性/不可判定）。
- 时间段：`date_from` / `date_to`，按观点创建日期（`created_at` 的日期部分）过滤，含两端，最细粒度到日。

列表接口 SHALL 校验非法排序字段，非法值 SHALL 回退默认排序；分页参数（`page`/`page_size`，上限 50）与 `total` 语义保持不变，`total` 反映过滤后的总条数。

#### Scenario: 总览响应含 as_of 与免责声明

- **WHEN** 请求总览
- **THEN** 响应 SHALL 含 as_of、sample_size、win_rate（或 null）、avg_excess（或 null）
- **AND** SHALL 含 disclaimer 文案

#### Scenario: 观点日志默认含全部状态

- **WHEN** 请求观点日志列表（不带任何过滤参数）
- **THEN** 默认 SHALL 返回全部状态（含 resolved_loss）
- **AND** status 过滤 SHALL 仅作为查看维度，不支持按结果筛选隐藏 loss

#### Scenario: 按列排序

- **WHEN** 请求观点日志列表并携带 `sort_by=raw_return&sort_dir=desc`
- **THEN** 响应 SHALL 按区间收益降序排列
- **AND** 携带 `sort_dir=asc` 时 SHALL 按升序排列

#### Scenario: 非法排序字段回退默认

- **WHEN** 请求携带非法 `sort_by`（如 `sort_by=unknown`）
- **THEN** 响应 SHALL 回退为默认排序 `created_at DESC`，不报错

#### Scenario: 关键字过滤

- **WHEN** 请求携带 `keyword=平安` 或 `keyword=600000`
- **THEN** 响应 SHALL 仅返回标的代码或名称匹配的记录
- **AND** 请求携带方向/状态中文标签（如 `keyword=命中`）时 SHALL 仅返回对应方向或状态的记录

#### Scenario: 时间段过滤含两端

- **WHEN** 请求携带 `date_from=2026-09-01&date_to=2026-09-30`
- **THEN** 响应 SHALL 仅返回创建日期落在 [2026-09-01, 2026-09-30] 内的记录（含两端）

#### Scenario: 过滤后分页 total

- **WHEN** 携带过滤参数请求列表
- **THEN** 响应 `total` SHALL 反映过滤后的总条数（而非全量总条数）

#### Scenario: 写入接口内部鉴权

- **WHEN** 外部调用方尝试 POST 创建观点
- **THEN** SHALL 因无内部鉴权被拒绝
- **AND** created_at SHALL 由服务端生成，不可由调用方指定

### Requirement: 战绩页面（总览 + 观点日志）

系统 SHALL 在前端提供战绩页面：总览区（胜率、平均超额、样本量、as_of）+ 观点日志列表。页面 SHALL 固定展示风险提示「历史业绩不代表未来表现」，不可关闭；观点日志默认视图 SHALL 包含 loss 记录（不可隐藏）；进行中观点 SHALL 展示当前浮动收益并标注「未结算」；状态标签以颜色区分（命中=绿、未中=红、中性=灰、进行中=蓝、不可判定=灰斜杠）。

观点日志表格 SHALL 新增「建立日期」列，展示观点创建日期，并作为可排序列之一。表格列头 SHALL 支持点击切换升/降序，可排序列 SHALL 包含建立日期/标的/方向/状态/入场价/结算价/区间收益/基准超额，当前排序 SHALL 有可见指示。表格上方 SHALL 提供过滤控件：关键字输入框（匹配代码/名称/方向/状态）与起止日期选择（按创建日，到日，含两端）；提交过滤后 SHALL 重新向后端拉取，并在服务端分页。表格 SHALL 提供分页控件以浏览过滤/排序后的完整结果。

#### Scenario: 页面渲染总览与观点日志

- **GIVEN** 已有若干不同状态观点
- **WHEN** 用户进入战绩页
- **THEN** SHALL 展示总览指标与观点日志列表
- **AND** 页面固定展示风险提示文案

#### Scenario: 默认视图不可隐藏 loss

- **WHEN** 用户打开观点日志默认视图
- **THEN** SHALL 同时展示 win 与 loss 记录
- **AND** SHALL 不存在「只看好单」类预设筛选

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

