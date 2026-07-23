"""DSML 防御性解析单元测试。

验证 _parse_dsml_from_text 能从 DeepSeek 泄漏的 DSML 文本标记中还原工具调用，
并清除标记文本，避免泄漏给用户。

背景：DeepSeek（V3.2+/V4）偶发以 DSML 文本标记输出工具调用，而非结构化
tool_calls 字段。litellm 不解析该格式，标记会作为 content 泄漏。
"""

import pytest

from finance_agent.harness.loop import _parse_dsml_from_text

# 全角竖线 ｜ = U+FF5C，数学双竖线 ‖ = U+2016（DSML 标记的实际字符）
BAR = "\uff5c"  # ｜
DBL = "\u2016"  # ‖


def test_no_dsml_returns_untouched():
    """无 DSML 标记的普通文本应原样返回。"""
    text = "你想重点关注贵州茅台的哪个方面？"
    calls, cleaned = _parse_dsml_from_text(text)
    assert calls == []
    assert cleaned == text


def test_user_reported_example():
    """用户报告的原始 DSML 泄漏文本（空参数 invoke）。"""
    text = (
        f"<{BAR}{BAR}DSML{BAR}{BAR}tool_calls> "
        f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"search_stock\"> "
        f"</{BAR}{BAR}DSML{BAR}{BAR}invoke> "
        f"</{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
    )
    calls, cleaned = _parse_dsml_from_text(text)
    assert len(calls) == 1
    assert calls[0].name == "search_stock"
    assert calls[0].arguments == {}
    assert "DSML" not in cleaned
    assert BAR not in cleaned


def test_invoke_with_parameter():
    """带 parameter 标签的 invoke。"""
    text = (
        f"<{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
        f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"search_stock\">"
        f"<{BAR}{BAR}DSML{BAR}{BAR}parameter name=\"query\">茅台</{BAR}{BAR}DSML{BAR}{BAR}parameter>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}invoke>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
    )
    calls, cleaned = _parse_dsml_from_text(text)
    assert len(calls) == 1
    assert calls[0].name == "search_stock"
    assert calls[0].arguments == {"query": "茅台"}
    assert "DSML" not in cleaned


def test_mixed_text_preserves_non_dsml():
    """DSML 标记前的普通文本应保留。"""
    text = (
        "我先搜索一下。"
        f"<{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
        f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"search_stock\">"
        f"<{BAR}{BAR}DSML{BAR}{BAR}parameter name=\"query\">茅台</{BAR}{BAR}DSML{BAR}{BAR}parameter>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}invoke>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
    )
    calls, cleaned = _parse_dsml_from_text(text)
    assert len(calls) == 1
    assert calls[0].name == "search_stock"
    assert calls[0].arguments == {"query": "茅台"}
    assert "我先搜索一下" in cleaned
    assert "DSML" not in cleaned


def test_lowercase_dsml_with_math_bar_variant():
    """小写 dsml + 数学双竖线 ‖(U+2016) 变体也应识别。"""
    text = f"<{DBL}dsml{DBL}invoke name=\"web_search\"></{DBL}dsml{DBL}invoke>"
    calls, cleaned = _parse_dsml_from_text(text)
    assert len(calls) == 1
    assert calls[0].name == "web_search"
    assert "dsml" not in cleaned.lower()


def test_multiple_invokes():
    """多个 invoke 应全部解析。"""
    text = (
        f"<{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
        f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"search_stock\">"
        f"<{BAR}{BAR}DSML{BAR}{BAR}parameter name=\"query\">茅台</{BAR}{BAR}DSML{BAR}{BAR}parameter>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}invoke>"
        f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"web_search\">"
        f"<{BAR}{BAR}DSML{BAR}{BAR}parameter name=\"query\">白酒板块</{BAR}{BAR}DSML{BAR}{BAR}parameter>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}invoke>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
    )
    calls, cleaned = _parse_dsml_from_text(text)
    assert len(calls) == 2
    assert calls[0].name == "search_stock"
    assert calls[0].arguments == {"query": "茅台"}
    assert calls[1].name == "web_search"
    assert calls[1].arguments == {"query": "白酒板块"}
    assert "DSML" not in cleaned


# ───────────────────────────────────────────────
# 端到端集成测试：ReAct 循环处理 DSML 文本
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_react_loop_parses_dsml_as_tool_call():
    """端到端：LLM 返回 DSML 文本（无结构化 tool_calls）时，Agent 应解析为工具调用并执行。

    回归用户报告的 bug：深度模式返回 `<｜｜DSML｜｜tool_calls>...` 乱码，
    Agent 应从 DSML 文本还原工具调用，而非把标记当作回复泄漏给用户。
    """
    from finance_agent.harness import ActionType, Agent, PermissionMode
    from finance_agent.harness.llm_client import LLMResponse

    class _MockLLM:
        def __init__(self, responses):
            self._responses = responses
            self._i = 0

        async def chat_stream(self, messages=None, tools=None, temperature=0.7, tool_choice=None):
            if self._i >= len(self._responses):
                yield LLMResponse(text_delta="", is_finished=True)
                return
            chunks = self._responses[self._i]
            self._i += 1  # 先递增，避免消费者 is_finished 时 break 关闭 generator 导致不递增
            for chunk in chunks:
                yield chunk

    async def echo(text: str) -> str:
        """回显输入文本

        Args:
            text: 要回显的文本
        """
        return f"echo: {text}"

    dsml = (
        f"<{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
        f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"echo\">"
        f"<{BAR}{BAR}DSML{BAR}{BAR}parameter name=\"text\">hello</{BAR}{BAR}DSML{BAR}{BAR}parameter>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}invoke>"
        f"</{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
    )

    mock_llm = _MockLLM(
        [
            [LLMResponse(text_delta=dsml, is_finished=True)],
            [LLMResponse(text_delta="完成", is_finished=True)],
        ]
    )

    agent = Agent(
        model="mock",
        api_key="test",
        permission_mode=PermissionMode.YOLO,
        max_iterations=5,
        llm=mock_llm,
    )
    agent.tools.register(echo, name="echo")

    events = []
    async for event in agent.run("测试 DSML"):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert ActionType.TOOL_CALL in event_types, f"DSML 未被解析为工具调用，事件: {event_types}"
    assert ActionType.TOOL_RESULT in event_types, f"缺少 TOOL_RESULT，事件: {event_types}"

    # DSML 标记不应泄漏到任何事件内容
    for e in events:
        content = e.content or ""
        assert "DSML" not in content, f"DSML 标记泄漏到事件: {e.event_type} = {content!r}"
        assert BAR not in content, f"DSML 竖线泄漏到事件: {e.event_type} = {content!r}"

