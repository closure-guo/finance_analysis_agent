# Delta for track-record

> 并行变更说明：本 delta 的「战绩页面」requirement 基于 add-current-stance-view（PR #260）合并后的文本修改（并行变更规则：后到者 rebase 到先到者合并结果）；#260 若未先合并，sync 时须以其合并结果为基线重放本 delta。

## MODIFIED Requirements

### Requirement: track-record 只读 API

系统 SHALL 提供统一前缀 `/api/v1/track-record` 的只读接口：总览（核心指标 + 样本量 + as_of + `legacy_open` 旧口径进行中计数）与观点日志列表（分页，默认时间倒序，包含全部状态）。写入接口仅服务端内部调用（Agent 编排层），SHALL 带鉴权，服务端生成权威 created_at。所有接口响应 SHALL 带 `as_of` 与 `disclaimer: "历史业绩不代表未来表现"`。总览响应 SHALL 新增 `legacy_open` 字段：`status='open'` 且 `horizon_days` 不等于当前头条口径（`caliber_horizon`）的观点计数——与 `legacy_settled`（旧口径已结算计数）分列，二者口径披露互补。

观点日志列表 `GET /api/v1/track-record/predictions` SHALL 支持可选查询参数进行排序与过滤（缺省保持全部状态、`created_at DESC`，不传任何参数时行为不变）：

- 排序：`sort_by`（可取值 `created_at`/`symbol`/`direction`/`status`/`entry_price`/`exit_price`/`raw_return`/`excess_return`）+ `sort_dir`（`asc`/`desc`，默认 `desc`）。
- 关键字：`keyword`，大小写不敏感，匹配标的代码 `symbol`、标的名称 `symbol_name`，或方向中文标签（看多/看空/中性）与状态中文标签（进行中/命中/未中/带内中性/回避/同日重复/不可判定）。
- 时间段：`date_from` / `date_to`，按观点创建日期（`created_at` 的日期部分）过滤，含两端，最细粒度到日。

列表接口 SHALL 校验非法排序字段，非法值 SHALL 回退默认排序；分页参数（`page`/`page_size`，上限 50）与 `total` 语义保持不变，`total` 反映过滤后的总条数。

(Previously: 总览响应无 legacy_open；keyword 状态中文标签集合为「进行中/命中/未中/中性/不可判定」（无回避/同日重复，「中性」一词与方向标签撞词）。)

#### Scenario: 总览响应含 as_of 与免责声明

- **WHEN** 请求总览
- **THEN** 响应 SHALL 含 as_of、sample_size、win_rate（或 null）、avg_excess（或 null）
- **AND** SHALL 含 disclaimer 文案

#### Scenario: 总览含旧口径双计数

- **GIVEN** 库内存在 5 条 252 日口径已结算行与 7 条 252 日口径 open 行，头条口径为 T+20
- **WHEN** 请求总览
- **THEN** `legacy_settled` SHALL 为 5，`legacy_open` SHALL 为 7
- **AND** 二者 SHALL 为独立字段，互不并入对方

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
- **AND** 请求携带状态中文标签（如 `keyword=带内中性` 或 `keyword=同日重复`）时 SHALL 仅返回对应状态的记录

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

系统 SHALL 在前端提供战绩页面：总览区（胜率、平均超额、样本量、as_of、**回避正确率（含样本数）、当前判定口径（caliber_horizon）、存量旧口径计数（legacy_settled 与 legacy_open 分列）**）+ 当前观点区（每股最新一条 open 观点的立场视图，add-current-stance-view）+ 观点日志列表。总览区样本量术语 SHALL 使用「已结算」（win+loss 口径）——横幅「样本积累中（已结算 N 条，满 10 条解锁胜率）」、胜率卡「胜率（已结算）」、回避卡「回避正确率（中性观点已结算）」；SHALL NOT 再使用「已判定」表述 win+loss 口径（与观点日志 tab 名「已判定」= 非 open 全集消歧）。口径披露行 SHALL 同时披露两个旧口径计数：`legacy_settled`（「另有 n 条旧口径已结算」或 0 时「无存量」）与 `legacy_open`（n>0 时「另有 n 条旧口径进行中，不计入头条口径」；0 时不渲染该分句）。回避正确率 SHALL 与胜率同门槛（settled < 10 不展示，展示「样本积累中」而非 0 值）；口径与存量计数 SHALL 常驻展示（二者为口径披露，不受样本门槛限制）。页面 SHALL 固定展示风险提示「历史业绩不代表未来表现」，不可关闭；观点日志默认视图 SHALL 包含 loss 记录（不可隐藏）；进行中观点 SHALL 展示当前浮动收益并标注「未结算」；状态标签以颜色区分（命中=绿、未中=红、**带内中性=灰**（resolved_neutral，标签文本「带内中性」，与方向「中性」=观望消歧）、进行中=蓝、不可判定=灰斜杠、回避=灰、同日重复=三级灰）。

**切片指标空态折叠**：总览 `settled=0` 时，切片指标区（持有期/行业/市值/市场环境）SHALL 折叠为一行说明文案（如「切片指标将在首批观点结算后可用」），SHALL NOT 渲染全「—」的四维表格；`settled>0` 时渲染行为不变。

观点日志表格 SHALL 新增「建立日期」列与「窗口」列（**展示该观点自带 `horizon_days`，如「T+20」「T+252」，混合口径显式可见**），并作为可排序列之一。表格列头 SHALL 支持点击切换升/降序，可排序列 SHALL 包含建立日期/标的/方向/状态/入场价/结算价/区间收益/基准超额（窗口列为展示列，不参与排序）。表格上方 SHALL 提供过滤控件：关键字输入框（匹配代码/名称/方向/状态）与起止日期选择（按创建日，到日，含两端）；提交过滤后 SHALL 重新向后端拉取，并在服务端分页。表格 SHALL 提供分页控件以浏览过滤/排序后的完整结果。

