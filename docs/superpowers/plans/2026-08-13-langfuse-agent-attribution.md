# langfuse-trace-agent-attribution 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Langfuse 中每个 LLM generation 以子 agent 名命名（`technical_analyst` 等），并带 `agent`/`session_id`/`stock_code` metadata，使 trace 列表可按 agent 定位调用。

**Architecture:** 在 `llm.py` 三入口（`call_llm`/`call_llm_stream`/`call_llm_with_tools`）+ harness `LiteLLMClient.chat_stream` 加可选 `agent`/`session_id`/`stock_code` 参数：observation `name = agent or f"litellm:{model}"`，metadata 经 `_generation_metadata` 合并。管线节点经 `call_llm_streaming(node_name=..., stock_code=...)` 透传；非管线调用点补固定 agent 标签。纯观测层，不碰业务字段。

**Tech Stack:** Python 3.12, FastAPI, Langfuse SDK 4.13, litellm, pytest（`tests/` 单测）。

## Global Constraints

- 不改变 SSE 事件流、API 响应、LLM 输入 prompt 与输出内容。
- Langfuse 未配置（`get_langfuse()` 返回 None）时全部跳过，业务不受影响。
- `agent` 缺省（空字符串）时 observation 名退化为现状 `litellm:{model}`，metadata 不写缺失键（向后兼容）。
- 测试必须 mock Langfuse（`_get_langfuse` 或 client `_langfuse`），不调用真实 LLM / Langfuse。
- 禁止动 `openspec/specs/` 主规范库；本 change 只经 delta（`openspec/changes/langfuse-trace-agent-attribution/`）sync。

---

### Task 1: llm.py 三入口 agent 命名 + metadata

**Files:**
- Modify: `src/finance_agent/llm.py`（`_prompt_metadata` 后加 `_generation_metadata`；`call_llm`/`call_llm_stream`/`call_llm_with_tools` 三入口）
- Test: `tests/test_llm.py`（文件末尾追加）

**Interfaces:**
- Produces: 三入口新增可选参数 `agent: str = ""`, `session_id: str | None = None`, `stock_code: str | None = None`；observation `name=agent or f"litellm:{model}"`；metadata 由 `_generation_metadata(prompt_name, prompt_version, agent, session_id, stock_code)` 生成（仅非空键）。

- [ ] **Step 1: 写失败测试（追加到 tests/test_llm.py）**

在 `tests/test_llm.py` 末尾追加（文件已 import `MagicMock`, `patch`, `_get_langfuse` 模式）：

```python
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


@patch("finance_agent.llm.litellm.completion")
@patch("finance_agent.llm._get_langfuse")
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


@patch("finance_agent.llm.litellm.completion")
@patch("finance_agent.llm._get_langfuse")
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


@patch("finance_agent.llm.litellm.completion")
@patch("finance_agent.llm._get_langfuse")
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


@patch("finance_agent.llm.litellm.completion")
@patch("finance_agent.llm._get_langfuse")
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


@patch("finance_agent.llm.litellm.completion")
@patch("finance_agent.llm._get_langfuse")
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_llm.py -k "named_by_agent or default_name_without_agent or metadata_omits_missing_fields" -q`
Expected: 5 个新测试 FAIL——`TypeError: call_llm() got an unexpected keyword argument 'agent'`

- [ ] **Step 3: 实现（llm.py）**

(1) 在 `_prompt_metadata` 定义后追加：

```python
def _generation_metadata(
    prompt_name: str | None,
    prompt_version: str | int | None,
    agent: str = "",
    session_id: str | None = None,
    stock_code: str | None = None,
) -> dict:
    """构造 generation metadata：prompt 元数据 + agent/session/stock 过滤字段。

    agent/session_id/stock_code 仅在显式提供时写入（与 _prompt_metadata 相同的
    向后兼容约定，不污染 metadata 命名空间）。
    """
    md = _prompt_metadata(prompt_name, prompt_version)
    if agent:
        md["agent"] = agent
    if session_id:
        md["session_id"] = session_id
    if stock_code:
        md["stock_code"] = stock_code
    return md
```

