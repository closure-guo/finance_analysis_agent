"""llm.py 单元测试。"""

from unittest.mock import MagicMock, patch


@patch("finance_agent.llm.legacy.litellm.completion")
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


@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_no_system(mock_completion):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    call_llm("hello")
    call_kwargs = mock_completion.call_args[1]
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"


@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_env_model(mock_completion):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_completion.return_value = mock_resp

    from finance_agent.llm import call_llm

    with patch.dict(
        "os.environ", {"LLM_MODEL": "gpt-4o", "LLM_API_KEY": "sk-test", "LLM_BASE_URL": ""}
    ):
        call_llm("hi")
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["api_key"] == "sk-test"


@patch("finance_agent.llm.legacy.litellm.completion")
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


@patch("finance_agent.llm.legacy.litellm.completion")
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


# ── tasks.md 2.3 / 2.4: _build_kwargs 的 llm_config 注入与回归测试 ──

from finance_agent.llm import LLMConfig, _build_kwargs  # noqa: E402


def _base_kwargs(**overrides):
    """构造 _build_kwargs 的公共参数。"""
    defaults = {
        "model": "deepseek/deepseek-chat",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 100,
    }
    defaults.update(overrides)
    return defaults


# ── 2.3: llm_config 注入测试 ──


def test_build_kwargs_llm_config_model_override():
    """llm_config.model 覆盖传入的 model 参数。"""
    kwargs = _build_kwargs(
        **_base_kwargs(),
        llm_config=LLMConfig(model="openai/gpt-4o"),
    )
    assert kwargs["model"] == "openai/gpt-4o"


def test_build_kwargs_llm_config_base_url_override():
    """llm_config.baseUrl 覆盖环境变量 LLM_BASE_URL。"""
    with patch.dict("os.environ", {"LLM_BASE_URL": "https://env.example.com/v1"}):
        kwargs = _build_kwargs(
            **_base_kwargs(),
            llm_config=LLMConfig(baseUrl="https://custom.example.com/v1"),
        )
    assert kwargs["api_base"] == "https://custom.example.com/v1"


def test_build_kwargs_llm_config_base_url_when_no_env():
    """无环境变量时 llm_config.baseUrl 注入 api_base。"""
    with patch.dict("os.environ", {}, clear=True):
        kwargs = _build_kwargs(
            **_base_kwargs(),
            llm_config=LLMConfig(baseUrl="https://custom.example.com/v1"),
        )
    assert kwargs["api_base"] == "https://custom.example.com/v1"


def test_build_kwargs_llm_config_api_key_overrides_param():
    """llm_config.apiKey 优先于 api_key 参数。"""
    kwargs = _build_kwargs(
        **_base_kwargs(api_key="sk-param"),
        llm_config=LLMConfig(apiKey="sk-config"),
    )
    assert kwargs["api_key"] == "sk-config"


def test_build_kwargs_llm_config_api_key_fallback_to_param():
    """llm_config.apiKey 为 None 时回退到 api_key 参数。"""
    kwargs = _build_kwargs(
        **_base_kwargs(api_key="sk-param"),
        llm_config=LLMConfig(),
    )
    assert kwargs["api_key"] == "sk-param"


def test_build_kwargs_llm_config_thinking_disabled():
    """llm_config.thinking=disabled 时 DeepSeek 模型走 temperature 模式（非思考）。"""
    kwargs = _build_kwargs(
        **_base_kwargs(),
        llm_config=LLMConfig(thinking="disabled"),
    )
    # disabled 时不应有 reasoning_effort，应有 temperature
    assert "reasoning_effort" not in kwargs
    assert "temperature" in kwargs


def test_build_kwargs_llm_config_thinking_enabled():
    """llm_config.thinking=enabled 时 DeepSeek 模型开启思考模式。"""
    kwargs = _build_kwargs(
        **_base_kwargs(),
        llm_config=LLMConfig(thinking="enabled"),
    )
    assert kwargs.get("extra_body") == {"thinking": {"type": "enabled"}}
    assert "reasoning_effort" in kwargs


def test_build_kwargs_llm_config_thinking_overrides_env():
    """llm_config.thinking 覆盖环境变量 LLM_THINKING。"""
    with patch.dict("os.environ", {"LLM_THINKING": "disabled"}):
        kwargs = _build_kwargs(
            **_base_kwargs(),
            llm_config=LLMConfig(thinking="enabled"),
        )
    assert kwargs.get("extra_body") == {"thinking": {"type": "enabled"}}
    assert "reasoning_effort" in kwargs


