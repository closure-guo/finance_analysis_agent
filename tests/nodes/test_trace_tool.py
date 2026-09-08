"""add-toolcall-evaluation：agent_factory._trace_tool 埋点守卫（selectively wrap）。

埋点语义：Langfuse 未配置时原样直通零开销；配置时包 span（入参/输出/异常
metadata.tool_error），行为（返回值与异常传播）与未埋点完全一致。
"""

from unittest.mock import patch

from finance_agent.agent_factory import _trace_tool


class FakeSpan:
    """对齐 Langfuse v4 LangfuseSpan：仅 update(output/metadata) 写回。"""

    def __init__(self):
        self.output = None
        self.metadata = {}

    def update(self, *, output=None, metadata=None):
        if output is not None:
            self.output = output
        if metadata:
            self.metadata.update(metadata)


class FakeClient:
    def __init__(self):
        self.spans = []

    def start_as_current_observation(self, *, as_type, name, input):
        span = FakeSpan()
        self.spans.append((name, input, span))
        return _SpanCtx(span)


class _SpanCtx:
    def __init__(self, span):
        self._span = span

    def __enter__(self):
        return self._span

    def __exit__(self, *exc):
        return False


@patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None)
def test_pass_through_when_no_client(mock_lf):
    marker = []

    @_trace_tool("web_search")
    def f(query):
        marker.append(query)
        return {"ok": True}

    assert f("x") == {"ok": True}
    assert marker == ["x"]
    mock_lf.assert_called_once()


def test_span_written_with_args_output():
    client = FakeClient()
    with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=client):

        @_trace_tool("web_search")
        def f(query):
            return "结果"

        assert f(query="茅台") == "结果"
    name, inp, span = client.spans[0]
    assert name == "tool_call:web_search"
    assert inp == {"call": {"query": "茅台"}}
    assert span.output == "结果"


def test_error_captured_and_re_raised():
    client = FakeClient()
    with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=client):

        @_trace_tool("web_search")
        def f(query):
            raise RuntimeError("网络失败")

        try:
            f("x")
            raise AssertionError("应传播异常")
        except RuntimeError as e:
            assert str(e) == "网络失败"
    _, _, span = client.spans[0]
    assert span.metadata.get("tool_error") == "网络失败"


def test_wraps_preserves_name():
    def f():  # pragma: no cover
        return 1

    assert _trace_tool("web_search")(f).__wrapped__ is f


class TestAsyncToolPath:
    def test_async_tool_awaited_and_spanned(self):
        import asyncio

        client = FakeClient()

        async def run():
            with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=client):

                @_trace_tool("web_search")
                async def f(query):
                    return "异步结果"

                return await f(query="茅台")

        assert asyncio.run(run()) == "异步结果"
        _, inp, span = client.spans[0]
        assert inp == {"call": {"query": "茅台"}}
        assert span.output == "异步结果"

    def test_async_passthrough_without_client(self):
        import asyncio

        async def run():
            with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None):

                @_trace_tool("web_search")
                async def f(query):
                    return f"r:{query}"

                return await f("x")

        assert asyncio.run(run()) == "r:x"
