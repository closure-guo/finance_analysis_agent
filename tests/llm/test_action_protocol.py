# tests/llm/test_action_protocol.py
"""ReAct action 文本协议兜底测试（delta Task 3.3，设计档案 §12）。

弱工具 provider（capability.tools=none）降级到文本 action 协议：
<action name="...">{json}</action> → 执行 → <observation> 回填。
纯函数层：解析与格式化，ReAct loop 集成在 Task 3.5。
"""

from __future__ import annotations

from finance_agent.llm.action_protocol import (
    extract_action,
    format_action,
    format_observation,
    is_action_block,
)


class TestExtractAction:
    def test_single_action(self):
        tc = extract_action('<action name="search_stock">{"query": "茅台"}</action>')
        assert tc is not None
        assert tc.name == "search_stock"
        assert tc.arguments == {"query": "茅台"}

    def test_action_with_surrounding_text(self):
        text = '我需要先查行情。\n<action name="get_quote">{"code": "600519"}</action>\n然后判断。'
        tc = extract_action(text)
        assert tc.name == "get_quote"
        assert tc.arguments == {"code": "600519"}

    def test_invalid_json_args(self):
        """参数非 JSON 时按原始文本传递（由执行侧 repair/拒绝）。"""
        tc = extract_action('<action name="search_stock">不是JSON</action>')
        assert tc is not None
        assert tc.arguments == {"raw": "不是JSON"}

    def test_no_action_returns_none(self):
        assert extract_action("纯文本回答，无 action。") is None

    def test_empty_text(self):
        assert extract_action("") is None


class TestFormatting:
    def test_format_action_roundtrip(self):
        text = format_action("search_stock", {"query": "茅台"})
        assert '<action name="search_stock">' in text
        assert '"query"' in text
        tc = extract_action(text)
        assert tc.name == "search_stock"
        assert tc.arguments == {"query": "茅台"}

    def test_format_observation(self):
        obs = format_observation("search_stock", "搜索结果：股价 1700")
        assert '<observation name="search_stock">' in obs
        assert "搜索结果：股价 1700" in obs

    def test_is_action_block(self):
        assert is_action_block('<action name="x">{"a":1}</action>')
        assert not is_action_block("普通文本")


class TestCompliance:
    def test_action_is_single_per_block(self):
        """协议约束：每轮最多一个 action（与 prompt「每次只调用一个工具」一致）。"""
        text = '<action name="a">{"x":1}</action><action name="b">{"y":2}</action>'
        tc = extract_action(text)
        # 解析取第一个 action，但双 action 属于协议违规——由 loop 层拒绝
        assert tc is not None
