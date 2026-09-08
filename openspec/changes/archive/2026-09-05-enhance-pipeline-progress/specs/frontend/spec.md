# frontend delta: enhance-pipeline-progress

## ADDED Requirements

### Requirement: 管线步骤时间线

管线进度 SHALL 以步骤时间线渲染，节点含四态：等待、运行中（高亮 + 呼吸动画）、完成（勾选标记）、失败（红色标记）；时间线 SHALL 随 SSE 管线节点事件实时推进。

#### Scenario: 事件驱动状态推进

- **GIVEN** 深度分析管线运行中
- **WHEN** 某节点完成事件到达
- **THEN** 该节点 SHALL 变为完成态，下一节点变为运行中
- **AND** 无需刷新页面

### Requirement: 节点已用时

当前运行节点 SHALL 显示已用时，计时源 SHALL 为快照 `pipeline_start_ts`；快照缺该字段时回退本地时间。

#### Scenario: 刷新后已用时不归零

- **GIVEN** 管线已运行若干分钟后刷新页面
- **WHEN** 时间线重建
- **THEN** 已用时 SHALL 以快照时间戳计算，不归零

### Requirement: 节点展开与完成折叠

运行中/完成节点 SHALL 可展开查看阶段摘要；管线完成后时间线 SHALL 整体折叠为单行摘要条（阶段数 + 总用时），点击可再展开。

#### Scenario: 完成后折叠

- **WHEN** 管线完成并发出 report_ready
- **THEN** 时间线 SHALL 折叠为摘要条
- **AND** 点击摘要条可展开查看全部节点
