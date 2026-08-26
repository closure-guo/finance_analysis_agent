# Tasks: parse-ark-text-tool-call

- [x] 流式识别过滤器 `ark_tool_call_text`（单测覆盖：完整块转调用 / 标签跨 chunk / 无标签透传 / 未闭合块原样返回）
- [x] `litellm_client.chat_stream` 接线：正文下发走过滤器，finished 时产出结构化 ToolCallRequest（集成测试）
- [x] 全量验证：uv run pytest / ruff check / mypy 通过
