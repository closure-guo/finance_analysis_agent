## 1. open_span helper 基础设施

- [x] 1.1 在 tests/ 下编写 `open_span` helper 的失败单元测试：覆盖「Langfuse 已配置时创建 span」「未配置时返回 nullcontext」「span 创建异常时降级」三个场景（对应 spec 的 open_span helper 优雅降级 requirement）
- [x]1.2 在 [langfuse_tracing.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/langfuse_tracing.py) 实现 `open_span(name, input)` 上下文管理器：复用 `get_langfuse()` 单例，已配置时调用 `start_as_current_observation(name=name, as_type="span", input=input)`，未配置或异常时返回 `contextlib.nullcontext()`；变量 camelCase、注释中文

## 2. 工具调用 span（loop.py）

- [x]2.1 编写工具调用 span 的失败单元测试：mock Langfuse 客户端，验证 ReAct Agent 执行工具时创建了 `tool:{name}` span、input 含 args、output 含 result、span 挂在 react_loop 下（对应 spec 的工具调用 span 可观测 requirement）
- [x]2.2 在 [harness/loop.py:497-512](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py#L497-L512) 工具执行处用 `open_span(name=f"tool:{toolName}", input={"args": args})` 包裹工具执行，执行完成后 `obs.update(output={"result": result})`

## 3. 网络搜索 span（web_search.py）

- [x]3.1 编写网络搜索 span 的失败单元测试：mock Langfuse 客户端，验证搜索函数执行时创建了 `search_api_call` span、input 含 query 与 max_results、output 含 count、作为调用方子 span（对应 spec 的网络搜索 span 可观测 requirement）
- [x]3.2 在 [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 搜索执行函数内用 `open_span(name="search_api_call", input={"query": query, "max_results": maxResults})` 包裹搜索调用，完成后 `obs.update(output={"count": len(results)})`

## 4. 业务行为不变验证

- [x]4.1 编写「span 对 SSE 事件流透明」的回归测试：对比有/无 span 时 SSE 事件流（类型、顺序、内容）完全一致（对应 spec 的 span 不改变业务行为 requirement）
- [x]4.2 编写「span 异常时业务结果不变」测试：强制 span 创建抛异常，验证工具执行结果/搜索结果仍正确返回

## 5. 质量门禁与人工验证

- [x]5.1 `uv run pytest` 全过，`uv run ruff check` 无错误，`uv run mypy` 无错误
- [x]5.2 在 tests/scripts/ 编写手动验证脚本：启动服务后触发一次 chat（含工具调用 + 搜索），拉取 Langfuse trace，断言 trace 含 `tool:{name}` 与 `search_api_call` span 且父子关系正确
- [x]5.3 在 tests/validation/ 落人工验证报告：记录 Langfuse trace 截图与 span 树结构，确认「LLM 回复 / 工具调用 / 网络搜索」三类操作在 trace 中分层可观测
