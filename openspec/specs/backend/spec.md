# backend Specification

## Purpose
TBD - created by archiving change fix-analysis-ux-polish. Update Purpose after archive.
## Requirements
### Requirement: 管线快照携带启动时间戳

后端在持久化管线进度快照时 SHALL 包含管线启动时间戳 `pipeline_start_ts`（Unix 毫秒），用于前端在刷新重建 running 管线时还原「已用时」计时，避免使用前端本地时间导致刷新归零。

#### Scenario: 快照包含 pipeline_start_ts

- GIVEN 一次深度分析管线已启动并记录 `_pipeline_start_time`
- WHEN `_persist_snapshot` 将 layerTree 组装为快照并落库
- THEN 快照 JSON SHALL 包含 `pipeline_start_ts` 字段
- AND 其值 SHALL 等于管线启动时刻（与 `_pipeline_start_time` 同源，毫秒精度）

#### Scenario: 刷新重建时已用时不归零

- GIVEN 管线运行中且快照已持久化（含 `pipeline_start_ts`）
- WHEN 前端刷新页面并重建 running 管线消息
- THEN 前端 SHALL 以快照 `pipeline_start_ts` 作为计时起点
- AND 「已用时」SHALL 反映自管线启动以来的真实时长（而非自刷新时刻）

