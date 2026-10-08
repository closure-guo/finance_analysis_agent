# Design: update-track-record-display-clarity

## Context

2026-10-08 UX 审计（生产实况）确认战绩页七类展示困惑（见 proposal）。本 delta 是展示治理包：不触碰判定链路行为与统计口径分母，全部改动落在「让已存在的数据/口径被正确看见」。superseded 不落超额（「基准超额」列已判定行为空的根因）是口径裁决，明确排除在外另立 B 类。

依赖：本 delta 基于 add-current-stance-view（PR #260）合并后的文本；与 #256（结算入场价列 + 口径标注，待评审）同触观点日志列集——列序协调：#256 在入场价/结算价处加「结算入场价」，本 delta 在状态后加「窗口」，二者不同位置，sync 顺序无论先后均可合，但实施计划须以先合并者的最终列集为基线。

## Goals / Non-Goals

**Goals:**

- 同屏四个总数（92/73/70/143）的可对账性：窗口列 + 披露行双计数（legacy_settled/legacy_open）让每个数字可归因
- 判定可自查：open 行展示浮动收益（盯市已在库），带内判定与方向「中性」消歧
- 噪声治理：同日重复折叠、切片空态折叠
- 术语与中文化：已结算/带内中性/详情页映射

**Non-Goals:**

- superseded 结算补算 excess_return 并落库（B 类口径裁决，另立 delta；本 delta 的基准超额列对已判定 superseded 行仍显示「—」）
- 修改 tab 名「已判定」（考虑过改「已关闭」：需同步改多个 E2E 断言文本，且「已结算」术语消歧已足够，收益/成本比不足）
- NAV/胜率/样本量任何统计口径
- #260 当前观点区、#256 结算入场价列（在途 PR 已覆盖）

## Decisions

**D1 窗口列：展示列、不排序。** 取行内 `horizon_days` 渲染「T+20/T+252」。不加排序：口径值域只有两三个离散值，排序价值低，且把 `horizon_days` 加进后端 `_SORT_WHITELIST` 会扩大注入面清单——不值。spec 明写「窗口列为展示列，不参与排序」。

**D2 同日重复折叠：纯前端分组、当前页作用域。** 服务端排序（created_at DESC）保证同 (symbol, 同日) 的 dup 行天然相邻（同日同股 dup 连续、且位于其日主行之后——日主 created_at 更晚时在前，实测 10-02 拓荆组连续成立）。前端渲染时对 consecutive 且 (symbol, 建立日期) 相同、status=duplicate_of_day 的行合并为一行汇总（显示标的/日期/「同日重复 ×n」），点击 toggle 展开明细。**边界**：跨页断组（组被 50 行分页切开）不追求合并——按「当前页内 consecutive」定义，spec 已明写「仅作用于当前页前端视图」；total 不变。不引入后端分组参数（YAGNI：当前最大组 9 条，页内合并已消除刷屏）。

**D3 浮动收益：列表行内嵌最新盯市，服务端批量注入。** `list_predictions` 返回行新增可选字段 `latest_mark: {mark_date, cum_return, cum_excess} | null`（对 open 行批量查 daily_marks 每观点最新一条，单条 SQL 窗口函数，页 ≤50 行成本可控）。前端 open 行区间收益/基准超额列读 latest_mark，附 title=盯市日期。**不选**前端另发 marks 请求：表格与浮点值同源渲染避免两跳闪烁。已结算行字段为 null、展示不变。closed/neutral 判定口径与浮动的语义差由「未结算」标注承载。

**D4 legacy_open：overview 端点差值法，与 legacy_settled 完全对称。** `legacy_open = max(0, legacy_all["open"] - stats["open"])`——legacy_all（无口径过滤）与 headline（horizon 过滤）两次查询 overview 本来就在发，零新增 SQL；语义=不在头条口径内的 open 计数（含 252 与潜在 NULL horizon）。0 值不渲染分句（与 legacy_settled=0 明示「无存量」的不对称是刻意的：已结算是合规披露常驻项，进行中是解释性补充）。

**D5 切片空态折叠：前端按 settled=0 隐藏。** 数据源 `/segments` 不改（含 143 未知桶的响应照旧，供后续结算期直接可用）；前端 settled==0 时整区渲染一行说明。**不选**后端跳过计算：端点语义保持稳定，避免 settled 翻转时响应形状突变。

**D6 术语映射单一真源。** 「带内中性」落在 `predictionStatus.ts`（前端标签）+ 后端 `_STATUS_KEYWORDS`（keyword 匹配）双侧同步；详情页方向/判定规则中文映射新建 `predictionDisplay.ts` 小映射模块（direction/resolution_rule → 中文），列表与详情共用，避免两处漂移。keyword 集合更新同步既有过滤用例。

**D7 E2E 造数缺口：seed 通道补 daily_marks。** 现 `/api/test/seed` 的 track_record 通道只支持 predictions；浮动收益 E2E 需要盯市行——predictions 造数行支持可选 `marks` 子数组（[{mark_date, cum_return, cum_excess, mark_price?}]，落库走生产 `insert_daily_mark` 同路径）。子键形态的原因：prediction_id 服务端生成，顶层数组无法引用，marks 必须按行携带。折叠/窗口列用现有 predictions 通道即可。

## Risks / Trade-offs

- **列数增长**（+窗口列，#256 再+结算入场价列）：窄屏可能横向滚动。缓解：窗口列紧凑（T+N 短文本）；实施时若 #256 已合并，验收含 1280px 无横向溢出。
- **折叠的「连续」前提依赖排序稳定性**：用户切换排序（如按 symbol）后组可能分散——接受（spec 定义为当前页 consecutive 语义，按 symbol 排序时同股同日仍相邻，天然仍成立；按 direction 排序时分散属合理代价）。
- **浮动收益与结算读数同列不同义**：open 行显示「盯市浮动」、closed 行显示「结算终值」，同列语义随状态切换。由「未结算」标注 + title 盯市日期承载区分；这是既有 spec 条款（「进行中观点 SHALL 展示当前浮动收益并标注未结算」）的落实，不是新引入的混排。
- **术语变更破坏存量断言**：「中性」→「带内中性」会打红现有 E2E/vitest 中按「中性」文本断言状态的用例——实施时逐个改断言为「带内中性」（属预期变更，diff 中说明；keyword 用例同步）。
