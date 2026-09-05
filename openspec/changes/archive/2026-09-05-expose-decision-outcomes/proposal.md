# Proposal: expose-decision-outcomes

## Why

决策结果追踪（decision-outcome-tracking）已实现「决策落库 + 交易日收盘日批结算 + Langfuse Score 回传」，`decision_log` 表中持续积累 open/hit_stop/hit_target/expired 状态的决策及其收益、基准超额数据，但这些结果**没有任何用户可见入口**：API 无查询端点，前端无展示页面，结算环断在 Langfuse（仅开发者可见）。README 承诺的「交易决策自动落库并按交易日收盘结算」对产品用户不可感知，已沉淀的决策效果数据资产无法回流到使用体验中。

## What Changes

- 新增只读查询 API：`GET /api/decisions`（决策列表，支持按 ticker / status 过滤、分页）与 `GET /api/decisions/stats`（聚合战绩统计：胜率、平均收益、平均超额、按状态计数）
- 新增前端「决策战绩」页面：战绩汇总卡 + 决策列表（状态、入场价、结算价、持有天数、收益、基准超额），按股票/状态过滤，可跳转来源会话
- 侧边栏新增「决策战绩」导航入口（沿用下载中心的导航模式）
- 不改结算逻辑、不落库逻辑、不改 Langfuse 回传——本变更只做**只读暴露**，无写入路径

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `decision-outcome`: 新增「决策查询 API」与「决策战绩页面」两个 Requirement（该 capability 由进行中提案 `decision-outcome-tracking` 建立，本 delta 以 ADDED Requirements 追加，不修改其已有需求；按并行变更规则，sync 时追加合并）

## Impact

- **后端**：`src/finance_agent/api.py`（新增两个只读端点）；可能需要在 `src/finance_agent/outcome/store.py` 增加列表/聚合查询函数（只读 SELECT）
- **前端**：`frontend/src/App.tsx`（路由入口）、侧边栏导航、新增 `frontend/src/pages/decisions/` 页面组件
- **数据**：仅读 `decision_log` 表，无 schema 变更、无迁移
- **测试**：后端 pytest（端点 + 查询函数）；交互类变更 → E2E spec 覆盖核心场景（列表渲染、过滤、空态）+ 人工验证报告
- **依赖**：无新增第三方依赖
- **风险**：单用户本地部署定位下无鉴权问题；数据量小（日批结算），无需复杂分页
