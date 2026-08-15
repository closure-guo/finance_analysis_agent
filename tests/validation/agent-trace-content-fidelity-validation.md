# 人工验证报告: agent-trace-content-fidelity

**日期**: 2026-08-12
**关联 delta**: openspec/changes/agent-trace-content-fidelity/
**E2E 门禁**: 不适用（纯后端 trace 埋点，非交互类变更，§2 判别）

## 验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| reasoning 落 trace | Langfuse generation output.reasoning 含完整思考链 | 单测已锁定 output 结构 `{answer, reasoning}`（`tests/test_litellm_client.py::test_chat_stream_writes_reasoning_to_langfuse_output`、`tests/test_llm.py::test_call_llm_writes_reasoning_to_output`）；「真实 DeepSeek 是否下发 reasoning_content + Langfuse UI 可见」需真 LLM 人工确认 —— 由 @live 用例 `tests/test_trace_content_live.py::test_live_reasoning_streamed_in_thinking_mode` + Langfuse UI 核对 | ⬜ 待人工 |
| tool_calls 落 trace | generation output.tool_calls 含工具名+参数 | 单测已锁定 output.tool_calls 结构（`tests/test_litellm_client.py::test_chat_stream_writes_tool_calls_to_output`、`tests/test_llm.py::test_call_llm_with_tools_writes_tool_calls_to_output`）；「真实 tool calling + Langfuse UI 可见」需真 LLM 人工确认 —— 由 @live 用例 `tests/test_trace_content_live.py::test_live_tool_calls_returned` + Langfuse UI 核对 | ⬜ 待人工 |
| prompt_name/version | generation metadata 含 prompt_name + version | 单测已锁定 metadata 挂载（`tests/test_litellm_client.py::test_chat_stream_attaches_prompt_metadata_from_client_fields`、`tests/test_prompt_loader.py`）；Langfuse UI 中 metadata 实际展示需真 LLM + Langfuse 人工核对 | ⬜ 待人工 |
| AKShare 失败标 ERROR | fetch 失败子 span level=ERROR | 单测锁定：`tests/nodes/test_fetch.py::test_span_marked_error_on_subcall_failure`（子调用失败时 update_current_span level=="ERROR"）、`test_span_naming_uses_data_source_prefix`（span 名 data_source 前缀） | ✅ |
| 降级路径可见 | parse_degraded/retries 在 span metadata | 单测锁定：`tests/nodes/test_analysts.py::test_parse_degraded_marks_span`（degradation=="parse_degraded" + level=="WARNING"）、`tests/test_react_loop.py::test_empty_retry_reports_counts`（retries 计数）、`tests/test_react_loop.py::test_dsml_fallback_reported`（dsml_fallback + count）、`tests/test_llm.py::test_call_llm_with_tools_degraded_records_via_open_span`（降级路径同样记录 tool_calls/reasoning） | ✅ |
| Langfuse 异常不阻断 | get_langfuse=None 时业务正常 | 单测覆盖：`tests/test_langfuse_tracing.py::test_span_creation_exception_degrades`、`test_update_current_span_swallows_exception`、`test_update_current_span_noop_when_unconfigured`、`tests/test_span_business_invariant.py::test_span_transparent_to_sse_events`、`test_search_result_invariant_with_span_exception` | ✅ |

## 结论

[ ] 全部通过，可 archive
[x] 存在待人工确认项：reasoning / tool_calls / prompt 元数据三项的「真实 LLM 行为 + Langfuse UI 可见性」未在本环境验证（无 DEEPSEEK_API_KEY，@live 用例 skip）。待 nightly 跑通 `tests/test_trace_content_live.py` 并在 Langfuse UI 核对 generation output/metadata 后，方可勾「全部通过」archive。后端埋点逻辑（output 结构、span level、降级不阻断）已由 715 项单测全绿锁定，ruff 0 错误，mypy 无新增错误。
