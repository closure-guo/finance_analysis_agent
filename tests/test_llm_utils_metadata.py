"""call_llm_streaming 透传 prompt_name/prompt_version 测试（Task 4）。

验证 5 层管线节点经 _llm_utils.call_llm_streaming 调 gateway.complete_stream 时，
prompt_name/prompt_version 正确透传到 Langfuse generation metadata（trace dict）。
"""

from __future__ import annotations

from unittest.mock import patch


@patch("finance_agent.llm.gateway.complete_stream")
def test_call_llm_streaming_forwards_prompt_metadata(mock_complete_stream):
    """call_llm_streaming 把 prompt_name/prompt_version 挂到 complete_stream 的 trace metadata。"""
    # complete_stream 是生成器；空生成器 → answer 为空串
    mock_complete_stream.return_value = iter([])

    from finance_agent.nodes._llm_utils import call_llm_streaming

    call_llm_streaming(
        "hi",
        system="你是助手",
        api_key="fake",
        node_name="technical_analyst",
        prompt_name="technical_analyst",
        prompt_version=3,
    )

    call_kwargs = mock_complete_stream.call_args.kwargs
    metadata = call_kwargs["trace"]["metadata"]
    assert metadata["prompt_name"] == "technical_analyst"
    assert metadata["prompt_version"] == 3


@patch("finance_agent.llm.gateway.complete_stream")
def test_call_llm_streaming_prompt_metadata_defaults_none(mock_complete_stream):
    """未传 prompt 元数据时 trace metadata 不含 prompt_name/prompt_version（向后兼容）。"""
    mock_complete_stream.return_value = iter([])

    from finance_agent.nodes._llm_utils import call_llm_streaming

    call_llm_streaming("hi", system="你是助手", api_key="fake", node_name="trader")

    call_kwargs = mock_complete_stream.call_args.kwargs
    metadata = call_kwargs["trace"]["metadata"]
    assert "prompt_name" not in metadata
    assert "prompt_version" not in metadata


@patch("finance_agent.llm.gateway.complete_stream")
def test_call_llm_streaming_forwards_agent_and_stock(mock_complete_stream):
    """call_llm_streaming 把 node_name 作为 trace.name、stock_code 原样挂 metadata。"""
    from finance_agent.llm.types import CanonicalEvent

    mock_complete_stream.return_value = iter(
        [
            CanonicalEvent(kind="reasoning", reasoning="t"),
            CanonicalEvent(kind="text", text="a"),
        ]
    )

    from finance_agent.nodes._llm_utils import call_llm_streaming

    result = call_llm_streaming(
        "prompt", system="s", node_name="technical_analyst", stock_code="300308"
    )
    assert result == "a"
    kwargs = mock_complete_stream.call_args.kwargs
    assert kwargs["trace"]["name"] == "technical_analyst"
    assert kwargs["trace"]["metadata"]["stock_code"] == "300308"
