# Delta for frontend

## ADDED Requirements

### Requirement: 跑赢指数对比卡片

战绩页(track-record)SHALL 提供「跑赢指数对比」卡片:调用 `GET /api/v1/track-record/index-compare`,展示选定跨度内组合区间收益与各指数区间收益的横向对比条(组合条置顶,指数条按收益降序),每条含指数名、区间收益百分比与跑赢标记(跑赢 ↑ 绿 / 跑输 ↓ 红 / 无数据灰显);卡片标题 SHALL 展示「跑赢 N/M 个指数」摘要(N=beat=true 数,M=beat 非 null 数;M=0 时展示空态文案)。时间跨度 SHALL 复用战绩页既有跨度偏好(fa_track_prefs.timeSpan,进页时与净值图同源读取一次;偏好变更经重新进入页面生效,与净值图行为一致);指数 effective_start_date 非窗口首日时 SHALL 在该指数条上标注实际起算日。

#### Scenario: 正常渲染

- **GIVEN** index-compare 返回窗口内组合收益 5.2%,五只指数中三只低于 5.2%
- **WHEN** 用户进入战绩页
- **THEN** 卡片标题展示「跑赢 3/5 个指数」,组合条置顶,指数条按收益降序排列
- **AND** 跑赢指数条带绿色↑标记,跑输带红色↓标记

#### Scenario: 跨度偏好应用

- **GIVEN** 用户在设置中心把默认时间跨度设为「近 3 月」
- **WHEN** 进入战绩页
- **THEN** 对比卡片以 span=3m 请求并渲染,与净值图使用同一跨度偏好

#### Scenario: 指数缺数灰显

- **GIVEN** 某指数 return/beat 为 null
- **WHEN** 卡片渲染
- **THEN** 该指数条灰显并标注「无数据」,不参与 N/M 摘要分母

#### Scenario: 组合净值不足空态

- **GIVEN** index-compare 返回 agent_return 为 null
- **WHEN** 卡片渲染
- **THEN** 展示空态文案(如「净值数据积累中」),SHALL NOT 渲染对比条与 N/M 摘要
