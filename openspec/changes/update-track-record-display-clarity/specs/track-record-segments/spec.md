# Delta for track-record-segments

## MODIFIED Requirements

### Requirement: 观点详情页

系统 SHALL 提供 `/predictions/:id` 详情页：预测 vs 实际走势叠加图（entry/target 水平线 + 结算点标记）、观点快照只读渲染、判定信息卡、时间轴。判定信息卡 SHALL 使用与观点日志一致的中文展示：方向 SHALL 显示中文标签（看多/看空/中性），SHALL NOT 显示英文原始值（long/short/neutral）；判定规则 SHALL 显示中文释义（`expiry`→到期结算、`superseded`→被新观点替代·提前结算、`duplicate_of_day`→同日重复关闭、`stale_no_market`→长期无行情），原始英文值 SHALL 以辅助形式（如悬浮提示）保留供排查。
(Previously: 判定信息卡直接渲染后端原始值——方向显示英文（如「short」）、判定规则显示英文技术词（如「superseded」），与列表页中文标签不一致。)

#### Scenario: 详情页渲染

- **WHEN** 用户从战绩列表点击进入某条观点详情
- **THEN** 页面展示叠加图、冻结字段快照（只读）、判定结果与关键事件时间轴

#### Scenario: 方向中文标签

- **GIVEN** 某观点 direction=short
- **WHEN** 渲染详情页判定信息卡
- **THEN** 方向 SHALL 显示「看空」
- **AND** SHALL NOT 显示「short」原文作为主展示值

#### Scenario: 判定规则中文释义

- **GIVEN** 某观点 resolution_rule=superseded
- **WHEN** 渲染详情页判定信息卡
- **THEN** 判定规则 SHALL 显示「被新观点替代·提前结算」
- **AND** 原始值「superseded」SHALL 以辅助提示形式可查
