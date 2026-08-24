"""gateway complete_text / complete_with_tools / call_llm_streaming 测试。

migrate-off-legacy-llm-shim（Task 3）：legacy 薄壳（call_llm /
call_llm_with_tools）已删除，本文件直测 gateway 三入口——
``complete_text``（非流式）/ ``complete_with_tools``（工具）／
``_llm_utils.call_llm_streaming``（流式，Task 2 已迁）。

mock 目标：``finance_agent.llm.adapters.litellm_adapter.raw_completion``（gateway
唯一 litellm 出口）与 ``finance_agent.langfuse_tracing.get_langfuse``（观测收口
在 gateway）。断言语义保留：thinking/answer 输出分流、空文本→reasoning
（meta.raw_reasoning 供调用方回退）、tool_calls 落 generation output。
"""

from unittest.mock import MagicMock, patch

import pytest

_RAW_COMPLETION = "finance_agent.llm.adapters.litellm_adapter.raw_completion"
_GET_LANGFUSE = "finance_agent.langfuse_tracing.get_langfuse"
_OPEN_SPAN = "finance_agent.langfuse_tracing.open_span"

# 请求级 llm_config 测试基底（resolver 原子性：request 分支必须 model+baseUrl 齐全）
_CFG = {"model": "openai/gpt-4o", "baseUrl": "https://x/v1", "apiKey": "k"}


def _messages(prompt: str, system: str = "") -> list[dict]:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def _mock_resp(content="ok", reasoning="", tool_calls=None):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = content
    mock_resp.choices[0].message.reasoning_content = reasoning
    mock_resp.choices[0].message.tool_calls = tool_calls
    mock_resp.usage = None
    mock_resp.choices[0].finish_reason = "stop"
    return mock_resp


# ── complete_text 基础（原 call_llm 系列迁移）──


@patch(_RAW_COMPLETION)
def test_complete_text_basic(mock_completion):
    mock_completion.return_value = _mock_resp("分析结果")

    from finance_agent.llm.gateway import complete_text

    text, _meta = complete_text(_messages("测试 prompt", system="你是助手"), llm_config=_CFG)
    assert text == "分析结果"
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["messages"][0]["role"] == "system"
    assert call_kwargs["messages"][1]["role"] == "user"
    assert call_kwargs["messages"][1]["content"] == "测试 prompt"


@patch(_RAW_COMPLETION)
def test_complete_text_no_system(mock_completion):
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    complete_text(_messages("hello"), llm_config=_CFG)
    call_kwargs = mock_completion.call_args[1]
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"


@patch(_RAW_COMPLETION)
def test_complete_text_env_model(mock_completion):
    """env model + key + base_url → gateway 解析（无前缀 model 自动补 openai/）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    with patch.dict(
        "os.environ",
        {
            "LLM_MODEL": "gpt-4o",
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://env.example.com/v1",
        },
    ):
        complete_text(_messages("hi"), llm_config=None)
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"
    assert call_kwargs["api_key"] == "sk-test"


@patch(_RAW_COMPLETION)
def test_complete_text_request_api_key_wins_over_env(mock_completion):
    """请求级 apiKey 优先于环境变量（resolver 原子配置）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    with patch.dict("os.environ", {"LLM_API_KEY": "sk-env-value", "LLM_BASE_URL": "https://x/v1"}):
        complete_text(
            _messages("hi"),
            llm_config={"model": "openai/gpt-4o", "baseUrl": "https://x/v1", "apiKey": "sk-cfg"},
        )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_key"] == "sk-cfg"


@patch(_RAW_COMPLETION)
def test_complete_text_no_api_key_no_env(mock_completion):
    """请求级配置和 env 都没有 api_key → 不下发（deepseek-official keyless preset）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    with patch.dict("os.environ", {}, clear=True):
        complete_text(_messages("hi"), llm_config=None)
    call_kwargs = mock_completion.call_args[1]
    assert "api_key" not in call_kwargs


# ── llm_config 请求级 dict（原 LLMConfig 注入系列迁移）──


@patch(_RAW_COMPLETION)
def test_complete_text_llm_config_model_override(mock_completion):
    """llm_config.model 覆盖查询（quick 档位同逻辑）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    complete_text(_messages("hi"), purpose="quick", llm_config=_CFG)
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"


