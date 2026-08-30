# frontend delta: add-assistant-ui-thread

## MODIFIED Requirements

### Requirement: quick 模式消息流渲染层（对应既有 frontend 能力的 quick 对话渲染）

quick 模式（通用问答）消息流的渲染实现 SHALL 替换为 assistant-ui Thread + AG-UI runtime；渲染语义约束：发送入口、流式增量呈现、回复完成态、历史恢复、会话切换守卫行为 SHALL 与替换前一致。既有前端测试中针对 quick 模式行为语义的用例 SHALL 无修改通过（纯实现层选择器/结构差异的用例允许随实现等价迁移，迁移清单 SHALL 记录在验证报告）。

#### Scenario: quick 模式行为语义不变

- **GIVEN** quick 模式消息流渲染层已替换为 assistant-ui
- **WHEN** 用户执行发送、等待流式回复、切换会话、刷新恢复
- **THEN** 各环节用户可感知行为与替换前一致
- **AND** 深度模式相关测试零修改通过