def test_build_kwargs_llm_config_non_deepseek_no_thinking():
    """非 DeepSeek 模型不受 thinking 配置影响，走 temperature 模式。"""
    kwargs = _build_kwargs(
        **_base_kwargs(model="openai/gpt-4o"),
        llm_config=LLMConfig(thinking="enabled"),
    )
    assert "extra_body" not in kwargs
    assert "temperature" in kwargs


def test_build_kwargs_llm_config_full_override():
    """llm_config 同时覆盖 model + base_url + api_key + thinking。"""
    kwargs = _build_kwargs(
        **_base_kwargs(model="deepseek/deepseek-chat", api_key="sk-param"),
        llm_config=LLMConfig(
            model="deepseek/deepseek-v4-pro",
            baseUrl="https://api.custom.com/v1",
            apiKey="sk-config-key",
            thinking="disabled",
        ),
    )
    assert kwargs["model"] == "deepseek/deepseek-v4-pro"
    assert kwargs["api_base"] == "https://api.custom.com/v1"
    assert kwargs["api_key"] == "sk-config-key"
    assert "reasoning_effort" not in kwargs


# ── 2.4: llm_config=None 回归测试 ──


def test_build_kwargs_none_config_matches_old_behavior_deepseek():
    """llm_config=None 时 DeepSeek 模型的 kwargs 与旧行为完全一致。"""
    with patch.dict(
        "os.environ",
        {"LLM_BASE_URL": "", "LLM_THINKING": "enabled", "LLM_REASONING_EFFORT": "max"},
    ):
        kwargs = _build_kwargs(**_base_kwargs())
    assert kwargs["model"] == "deepseek/deepseek-chat"
    assert kwargs["max_tokens"] == 100
    assert kwargs.get("extra_body") == {"thinking": {"type": "enabled"}}
    assert kwargs["reasoning_effort"] == "max"
    # 无 LLM_BASE_URL 时不应有 api_base
    assert "api_base" not in kwargs


def test_build_kwargs_none_config_no_api_key():
    """llm_config=None 且无 api_key 参数/环境变量时，kwargs 不含 api_key。"""
    with patch.dict("os.environ", {}, clear=True):
        kwargs = _build_kwargs(**_base_kwargs())
    assert "api_key" not in kwargs


def test_build_kwargs_none_config_base_url_from_env():
    """llm_config=None 时 base_url 从环境变量 LLM_BASE_URL 读取（旧行为）。"""
    with patch.dict("os.environ", {"LLM_BASE_URL": "https://env.example.com/v1"}):
        kwargs = _build_kwargs(**_base_kwargs())
    assert kwargs["api_base"] == "https://env.example.com/v1"


def test_build_kwargs_none_config_thinking_from_env():
    """llm_config=None 时 thinking 从环境变量 LLM_THINKING 读取（旧行为）。"""
    with patch.dict("os.environ", {"LLM_THINKING": "disabled"}):
        kwargs = _build_kwargs(**_base_kwargs())
    # disabled 时 DeepSeek 走 temperature
    assert "reasoning_effort" not in kwargs
    assert "temperature" in kwargs


def test_build_kwargs_none_config_with_tools():
    """llm_config=None 时带 tools 的 kwargs 与旧行为一致。"""
    kwargs = _build_kwargs(
        **_base_kwargs(), tools=[{"type": "function", "function": {"name": "f"}}]
    )
    assert kwargs["tools"] == [{"type": "function", "function": {"name": "f"}}]
    assert kwargs["tool_choice"] == "auto"
    # tools + DeepSeek -> 显式 disabled thinking
    assert kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}


def test_call_llm_llm_config_model_override():
    """call_llm 的 llm_config.model 覆盖 quick/非 quick model 解析。"""
    with patch("finance_agent.llm.legacy.litellm.completion") as mock_completion:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "ok"
        mock_completion.return_value = mock_resp

        from finance_agent.llm import call_llm

        call_llm("hi", quick=True, llm_config=LLMConfig(model="openai/gpt-4o"))
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"


# ── 自动补全 provider 前缀测试（修复 BadRequestError: LLM Provider NOT provided）──


