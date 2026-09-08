# Proposal: add-track-record

## Why

现有 `decision_log` 战绩体系（decision-outcome-tracking + expose-decision-outcomes）是简化版 v0：只记 approve、止损/目标/超期结算、普通可改写表。用户提供的《历史战绩体系设计文档 v1.0》定义了一套**可验证、不可篡改、回测与实盘分离**的完整战绩系统（全量记录每一条观点、horizon+中性带判定、显著性门槛、风险提示）。本提案按「取代/演进现有体系」+「阶段 A 核心骨架」立项，先把战绩从「只有被批准决策的粗略胜率」升级为「所有观点的不可篡改判定记录」。

## What Changes

- 新增 `predictions` 数据模型（append-only，观点快照冻结，含 `source_type` 回测/实盘区分、`direction` long/short/neutral、`confidence` 校准字段），现有 `decision_log` 记录迁移进新表
- 观点**全量记录**（P1：每条观点落库，不再只记 approve；reject/hold/watch 也进入观点日志，中性方向默认不进胜率分母）
- 判定规则替换现有「止损/目标/超期」：默认 horizon T+252 交易日、±2% 中性带、反向/改价新观点触发旧观点提前结算（superseded）、停牌/退市标 `unresolvable`
- 基础指标：胜率（含中性带与显著性门槛 n<10 不展示、10–29 标注、≥30 完整评级）+ 平均超额；胜率/均值口径与阶段 A 对齐
- 只读 track-record API（`/api/v1/track-record` 前缀：总览 + 观点日志列表）
- 前端战绩页改为接 track-record API（总览 + 观点日志合并单页），固定风险提示文案、不可隐藏 loss
- 阶段 A **不做**（后续增量 delta）：equity curve/daily marks、组合指标（回撤/波动/夏普/风险分）、校准分桶与 Brier、分行业/市值/环境切片、观点详情页与校准页、版本分段、审计日志、跟单/排行榜/实时盯市

## Capabilities

### New Capabilities

- `track-record`: 观点全量记录（append-only + 冻结快照）、判定规则（horizon/中性带/superseded/unresolvable）、基础统计（胜率含显著性门槛/平均超额）、track-record 只读 API 与战绩页面

### Modified Capabilities

- `decision-outcome`: 「决策落库」演进为「观点写入 predictions」（全量记录 + 快照冻结 + direction/confidence 字段）；「事后行情追踪」的止损/目标/超期结算规则被替换为 track-record 判定规则（horizon/中性带/superseded）

## Impact

- **数据**：新增 `predictions` / 关联表（同库 SQLite，WAL）；现有 `decision_log` 迁移进 `predictions`（一次性迁移脚本）；`decision_log` 保留只读不再写入
- **后端**：`src/finance_agent/outcome/` 新增 `track_record/` 子模块（predictions 模型 + 判定引擎 + 统计）；api.py 新增 `/api/v1/track-record/*` 端点；`_persist_decision_log` 改为写 predictions（reject/hold/watch 也落）
- **前端**：战绩页改为接 track-record API，新增风险提示组件；`pages/decisions/` 重定向或替换为 track-record 视图
- **与并行变更关系**：`decision-outcome-tracking` 与 `expose-decision-outcomes` 未归档；本 delta 以 MODIFIED 演进其需求（按 §6 并行规则，sync 顺序在合并时确认，以先归档者为准 rebase）
- **测试**：后端 pytest（判定引擎/统计/API）+ 交互类 → E2E spec + 人工验证报告
- **依赖**：无新增第三方依赖（SQLite + 现有 akshare 行情）
