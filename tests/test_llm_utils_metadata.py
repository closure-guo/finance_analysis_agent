"""call_llm_streaming 透传 prompt_name/prompt_version 测试（Task 4）。

验证 5 层管线节点经 _llm_utils.call_llm_streaming 调 call_llm_stream 时，
prompt_name/prompt_version 正确透传到底层 LLM 调用（从而挂到 generation metadata）。
"""

from __future__ import annotations

from unittest.mock import patch


@patch("finance_agent.llm.call_llm_stream")
def test_call_llm_streaming_forwards_prompt_metadata(mock_call_llm_stream):
    """call_llm_streaming 把 prompt_name/prompt_version 透传给 call_llm_stream。"""
    # call_llm_stream 是生成器（yield (kind, text)）；空生成器 → answer 为空串
    mock_call_llm_stream.return_value = iter([])

    from finance_agent.nodes._llm_utils import call_llm_streaming

    call_llm_streaming(
        "hi",
        system="你是助手",
        api_key="fake",
        node_name="technical_analyst",
        prompt_name="technical_analyst",
        prompt_version=3,
    )

    call_kwargs = mock_call_llm_stream.call_args.kwargs
    assert call_kwargs["prompt_name"] == "technical_analyst"
    assert call_kwargs["prompt_version"] == 3


@patch("finance_agent.llm.call_llm_stream")
def test_call_llm_streaming_prompt_metadata_defaults_none(mock_call_llm_stream):
    """未传 prompt 元数据时底层 call_llm_stream 收到 None（向后兼容）。"""
    mock_call_llm_stream.return_value = iter([])

    from finance_agent.nodes._llm_utils import call_llm_streaming

    call_llm_streaming("hi", system="你是助手", api_key="fake", node_name="trader")

    call_kwargs = mock_call_llm_stream.call_args.kwargs
    assert call_kwargs["prompt_name"] is None
    assert call_kwargs["prompt_version"] is None
