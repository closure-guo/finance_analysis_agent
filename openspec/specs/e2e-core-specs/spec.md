# E2E Core Specs Specification

> 来源：change `add-e2e-core-specs`（E2E 核心测试用例规范）
> 基线构建日期：2026-07-26
> 说明：本 spec 从 change `add-e2e-core-specs` 的 delta 同步而来，定义 E2E 核心测试用例（流式渲染、契约验证、交互状态生命周期）的行为契约。

## Purpose

定义 E2E 核心测试用例的行为契约，覆盖三个核心 spec 文件，验证从前端 UI 到后端 SSE 流式的完整链路：

- `streaming.spec.ts`：验证快速模式 SSE 流式增量渲染与流式中断错误展示
- `contract.spec.ts`：验证前后端 POST /api/chat 请求体与 SSE 响应契约
- `interaction.spec.ts`：验证流式状态指示器的可见性生命周期

## Requirements

---

### Requirement: Streaming Spec Verifies Incremental Render and Indicator Lifecycle

The E2E test suite SHALL include `streaming.spec.ts` that verifies the quick chat mode's incremental SSE rendering: content accumulates, streaming indicator appears then disappears, and interrupt triggers error display with retry option.

#### Scenario: 快速模式流式增量渲染

- **GIVEN** 双 webServer 已启动（TESTING=1，LLM stub 激活）
- **WHEN** 用户在输入框输入文本并发送（POST /api/chat）
- **THEN** 流式状态指示器（data-testid="stream-status"）出现
- **AND** 流式输出区域（data-testid="stream-output"）内容逐步累积
- **AND** 流式状态指示器消失（流结束）

#### Scenario: 流式中断显示错误

- **GIVEN** 双 webServer 已启动
- **WHEN** 用户发送消息，但 `page.route('**/api/chat', route => route.abort())` 拦截请求
- **THEN** 错误提示（data-testid="stream-error"）可见

### Requirement: Contract Spec Verifies Request Response SSE

The E2E test suite SHALL include `contract.spec.ts` that verifies the frontend sends a correct POST /api/chat request and the backend responds with SSE stream.

#### Scenario: 点击发送发出正确请求并收到 SSE

- **GIVEN** 双 webServer 已启动（TESTING=1）
- **WHEN** 用户输入文本并点击发送按钮
- **THEN** 捕获到 POST /api/chat 请求
- **AND** 请求体含 message、user_id、api_key 字段
- **AND** 响应 Content-Type 含 text/event-stream

### Requirement: Interaction Spec Verifies Streaming State Lifecycle

The E2E test suite SHALL include `interaction.spec.ts` that verifies the streaming state indicator's visibility lifecycle (appears when streaming starts, disappears when streaming ends) as the interaction state verification.

> 备注：原计划断言「发送按钮 disabled + opacity 0.5」，但前端当前未实现流式中按钮禁用行为。改为断言 stream-status 可见性周期作为交互状态验证。按钮 disabled 行为属新功能，待前端实现后另立 delta 补充。

#### Scenario: 流式状态指示器可见性周期

- **GIVEN** 双 webServer 已启动（TESTING=1）
- **WHEN** 用户输入文本并点击发送按钮（data-testid="send-button"）
- **THEN** 流式状态指示器（data-testid="stream-status"）可见（流式开始）
- **AND** 流式状态指示器消失（data-testid="stream-status" hidden，流式结束）

### Requirement: Session Switch Spec Verifies Stream Resumption

E2E 测试 SHALL 覆盖"流式输出中途切换会话再切回"场景：基于 stub 管线发起深度分析，输出进行中切换到另一会话，等待若干事件后继续，切回原会话，断言输出内容从切出位置继续增长且不重复。测试禁止 mock 数据，必须通过前端模拟用户真实点击操作。

#### Scenario: 中途切出再切回，内容继续增长

- **GIVEN** stub 管线深度分析流式输出进行中（节点延迟已配置，窗口足够长）
- **WHEN** 用户点击侧边栏切换到另一会话，等待 2 秒，再点击切回原会话
- **THEN** 原会话的输出内容在切回后继续增长
- **AND** 重放区间的事件不在 UI 中重复渲染（pipeline 卡片、报告文本无重复段落）

#### Scenario: 显式停止后状态为中断

- **GIVEN** stub 管线深度分析流式输出进行中
- **WHEN** 用户点击"停止"按钮
- **THEN** 流式状态结束，半截内容保留并展示中断标记
- **AND** 刷新页面重新加载该会话，中断标记与半截内容仍在

#### Scenario: 运行中的会话拒绝新输入

- **GIVEN** stub 管线深度分析流式输出进行中
- **WHEN** 用户在输入框提交新消息
- **THEN** 展示"生成中"提示，且不发出新的分析请求
