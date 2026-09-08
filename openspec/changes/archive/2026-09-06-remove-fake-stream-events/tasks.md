# Tasks: remove-fake-stream-events

- [x] 1. 删除 ① `_run_react_analysis` 预搜索块（伪 thinking/tool_call、手工 search_start/search_result、结果注入用户消息）
- [x] 2. 删除 ② ③ `_run_graph_streaming` 节点开始/完成伪 thinking_token 及 `_NODE_THINKING` 常量
- [x] 3. 回归：时效性查询流式无系统生成事件（TESTING stub 集成测试）；节点真实 thinking 转发保留（既有测试不回退）
- [x] 4. 全量验证：uv run pytest / ruff / mypy；前端 vitest；E2E stub 门禁全绿
- [x] 5. 真实 LLM 验证：时效性查询模型自主搜索（真实思考 + 真实工具调用，无预注入）
- [x] 6. transparent-system-events 标记 superseded 移入 archive；验证报告落 tests/validation/