def test_build_kwargs_auto_prefix_openai_when_base_url_and_no_slash():
    """自定义 base_url + 模型名无 provider 前缀时自动补 openai/。"""
    kwargs = _build_kwargs(
        **_base_kwargs(),
        llm_config=LLMConfig(
            model="deepseek-v4-flash",
            baseUrl="https://opencode.ai/v1",
        ),
    )
    assert kwargs["model"] == "openai/deepseek-v4-flash"
    assert kwargs["api_base"] == "https://opencode.ai/v1"


def test_build_kwargs_no_auto_prefix_when_model_has_slash():
    """模型名已含 / 时不自动补全（如 deepseek/deepseek-chat）。"""
    kwargs = _build_kwargs(
        **_base_kwargs(),
        llm_config=LLMConfig(
            model="deepseek/deepseek-chat",
            baseUrl="https://api.deepseek.com/v1",
        ),
    )
    assert kwargs["model"] == "deepseek/deepseek-chat"


def test_build_kwargs_no_auto_prefix_when_no_base_url():
    """无 base_url 时不自动补全（由 litellm 按模型名前缀路由）。"""
    with patch.dict("os.environ", {}, clear=True):
        kwargs = _build_kwargs(
            **_base_kwargs(),
            llm_config=LLMConfig(model="gpt-4o"),
        )
    assert kwargs["model"] == "gpt-4o"


# ── agent-trace-content-fidelity Task 2: reasoning 落 generation output ──


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_writes_reasoning_to_output(mock_completion, mock_get_langfuse):
    """call_llm 把 message.reasoning_content 写入 generation output.reasoning。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "最终答案"
    mock_resp.choices[0].message.reasoning_content = "思考过程"
    mock_resp.usage = None
    mock_completion.return_value = mock_resp

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm

    result = call_llm("hi", api_key="fake")

    assert result == "最终答案"
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["answer"] == "最终答案"
    assert call_kwargs["output"]["reasoning"] == "思考过程"


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_stream_writes_reasoning_to_output(mock_completion, mock_get_langfuse):
    """call_llm_stream 累加 reasoning_content 并写入 generation output.reasoning。"""

    def _delta(reasoning=None, content=None):
        d = MagicMock()
        d.reasoning_content = reasoning
        d.content = content
        return d

    def _chunk(delta):
        c = MagicMock()
        c.choices = [MagicMock(delta=delta)]
        c.usage = None
        return c

    # litellm.completion(stream=True) 返回同步 iterator（call_llm_stream 用 for 消费）
    mock_completion.return_value = iter(
        [
            _chunk(_delta(reasoning="思考A")),
            _chunk(_delta(reasoning="思考B")),
            _chunk(_delta(content="最终答案")),
        ]
    )

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_stream

    results = list(call_llm_stream("hi", api_key="fake"))

    # yield 顺序：thinking x2 + answer x1
    assert results == [("thinking", "思考A"), ("thinking", "思考B"), ("answer", "最终答案")]
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["reasoning"] == "思考A思考B"
    assert call_kwargs["output"]["answer"] == "最终答案"


# ── agent-trace-content-fidelity Task 3: call_llm_with_tools tool_calls 落 output ──


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_with_tools_writes_tool_calls_to_output(mock_completion, mock_get_langfuse):
    """call_llm_with_tools 把 message.tool_calls 写入 generation output.tool_calls。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = ""
    mock_resp.choices[0].message.reasoning_content = "为何调用此工具"
    mock_resp.usage = None
    # litellm completion: message.tool_calls = [{id, type, function: {name, arguments(JSON 字符串)}}]
    _tc = MagicMock()
    _tc.function.name = "web_search"
    _tc.function.arguments = '{"q":"茅台"}'
    mock_resp.choices[0].message.tool_calls = [_tc]
    mock_completion.return_value = mock_resp

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_with_tools

    resp = call_llm_with_tools(
        "搜一下",
        api_key="fake",
        tools=[{"type": "function", "function": {"name": "web_search"}}],
    )

    # 函数仍返回原始 resp（行为契约不变）
    assert resp is mock_resp
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["tool_calls"] == [
        {"name": "web_search", "arguments": '{"q":"茅台"}'}
    ]
    # Finding 2: reasoning 字段对称写入（与 call_llm / chat_stream 一致）
    assert call_kwargs["output"]["reasoning"] == "为何调用此工具"


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_with_tools_empty_tool_calls_list(mock_completion, mock_get_langfuse):
    """无 tool_calls 时 output 不含 tool_calls 字段（与 chat_stream 文本分支一致）。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "纯文本回答"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.usage = None
    # 显式声明 message.tool_calls = None
    mock_resp.choices[0].message.tool_calls = None
    mock_completion.return_value = mock_resp

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_with_tools

    call_llm_with_tools("hi", api_key="fake")

    call_kwargs = mockObs.update.call_args.kwargs
    # Finding 3: 空 tool_calls 统一省略 key（不再写 tool_calls: []）
    assert "tool_calls" not in call_kwargs["output"]
    assert call_kwargs["output"]["answer"] == "纯文本回答"


# ── Task 3 fix: 降级路径经 open_span 记录 tool_calls（spec「降级路径同样记录」）──


@patch("finance_agent.llm.legacy.open_span")
@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_with_tools_degraded_records_via_open_span(
    mock_completion, mock_get_langfuse, mock_open_span
):
    """start_as_current_observation 抛异常时，降级分支经 open_span 记录 tool_calls/reasoning。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "答案"
    mock_resp.choices[0].message.reasoning_content = "推理过程"
    mock_resp.usage = None
    _tc = MagicMock()
    _tc.function.name = "web_search"
    _tc.function.arguments = '{"q":"茅台"}'
    mock_resp.choices[0].message.tool_calls = [_tc]
    mock_completion.return_value = mock_resp

    # 主观测路径抛异常 → 触发降级
    mockLf = MagicMock()
    mockLf.start_as_current_observation.side_effect = RuntimeError("langfuse down")
    mock_get_langfuse.return_value = mockLf

    # open_span yield 一个 mock obs，验证降级路径写入 output
    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mock_open_span.return_value = mockCm

    from finance_agent.llm import call_llm_with_tools

    resp = call_llm_with_tools(
        "搜一下",
        api_key="fake",
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        model="deepseek/deepseek-chat",
    )

    # 业务正常返回
    assert resp is mock_resp
    # 降级路径经 open_span 记录（spec「降级路径同样记录」）
    mock_open_span.assert_called_once()
    _kwargs = mock_open_span.call_args.kwargs
    assert _kwargs["name"] == "litellm:deepseek/deepseek-chat"
    assert _kwargs["input"] == {
        "messages": [
            {"role": "user", "content": "搜一下"},
        ]
    }
    mockObs.update.assert_called_once()
    out = mockObs.update.call_args.kwargs["output"]
    assert out["answer"] == "答案"
    assert out["reasoning"] == "推理过程"
    assert out["tool_calls"] == [{"name": "web_search", "arguments": '{"q":"茅台"}'}]


