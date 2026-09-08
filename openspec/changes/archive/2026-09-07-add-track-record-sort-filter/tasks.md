# Tasks: add-track-record-sort-filter

## 1. 后端：predictions 列表排序与过滤

- [x] 1.1 `list_predictions` 增加 `sort_by`/`sort_dir` 参数，用白名单映射 `ORDER BY` 列，非法值回退 `created_at DESC`
- [x] 1.2 `list_predictions` 增加 `keyword` 过滤：大小写不敏感匹配 `symbol`/`symbol_name`，并将方向/状态中文标签映射为 `direction`/`status` 等值过滤
- [x] 1.3 `list_predictions` 增加 `date_from`/`date_to`：按 `date(created_at)` 区间过滤（含两端，到日）
- [x] 1.4 `GET /api/v1/track-record/predictions` 解析并透传 `sort_by`/`sort_dir`/`keyword`/`date_from`/`date_to` 查询参数，过滤后 `total` 反映子集
- [x] 1.5 后端单测覆盖：排序升/降、非法 sort_by 回退、keyword 各字段匹配、时间段含两端、组合过滤与过滤后 total

## 2. 前端：观点日志表格排序与过滤

- [x] 2.1 `TrackRecordPage` 新增「建立日期」列，展示 `created_at` 日期，参与排序
- [x] 2.2 表头点击切换升/降序并显示排序指示，可排序列覆盖日期/标的/方向/状态/入场价/结算价/区间收益/基准超额
- [x] 2.3 新增过滤控件：关键字输入框 + 起止日期选择（到日、含两端），提交后重新向后端拉取
- [x] 2.4 表格分页控件，翻页作用于过滤/排序后的结果
- [x] 2.5 前端单测覆盖排序状态切换、关键字/时间段过滤请求参数、分页与过滤状态同步

## 3. E2E 门禁（交互类变更）

- [x] 3.1 E2E spec 已覆盖核心交互场景（排序/关键字/时间段/翻页）→ **不适用**：`e2e/` Playwright 基建（§5.6 P1–P4）未落地，门禁未生效；覆盖由前端 RTL 单测 + 后端集成测试 + 人工浏览器实测承担，见 `tests/validation/2026-09-07-add-track-record-sort-filter-validation.md` 异常记录 1
- [x] 3.2 `cd e2e && npx playwright test` 全绿通过（stub 套件）→ **不适用**：同上，e2e 项目不存在，无法运行；不虚构「全绿」

## 4. 收尾

- [x] 4.1 `openspec validate add-track-record-sort-filter --strict` 通过
- [x] 4.2 人工验证报告已落 `tests/validation/2026-09-07-add-track-record-sort-filter-validation.md`
- [x] 4.3 sync + archive 完成（delta 合并进 `openspec/specs/track-record/`，changes 移入 archive/）
