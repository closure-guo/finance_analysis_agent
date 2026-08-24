"""管线深层调用链 llm_config 透传单元测试。

覆盖 tasks.md 8.3：验证 call_llm_streaming 透传 llm_config（复刻 legacy
_request_config_dict 语义转请求级 dict），以及管线节点从 state 读取
llm_config 后使用正确模型。
"""

from __future__ import annotations

from unittest.mock import patch

from finance_agent.llm import LLMConfig
from finance_agent.llm.types import CanonicalEvent

_COMPLETE_STREAM = "finance_agent.llm.gateway.complete_stream"


def _answer(text: str):
    """构造 complete_stream mock 返回值：单个 text CanonicalEvent。"""
    return iter([CanonicalEvent(kind="text", text=text)])


# ── call_llm_streaming 透传 llm_config ──


def test_call_llm_streaming_passes_llm_config_to_complete_stream():
    """call_llm_streaming 将 llm_config（LLMConfig）转为请求级 dict 传入 complete_stream。"""
    with patch(_COMPLETE_STREAM) as mock_stream:
        mock_stream.return_value = _answer("ok")

        from finance_agent.nodes._llm_utils import call_llm_streaming

        cfg = LLMConfig(model="openai/gpt-4o")
        call_llm_streaming("test", system="sys", llm_config=cfg)

    call_kwargs = mock_stream.call_args[1]
    # 只断言 model 透传：_request_config_dict 会按 env 回退链补 apiKey/baseUrl
    # （LLM_API_KEY / DEEPSEEK_API_KEY），测试环境不固定，不做全 dict 断言。
    assert call_kwargs["llm_config"] is not None
    assert call_kwargs["llm_config"]["model"] == "openai/gpt-4o"


def test_call_llm_streaming_none_llm_config():
    """call_llm_streaming 不传 llm_config 时，complete_stream 收到 None（env/preset 解析）。"""
    with patch(_COMPLETE_STREAM) as mock_stream:
        mock_stream.return_value = _answer("ok")

        from finance_agent.nodes._llm_utils import call_llm_streaming

        call_llm_streaming("test", system="sys")

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["llm_config"] is None


# ── 管线节点从 state 读取 llm_config 并透传 ──


@patch(_COMPLETE_STREAM)
def test_technical_analyst_passes_llm_config_from_state(mock_stream):
    """technical_analyst 节点从 state 读取 llm_config 并转请求级 dict 传入 complete_stream。"""
    mock_stream.return_value = _answer(
        '{"agent_name": "technical", "summary": "s", "key_findings": [], "claims": [], "markdown": "m"}'
    )

    from finance_agent.nodes.analysts import technical_analyst

    cfg = LLMConfig(model="openai/gpt-4o")
    state = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "technical_indicators": {},
        "api_key": None,
        "llm_config": cfg,
    }
    technical_analyst(state)

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["llm_config"] is not None
    assert call_kwargs["llm_config"]["model"] == "openai/gpt-4o"


@patch(_COMPLETE_STREAM)
def test_trader_passes_llm_config_from_state(mock_stream):
    """trader 节点从 state 读取 llm_config 并转请求级 dict 传入 complete_stream。"""
    mock_stream.return_value = _answer('{"action": "hold", "confidence": 0.5, "reasoning": "r"}')

    from finance_agent.nodes.trader import trader

    cfg = LLMConfig(model="deepseek/deepseek-v4-pro")
    state = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "api_key": None,
        "llm_config": cfg,
    }
    trader(state)

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["llm_config"] is not None
    assert call_kwargs["llm_config"]["model"] == "deepseek/deepseek-v4-pro"


@patch(_COMPLETE_STREAM)
def test_node_without_llm_config_passes_none(mock_stream):
    """state 无 llm_config 时节点透传 None（向后兼容）。"""
    mock_stream.return_value = _answer('{"action": "hold", "confidence": 0.5, "reasoning": "r"}')

    from finance_agent.nodes.trader import trader

    state = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "api_key": None,
    }
    trader(state)

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["llm_config"] is None


# ── 端到端：llm_config 注入后使用正确模型 ──


@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_pipeline_llm_config_uses_correct_model(mock_raw_stream):
    """llm_config.model 注入后，call_llm_streaming 经 gateway.complete_stream 下发给 raw_stream 正确 model。

    5.1-C 迁移：call_llm_streaming 直连 complete_stream，mock 目标在 adapter 层
    raw_stream；llm_config 需完整（resolver 原子性）。

    验证完整透传链：call_llm_streaming(llm_config) → complete_stream(llm_config)
    → raw_stream(model=cfg.model)。
    """
    from types import SimpleNamespace

    delta = SimpleNamespace(reasoning_content=None, content="answer")
    choice = SimpleNamespace(delta=delta, finish_reason="stop")
    chunk = SimpleNamespace(choices=[choice], usage=None)

    def _fake_stream(**kwargs):  # noqa: ARG001
        yield chunk

    mock_raw_stream.side_effect = _fake_stream

    from finance_agent.nodes._llm_utils import call_llm_streaming

    cfg = LLMConfig(model="openai/gpt-4o-mini", baseUrl="https://api.test/v1", apiKey="k")
    call_llm_streaming("test", system="sys", llm_config=cfg)

    completion_kwargs = mock_raw_stream.call_args[1]
    assert completion_kwargs["model"] == "openai/gpt-4o-mini"