(2) `call_llm`（200 行）签名加三参数：

```python
    prompt_name: str | None = None,
    prompt_version: str | int | None = None,
    agent: str = "",
    session_id: str | None = None,
    stock_code: str | None = None,
) -> str:
```

其 observation（247-253 行）改为：

```python
            with _lf.start_as_current_observation(
                as_type="generation",
                name=agent or f"litellm:{model}",
                model=model,
                input={"messages": messages},
                metadata=_generation_metadata(
                    prompt_name, prompt_version, agent, session_id, stock_code
                ),
            ) as _gen:
```

(3) `call_llm_stream`（288 行）签名加同三参数；observation（344-347 行）同样改为 `name=agent or f"litellm:{model}"` + `metadata=_generation_metadata(...)`。

(4) `call_llm_with_tools`（436 行）签名加同三参数；其 observation（`name=f"litellm:{model}"` 处）同样改为 `name=agent or f"litellm:{model}"` + `metadata=_generation_metadata(...)`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_llm.py -k "named_by_agent or default_name_without_agent or metadata_omits_missing_fields" -q`
Expected: PASS（5 个新测试）

- [ ] **Step 5: 全量回归 llm 相关**

Run: `uv run pytest tests/test_llm.py tests/test_litellm_client.py -q`
Expected: 全部 PASS（含 content-fidelity 已并入的 reasoning/tool_calls/metadata 测试不回归）

- [ ] **Step 6: Commit**

```bash
git add src/finance_agent/llm.py tests/test_llm.py
git commit -m "feat: [trace] LLM 三入口 agent 命名 + agent/session/stock metadata"
```

---

### Task 2: call_llm_streaming 透传 agent + stock_code

**Files:**
- Modify: `src/finance_agent/nodes/_llm_utils.py`（`call_llm_streaming`，约 136-193 行）
- Test: `tests/test_llm_utils_metadata.py`（追加）

**Interfaces:**
- Consumes: `call_llm_stream(..., agent=..., stock_code=...)`（Task 1 产出）。
- Produces: `call_llm_streaming(prompt, system="", api_key=None, node_name="", llm_config=None, stock_code=None) -> str`——内部转发 `agent=node_name, stock_code=stock_code`。

- [ ] **Step 1: 写失败测试（追加到 tests/test_llm_utils_metadata.py）**

```python
@patch("finance_agent.llm.call_llm_stream")
def test_call_llm_streaming_forwards_agent_and_stock(mock_stream):
    """call_llm_streaming 把 node_name 作为 agent、stock_code 原样透传给 call_llm_stream。"""
    mock_stream.return_value = iter([("thinking", "t"), ("answer", "a")])

    from finance_agent.nodes._llm_utils import call_llm_streaming

    result = call_llm_streaming("prompt", system="s", node_name="technical_analyst", stock_code="300308")
    assert result == "a"
    kwargs = mock_stream.call_args.kwargs
    assert kwargs["agent"] == "technical_analyst"
    assert kwargs["stock_code"] == "300308"
```

（若该文件未 import `patch`，在文件头补 `from unittest.mock import patch`。若测试环境设置了 `TESTING` 导致走 stub 路径，测试开头加 `import os; os.environ.pop("TESTING", None)`。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_llm_utils_metadata.py::test_call_llm_streaming_forwards_agent_and_stock -q`
Expected: FAIL——`call_llm_stream()` got an unexpected keyword argument 'agent'（透传尚未实现）

- [ ] **Step 3: 实现（_llm_utils.py）**

`call_llm_streaming` 签名加 `stock_code: str | None = None`；其循环内调用（约 185-187 行）改为：

