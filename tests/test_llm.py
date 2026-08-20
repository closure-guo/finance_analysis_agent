"""legacy call_llm/call_llm_with_tools 薄壳测试（5.1-C 迁移）。

mock 目标：``finance_agent.llm.adapters.litellm_adapter.raw_completion``（gateway
唯一 litellm 出口）与 ``finance_agent.langfuse_tracing.get_langfuse``（观测收口
在 gateway）。原 ``_build_kwargs`` 级测试迁移说明见
``.superpowers/sdd/task-3-report.md``。
"""

from unittest.mock import MagicMock, patch

import pytest

_RAW_COMPLETION = "finance_agent.llm.adapters.litellm_adapter.raw_completion"
_GET_LANGFUSE = "finance_agent.langfuse_tracing.get_langfuse"
_OPEN_SPAN = "finance_agent.langfuse_tracing.open_span"


def _mock_resp(content="ok", reasoning="", tool_calls=None):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = content
    mock_resp.choices[0].message.reasoning_content = reasoning
    mock_resp.choices[0].message.tool_calls = tool_calls
    mock_resp.usage = None
    mock_resp.choices[0].finish_reason = "stop"
    return mock_resp


@patch(_RAW_COMPLETION)
def test_call_llm_basic(mock_completion):
    mock_completion.return_value = _mock_resp("分析结果")

    from finance_agent.llm import call_llm

    result = call_llm("测试 prompt", system="你是助手")
    assert result == "分析结果"
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["messages"][0]["role"] == "system"
    assert call_kwargs["messages"][1]["role"] == "user"
    assert call_kwargs["messages"][1]["content"] == "测试 prompt"


@patch(_RAW_COMPLETION)
def test_call_llm_no_system(mock_completion):
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    call_llm("hello")
    call_kwargs = mock_completion.call_args[1]
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"


@patch(_RAW_COMPLETION)
def test_call_llm_env_model(mock_completion):
    """env model + key + base_url → gateway 解析（无前缀 model 自动补 openai/）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    with patch.dict(
        "os.environ",
        {
            "LLM_MODEL": "gpt-4o",
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://env.example.com/v1",
        },
    ):
        call_llm("hi")
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"
    assert call_kwargs["api_key"] == "sk-test"


@patch(_RAW_COMPLETION)
def test_call_llm_param_api_key_overrides_env(mock_completion):
    """llm_config 请求级下 api_key 参数优先于环境变量（_request_config_dict 链）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import LLMConfig, call_llm

    with patch.dict("os.environ", {"LLM_API_KEY": "sk-env-value", "LLM_BASE_URL": "https://x/v1"}):
        call_llm(
            "hi",
            api_key="sk-param-value",
            llm_config=LLMConfig(model="openai/gpt-4o"),
        )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_key"] == "sk-param-value"


@patch(_RAW_COMPLETION)
def test_call_llm_no_api_key_no_env(mock_completion):
    """api_key 参数和 env 都没有时，不传 api_key 给 litellm。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {}, clear=True):
        call_llm("hi", api_key="")
    call_kwargs = mock_completion.call_args[1]
    assert "api_key" not in call_kwargs


# ── llm_config 注入（原 _build_kwargs llm_config 系列迁移为薄壳级断言）──

from finance_agent.llm import LLMConfig  # noqa: E402


@patch(_RAW_COMPLETION)
def test_call_llm_llm_config_model_override(mock_completion):
    """llm_config.model 覆盖 quick/非 quick model 解析（原 test_build_kwargs_llm_config_model_override）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    call_llm(
        "hi",
        quick=True,
        llm_config=LLMConfig(model="openai/gpt-4o", baseUrl="https://x/v1", apiKey="k"),
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"


@patch(_RAW_COMPLETION)
def test_call_llm_llm_config_base_url_override(mock_completion):
    """llm_config.baseUrl 覆盖环境变量 LLM_BASE_URL（原 base_url_override 迁移）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {"LLM_BASE_URL": "https://env.example.com/v1"}):
        call_llm(
            "hi",
            llm_config=LLMConfig(
                model="openai/gpt-4o", baseUrl="https://custom.example.com/v1", apiKey="k"
            ),
        )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_base"] == "https://custom.example.com/v1"


@patch(_RAW_COMPLETION)
def test_call_llm_llm_config_base_url_from_env(mock_completion):
    """llm_config.baseUrl 缺省时回退环境变量 LLM_BASE_URL（原 base_url_when_no_env 迁移）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {"LLM_BASE_URL": "https://env.example.com/v1"}):
        call_llm("hi", llm_config=LLMConfig(model="openai/gpt-4o", apiKey="k"))
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_base"] == "https://env.example.com/v1"


