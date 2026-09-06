# Proposal: add-track-record-stage-c

## Why

阶段 A/B 覆盖了记录与指标，但设计档案 v1.0 的「防刷胜率」「防篡改」「可追溯」三块还空着：无校准分桶与 Brier Score（置信度字段已存但从未验证）、无市场环境/持有期切片、无观点详情页（预测 vs 实际叠加图）、无版本分段（模型升级后战绩混算违反 P6）。

## What Changes

- 校准分桶：confidence 按 [0.5,0.6)...[0.9,1.0] 分桶输出 {桶中值, 实际命中率, 样本数}；Brier Score（neutral 按 0.5 处理，可配置剔除）；校准曲线 API + 页面四
- 切片指标：按行业/市值桶/市场环境（基准 250 日均线牛熊判定）/持有期桶 输出 {样本数, 胜率, 平均超额}（`metrics_by_segment`）
- 观点详情页 `/predictions/:id`：预测 vs 实际叠加图（entry/target 水平线 + 结算点标记）、观点快照只读渲染、判定信息卡、时间轴
- 版本分段：`agents` 表（model_version/version_seq/retired_at），模型/策略升级后战绩分段封存不跨版本混算（P6）
- 完整性：`rationale_snapshot` 哈希校验任务 `integrity-check`（每日，篡改告警）+ 审计日志

## Capabilities

### New Capabilities

- `track-record-calibration`: 校准分桶、Brier Score、校准页
- `track-record-segments`: 四维切片指标
- `track-record-versioning`: agents 版本分段与 P6 封存语义
- `track-record-integrity`: 快照哈希校验与审计日志

### Modified Capabilities

（无——纯增量）

## Impact

- 依赖：阶段 B 的 `agent_metrics_daily`（切片挂在其 JSON 字段）
- 前端：新增两个页面（详情、校准）；战绩页增加切片面板
- 数据：agents 新表；predictions 增加 agent_id 外键语义（阶段 A 表结构预留列名对齐）
- 前置：建议在阶段 B 之后立项（指标快照是切片的数据源）
