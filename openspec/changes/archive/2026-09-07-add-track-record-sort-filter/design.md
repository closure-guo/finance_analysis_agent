# Design: add-track-record-sort-filter

## Context

历史战绩页「观点日志」当前是静态表：后端 `GET /api/v1/track-record/predictions` 固定 `ORDER BY created_at DESC`、分页上限 50，前端只取第 1 页且无分页控件。观点量随实盘与回测积累后，用户无法检索/排序，浏览体验差。

约束：交互类变更（前端 UI）→ 走完整 §3 管线含 E2E 门禁；`openspec/specs/track-record/` 为行为唯一真相；过滤/排序须在服务端执行以保证正确性（用户已确认）。

## Goals / Non-Goals

Goals：
- 后端 `/predictions` 支持可选排序（`sort_by`/`sort_dir`）与过滤（`keyword`/`date_from`/`date_to`），缺省行为完全不变。
- 前端观点日志表新增「建立日期」列、列头排序、关键字 + 起止日期过滤控件、分页。
- 过滤后的 `total` 正确反映过滤子集，分页翻页在过滤/排序结果上生效。

Non-Goals：
- 不做「只看好单」类预设筛选（红线：loss 不可隐藏）。
- 不改 overview/equity-curve/segments/calibration 等其它只读接口。
- 不引入新的前端表格/日期库依赖（用原生 `<input type=date>` 与现有样式体系）。

## Decisions

**D1：服务端排序与过滤，而非纯前端内存。**
理由：现有接口已按 `created_at DESC` 分页（上限 50），纯前端过滤只作用于已加载的第 1 页子集，会漏历史数据、`total` 失真。服务端下推可让排序/过滤/分页一致作用于全量。
- 备选 A（前端内存）：实现快，但只对可见子集生效，>50 条即错误。不选。

**D2：`sort_by` 白名单校验，非法值回退默认排序。**
`list_predictions` 的 `ORDER BY` 用白名单映射到列名，绝不直接拼接用户输入（防注入）。可排序列 = 现有可见列 + created_at：`created_at/symbol/direction/status/entry_price/exit_price/raw_return/excess_return`。`direction`/`status` 为文本列，排序按列值字典序即可。
- 备选：允许任意列 → 注入风险且超出表格可见列语义。不选。

**D3：关键字匹配代码/名称 + 方向/状态中文标签。**
`keyword` 大小写不敏感：`symbol LIKE %kw% OR symbol_name LIKE %kw%`；同时若关键字命中方向标签（看多/看空/中性）或状态标签（进行中/命中/未中/中性/不可判定）则映射为对应 `direction`/`status` 值参与过滤。标签 → 值映射集中在后端一处（与前端 `DIRECTION_LABEL`/`STATUS_LABEL` 保持一致）。
- 备选：仅匹配代码/名称 → 用户按中文状态/方向检索不到。不选（用户已确认要匹配方向+状态）。

**D4：时间段按 `created_at` 日期过滤，含两端。**
`date_from`/`date_to`（YYYY-MM-DD）按 `date(created_at) BETWEEN ? AND ?` 过滤，最细粒度到日、含两端。仅填一端时只约束对应边界。日期非法时回退为不设该端（宽容处理，不报 5xx）。
- 备选：按 `resolved_at`（判定日）→ open 记录无值会被排除，语义不完整。不选（用户已确认按创建日）。

**D5：前端分页 + 过滤状态集中在组件内。**
`TrackRecordPage` 持有 `{keyword, dateFrom, dateTo, sortBy, sortDir, page}` 查询状态，任一变化即重新 `fetch('/predictions?...')`，响应复用现有 `PredictionsResponse`（`predictions/page/page_size/total`）。表头点击在 `sortBy/sortDir` 间循环（默认→升→降）。新增「建立日期」列展示 `created_at` 的日期部分并参与排序。

## Risks / Trade-offs

- [keyword 多列 OR 匹配使 SQL 子句复杂度上升] → 仅对 `symbol`/`symbol_name` 用 LIKE，方向/状态走等值映射，条件仍为参数化拼接；加 `tests/outcome/` 覆盖组合过滤。
- [日期字符串时区/格式不一致] → `created_at` 由服务端生成、统一 ISO 格式；过滤统一按日期部分比较，前端 `input[type=date]` 输出 `YYYY-MM-DD`。
- [分页 UI 是本次新增交互面] → E2E spec 覆盖排序/关键字/时间段/翻页核心场景，防止翻页与过滤状态不同步。
- [非法查询参数破坏现有调用] → 全部新参数可选，缺省回退既有行为，保证向后兼容、无 BREAKING。

## Migration Plan

纯增量（新查询参数可选 + 前端同版本发布），无数据迁移、无停机；后端缺省路径与现行为逐字节一致。回滚 = 回退本次提交，前端回退到无过滤/排序版本。

## Open Questions

- 分页默认每页条数沿用现接口 `page_size` 上限（50）即可，无需额外决策。
