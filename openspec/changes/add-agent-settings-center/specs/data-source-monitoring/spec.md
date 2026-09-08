# Delta for data-source-monitoring

## ADDED Requirements

### Requirement: 数据源命中与失败计数（非侵入）
系统 SHALL 在数据缓存层维护进程内命中/未命中/失败计数，计数 SHALL NOT 改变 fetch 重试/降级/回退逻辑；计数为进程内聚合，进程重启后清零。

#### Scenario: 命中计数
- **GIVEN** 分析请求命中数据缓存
- **THEN** 命中计数 SHALL 加 1
- **AND** 计数维护 SHALL 不改变缓存读取结果

#### Scenario: 未命中计数
- **GIVEN** 分析请求未命中数据缓存（缓存不存在或已过期）
- **THEN** 未命中计数 SHALL 加 1

#### Scenario: 拉取失败计数
- **GIVEN** 数据源拉取请求失败
- **THEN** 失败计数 SHALL 加 1
- **AND** 既有重试/降级/回退行为 SHALL 保持不变

#### Scenario: 计数为进程内聚合
- **GIVEN** 后端进程重启
- **THEN** 命中/未命中/失败计数 SHALL 归零

### Requirement: 数据新鲜度暴露
系统 SHALL 暴露每条缓存数据的新鲜度（过期时间），供监控展示距过期剩余时间，并将已过期条目标记为待清理。

#### Scenario: 返回条目新鲜度
- **GIVEN** 数据缓存存在条目
- **WHEN** 前端请求数据源状态
- **THEN** 响应 SHALL 包含各条目的过期时间/剩余时间

#### Scenario: 已过期条目标记
- **GIVEN** 数据缓存存在已超过过期时间的条目
- **THEN** 数据源状态响应 SHALL 将该条目标记为「已过期/待清理」

### Requirement: 数据源状态端点
系统 SHALL 提供 `GET /api/data-source/status` 端点，聚合返回命中/未命中/失败计数与各数据类别/代码的新鲜度列表。

#### Scenario: 返回计数与新鲜度
- **GIVEN** 系统已有若干缓存命中/未命中/失败记录
- **WHEN** 前端调用 `GET /api/data-source/status`
- **THEN** 响应 SHALL 包含命中、未命中、失败计数
- **AND** 响应 SHALL 包含数据新鲜度列表（含已过期标记）

#### Scenario: 无数据时的响应
- **GIVEN** 数据缓存为空且无任何计数记录
- **WHEN** 前端调用 `GET /api/data-source/status`
- **THEN** 响应 SHALL 返回零计数与空新鲜度列表
- **AND** 响应 SHALL NOT 报错

### Requirement: 前端数据监控分区
系统 SHALL 在设置中心页提供「数据监控」分区，展示命中/未命中/失败计数与数据新鲜度列表，并处理加载与错误态。

#### Scenario: 展示监控计数
- **GIVEN** 用户进入设置中心页「数据监控」分区
- **THEN** 分区 SHALL 展示命中、未命中、失败计数的汇总卡

#### Scenario: 展示新鲜度列表
- **GIVEN** 数据源状态端点返回新鲜度列表
- **THEN** 分区 SHALL 以列表展示各条目新鲜度与已过期标记

#### Scenario: 加载与错误态
- **WHEN** 数据源状态请求进行中
- **THEN** 分区 SHALL 展示加载态
- **WHEN** 数据源状态请求失败
- **THEN** 分区 SHALL 展示错误信息，且不阻塞其他分区操作
