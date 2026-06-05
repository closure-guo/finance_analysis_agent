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


@patch("finance_agent.llm.litellm.completion")
def test_call_llm_param_api_key_overrides_env(mock_completion):
    """传入 api_key 参数时优先使用，忽略环境变量。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {"LLM_API_KEY": "sk-env-value"}):
        call_llm("hi", api_key="sk-param-value")
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_key"] == "sk-param-value"


@patch("finance_agent.llm.litellm.completion")
def test_call_llm_no_api_key_no_env(mock_completion):
    """api_key 参数和 env 都没有时，不传 api_key 给 litellm。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {}, clear=True):
        call_llm("hi", api_key="")
    call_kwargs = mock_completion.call_args[1]
    assert "api_key" not in call_kwargs