@patch(_RAW_COMPLETION)
def test_call_llm_llm_config_full_override(mock_completion):
    """llm_config 同时覆盖 model + base_url + api_key（原 full_override 迁移）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    call_llm(
        "hi",
        llm_config=LLMConfig(
            model="openai/gpt-4o",
            baseUrl="https://api.custom.com/v1",
            apiKey="sk-config-key",
        ),
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"
    assert call_kwargs["api_base"] == "https://api.custom.com/v1"
    assert call_kwargs["api_key"] == "sk-config-key"


@patch(_RAW_COMPLETION)
def test_call_llm_auto_prefix_openai_when_base_url_and_no_slash(mock_completion):
    """自定义 base_url + 模型名无 provider 前缀时自动补 openai/（resolver._ensure_prefix）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    call_llm(
        "hi",
        llm_config=LLMConfig(
            model="deepseek-v4-flash", baseUrl="https://opencode.ai/v1", apiKey="k"
        ),
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/deepseek-v4-flash"
    assert call_kwargs["api_base"] == "https://opencode.ai/v1"


@patch(_RAW_COMPLETION)
def test_call_llm_no_auto_prefix_when_model_has_slash(mock_completion):
    """模型名已含 / 时不自动补全（如 deepseek/deepseek-chat）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    call_llm(
        "hi",
        llm_config=LLMConfig(
            model="deepseek/deepseek-chat", baseUrl="https://api.deepseek.com/v1", apiKey="k"
        ),
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "deepseek/deepseek-chat"


@patch(_RAW_COMPLETION)
def test_call_llm_no_auto_prefix_when_no_base_url(mock_completion):
    """无 base_url 时不自动补全（官方端点语义，由 litellm 按前缀路由）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    with patch.dict("os.environ", {"LLM_BASE_URL": ""}):
        call_llm(
            "hi",
            llm_config=LLMConfig(model="openai/gpt-4o", apiKey="k", baseUrl="https://x/v1"),
        )
    # openai/gpt-4o 已带前缀，保持原样
    assert mock_completion.call_args[1]["model"] == "openai/gpt-4o"


# ── agent-trace-content-fidelity Task 2: reasoning 落 generation output ──


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_writes_reasoning_to_output(mock_completion, mock_get_langfuse):
    """call_llm 把 message.reasoning_content 写入 generation output.reasoning。"""
    mock_completion.return_value = _mock_resp("最终答案", reasoning="思考过程")

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


@patch("finance_agent.langfuse_tracing.get_langfuse")
@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_call_llm_stream_writes_reasoning_to_output(mock_raw_stream, mock_get_langfuse):
    """call_llm_stream 累加 reasoning_content 并写入 generation output.reasoning。

    5.1-B2 迁移：观测收口在 gateway（complete_stream 经 trace 开启），
    mock 目标改为 adapter.raw_stream / langfuse_tracing.get_langfuse。
    """

    def _fake_stream(**kwargs):  # noqa: ARG001
        from types import SimpleNamespace

        def _chunk(reasoning=None, content=None, finish=None):
            delta = SimpleNamespace(reasoning_content=reasoning, content=content)
            choice = SimpleNamespace(delta=delta, finish_reason=finish)
            return SimpleNamespace(choices=[choice], usage=None)

        yield _chunk(reasoning="思考A")
        yield _chunk(reasoning="思考B")
        yield _chunk(content="最终答案")

    mock_raw_stream.side_effect = _fake_stream

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_stream

    results = list(
        call_llm_stream(
            "hi",
            llm_config={
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            },
        )
    )

    # yield 顺序：thinking x2 + answer x1
    assert results == [("thinking", "思考A"), ("thinking", "思考B"), ("answer", "最终答案")]
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["reasoning"] == "思考A思考B"
    assert call_kwargs["output"]["answer"] == "最终答案"


# ── agent-trace-content-fidelity Task 3: call_llm_with_tools tool_calls 落 output ──


def _tool_call_mock(name="web_search", arguments='{"q":"茅台"}'):
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_writes_tool_calls_to_output(mock_completion, mock_get_langfuse):
    """call_llm_with_tools 把 message.tool_calls 写入 generation output.tool_calls。"""
    mock_completion.return_value = _mock_resp(
        "", reasoning="为何调用此工具", tool_calls=[_tool_call_mock()]
    )

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
    assert resp is mock_completion.return_value
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["tool_calls"] == [
        {"name": "web_search", "arguments": '{"q":"茅台"}'}
    ]
    # Finding 2: reasoning 字段对称写入（与 call_llm / chat_stream 一致）
    assert call_kwargs["output"]["reasoning"] == "为何调用此工具"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_empty_tool_calls_list(mock_completion, mock_get_langfuse):
    """无 tool_calls 时 output 不含 tool_calls 字段（与 chat_stream 文本分支一致）。"""
    mock_completion.return_value = _mock_resp("纯文本回答", tool_calls=None)

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


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_passes_tools_and_tool_choice(mock_completion, mock_get_langfuse):
    """tools/tool_choice 透传 raw_completion（原 test_build_kwargs_none_config_with_tools 迁移）。

    计划内语义修正（5.1-C）：deepseek thinking+tools 保持开启（registry
    provider_options 默认 enabled），不再像 legacy 显式 disabled。
    """
    mock_completion.return_value = _mock_resp("ok", tool_calls=None)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = MagicMock()
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm import call_llm_with_tools

    tools = [{"type": "function", "function": {"name": "f"}}]
    call_llm_with_tools(
        "hi",
        tools=tools,
        llm_config=LLMConfig(model="deepseek/deepseek-chat", baseUrl="https://x/v1", apiKey="k"),
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["tools"] == tools
    assert call_kwargs["tool_choice"] == "auto"
    # 计划内修正：thinking 保持 enabled（不再 {"thinking": {"type": "disabled"}}）
    assert call_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


# ── Task 3 fix: 降级路径经 open_span 记录 tool_calls（spec「降级路径同样记录」）──


@patch(_OPEN_SPAN)
@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_degraded_records_via_open_span(
    mock_completion, mock_get_langfuse, mock_open_span
):
    """start_as_current_observation 抛异常时，降级分支经 open_span 记录 tool_calls/reasoning。"""
    mock_completion.return_value = _mock_resp(
        "答案", reasoning="推理过程", tool_calls=[_tool_call_mock()]
    )

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
        llm_config=LLMConfig(model="deepseek/deepseek-chat", baseUrl="https://x/v1", apiKey="k"),
    )

    # 业务正常返回
    assert resp is mock_completion.return_value
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


@patch(_OPEN_SPAN)
@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_degraded_noop_without_error(
    mock_completion, mock_get_langfuse, mock_open_span
):
    """open_span 降级到 no-op（yield None）时不报错，业务正常返回 resp。"""
    mock_completion.return_value = _mock_resp("答案", tool_calls=None)

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
    assert resp is mock_completion.return_value
    mock_open_span.assert_called_once()


# ── agent-trace-content-fidelity Task 4: prompt_name/version 挂 generation metadata ──


def _mock_langfuse_obs(mock_get_langfuse):
    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf
    return mockLf


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """call_llm 把 prompt_name/prompt_version 经 metadata 挂到 generation。"""
    mock_completion.return_value = _mock_resp("答案", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake", prompt_name="trader", prompt_version=3)

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "trader"
    assert call_kwargs["metadata"]["prompt_version"] == 3


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_omits_metadata_when_prompt_unset(mock_completion, mock_get_langfuse):
    """call_llm 未传 prompt_name/prompt_version 时 metadata 不含这两个键（向后兼容）。"""
    mock_completion.return_value = _mock_resp("答案", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake")

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    md = call_kwargs.get("metadata", {})
    assert "prompt_name" not in md
    assert "prompt_version" not in md


@patch("finance_agent.langfuse_tracing.get_langfuse")
@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_call_llm_stream_attaches_prompt_metadata(mock_raw_stream, mock_get_langfuse):
    """call_llm_stream 把 prompt_name/prompt_version 经 metadata 挂到 generation。

    5.1-B2 迁移：metadata 经 trace dict 由 gateway 观测写入；mock 目标改
    adapter.raw_stream / langfuse_tracing.get_langfuse。
    """

    def _fake_stream(**kwargs):  # noqa: ARG001
        from types import SimpleNamespace

        delta = SimpleNamespace(reasoning_content=None, content="答案")
        choice = SimpleNamespace(delta=delta, finish_reason=None)
        yield SimpleNamespace(choices=[choice], usage=None)

    mock_raw_stream.side_effect = _fake_stream
    _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm_stream

    list(
        call_llm_stream(
            "hi",
            llm_config={
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            },
            prompt_name="bull_debater",
            prompt_version="local",
        )
    )

    call_kwargs = mock_get_langfuse.return_value.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "bull_debater"
    assert call_kwargs["metadata"]["prompt_version"] == "local"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """call_llm_with_tools 把 prompt_name/prompt_version 经 metadata 挂到 generation。"""
    mock_completion.return_value = _mock_resp("答案", tool_calls=None)
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

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


# ── observation 命名 / metadata 过滤字段（agent/session/stock）──


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_named_by_agent(mock_completion, mock_get_langfuse):
    """call_llm 传 agent 时 observation name 用 agent 名而非 litellm:{model}。"""
    mock_completion.return_value = _mock_resp("ok", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake", agent="technical_analyst")
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "technical_analyst"
    assert kwargs["metadata"]["agent"] == "technical_analyst"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_default_name_without_agent(mock_completion, mock_get_langfuse):
    """未传 agent 时 observation name 退化为 litellm:{model}（向后兼容）。"""
    mock_completion.return_value = _mock_resp("ok", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake")
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"].startswith("litellm:")
    assert "agent" not in kwargs["metadata"]


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_metadata_omits_missing_fields(mock_completion, mock_get_langfuse):
    """session_id/stock_code 未提供时 metadata 省略对应键；提供时写入。"""
    mock_completion.return_value = _mock_resp("ok", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm

    call_llm("hi", api_key="fake", agent="trader", session_id="sess-1", stock_code="300308")
    md = mockLf.start_as_current_observation.call_args.kwargs["metadata"]
    assert md == {"agent": "trader", "session_id": "sess-1", "stock_code": "300308"}

    mock_get_langfuse.reset_mock()
    mockLf = _mock_langfuse_obs(mock_get_langfuse)
    call_llm("hi", api_key="fake", agent="trader")
    md2 = mockLf.start_as_current_observation.call_args.kwargs["metadata"]
    assert md2 == {"agent": "trader"}


@patch("finance_agent.langfuse_tracing.get_langfuse")
@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_call_llm_stream_named_by_agent(mock_raw_stream, mock_get_langfuse):
    """call_llm_stream 传 agent 时 observation name 用 agent 名。

    5.1-B2 迁移：观测收口在 gateway；mock 目标改
    adapter.raw_stream / langfuse_tracing.get_langfuse。
    """

    def _fake_stream(**kwargs):  # noqa: ARG001
        from types import SimpleNamespace

        def _chunk(text):
            delta = SimpleNamespace(reasoning_content=None, content=text)
            choice = SimpleNamespace(delta=delta, finish_reason=None)
            return SimpleNamespace(choices=[choice], usage=None)

        yield _chunk("a")
        yield _chunk("b")

    mock_raw_stream.side_effect = _fake_stream
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm_stream

    list(
        call_llm_stream(
            "hi",
            llm_config={
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            },
            agent="trader",
        )
    )
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "trader"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_named_by_agent(mock_completion, mock_get_langfuse):
    """call_llm_with_tools 传 agent 时 observation name 用 agent 名。"""
    mock_completion.return_value = _mock_resp("ok", tool_calls=[])
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm import call_llm_with_tools

    call_llm_with_tools("hi", api_key="fake", agent="bull_debater")
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "bull_debater"


# ── 5.1-C 薄壳新增：DeprecationWarning + content 空回退 reasoning ──


@patch(_RAW_COMPLETION)
def test_call_llm_warns_deprecation(mock_completion):
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm import call_llm

    with pytest.warns(DeprecationWarning, match="complete_text"):
        call_llm("hi")


@patch(_RAW_COMPLETION)
def test_call_llm_with_tools_warns_deprecation(mock_completion):
    mock_completion.return_value = _mock_resp("ok", tool_calls=None)

    from finance_agent.llm import call_llm_with_tools

    with pytest.warns(DeprecationWarning, match="complete_with_tools"):
        call_llm_with_tools("hi")


@patch(_RAW_COMPLETION)
def test_call_llm_falls_back_to_reasoning_when_content_empty(mock_completion):
    """content 为空时回退 reasoning_content（legacy 行为在 shell 层保留）。"""
    mock_completion.return_value = _mock_resp("", reasoning="纯思考输出")

    from finance_agent.llm import call_llm

    assert call_llm("hi") == "纯思考输出"
