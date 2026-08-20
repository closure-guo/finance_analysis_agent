# tests/llm/test_gateway_fallback.py
"""complete_text_with_fallback：fallback 链执行器（harden-llm-gateway-governance Task 4）。

合同（spec llm-policy-router Requirement 2）：
- 捕获 OutputContractError/ContentFilteredError/AuthError/ModelNotFoundError/
  UnsupportedCapabilityError → 链未耗尽换下一 profile 重试；
- 成功且发生过切换 → 返回 metadata 带 fallback_from（前一 profile 名）+ router trace；
- 链耗尽 → 上抛最后一个错误；其他异常立即传播（网络重试在流路径内部处理）；
- 总尝试次数 ≤3；无 fallback 配置 → 单次尝试。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from finance_agent.llm.errors import AuthError, OutputContractError
from finance_agent.llm.gateway import complete_text_with_fallback
from finance_agent.llm.registry import get_profile_preset

MSGS = [{"role": "user", "content": "hi"}]


def _pin_deepseek_primary():
    """固定 primary=deepseek-official（隔离套件中其他测试对 env/probe 缓存的污染）。"""
    from unittest.mock import patch

    return patch(
        "finance_agent.llm.gateway.resolve_profile",
        return_value=get_profile_preset("deepseek-official"),
    )


def _ok(text: str = "ok"):
    return (text, {"profile": "openai-official"})


def test_primary_contract_error_falls_back_to_preset():
    calls = []

    def fake(
        messages,
        *,
        purpose="deep",
        max_tokens=None,
        llm_config=None,
        temperature=None,
        trace=None,
        preset=None,
        **kw,
    ):
        calls.append({"purpose": purpose, "llm_config": llm_config, "preset": preset})
        if len(calls) == 1:
            raise OutputContractError("contract exhausted")
        return _ok()

    with (
        _pin_deepseek_primary(),
        patch("finance_agent.llm.gateway.complete_text", side_effect=fake),
    ):
        text, meta = complete_text_with_fallback(MSGS, purpose="deep")

    assert text == "ok"
    assert meta["fallback_from"] == "deepseek-official"
    assert meta["router_trace"]["fallback_chain"] == ["openai-official"]
    assert len(calls) == 2
    # 第一次：registry 默认（无 llm_config，preset 指向解析出的命名 preset）
    assert calls[0]["preset"] == "deepseek-official"
    assert calls[0]["llm_config"] is None
    # 第二次：fallback 成员用 preset 名
    assert calls[1]["preset"] == "openai-official"
    assert calls[1]["llm_config"] is None


def test_chain_exhausted_raises_last_error():
    def fake(*a, **kw):
        raise AuthError("bad key")

    with (
        _pin_deepseek_primary(),
        patch("finance_agent.llm.gateway.complete_text", side_effect=fake) as m,
        pytest.raises(AuthError),
    ):
        complete_text_with_fallback(MSGS, purpose="deep")
    assert m.call_count == 2  # deepseek-official -> openai-official


def test_non_fallback_error_propagates_immediately():
    with (
        patch(
            "finance_agent.llm.gateway.complete_text",
            side_effect=RuntimeError("boom"),
        ) as m,
        pytest.raises(RuntimeError),
    ):
        complete_text_with_fallback(MSGS, purpose="deep")
    assert m.call_count == 1


def test_request_level_config_no_fallback_single_attempt():
    cfg = {"model": "my-model", "baseUrl": "http://localhost:1234/v1"}

    def fake(messages, *, purpose="deep", llm_config=None, preset=None, **kw):
        assert llm_config is cfg
        return _ok()

    with patch("finance_agent.llm.gateway.complete_text", side_effect=fake) as m:
        text, meta = complete_text_with_fallback(MSGS, purpose="deep", llm_config=cfg)

    assert text == "ok"
    assert "fallback_from" not in meta or meta["fallback_from"] is None
    assert m.call_count == 1


def test_attempts_capped_at_three():
    with (
        patch(
            "finance_agent.llm.gateway.complete_text",
            side_effect=AuthError("no"),
        ) as m,
        pytest.raises(AuthError),
    ):
        # 构造 3 成员链：deepseek-official -> openai-official -> anthropic
        import dataclasses

        from finance_agent.llm.registry import get_profile_preset

        with patch(
            "finance_agent.llm.gateway.resolve_profile",
            return_value=dataclasses.replace(
                get_profile_preset("deepseek-official"),
                fallback=("openai-official", "anthropic"),
            ),
        ):
            complete_text_with_fallback(MSGS, purpose="deep")
    assert m.call_count == 3
