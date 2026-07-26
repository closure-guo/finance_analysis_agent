# Delta for e2e-core-specs

## ADDED Requirements

### Requirement: Streaming Spec Verifies Incremental Render and Indicator Lifecycle

The E2E test suite SHALL include `streaming.spec.ts` that verifies the quick chat mode's incremental SSE rendering: content accumulates, streaming indicator appears then disappears, and interrupt triggers error display with retry option.

#### Scenario: 快速模式流式增量渲染

- **GIVEN** 双 webServer 已启动（TESTING=1，LLM stub 激活）
- **WHEN** 用户在输入框输入文本并发送（POST /api/chat）
- **THEN** 流式状态指示器（data-testid="stream-status"）出现
- **AND** 流式输出区域（data-testid="stream-output"）内容逐步累积
- **AND** 流式状态指示器消失（流结束）

#### Scenario: 流式中断显示错误与重试

- **GIVEN** 双 webServer 已启动
- **WHEN** 用户发送消息，但 `page.route('**/api/chat', route => route.abort())` 拦截请求
- **THEN** 错误提示（data-testid="stream-error"）可见
- **AND** 重试按钮（data-testid="retry-button"）可见

### Requirement: Contract Spec Verifies Request Response SSE

The E2E test suite SHALL include `contract.spec.ts` that verifies the frontend sends a correct POST /api/chat request and the backend responds with SSE stream.

#### Scenario: 点击发送发出正确请求并收到 SSE

- **GIVEN** 双 webServer 已启动（TESTING=1）
- **WHEN** 用户输入文本并点击发送按钮
- **THEN** 捕获到 POST /api/chat 请求
- **AND** 请求体含 message、user_id、api_key 字段
- **AND** 响应 Content-Type 含 text/event-stream

### Requirement: Interaction Spec Verifies Button Disabled State

The E2E test suite SHALL include `interaction.spec.ts` that verifies the send button is disabled during streaming.

#### Scenario: 发送中按钮禁用并变色

- **GIVEN** 双 webServer 已启动（TESTING=1）
- **WHEN** 用户输入文本并点击发送按钮（data-testid="send-button"）
- **THEN** 发送按钮变为 disabled 状态
- **AND** 发送按钮 opacity 变为 0.5（终态，等 transition 完成）
