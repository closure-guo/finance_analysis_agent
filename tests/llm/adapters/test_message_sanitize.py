# tests/llm/adapters/test_message_sanitize.py
"""adapter 消息序列化收口测试（delta Task 2.1）。

按 capability 决定 reasoning 字段回传（DeepSeek 要求/方舟拒绝）；
arguments 规范化对全部 provider 生效（合法 JSON 是通用要求）。
自 harness/litellm_client._sanitize_messages_for_openai_compat 迁入升级。
"""

from __future__ import annotations

import json

from finance_agent.llm.adapters.litellm_adapter import (
    capability_for_model,
    sanitize_messages_for_profile,
)

_TC = [
    {
        "id": "c1",
        "type": "function",
        "function": {"name": "web_search", "arguments": "{'query': '茅台'}"},
    }
]


def _msg(**extra):
    return {"role": "assistant", "content": "", **extra}


class TestCapabilityForModel:
    def test_glm_maps_to_ark_profile(self):
        cap = capability_for_model("openai/glm-5.2")
        assert cap.reasoning_must_echo_on_tool is False
        assert cap.reasoning_forced is True

    def test_deepseek_maps_to_official(self):
        cap = capability_for_model("deepseek/deepseek-chat")
        assert cap.reasoning_must_echo_on_tool is True

    def test_plain_model_neutral(self):
        cap = capability_for_model("openai/gpt-4o")
        assert cap.reasoning_must_echo_on_tool is False
        assert cap.reasoning_field is None


class TestSanitizeByCapability:
    def test_no_echo_strips_reasoning(self):
        cap = capability_for_model("openai/glm-5.2")
        out = sanitize_messages_for_profile([_msg(tool_calls=_TC, reasoning_content="思考")], cap)
        assert "reasoning_content" not in out[0]

    def test_must_echo_keeps_reasoning(self):
        cap = capability_for_model("deepseek/deepseek-chat")
        out = sanitize_messages_for_profile([_msg(tool_calls=_TC, reasoning_content="思考")], cap)
        assert out[0]["reasoning_content"] == "思考"

    def test_arguments_normalized_for_all_providers(self):
        """单引号 Python 字面量 → 合法 JSON（对 must_echo 两类 provider 均生效）。"""
        for model in ("openai/glm-5.2", "deepseek/deepseek-chat"):
            cap = capability_for_model(model)
            out = sanitize_messages_for_profile([_msg(tool_calls=_TC)], cap)
            args = out[0]["tool_calls"][0]["function"]["arguments"]
            assert json.loads(args) == {"query": "茅台"}, model

    def test_valid_arguments_untouched(self):
        cap = capability_for_model("openai/glm-5.2")
        tc = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"a": 1}'}}]
        out = sanitize_messages_for_profile([_msg(tool_calls=tc)], cap)
        assert out[0]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'

    def test_unparseable_arguments_kept(self):
        cap = capability_for_model("openai/glm-5.2")
        tc = [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "f", "arguments": "不是json也不是字面量((("},
            }
        ]
        out = sanitize_messages_for_profile([_msg(tool_calls=tc)], cap)
        assert out[0]["tool_calls"][0]["function"]["arguments"] == "不是json也不是字面量((("

    def test_plain_messages_passthrough(self):
        cap = capability_for_model("openai/glm-5.2")
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "q"},
            {"role": "tool", "tool_call_id": "c1", "content": "r"},
        ]
        assert sanitize_messages_for_profile(msgs, cap) == msgs
