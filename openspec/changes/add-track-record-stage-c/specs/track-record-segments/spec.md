# track-record-segments Specification Delta

## ADDED Requirements

### Requirement: 四维切片指标

系统 SHALL 支持按行业/市值桶/市场环境/持有期桶切片输出 {样本数, 胜率, 平均超额}；市场环境按基准 250 日均线判定牛熊。

#### Scenario: 切片查询

- **WHEN** 请求切片指标 API 并指定维度
- **THEN** 返回该维度各分段的样本数/胜率/平均超额，n<10 分段按显著性规则标注

### Requirement: 观点详情页

系统 SHALL 提供 `/predictions/:id` 详情页：预测 vs 实际走势叠加图（entry/target 水平线 + 结算点标记）、观点快照只读渲染、判定信息卡、时间轴。

#### Scenario: 详情页渲染

- **WHEN** 用户从战绩列表点击进入某条观点详情
- **THEN** 页面展示叠加图、冻结字段快照（只读）、判定结果与关键事件时间轴
