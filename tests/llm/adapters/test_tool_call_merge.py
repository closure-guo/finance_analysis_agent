# tests/llm/adapters/test_tool_call_merge.py
"""adapter 工具增量合并收口测试（delta Task 5.1-C.1，设计 §8 职责 3）。

ToolCallAccumulator/finalize_tool_calls 自 harness/litellm_client.py
（:270-287 增量累积、:46-57 嵌套解包、:411-430 解析）移植：
流式 tool_calls 增量按 index 聚合，arguments 片段拼接后规范化。
"""

from __future__ import annotations

import json

from finance_agent.llm.adapters.litellm_adapter import (
    ToolCallAccumulator,
    finalize_tool_calls,
    sanitize_request_messages,
)


def _delta(
    index: int, *, id: str | None = None, name: str | None = None, args: str | None = None
) -> dict:
    """构造 litellm 流式 delta tool_calls 片段（dict 形态，与 attrs 同构）。"""
    return {
        "index": index,
        "id": id or "",
        "function": {"name": name or "", "arguments": args or ""},
    }


class TestAccumulatorMerge:
    def test_argument_fragments_merge_into_one_call(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="call_1", name="web_search", args='{"qu'))
        acc.add(_delta(0, args='ery": "'))
        acc.add(_delta(0, args='茅台"}'))
        calls = finalize_tool_calls(acc)
        assert len(calls) == 1
        assert calls[0]["id"] == "call_1"
        assert calls[0]["function"]["name"] == "web_search"
        assert json.loads(calls[0]["function"]["arguments"]) == {"query": "茅台"}

    def test_multiple_indexes_stay_separate_and_ordered(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(1, id="call_b", name="tool_b", args="{}"))
        acc.add(_delta(0, id="call_a", name="tool_a", args="{}"))
        calls = finalize_tool_calls(acc)
        assert [c["id"] for c in calls] == ["call_a", "call_b"]
        assert [c["function"]["name"] for c in calls] == ["tool_a", "tool_b"]

    def test_id_and_name_set_once_preserved(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="call_x", name="fetch", args='{"u'))
        acc.add(_delta(0, args='rl": 1}'))  # 后续片段无 id/name，不得清空
        calls = finalize_tool_calls(acc)
        assert calls[0]["id"] == "call_x"
        assert calls[0]["function"]["name"] == "fetch"

    def test_calls_property_returns_keyed_dict(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c1", name="n", args="{}"))
        assert acc.calls[0]["id"] == "c1"
        assert acc.calls[0]["function"]["arguments"] == "{}"


class TestFinalizeArguments:
    def test_nested_arguments_dict_unwrapped(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c", name="t", args=json.dumps({"arguments": {"q": "x"}})))
        calls = finalize_tool_calls(acc)
        assert json.loads(calls[0]["function"]["arguments"]) == {"q": "x"}

    def test_nested_arguments_str_unwrapped(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c", name="t", args=json.dumps({"arguments": '{"q": "x"}'})))
        calls = finalize_tool_calls(acc)
        assert json.loads(calls[0]["function"]["arguments"]) == {"q": "x"}

    def test_single_quote_python_literal_reserialized(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c", name="t", args="{'q': 'x'}"))
        calls = finalize_tool_calls(acc)
        assert json.loads(calls[0]["function"]["arguments"]) == {"q": "x"}

    def test_valid_json_arguments_unchanged(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c", name="t", args='{"q": "x"}'))
        calls = finalize_tool_calls(acc)
        assert calls[0]["function"]["arguments"] == '{"q": "x"}'

    def test_empty_arguments_become_empty_object(self):
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c", name="t"))
        calls = finalize_tool_calls(acc)
        assert json.loads(calls[0]["function"]["arguments"]) == {}

    def test_nested_arguments_invalid_json_inner_kept_as_wrapper(self):
        """literal 用例（review finding）：嵌套 arguments 内层非法 JSON → 解包失败，
        保留 wrapper dict 原样重序列化（不因清洗破坏请求）。"""
        acc = ToolCallAccumulator()
        acc.add(_delta(0, id="c", name="t", args=json.dumps({"arguments": "not json {{"})))
        calls = finalize_tool_calls(acc)
        assert json.loads(calls[0]["function"]["arguments"]) == {"arguments": "not json {{"}


class TestSanitizeRequestMessages:
    def test_delegates_to_sanitize_messages_for_profile(self):
        from finance_agent.llm.adapters.litellm_adapter import capability_for_model

        cap = capability_for_model("openai/glm-5.2")  # reasoning_must_echo_on_tool=False
        msgs = [{"role": "assistant", "content": "", "reasoning_content": "think"}]
        out = sanitize_request_messages(msgs, cap)
        assert "reasoning_content" not in out[0]

    def test_reasoning_kept_when_must_echo(self):
        from finance_agent.llm.adapters.litellm_adapter import capability_for_model

        cap = capability_for_model("deepseek/deepseek-chat")
        msgs = [{"role": "assistant", "content": "", "reasoning_content": "think"}]
        out = sanitize_request_messages(msgs, cap)
        assert out[0]["reasoning_content"] == "think"