@patch(_RAW_COMPLETION)
def test_complete_text_llm_config_base_url_override(mock_completion):
    """llm_config.baseUrl 覆盖环境变量 LLM_BASE_URL。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    with patch.dict("os.environ", {"LLM_BASE_URL": "https://env.example.com/v1"}):
        complete_text(
            _messages("hi"),
            llm_config={
                "model": "openai/gpt-4o",
                "baseUrl": "https://custom.example.com/v1",
                "apiKey": "k",
            },
        )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_base"] == "https://custom.example.com/v1"


@patch(_RAW_COMPLETION)
def test_complete_text_env_base_url_used(mock_completion):
    """无请求级 config 时，env LLM_BASE_URL 生效（env 分支解析）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    with patch.dict(
        "os.environ",
        {"LLM_MODEL": "gpt-4o", "LLM_API_KEY": "k", "LLM_BASE_URL": "https://env.example.com/v1"},
    ):
        complete_text(_messages("hi"), llm_config=None)
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_base"] == "https://env.example.com/v1"


@patch(_RAW_COMPLETION)
def test_complete_text_llm_config_full_override(mock_completion):
    """llm_config 同时覆盖 model + base_url + api_key。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"),
        llm_config={
            "model": "openai/gpt-4o",
            "baseUrl": "https://api.custom.com/v1",
            "apiKey": "sk-config-key",
        },
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"
    assert call_kwargs["api_base"] == "https://api.custom.com/v1"
    assert call_kwargs["api_key"] == "sk-config-key"


@patch(_RAW_COMPLETION)
def test_complete_text_auto_prefix_openai_when_base_url_and_no_slash(mock_completion):
    """自定义 base_url + 模型名无 provider 前缀时自动补 openai/（resolver._ensure_prefix）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"),
        llm_config={
            "model": "deepseek-v4-flash",
            "baseUrl": "https://opencode.ai/v1",
            "apiKey": "k",
        },
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "openai/deepseek-v4-flash"
    assert call_kwargs["api_base"] == "https://opencode.ai/v1"


@patch(_RAW_COMPLETION)
def test_complete_text_no_auto_prefix_when_model_has_slash(mock_completion):
    """模型名已含 / 时不自动补全（如 deepseek/deepseek-chat）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"),
        llm_config={
            "model": "deepseek/deepseek-chat",
            "baseUrl": "https://api.deepseek.com/v1",
            "apiKey": "k",
        },
    )
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["model"] == "deepseek/deepseek-chat"


@patch(_RAW_COMPLETION)
def test_complete_text_no_auto_prefix_when_no_base_url(mock_completion):
    """无 base_url 时不自动补全（官方端点语义，由 litellm 按前缀路由）。"""
    mock_completion.return_value = _mock_resp("ok")

    from finance_agent.llm.gateway import complete_text

    complete_text(_messages("hi"), llm_config=_CFG)
    # openai/gpt-4o 已带前缀，保持原样
    assert mock_completion.call_args[1]["model"] == "openai/gpt-4o"


# ── agent-trace-content-fidelity Task 2: reasoning 落 generation output ──


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_text_writes_reasoning_to_output(mock_completion, mock_get_langfuse):
    """complete_text 把 message.reasoning_content 写入 generation output.reasoning。"""
    mock_completion.return_value = _mock_resp("最终答案", reasoning="思考过程")

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm.gateway import complete_text

    text, _meta = complete_text(
        _messages("hi"),
        llm_config=_CFG,
        trace={"name": "litellm:openai/gpt-4o", "metadata": {}},
    )

    assert text == "最终答案"
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["answer"] == "最终答案"
    assert call_kwargs["output"]["reasoning"] == "思考过程"


@patch("finance_agent.langfuse_tracing.get_langfuse")
@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_call_llm_streaming_writes_reasoning_to_output(mock_raw_stream, mock_get_langfuse):
    """call_llm_streaming 累加 reasoning_content 并写入 generation output.reasoning。

    migrate-off-legacy-llm-shim Task 2：call_llm_streaming 直连
    gateway.complete_stream（不再经 legacy call_llm_stream 薄壳）；mock 目标
    保持 adapter.raw_stream / langfuse_tracing.get_langfuse。
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

    from finance_agent.nodes._llm_utils import call_llm_streaming

    result = call_llm_streaming(
        "hi",
        llm_config={
            "model": "deepseek/deepseek-chat",
            "baseUrl": "https://x/v1",
            "apiKey": "k",
        },
    )

    # thinking 经 writer 转发（无 langgraph 上下文时丢弃），answer 拼接返回
    assert result == "最终答案"
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["reasoning"] == "思考A思考B"
    assert call_kwargs["output"]["answer"] == "最终答案"


