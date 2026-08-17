"""管线深层调用链 llm_config 透传单元测试。

覆盖 tasks.md 8.3：验证 call_llm_streaming 透传 llm_config，
以及管线节点从 state 读取 llm_config 后使用正确模型。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from finance_agent.llm import LLMConfig

# ── call_llm_streaming 透传 llm_config ──


def test_call_llm_streaming_passes_llm_config_to_call_llm_stream():
    """call_llm_streaming 将 llm_config 透传给 call_llm_stream。"""
    with patch("finance_agent.llm.call_llm_stream") as mock_stream:
        mock_stream.return_value = iter([("answer", "ok")])

        from finance_agent.nodes._llm_utils import call_llm_streaming

        cfg = LLMConfig(model="openai/gpt-4o")
        call_llm_streaming("test", system="sys", llm_config=cfg)

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["llm_config"] is cfg


def test_call_llm_streaming_none_llm_config():
    """call_llm_streaming 不传 llm_config 时，call_llm_stream 收到 None。"""
    with patch("finance_agent.llm.call_llm_stream") as mock_stream:
        mock_stream.return_value = iter([("answer", "ok")])

        from finance_agent.nodes._llm_utils import call_llm_streaming

        call_llm_streaming("test", system="sys")

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["llm_config"] is None


# ── 管线节点从 state 读取 llm_config 并透传 ──


@patch("finance_agent.llm.call_llm_stream")
def test_technical_analyst_passes_llm_config_from_state(mock_stream):
    """technical_analyst 节点从 state 读取 llm_config 并透传给 call_llm_stream。"""
    mock_stream.return_value = iter(
        [
            (
                "answer",
                '{"agent_name": "technical", "summary": "s", "key_findings": [], "claims": [], "markdown": "m"}',
            )
        ]
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
    assert call_kwargs["llm_config"] is cfg


@patch("finance_agent.llm.call_llm_stream")
def test_trader_passes_llm_config_from_state(mock_stream):
    """trader 节点从 state 读取 llm_config 并透传。"""
    mock_stream.return_value = iter(
        [("answer", '{"action": "hold", "confidence": 0.5, "reasoning": "r"}')]
    )

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
    assert call_kwargs["llm_config"] is cfg


@patch("finance_agent.llm.call_llm_stream")
def test_node_without_llm_config_passes_none(mock_stream):
    """state 无 llm_config 时节点透传 None（向后兼容）。"""
    mock_stream.return_value = iter(
        [("answer", '{"action": "hold", "confidence": 0.5, "reasoning": "r"}')]
    )

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


@patch("finance_agent.llm.legacy.litellm.completion")
def test_pipeline_llm_config_uses_correct_model(mock_completion):
    """llm_config.model 注入后，call_llm_stream 内部 litellm.completion 收到正确 model。

    这验证了完整透传链：call_llm_streaming(llm_config) → call_llm_stream(llm_config)
    → _build_kwargs(llm_config) → litellm.completion(model=cfg.model)。
    """
    # 构造流式响应 mock（call_llm_stream 用 litellm.completion(**kwargs, stream=True)）
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "answer"
    mock_chunk.choices[0].delta.reasoning_content = None
    mock_chunk.choices[0].finish_reason = "stop"
    mock_chunk.usage = None
    mock_completion.return_value = iter([mock_chunk])

    from finance_agent.nodes._llm_utils import call_llm_streaming

    cfg = LLMConfig(model="openai/gpt-4o-mini")
    call_llm_streaming("test", system="sys", llm_config=cfg)

    completion_kwargs = mock_completion.call_args[1]
    assert completion_kwargs["model"] == "openai/gpt-4o-mini"