```python
    for kind, text in call_llm_stream(
        prompt,
        system=system,
        api_key=api_key,
        llm_config=llm_config,
        agent=node_name,
        stock_code=stock_code,
    ):
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_llm_utils_metadata.py::test_call_llm_streaming_forwards_agent_and_stock -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/_llm_utils.py tests/test_llm_utils_metadata.py
git commit -m "feat: [trace] call_llm_streaming 透传 node_name→agent + stock_code"
```

---

### Task 3: 管线节点 9 处 call_llm_streaming 补传 stock_code

**Files:**
- Modify: `src/finance_agent/nodes/analysts.py`（95/132/182/286 四处）、`src/finance_agent/nodes/research_manager.py:15`、`src/finance_agent/nodes/risk.py`（28/62 两处）、`src/finance_agent/nodes/trader.py:16`、`src/finance_agent/nodes/fund_manager.py:18`、`src/finance_agent/nodes/debate.py:22`

**Interfaces:**
- Consumes: `call_llm_streaming(..., node_name=..., stock_code=...)`（Task 2 产出）。
- 每处都在现有 `call_llm_streaming(...)` 调用里加一行 `stock_code=state.get("stock_code"),`（所有节点函数都有 `state: dict` 参数；`initial_state` 已含 `stock_code`，见 agent_factory.py:351）。

- [ ] **Step 1: 逐处加参（以 analysts.py:95-101 为模板）**

```python
    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="technical_analyst",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
    )
```

其余 8 处同样加 `stock_code=state.get("stock_code"),`（保持各自现有参数不变）。

- [ ] **Step 2: 节点测试回归**

Run: `uv run pytest tests/nodes/ -q`
Expected: PASS（节点测试不回归；透传行为由 Task 2 单测 + Task 6 实跑对账覆盖）

- [ ] **Step 3: Commit**

```bash
git add src/finance_agent/nodes/
git commit -m "feat: [trace] 管线节点 call_llm_streaming 传 stock_code"
```

---

### Task 4: harness generation agent 标签

**Files:**
- Modify: `src/finance_agent/harness/litellm_client.py`（构造器 + `chat_stream` observation + 本地 `_prompt_metadata`）
- Modify: `src/finance_agent/agent_factory.py`（`_make_llm_client` 构造 LiteLLMClient 时传 `agent="react_agent"`）
- Test: `tests/test_litellm_client.py`（追加）

**Interfaces:**
- Produces: `LiteLLMClient(..., agent: str | None = None)` 实例字段；`chat_stream` observation `name=self.agent or f"litellm:{self.model}"`，metadata 含 `agent`（非空时）。

- [ ] **Step 1: 写失败测试（追加到 tests/test_litellm_client.py）**

```python
@pytest.mark.asyncio
async def test_chat_stream_generation_named_by_agent(monkeypatch):
    """LiteLLMClient 设 agent 时 generation observation 用 agent 名。"""
    from finance_agent.harness.litellm_client import LiteLLMClient

    # 与 test_chat_stream_writes_reasoning_to_langfuse_output 同款流式 mock
    def _delta(reasoning=None, content=None):
        d = MagicMock()
        d.reasoning_content = reasoning
        d.content = content
        return d

    def _chunk(deltas, finish_reason=None):
        chunk = MagicMock()
        chunk.usage = None
        chunk.choices = [MagicMock(delta=deltas, finish_reason=finish_reason)]
        return chunk

    async def _mock_acompletion(**kwargs):
        async def _stream():
            yield _chunk(_delta(content="ok"), finish_reason="stop")

        return _stream()

    monkeypatch.setattr("litellm.acompletion", _mock_acompletion)

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)

    client = LiteLLMClient(model="deepseek-chat", agent="react_agent")
    monkeypatch.setattr(client, "_langfuse", MagicMock())
    client._langfuse.start_as_current_observation.return_value = mockCm

    out = []
    async for r in client.chat_stream(messages=[{"role": "user", "content": "hi"}]):
        out.append(r)
    kwargs = client._langfuse.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "react_agent"
    assert kwargs["metadata"]["agent"] == "react_agent"
```