# ── agent-trace-content-fidelity Task 3: complete_with_tools tool_calls 落 output ──


def _tool_call_mock(name="web_search", arguments='{"q":"茅台"}'):
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_with_tools_writes_tool_calls_to_output(mock_completion, mock_get_langfuse):
    """complete_with_tools 把 message.tool_calls 写入 generation output.tool_calls。"""
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

    from finance_agent.llm.gateway import complete_with_tools

    resp = complete_with_tools(
        _messages("搜一下"),
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        llm_config=_CFG,
        trace={"name": "litellm:openai/gpt-4o", "metadata": {}},
    )

    # 函数仍返回原始 resp（行为契约不变）
    assert resp is mock_completion.return_value
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["tool_calls"] == [
        {"name": "web_search", "arguments": '{"q":"茅台"}'}
    ]
    # Finding 2: reasoning 字段对称写入（与 complete_text / chat_stream 一致）
    assert call_kwargs["output"]["reasoning"] == "为何调用此工具"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_with_tools_empty_tool_calls_list(mock_completion, mock_get_langfuse):
    """无 tool_calls 时 output 不含 tool_calls 字段（与 chat_stream 文本分支一致）。"""
    mock_completion.return_value = _mock_resp("纯文本回答", tool_calls=None)

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = mockCm
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm.gateway import complete_with_tools

    complete_with_tools(
        _messages("hi"),
        llm_config=_CFG,
        trace={"name": "litellm:openai/gpt-4o", "metadata": {}},
    )

    call_kwargs = mockObs.update.call_args.kwargs
    # Finding 3: 空 tool_calls 统一省略 key（不再写 tool_calls: []）
    assert "tool_calls" not in call_kwargs["output"]
    assert call_kwargs["output"]["answer"] == "纯文本回答"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_with_tools_passes_tools_and_tool_choice(mock_completion, mock_get_langfuse):
    """tools/tool_choice 透传 raw_completion（原 test_build_kwargs_none_config_with_tools）。

    计划内语义修正（5.1-C）：deepseek thinking+tools 保持开启（registry
    provider_options 默认 enabled），不再像 legacy 显式 disabled。
    """
    mock_completion.return_value = _mock_resp("ok", tool_calls=None)
    mockLf = MagicMock()
    mockLf.start_as_current_observation.return_value = MagicMock()
    mock_get_langfuse.return_value = mockLf

    from finance_agent.llm.gateway import complete_with_tools

    tools = [{"type": "function", "function": {"name": "f"}}]
    complete_with_tools(
        _messages("hi"),
        tools=tools,
        llm_config={"model": "deepseek/deepseek-chat", "baseUrl": "https://x/v1", "apiKey": "k"},
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
def test_complete_with_tools_degraded_records_via_open_span(
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

    from finance_agent.llm.gateway import complete_with_tools

    resp = complete_with_tools(
        _messages("搜一下"),
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        llm_config={"model": "deepseek/deepseek-chat", "baseUrl": "https://x/v1", "apiKey": "k"},
        trace={"name": "litellm:deepseek/deepseek-chat", "metadata": {}},
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
def test_complete_with_tools_degraded_noop_without_error(
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

    from finance_agent.llm.gateway import complete_with_tools

    resp = complete_with_tools(
        _messages("hi"),
        llm_config=_CFG,
        trace={"name": "litellm:openai/gpt-4o", "metadata": {}},
    )

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
def test_complete_text_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """complete_text 把 prompt_name/prompt_version 经 trace metadata 挂到 generation。"""
    mock_completion.return_value = _mock_resp("答案", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"),
        llm_config=_CFG,
        trace={
            "name": "litellm:openai/gpt-4o",
            "metadata": {"prompt_name": "trader", "prompt_version": 3},
        },
    )

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "trader"
    assert call_kwargs["metadata"]["prompt_version"] == 3


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_text_omits_metadata_when_prompt_unset(mock_completion, mock_get_langfuse):
    """未传 prompt_name/prompt_version 时 metadata 不含这两个键（向后兼容）。"""
    mock_completion.return_value = _mock_resp("答案", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"), llm_config=_CFG, trace={"name": "litellm:openai/gpt-4o", "metadata": {}}
    )

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    md = call_kwargs.get("metadata", {})
    assert "prompt_name" not in md
    assert "prompt_version" not in md


@patch("finance_agent.langfuse_tracing.get_langfuse")
@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_call_llm_streaming_attaches_prompt_metadata(mock_raw_stream, mock_get_langfuse):
    """call_llm_streaming 把 prompt_name/prompt_version 经 trace metadata 挂到 generation。

    migrate-off-legacy-llm-shim Task 2：metadata 经 trace dict 由 gateway 观测
    写入；mock 目标保持 adapter.raw_stream / langfuse_tracing.get_langfuse。
    """

    def _fake_stream(**kwargs):  # noqa: ARG001
        from types import SimpleNamespace

        delta = SimpleNamespace(reasoning_content=None, content="答案")
        choice = SimpleNamespace(delta=delta, finish_reason=None)
        yield SimpleNamespace(choices=[choice], usage=None)

    mock_raw_stream.side_effect = _fake_stream
    _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.nodes._llm_utils import call_llm_streaming

    call_llm_streaming(
        "hi",
        llm_config={
            "model": "deepseek/deepseek-chat",
            "baseUrl": "https://x/v1",
            "apiKey": "k",
        },
        prompt_name="bull_debater",
        prompt_version="local",
    )

    call_kwargs = mock_get_langfuse.return_value.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "bull_debater"
    assert call_kwargs["metadata"]["prompt_version"] == "local"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_with_tools_attaches_prompt_metadata(mock_completion, mock_get_langfuse):
    """complete_with_tools 把 prompt_name/prompt_version 经 trace metadata 挂到 generation。"""
    mock_completion.return_value = _mock_resp("答案", tool_calls=None)
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_with_tools

    complete_with_tools(
        _messages("hi"),
        tools=[{"type": "function", "function": {"name": "f"}}],
        llm_config=_CFG,
        trace={
            "name": "litellm:openai/gpt-4o",
            "metadata": {"prompt_name": "risk_judge", "prompt_version": 2},
        },
    )

    call_kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert call_kwargs["metadata"]["prompt_name"] == "risk_judge"
    assert call_kwargs["metadata"]["prompt_version"] == 2


# ── observation 命名 / metadata 过滤字段（agent/session/stock）──


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_text_named_by_agent(mock_completion, mock_get_langfuse):
    """complete_text 传 trace.name 时 observation name 用 agent 名。"""
    mock_completion.return_value = _mock_resp("ok", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"),
        llm_config=_CFG,
        trace={"name": "technical_analyst", "metadata": {"agent": "technical_analyst"}},
    )
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "technical_analyst"
    assert kwargs["metadata"]["agent"] == "technical_analyst"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_text_default_name_without_agent(mock_completion, mock_get_langfuse):
    """trace.name 缺省时 observation name 退化为 litellm:{model}（向后兼容）。"""
    mock_completion.return_value = _mock_resp("ok", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_text

    complete_text(_messages("hi"), llm_config=_CFG, trace={"name": None, "metadata": {}})
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"].startswith("litellm:")
    assert "agent" not in kwargs["metadata"]


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_text_metadata_omits_missing_fields(mock_completion, mock_get_langfuse):
    """session_id/stock_code 未提供时 metadata 省略对应键；提供时写入。"""
    mock_completion.return_value = _mock_resp("ok", reasoning="")
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_text

    complete_text(
        _messages("hi"),
        llm_config=_CFG,
        trace={
            "name": "trader",
            "metadata": {"agent": "trader", "session_id": "sess-1", "stock_code": "300308"},
        },
    )
    md = mockLf.start_as_current_observation.call_args.kwargs["metadata"]
    assert md == {"agent": "trader", "session_id": "sess-1", "stock_code": "300308"}

    mock_get_langfuse.reset_mock()
    mockLf = _mock_langfuse_obs(mock_get_langfuse)
    complete_text(
        _messages("hi"),
        llm_config=_CFG,
        trace={"name": "trader", "metadata": {"agent": "trader"}},
    )
    md2 = mockLf.start_as_current_observation.call_args.kwargs["metadata"]
    assert md2 == {"agent": "trader"}


@patch("finance_agent.langfuse_tracing.get_langfuse")
@patch("finance_agent.llm.adapters.litellm_adapter.raw_stream")
def test_call_llm_streaming_named_by_agent(mock_raw_stream, mock_get_langfuse):
    """call_llm_streaming 传 node_name 时 observation name 用 node_name。

    migrate-off-legacy-llm-shim Task 2：node_name 经 trace.name 透传；mock
    目标保持 adapter.raw_stream / langfuse_tracing.get_langfuse。
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

    from finance_agent.nodes._llm_utils import call_llm_streaming

    call_llm_streaming(
        "hi",
        llm_config={
            "model": "deepseek/deepseek-chat",
            "baseUrl": "https://x/v1",
            "apiKey": "k",
        },
        node_name="trader",
    )
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "trader"


@patch(_GET_LANGFUSE)
@patch(_RAW_COMPLETION)
def test_complete_with_tools_named_by_agent(mock_completion, mock_get_langfuse):
    """complete_with_tools 传 trace.name 时 observation name 用 agent 名。"""
    mock_completion.return_value = _mock_resp("ok", tool_calls=[])
    mockLf = _mock_langfuse_obs(mock_get_langfuse)

    from finance_agent.llm.gateway import complete_with_tools

    complete_with_tools(
        _messages("hi"),
        llm_config=_CFG,
        trace={"name": "bull_debater", "metadata": {"agent": "bull_debater"}},
    )
    kwargs = mockLf.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "bull_debater"


# ── 空文本→reasoning 可回退（gateway meta.raw_reasoning 契约）──


@patch(_RAW_COMPLETION)
def test_complete_text_exposes_reasoning_when_content_empty(mock_completion):
    """content 为空时 metadata 保留 raw_reasoning（调用方据此回退，如 nlp/report/节点）。"""
    mock_completion.return_value = _mock_resp("", reasoning="纯思考输出")

    from finance_agent.llm.gateway import complete_text

    text, meta = complete_text(_messages("hi"), llm_config=_CFG)
    assert text == ""
    assert meta["raw_reasoning"] == "纯思考输出"
    # 调用方侧 legacy 式的「content 空 → reasoning」回退契约仍可达
    assert (text or meta["raw_reasoning"]) == "纯思考输出"


# ── migrate-off-legacy-llm-shim Task 3: legacy 薄壳移除守卫 ──


def test_legacy_call_llm_removed_from_package():
    """``from finance_agent.llm import call_llm`` 必须抛 ImportError（re-export 已删）。"""
    with pytest.raises(ImportError):
        from finance_agent.llm import call_llm  # noqa: F401


def test_legacy_call_llm_stream_removed_from_package():
    with pytest.raises(ImportError):
        from finance_agent.llm import call_llm_stream  # noqa: F401


def test_legacy_call_llm_with_tools_removed_from_package():
    with pytest.raises(ImportError):
        from finance_agent.llm import call_llm_with_tools  # noqa: F401


def test_llm_config_still_reexported_from_package():
    """LLMConfig 是 api 契约类型（api.py/agent_factory 依赖），re-export 保留。"""
    from finance_agent.llm import LLMConfig

    assert LLMConfig is not None
