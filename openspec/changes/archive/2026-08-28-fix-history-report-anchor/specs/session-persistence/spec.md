# Session Persistence Delta: fix-history-report-anchor

## ADDED Requirements

### Requirement: 管线触发锚点持久化

系统 SHALL 在深度分析管线启动时将触发锚点持久化到 sessions 表 `pipeline_anchor` 列（INTEGER，NULL 表示无锚点）。锚点 = 启动时刻 chat_history 中最后一条 role='user' 条目的索引 + 1，即"触发本轮分析的用户消息之后"，供前端历史重建时定位报告消息插入位置。

锚点 SHALL 在两条管线启动路径上写入：fast path（已知股票代码直接启动 PipelineRunner）与 ReAct 路径（run_deep_analysis 工具实际启动管线时）。锚定 user 消息而非取 chat_history 长度，避免 ReAct 路径 assistant 在途增量 upsert 导致锚点随持久化时机抖动。

#### Scenario: fast path 写入锚点

- **GIVEN** 新会话首次输入即解析出股票代码（fast path）
- **WHEN** 用户消息追加到 chat_history 后、管线启动前
- **THEN** 系统 SHALL 将 pipeline_anchor 写为 1（chat_history 仅一条 user 消息）
- **AND** 旧库启动时经幂等 ALTER TABLE 迁移添加 pipeline_anchor 列，既有行保持 NULL

#### Scenario: ReAct 路径写入锚点

- **GIVEN** 多轮澄清会话的 chat_history 为 [user1, assistant1, user2]
- **WHEN** ReAct Agent 调用 run_deep_analysis 工具实际启动管线
- **THEN** 系统 SHALL 将 pipeline_anchor 写为 3（最后一条 user 消息 user2 的索引 + 1）
- **AND** 当前轮 assistant 在途消息的增量 upsert 不影响锚点值

#### Scenario: 会话详情返回锚点

- **GIVEN** 某会话的 pipeline_anchor 已写入
- **WHEN** 前端请求 GET /api/sessions/{sessionId}
- **THEN** 响应 SHALL 包含 pipeline_anchor 整数值
- **AND** 未写入过的会话（旧数据）返回 NULL/缺失，前端走回退逻辑
