# Delta Spec: frontend

## ADDED Requirements

### Requirement: Restore Current Session On Refresh

系统 SHALL 在浏览器刷新/重新加载后自动恢复用户此前正在查看的会话，无需用户手动点击侧边栏。前端 SHALL 将 `currentSessionId` 持久化到 localStorage（key：`fa_current_session_id`），并在会话选中、创建、删除、新建分析时同步维护该值。应用初始化时，若持久化的 `currentSessionId` 存在且对应会话仍存在于后端，前端 SHALL 自动执行与「手动点击会话」等价的恢复逻辑（加载会话详情、重建消息列表、若会话 running 则重连事件流），直接恢复到该会话视图而非停留在空状态首页。

#### Scenario: 刷新后自动恢复进行中的会话

- **GIVEN** 用户在某会话（深度分析或快速对话）进行中刷新了页面，localStorage 已持久化该会话的 `currentSessionId`
- **WHEN** 应用初始化并完成会话列表加载
- **THEN** 前端 SHALL 自动选中该会话，向 GET /api/sessions/{sessionId} 请求详情
- **AND** 从 chat_history（含 agentTimeline）重建消息列表（工具调用、思考、assistant 文本）
- **AND** 若会话 status 为 running，经 GET /api/sessions/{id}/stream 重连事件流，输出从断点继续增长
- **AND** 全程无需用户手动点击侧边栏

#### Scenario: 刷新后自动恢复已完成的会话

- **GIVEN** 用户在某已完成（completed）会话视图刷新了页面
- **WHEN** 应用初始化
- **THEN** 前端 SHALL 自动恢复该会话的报告/对话视图
- **AND** 按 session_type 锁定模式，appState 切换为对应视图（report / 对话）

#### Scenario: 持久化会话已删除时回退空态

- **GIVEN** localStorage 存在持久化的 `currentSessionId`，但该会话在后端已被删除
- **WHEN** 应用初始化并尝试恢复
- **THEN** 前端 SHALL 清除该 localStorage 项
- **AND** 回退到空状态首页，不报错、不显示无效会话

#### Scenario: 无持久化会话时保持空态首页

- **GIVEN** localStorage 不存在 `fa_current_session_id`（首次访问或已清空）
- **WHEN** 应用初始化
- **THEN** 前端 SHALL 显示空状态首页（维持现有 Empty State Landing Page 行为）

#### Scenario: currentSessionId 生命周期同步

- **GIVEN** 应用运行中
- **WHEN** 用户选中会话、创建新会话（session_created）、删除当前会话、或点击「新建分析」
- **THEN** 前端 SHALL 同步更新或清除 localStorage 的 `fa_current_session_id`
- **AND** 删除当前会话、新建分析时清除该项（对应 currentSessionId 置 null）
