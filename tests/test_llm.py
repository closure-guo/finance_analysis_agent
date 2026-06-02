"""llm.py 单元测试。"""

from unittest.mock import MagicMock, patch


@patch("finance_agent.llm.litellm.completion")
def test_call_llm_basic(mock_completion):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "分析结果"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    result = call_llm("测试 prompt", system="你是助手")
    assert result == "分析结果"
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["messages"][0]["role"] == "system"
    assert call_kwargs["messages"][1]["role"] == "user"
    assert call_kwargs["messages"][1]["content"] == "测试 prompt"


@patch("finance_agent.llm.litellm.completion")
def test_call_llm_no_system(mock_completion):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    call_llm("hello")
    call_kwargs = mock_completion.call_args[1]
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"


@patch("finance_agent.llm.litellm.completion")
def test_call_llm_env_model(mock_completion):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {"LLM_MODEL": "gpt-4o", "LLM_API_KEY": "sk-test"}):
        call_llm("hi")
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["api_key"] == "sk-test"