（`LLMResponse` 需确认本文件已 import——若未，加 `from finance_agent.harness import LLMResponse`；现有 `chat_stream` 测试用同一模式，见 `tests/test_litellm_client.py:121-158`。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_litellm_client.py::test_chat_stream_generation_named_by_agent -q`
Expected: FAIL——`LiteLLMClient.__init__() got an unexpected keyword argument 'agent'`

- [ ] **Step 3: 实现（litellm_client.py + agent_factory.py）**

(1) 构造器（`__init__` 签名）加 `agent: str | None = None`，并 `self.agent = agent`。

(2) `chat_stream` 的 observation（约 157 行）改为：

```python
                _lf_cm = self._langfuse.start_as_current_observation(
                    name=self.agent or f"litellm:{self.model}",
                    as_type="generation",
                    input={"messages": messages},
                    model=self.model,
                    metadata=_generation_metadata(
                        self.prompt_name, self.prompt_version, self.agent
                    ),
                )
```

(3) 本文件本地 helper `_prompt_metadata`（38 行）后追加 `_generation_metadata`（与 llm.py 同构，仅 agent/session_id/stock_code）：

```python
def _generation_metadata(
    prompt_name: str | None,
    prompt_version: str | int | None,
    agent: str | None = None,
) -> dict:
    md = _prompt_metadata(prompt_name, prompt_version)
    if agent:
        md["agent"] = agent
    return md
```

(4) `agent_factory.py` `_make_llm_client`（862 行）构造 `LiteLLMClient(...)` 时加 `agent="react_agent"`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_litellm_client.py::test_chat_stream_generation_named_by_agent -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/harness/litellm_client.py src/finance_agent/agent_factory.py tests/test_litellm_client.py
git commit -m "feat: [trace] harness generation agent 标签(react_agent)"
```

---

### Task 5: 非管线 call_llm 调用点 agent 标签

**Files:**
- Modify: `src/finance_agent/react_agent.py`（369、430 两处）
- Modify: `src/finance_agent/nlp.py`（77）
- Modify: `src/finance_agent/events/web_fetcher.py`（135）
- Modify: `src/finance_agent/nodes/report.py`（144）

- [ ] **Step 1: 逐处加 agent 参数**

- `react_agent.py:369`：`call_llm(query, system=system, api_key=api_key, max_tokens=200, quick=True, agent="react_agent")`
- `react_agent.py:430`：同文件另一处 `call_llm(...)` 加 `agent="react_agent"`
- `nlp.py:77`：`call_llm(query, system=system, api_key=api_key, max_tokens=100, agent="intent_parser")`
- `web_fetcher.py:135`：`call_llm(_EXTRACTION_PROMPT..., system=..., temperature=0.1, agent="web_fetcher")`
- `report.py:144`：`call_llm(prompt, system=system, api_key=api_key, max_tokens=400, agent="report")`

（`api.py:1701` 的健康检查 `call_llm("Hi", ...)` 不加 agent——保持退化命名，不污染观测。）

- [ ] **Step 2: 相关模块测试回归**

Run: `uv run pytest tests/test_llm_utils_metadata.py tests/test_litellm_client.py tests/nodes/ -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/finance_agent/react_agent.py src/finance_agent/nlp.py src/finance_agent/events/web_fetcher.py src/finance_agent/nodes/report.py
git commit -m "feat: [trace] 非管线 LLM 调用点补 agent 标签"
```

---

### Task 6: 验证与 Langfuse 对账

**Files:**
- Test: `tests/validation/`（新增人工验证报告）

- [ ] **Step 1: 全量后端回归**

Run: `uv run pytest tests/ --ignore=tests/e2e -m "not live" -q`
Expected: 全部 PASS（含 content-fidelity 的 715 项基线）

- [ ] **Step 2: Lint + 类型**

Run: `uv run ruff check src/ tests/ && uv run mypy src/`
Expected: ruff 0 error；mypy 无新增错误