**进行中浮动收益**：观点日志中 `status='open'` 的行，区间收益列 SHALL 展示该观点最新每日盯市累计收益（`daily_marks.cum_return`）、基准超额列 SHALL 展示累计超额（`cum_excess`），并保留「未结算」标注；展示值 SHALL 附盯市日期提示（title/悬浮）。无盯市记录的 open 行两列 SHALL 显示「—」。已结算行展示口径不变（结算读数）。

**同日重复折叠**：「已判定」与「全部」tab 中，连续的同 (symbol, 建立日期) `duplicate_of_day` 行 SHALL 默认折叠为一行汇总（展示标的、日期与「同日重复 ×n」），点击汇总行 SHALL 展开组内明细行；展开状态 SHALL 仅作用于当前页前端视图。折叠 SHALL NOT 改变服务端分页 `total`、append-only 台账语义与任何统计口径。「当前持有」tab 无 duplicate_of_day 行，不受影响。
(Previously: 样本量术语用「已判定」（与 tab 名撞词）；口径披露行仅有 legacy_settled（「无存量」与全部 tab 内旧口径 open 行并存的观感矛盾）；表格无窗口列（252 行混入无从分辨）；open 行区间收益/基准超额恒「—」（盯市数据未接）；resolved_neutral 标签「中性」与方向「中性」同词；settled=0 时切片区渲染全「—」四维表格；同日重复行无折叠刷屏。当前观点区一段为 add-current-stance-view 引入，本 delta 不改动其语义。)

#### Scenario: 页面渲染总览与观点日志

- **GIVEN** 已有若干不同状态观点
- **WHEN** 用户进入战绩页
- **THEN** SHALL 展示总览指标与观点日志列表
- **AND** 页面固定展示风险提示文案

#### Scenario: 默认视图不可隐藏 loss

- **WHEN** 用户打开观点日志默认视图
- **THEN** SHALL 同时展示 win 与 loss 记录
- **AND** SHALL NOT 存在「只看好单」类预设筛选

#### Scenario: 样本量术语消歧

- **GIVEN** settled=0 而观点日志「已判定」tab 有 70 行（dup/带内中性/不可判定）
- **WHEN** 渲染总览
- **THEN** 横幅 SHALL 显示「样本积累中（已结算 0 条…）」
- **AND** SHALL NOT 出现「已判定 0 条」表述

#### Scenario: 口径披露行双计数

- **GIVEN** legacy_settled=5、legacy_open=7
- **WHEN** 渲染口径披露行
- **THEN** SHALL 同时展示「另有 5 条旧口径已结算」与「另有 7 条旧口径进行中，不计入头条口径」
- **AND** legacy_open=0 时该分句 SHALL 不渲染（legacy_settled=0 时仍明示「无存量」）

#### Scenario: 窗口列渲染

- **GIVEN** 观点日志同时存在 horizon_days=20 与 252 的行
- **WHEN** 用户查看观点日志
- **THEN** 窗口列 SHALL 分别显示「T+20」与「T+252」
- **AND** 「当前持有」tab 中的旧口径行 SHALL 可通过窗口列识别

#### Scenario: 进行中浮动收益展示

- **GIVEN** 某 open 观点存在盯市记录（最新 mark：cum_return=-1.2%、cum_excess=-0.8%，mark_date=2026-10-08）
- **WHEN** 渲染观点日志该行
- **THEN** 区间收益列 SHALL 显示 -1.20%、基准超额列 SHALL 显示 -0.80%，状态列保留「未结算」标注
- **AND** 展示值 SHALL 附盯市日期提示

#### Scenario: 无盯市 open 行

- **GIVEN** 某 open 观点无任何盯市记录
- **WHEN** 渲染该行
- **THEN** 区间收益与基准超额列 SHALL 显示「—」（SHALL NOT 显示 0 值冒充）

#### Scenario: 同日重复折叠与展开

- **GIVEN** 「全部」tab 存在某标的某日连续 6 条 duplicate_of_day 行
- **WHEN** 渲染
- **THEN** SHALL 默认显示 1 行汇总（含「同日重复 ×6」），6 条明细行隐藏
- **WHEN** 用户点击汇总行
- **THEN** 6 条明细行展开可见；再次点击收起
- **AND** 分页 total SHALL 保持含全部 6 条的计数值不变

#### Scenario: 切片空态折叠

- **GIVEN** 总览 settled=0
- **WHEN** 渲染切片指标区
- **THEN** SHALL 仅显示一行说明（如「切片指标将在首批观点结算后可用」）
- **AND** SHALL NOT 渲染四维分桶表格

#### Scenario: 回避终态标签渲染

- **GIVEN** 存在 `status="avoidance"` 的 neutral 终态观点
- **WHEN** 战绩页观点日志渲染该行
- **THEN** 状态标签 SHALL 显示「回避」文本（由前端 `predictionStatus.ts` 的单一状态映射产出）
- **AND** SHALL NOT 渲染为空白标签

#### Scenario: 带内中性标签渲染

- **GIVEN** 某看空观点判定为 resolved_neutral（超额落 ±2% 带）
- **WHEN** 渲染该行
- **THEN** 状态列 SHALL 显示「带内中性」（SHALL NOT 与方向「中性」同词）
- **AND** keyword=带内中性 SHALL 能过滤出该行

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
- **THEN** SHALL 展示当前判定口径（如「T+20 交易日」）与存量旧口径计数
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
