# tests/nodes/test_call_llm_for_json.py
"""call_llm_for_json 重试收口测试（incident 017 延伸：空 content 非 配额问题）。

实测方舟 GLM-5.2 在风控辩论等 prompt 下稳定触发「thinking 后即止」：
reasoning 正常（994-3485 字符）而 content 为空，与 max_tokens 配额无关
（16384 未吃满、无截断）。下游节点 parse 裸奔会炸整行 → 收口
「LLM 调用 + parse」，失败带强化指令重试一次；仍失败向上抛
（保留 fund_manager「不静默降级」设计：重试 ≠ 降级）。
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from finance_agent.nodes._llm_utils import call_llm_for_json


def _mock_call(responses: list[str]):
    """按序返回 responses 的 call_llm_streaming mock，记录调用参数。"""
    calls: list[dict] = []
    it = iter(responses)

    def fake(prompt: str, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        try:
            return next(it)
        except StopIteration:
            raise AssertionError("unexpected extra LLM call") from None

    return fake, calls


class TestRetryOnBadOutput:
    def test_empty_then_valid_retries_once(self):
        fake, calls = _mock_call(["", '{"decision": "hold"}'])
        with patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake):
            result = call_llm_for_json("分析风险", system="你是风控")
        assert result == {"decision": "hold"}
        assert len(calls) == 2
        # 重试时 prompt 必须追加强化指令（否则同样的空输出概率复现）
        assert "JSON" in calls[1]["prompt"]
        assert "JSON" not in calls[0]["prompt"]

    def test_unparseable_then_valid_retries(self):
        """容错层救不了的输出（纯文本无 JSON）触发重试。"""
        fake, calls = _mock_call(["我认为风险可控，无需 JSON。", '{"a": 1}'])
        with patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake):
            result = call_llm_for_json("x")
        assert result == {"a": 1}
        assert len(calls) == 2

    def test_trailing_comma_saved_by_tolerance_no_retry(self):
        """尾逗号由 parse 容错层直接救回，不应浪费重试调用。"""
        fake, calls = _mock_call(['{"a": 1,}'])
        with patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake):
            result = call_llm_for_json("x")
        assert result == {"a": 1}
        assert len(calls) == 1

    def test_valid_first_try_no_retry(self):
        fake, calls = _mock_call(['{"ok": true}'])
        with patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake):
            result = call_llm_for_json("x")
        assert result == {"ok": True}
        assert len(calls) == 1

    def test_both_bad_raises(self):
        """两次都失败必须抛（不静默降级），上游节点/管线按原语义中断。"""
        fake, _ = _mock_call(["", "   "])
        with (
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(json.JSONDecodeError),
        ):
            call_llm_for_json("x")

    def test_kwargs_passthrough(self):
        """node_name/prompt 元数据等透传给底层调用（Langfuse 命名依赖）。"""
        fake, calls = _mock_call(['{"a": 1}'])
        with patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake):
            call_llm_for_json(
                "x",
                system="s",
                node_name="aggressive_debater",
                prompt_name="risk_debater",
                prompt_version="1",
                stock_code="600519",
            )
        assert calls[0]["node_name"] == "aggressive_debater"
        assert calls[0]["prompt_name"] == "risk_debater"
        assert calls[0]["stock_code"] == "600519"


class TestRetryOnApiError:
    def test_api_error_then_valid_retries(self):
        """方舟偶发服务端 500（r4 实测 MidStreamFallbackError）重试一次即恢复。"""
        import litellm

        calls: list[dict] = []

        def fake(prompt: str, **kwargs):
            calls.append({"prompt": prompt})
            if len(calls) == 1:
                raise litellm.exceptions.APIConnectionError(
                    message="service internal error", llm_provider="openai"
                )
            return '{"ok": true}'

        with patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake):
            result = call_llm_for_json("x")
        assert result == {"ok": True}
        assert len(calls) == 2

    def test_api_error_twice_raises(self):
        """连续两次 API 错误仍向上抛（不静默吞错）。"""
        import litellm

        calls: list[dict] = []

        def fake(prompt: str, **kwargs):
            calls.append({"prompt": prompt})
            raise litellm.exceptions.APIConnectionError(
                message="still down", model="openai/glm-5.2", llm_provider="openai"
            )

        with (
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(litellm.exceptions.APIConnectionError),
        ):
            call_llm_for_json("x")
        assert len(calls) == 2
