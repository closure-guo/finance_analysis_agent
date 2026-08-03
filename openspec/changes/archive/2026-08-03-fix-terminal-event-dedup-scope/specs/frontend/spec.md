## ADDED Requirements

### Requirement: Streaming State Defensive Cleanup

系统 SHALL 保证 SSE 流结束时（reader 正常结束或连接异常断开）助手消息的流式状态被清除，使流式游标不依赖单一终态事件。当 SSE 流结束但前端未收到终态事件（done/interrupted/error）时，前端 SHALL 将当前轮次的助手消息 `streaming` 置为 false。终态事件处理与防御性清理对 `streaming` 的设置 SHALL 幂等，重复设置无副作用。

#### Scenario: 流结束未收到终态事件时清除游标

- **GIVEN** 深度分析或快速对话 SSE 流进行中，助手消息 streaming=true
- **WHEN** SSE reader 正常结束（读到流末尾）但未收到 done/interrupted/error 终态事件
- **THEN** 前端 SHALL 将助手消息 streaming 置为 false
- **AND** 流式游标消失，用户可继续追问

#### Scenario: 连接异常断开时清除游标

- **GIVEN** 深度分析或快速对话 SSE 流进行中，助手消息 streaming=true
- **WHEN** 发生非 AbortError 的连接错误导致流中断
- **THEN** 前端 SHALL 将助手消息 streaming 置为 false
- **AND** 展示连接错误消息

#### Scenario: 终态事件与防御性清理幂等

- **GIVEN** SSE 流进行中，助手消息 streaming=true
- **WHEN** 先收到 done 终态事件（streaming 置 false），随后 reader 结束触发防御性清理
- **THEN** 防御性清理再次设置 streaming=false 无副作用
- **AND** 游标保持消失状态，不闪烁或复活

### Requirement: Deep Mode chat_done Event Routing

深度模式（`startAnalysis`）的 SSE 事件循环 SHALL 将 `chat_done` 事件路由到对话流共享处理函数（`handleChatStreamEvent`），与快速模式（`quickChat`）保持一致。`chat_done` 事件经 `applyChatStreamEvent` 处理后 SHALL 将助手消息 `streaming` 置为 false 并收口所有 thinking item。

#### Scenario: 深度模式澄清阶段收到 chat_done 清除流式状态

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段），助手消息 streaming=true
- **WHEN** 收到 `chat_done` 事件
- **THEN** 事件 SHALL 经 `handleChatStreamEvent` 处理，助手消息 streaming 置为 false
- **AND** 所有 thinking item 收口并提取标题写入 title 字段
- **AND** 流式游标消失

#### Scenario: 深度模式管线运行期间不误处理 chat_done

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 不为空（管线模式）
- **WHEN** 收到 `chat_done` 事件
- **THEN** 事件 SHALL 经 `handleChatStreamEvent` 处理（写入对话流消息 timeline）
- **AND** 管线消息不受影响，管线进度继续由管线事件驱动