@patch("finance_agent.llm.legacy.open_span")
@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_with_tools_degraded_noop_without_error(
    mock_completion, mock_get_langfuse, mock_open_span
):
    """open_span 降级到 no-op（yield None）时不报错，业务正常返回 resp。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "答案"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.choices[0].message.tool_calls = None
    mock_resp.usage = None
    mock_completion.return_value = mock_resp

    mockLf = MagicMock()
    mockLf.start_as_current_observation.side_effect = RuntimeError("langfuse down")
    mock_get_langfuse.return_value = mockLf

    # open_span 降级：yield None（no-op，对应未配置 Langfuse 的场景）
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=None)
    mockCm.__exit__ = MagicMock(return_value=False)
    mock_open_span.return_value = mockCm

    from finance_agent.llm import call_llm_with_tools

    resp = call_llm_with_tools("hi", api_key="fake")

    # 业务正常返回，未报错（spec「若降级到 no-op 则不报错」）
    assert resp is mock_resp
    mock_open_span.assert_called_once()


# ── agent-trace-content-fidelity Task 4: prompt_name/version 挂 generation metadata ──


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """call_llm 把 prompt_name/prompt_version 经 metadata 挂到 generation。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "答案"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.usage = None
    mock_completion.return_value = mock_resp

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake", prompt_name="trader", prompt_version=3)

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "trader"
    assert call_kwargs["metadata"]["prompt_version"] == 3


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_omits_metadata_when_prompt_unset(mock_completion, mock_get_langfuse):
    """call_llm 未传 prompt_name/prompt_version 时 metadata 不含这两个键（向后兼容）。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "答案"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.usage = None
    mock_completion.return_value = mock_resp

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake")

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    md = call_kwargs.get("metadata", {})
    assert "prompt_name" not in md
    assert "prompt_version" not in md


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_stream_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """call_llm_stream 把 prompt_name/prompt_version 经 metadata 挂到 generation。"""

    def _delta(content=None):
        d = MagicMock()
        d.reasoning_content = None
        d.content = content
        return d

    def _chunk(content):
        c = MagicMock()
        c.choices = [MagicMock(delta=_delta(content=content))]
        c.usage = None
        return c

    mock_completion.return_value = iter([_chunk("答案")])

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_stream

    list(call_llm_stream("hi", api_key="fake", prompt_name="bull_debater", prompt_version="local"))

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "bull_debater"
    assert call_kwargs["metadata"]["prompt_version"] == "local"


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_with_tools_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """call_llm_with_tools 把 prompt_name/prompt_version 经 metadata 挂到 generation。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "答案"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.choices[0].message.tool_calls = None
    mock_resp.usage = None
    mock_completion.return_value = mock_resp

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_with_tools

    call_llm_with_tools(
        "hi",
        api_key="fake",
        tools=[{"type": "function", "function": {"name": "f"}}],
        prompt_name="risk_judge",
        prompt_version=2,
    )

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "risk_judge"
    assert call_kwargs["metadata"]["prompt_version"] == 2


