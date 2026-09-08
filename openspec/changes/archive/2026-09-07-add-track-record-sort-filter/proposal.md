## Why

历史战绩页的「观点日志」目前是静态表格：后端 `/api/v1/track-record/predictions` 固定按 `created_at DESC` 返回且前端只取第 1 页（最多 50 条、无分页），用户无法从大量历史观点中定位某只标的、某段时期或某种结果，也无法按收益、日期等维度排序。数据积累越多，浏览体验越差。

## What Changes

- 后端 `GET /api/v1/track-record/predictions` 增加排序与过滤查询参数：
  - 排序：`sort_by`（可排序列：建立日期 created_at / 标的 symbol / 方向 direction / 状态 status / 入场价 entry_price / 结算价 exit_price / 区间收益 raw_return / 基准超额 excess_return）+ `sort_dir`（asc/desc），默认仍为 `created_at DESC`。
  - 关键字过滤：`keyword`，大小写不敏感，匹配标的代码 symbol、标的名称 symbol_name，以及方向（看多/看空/中性）与状态（进行中/命中/未中/中性/不可判定）的中文标签。
  - 时间段过滤：`date_from` / `date_to`，按观点创建日（`created_at` 的日期）过滤，含两端，最细粒度到日。
- 前端历史战绩页「观点日志」：
  - 表格新增「建立日期」列，展示观点创建日期，可参与排序。
  - 表头可点击切换升/降序（可排序列含日期/标的/方向/状态/入场价/结算价/区间收益/基准超额），提供当前排序指示。
  - 新增过滤控件：关键字输入框 + 起止日期选择（到日），提交后重新向后端拉取。
  - 补充分页控件，浏览过滤/排序后的完整结果（响应已含 `page/page_size/total`）。
- 过滤与排序均在服务端执行，前端仅展示服务端返回的结果子集，保证正确性（现有接口分页上限 50）。

## Capabilities

### New Capabilities

- 无（能力并入既有 `track-record` 规范）

### Modified Capabilities

- `track-record`: 「track-record 只读 API」需求扩展排序/关键字/时间段过滤查询参数；「战绩页面（总览 + 观点日志）」需求扩展表格排序、关键字/时间段过滤、日期列与分页交互。

## Impact

- 后端：`src/finance_agent/api.py`（predictions 端点解析新查询参数）、`src/finance_agent/outcome/track_record/model.py`（`list_predictions` 增加排序与过滤子句，及对应的 keyword 匹配与 created_at 日期区间）。
- 前端：`frontend/src/pages/trackRecord/TrackRecordPage.tsx`（表格列头排序、过滤控件、日期列、分页）、`frontend/src/types.ts`（若需扩展响应类型/查询参数类型）。
- 测试：后端单测 `tests/outcome/`（list_predictions 过滤/排序）、前端单测（过滤/排序状态）、E2E spec（排序/关键字/时间段交互场景，交互类变更须过 E2E 门禁）。
- 无破坏性变更：新增查询参数为可选，缺省行为（全部状态、created_at DESC）保持不变。