- [ ] **Step 3: 实跑对账**

在 vite dev + docker 后端跑一次深度分析，打开 Langfuse `localhost:3000`：
- `deep_analysis:{股票}` trace 下，generation `name` 应显示为 `technical_analyst`/`bull_debater`/`risk_judge`/`trader`/`fund_manager` 等，而非 `litellm:{model}`
- generation metadata 含 `agent`；管线节点 generation 含 `stock_code`
- `react_loop` trace 的 generation 显示 `react_agent`
- 人工验证报告落 `tests/validation/langfuse-trace-agent-attribution-validation.md`

- [ ] **Step 4: Commit 验证报告**

```bash
git add tests/validation/langfuse-trace-agent-attribution-validation.md
git commit -m "docs: [trace] agent 命名人工验证报告"
```

---

### Task 7: 根 trace 记录会话内容（deep_analysis root output + react_loop output）

**Files:**
- Modify: `src/finance_agent/agent_factory.py`（`_stream_graph` 捕获 root obs + 新 helper；`_make_run_deep_analysis` 传 sink + `_background_consume` 完成点写 output；`stream_agent_to_sse` 捕获 react obs + 追踪 ANSWER + 退出写 output）
- Test: `tests/test_deep_trace_root.py`（追加）+ 新 `tests/test_trace_output.py`

**Interfaces:**
- `_stream_graph(initial_state, config=None, session_id=None, root_obs_sink: dict | None = None)` → 进入根 span 后写 `root_obs_sink["obs"] = _root_obs`（供事件循环侧写 output）。
- `_build_trace_output(accumulated: dict) -> dict`：纯函数，从 accumulated 提取摘要级 agent 产出。
- `stream_agent_to_sse`：退出 react_loop span 前 `_react_obs.update(output={"answer": <最终回复>})`。

- [ ] **Step 1: 写失败测试（新 tests/test_trace_output.py）**

```python
from unittest.mock import MagicMock, patch

# ── 纯函数: 从 accumulated 构建根 span output 摘要 ──
def test_build_trace_output_summarizes_agent_outputs():
    from finance_agent.agent_factory import _build_trace_output

    accumulated = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "final_report": "## 投资分析\n完整报告…" + "x" * 600,
        "analyst_reports": {"technical": {"summary": "技术面摘要"}, "fundamental": {"summary": "基本面摘要"}},
        "trader_decision": {"decision": "buy", "confidence": 0.8},
    }
    out = _build_trace_output(accumulated)
    assert out["stock_code"] == "600519"
    assert out["stock_name"] == "贵州茅台"
    assert out["final_report_summary"].startswith("## 投资分析")
    assert len(out["final_report_summary"]) <= 600  # 摘要截断防体积膨胀
    assert out["analyst_reports"]["technical"] == "技术面摘要"
    assert out["trader_decision"]["decision"] == "buy"


# ── _stream_graph: root_obs_sink 透传根 obs 句柄 ──
def test_stream_graph_exposes_root_obs_via_sink():
    from finance_agent.agent_factory import _stream_graph

    mock_lf = MagicMock()
    mock_root = MagicMock()
    mock_lf.start_as_current_observation.return_value = mock_root
    sink: dict = {}
    with (
        patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
        patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
        patch("finance_agent.graph.build_5layer_graph", lambda: iter([MagicMock()])),
    ):
        from types import SimpleNamespace

        g = SimpleNamespace(stream=lambda *a, **k: iter([]))
        with patch("finance_agent.agent_factory.build_5layer_graph", return_value=g):
            list(_stream_graph({"stock_code": "600519"}, session_id="sess-1", root_obs_sink=sink))
    assert sink.get("obs") is mock_root.__enter__.return_value
```

