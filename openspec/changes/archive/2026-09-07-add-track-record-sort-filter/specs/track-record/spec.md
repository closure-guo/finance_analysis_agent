# Delta for track-record

## MODIFIED Requirements

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
