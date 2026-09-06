# Delta for chat-stream

## ADDED Requirements

### Requirement: 流式事件真实性（禁系统冒充）

LLM 事件通道（thinking_token / tool_call / tool_result）SHALL 仅承载模型真实推理与真实工具调用：系统 SHALL NOT 生成伪造的 thinking_token（如预搜索说明、节点执行/完成文案）、伪造的 tool_call，SHALL NOT 在用户消息中预注入搜索结果替代模型自主决策。时效性查询的搜索 SHALL 由模型基于 reasoning 自行决定并发起。管线节点进度 SHALL 经管线事件（node_start / node_complete / 节点时序）呈现，SHALL NOT 经 thinking_token 旁路下发。

#### Scenario: 时效性查询由模型自主搜索

- GIVEN 深度/快速通道收到不含股票代码、含时效性关键词的查询
- WHEN 流式输出
- THEN 系统 SHALL NOT 发出预生成的 thinking_token / tool_call / search_start（预搜索旁路）
- AND 模型若判定需要搜索，SHALL 经 ReAct 工具调用真实发起 web_search（真实思考 + 真实工具事件）

#### Scenario: 管线进度不经思考旁路

- GIVEN 深度分析管线运行中
- WHEN 节点开始或完成
- THEN 系统 SHALL NOT 生成 `▶ …` / `✓ …` 形式的 thinking_token
- AND 节点进度 SHALL 由 node_start / node_complete 及管线时间轴承载

#### Scenario: 节点真实思考不受影响

- GIVEN 深度分析管线运行中
- WHEN 节点 LLM 产生真实 thinking 输出
- THEN 该 thinking SHALL 照常经 thinking_token 转发（custom mode 转发路径保留）