def _mock_langfuse_for_naming(mock_get_langfuse):
    """构造 mock Langfuse：start_as_current_observation 返回可 enter/exit 的 CM。"""
    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf
    return mockLf


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_named_by_agent(mock_completion, mock_get_langfuse):
    """call_llm 传 agent 时 observation name 用 agent 名而非 litellm:{model}。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.usage = None
    mock_completion.return_value = mock_resp
    mockLf = _mock_langfuse_for_naming(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake", agent="technical_analyst")
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "technical_analyst"
    assert kwargs["metadata"]["agent"] == "technical_analyst"


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_default_name_without_agent(mock_completion, mock_get_langfuse):
    """未传 agent 时 observation name 退化为 litellm:{model}（向后兼容）。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.usage = None
    mock_completion.return_value = mock_resp
    mockLf = _mock_langfuse_for_naming(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake")
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"].startswith("litellm:")
    assert "agent" not in kwargs["metadata"]


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_metadata_omits_missing_fields(mock_completion, mock_get_langfuse):
    """session_id/stock_code 未提供时 metadata 省略对应键；提供时写入。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_resp.choices[0].message.reasoning_content = ""
    mock_resp.usage = None
    mock_completion.return_value = mock_resp
    mockLf = _mock_langfuse_for_naming(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake", agent="trader", session_id="sess-1", stock_code="300308")
    md = mockLf.start_as_current_observation.call_args.kwargs["metadata"]
    assert md == {"agent": "trader", "session_id": "sess-1", "stock_code": "300308"}

    mock_get_langfuse.reset_mock()
    call_llm("hi", api_key="fake", agent="trader")
    md2 = mockLf.start_as_current_observation.call_args.kwargs["metadata"]
    assert md2 == {"agent": "trader"}


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_stream_named_by_agent(mock_completion, mock_get_langfuse):
    """call_llm_stream 传 agent 时 observation name 用 agent 名。"""

    def _chunk(text):
        c = MagicMock()
        d = MagicMock()
        d.reasoning_content = None
        d.content = text
        c.choices = [MagicMock(delta=d)]
        c.usage = None
        return c

    mock_completion.return_value = iter([_chunk("a"), _chunk("b")])
    mockLf = _mock_langfuse_for_naming(mock_get_langfuse)

    from finance_agent.llm import call_llm_stream

    list(call_llm_stream("hi", api_key="fake", agent="trader"))
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "trader"


@patch("finance_agent.llm.legacy._get_langfuse")
@patch("finance_agent.llm.legacy.litellm.completion")
def test_call_llm_with_tools_named_by_agent(mock_completion, mock_get_langfuse):
    """call_llm_with_tools 传 agent 时 observation name 用 agent 名。"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "ok"
    mock_resp.choices[0].message.tool_calls = []
    mock_resp.usage = None
    mock_completion.return_value = mock_resp
    mockLf = _mock_langfuse_for_naming(mock_get_langfuse)

    from finance_agent.llm import call_llm_with_tools

    call_llm_with_tools("hi", api_key="fake", agent="bull_debater")
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "bull_debater"
