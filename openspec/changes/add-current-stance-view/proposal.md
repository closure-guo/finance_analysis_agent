## Why

战绩页观点日志是台账视角：同股跨日的多条 open 观点并排平铺（当前 58 条 open 仅覆盖 13 只股票，601058 一股 8 条），用户无法直接回答「系统现在怎么看这只股」——立场语义上每股只有一条（最新一条），但页面上没有任何视图做这层收敛，用户困惑「多个观点并存哪个算数」（2026-10-07 审计确认）。

## What Changes

- 新增只读接口 `GET /api/v1/track-record/current`：按标的返回最新一条 `status='open'` 的观点（当前立场视图），响应沿用 as_of + disclaimer 约定，支持可选 `source` 过滤（回测/实盘分离红线）
- 战绩页在观点日志上方新增「当前观点」区：每股一行（标的/方向/建立日期/入场价/判定窗口/状态），行点击进入既有观点详情页；观点日志台账保持不变
- 不改动任何统计口径：胜率/样本量/NAV/IC 的分母仍为日主观点全集（本变更纯展示分层，台账每条仍独立判定）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `track-record`: 只读 API 家族新增当前立场接口；战绩页面需求新增「当前观点」区（总览与观点日志之间），页面信息架构从「台账单视图」变为「立场 + 台账」双层

## Impact

- 后端：`src/finance_agent/outcome/track_record/model.py`（新增按标的取最新 open 的查询函数）、`src/finance_agent/api.py`（新增端点）
- 前端：`frontend/src/pages/trackRecord/TrackRecordPage.tsx`（新增区块）、`frontend/src/types`（响应类型）
- 测试：后端单测（查询语义）、E2E（区块渲染/空态/行点击，交互类变更走 E2E 门禁）
- 不涉及：判定链路、统计函数、数据库 schema、prompt