（`build_5layer_graph` 的 patch 路径以现有 `tests/test_deep_trace_root.py` 的写法为准——`finance_agent.graph.build_5layer_graph` 或 `finance_agent.agent_factory.build_5layer_graph`，实现时按实际 import 修正一处即可。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_trace_output.py -q`
Expected: FAIL——`ImportError: cannot import name '_build_trace_output'` / `TypeError: _stream_graph() got an unexpected keyword argument 'root_obs_sink'`

- [ ] **Step 3: 实现（agent_factory.py）**

(1) 新增纯函数（`_stream_graph` 前）：

```python
def _build_trace_output(accumulated: dict) -> dict:
    """从管线 accumulated 状态构建根 span output 摘要（会话内容可见）。

    只放摘要级内容防 trace 体积膨胀：各 agent 产出摘要 + 最终报告前 500 字符。
    """
    out: dict = {}
    for key in ("stock_code", "stock_name", "analysis_type"):
        if accumulated.get(key):
            out[key] = accumulated[key]
    final_report = accumulated.get("final_report")
    if final_report:
        out["final_report_summary"] = final_report[:500] + ("…" if len(final_report) > 500 else "")
    reports = accumulated.get("analyst_reports") or {}
    if reports:
        out["analyst_reports"] = {
            k: (v.get("summary", "")[:200] if isinstance(v, dict) else str(v)[:200])
            for k, v in reports.items()
        }
    for key in ("trader_decision", "risk_decision", "fund_manager_decision"):
        v = accumulated.get(key)
        if v:
            out[key] = v if isinstance(v, dict) else str(v)[:300]
    return out
```

(2) `_stream_graph` 签名加 `root_obs_sink: dict | None = None`；进入 root span 处（原 `_root_cm.__enter__()`）改为：

```python
    _root_obs = _root_cm.__enter__()
    if root_obs_sink is not None:
        root_obs_sink["obs"] = _root_obs
```

(3) `_make_run_deep_analysis`：`_run_graph` 调 `_stream_graph(initial_state, session_id=session_id, root_obs_sink=_root_obs_sink)`；定义 `_root_obs_sink: dict = {}`。`_background_consume` 的 `if item is None: break` 之后、函数收尾处：

```python
        # 管线完成: 根 span 写 agent 产出（会话内容可见，不再 output=null）
        _root_obs = _root_obs_sink.get("obs")
        if _root_obs is not None:
            with contextlib.suppress(Exception):
                _root_obs.update(output=_build_trace_output(accumulated))
```

(4) `stream_agent_to_sse`：`_react_obs = _react_cm.__enter__()`（原 1102 行捕获返回）；循环内 ANSWER 分支追加 `_final_answer_parts.append(event.content)`（需先在函数顶部初始化 `_final_answer_parts: list[str] = []`）；退出处（`_react_cm.__exit__` 前）：

```python
        # ADR-0015: 退出 react_loop span 前记录 agent 最终回复（会话内容可见）
        if _react_obs is not None and _final_answer_parts:
            with contextlib.suppress(Exception):
                _react_obs.update(output={"answer": "".join(_final_answer_parts)})
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_trace_output.py tests/test_deep_trace_root.py -q`
Expected: PASS

- [ ] **Step 5: 回归**

Run: `uv run pytest tests/test_agent_factory.py tests/test_react_loop.py tests/test_deep_analysis_tool.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/finance_agent/agent_factory.py tests/test_trace_output.py tests/test_deep_trace_root.py
git commit -m "feat: [trace] 根 trace 记录会话内容 — root/react_loop span 写 agent 产出"
```

---

### Task 8: 验证与收尾

- [ ] 8.1 全量 `uv run pytest tests/ --ignore=tests/e2e -m "not live"` + `ruff check` + `mypy`（基线对比）
- [ ] 8.2 实跑深度分析，Langfuse 对账：session/trace 级可见 agent 输出（deep_analysis root span 与 react_loop span 的 output 非 null，含产出摘要/最终回复）；更新验证报告 `tests/validation/langfuse-trace-agent-attribution-validation.md`
- [ ] 8.3 commit 验证报告
