# Delta for e2e-infrastructure

## MODIFIED Requirements

### Requirement: Testing Mode Switch

The system SHALL read the `TESTING` environment variable at startup and expose a module-level `TESTING` boolean constant. When `TESTING == "1"`, the system enters test mode: testing-only endpoints are registered, and the LLM client is replaced with a controlled stub (`StubLLMClient`) that emits fixed text deltas at a controlled pace (replacing F2's placeholder `return None`).

(Previously: F2 占位实现--TESTING=1 时 `_make_llm_client` 返回 None，不创建真实 LiteLLMClient。完整 stub 推迟到 F3。)

#### Scenario: TESTING=1 进入测试模式

- **GIVEN** 环境变量 `TESTING=1` 已设置
- **WHEN** 后端启动
- **THEN** `finance_agent.api.TESTING` 常量为 `True`
- **AND** `/api/test/seed` 与 `/api/test/reset` 端点可访问
- **AND** `agent_factory._make_llm_client` 返回 `StubLLMClient` 实例（非 None 占位，非真实 LiteLLMClient）

#### Scenario: 未设 TESTING 时测试端点 404

- **GIVEN** 环境变量 `TESTING` 未设置或非 `"1"`
- **WHEN** 访问 `/api/test/seed` 或 `/api/test/reset`
- **THEN** 返回 HTTP 404（测试端点在非测试模式下不可用）
