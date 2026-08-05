# trace-observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ReAct Agent 工具调用与网络搜索补齐 Langfuse trace span，使 trace 中「LLM 回复 / 工具调用 / 网络搜索」三类操作分层可观测。

**Architecture:** 在 `langfuse_tracing.py` 新增 `open_span(name, input)` 上下文管理器 helper（封装 `start_as_current_observation` + 优雅降级），在 `harness/loop.py` 工具执行处与 `web_search.py` 搜索执行处用 `open_span` 包裹，span 通过 contextvar 自动挂到现有 `react_loop` span 下。不改 SSE 事件流、不改前端。

**Tech Stack:** Python 3.12, Langfuse SDK, contextlib, unittest.mock, pytest

## Global Constraints

- 变量命名使用 camelCase（项目规范）
- 代码注释使用中文（项目规范）
- 优先使用 Python 标准库（contextlib.nullcontext 等）
- 未配置 Langfuse 时必须优雅降级，不影响业务流程
- span 创建不得改变 SSE 事件流、API 响应、工具执行结果
- 测试产物路径：fixtures → `tests/fixtures/`｜脚本 → `tests/scripts/`｜验证报告 → `tests/validation/`
- E2E 测试禁止 mock 被测系统（LLM 可用 TESTING=1 stub）

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `src/finance_agent/langfuse_tracing.py` | 新增 `open_span` helper，封装 span 创建与降级 | Modify |
| `src/finance_agent/harness/loop.py` | 工具执行处补 `tool:{name}` span | Modify |
| `src/finance_agent/web_search.py` | `tavily_search` 内补 `search_api_call` span | Modify |
| `tests/test_langfuse_tracing.py` | `open_span` 单元测试 | Create |
| `tests/test_tool_call_span.py` | 工具调用 span 单元测试 | Create |
| `tests/test_web_search_span.py` | 网络搜索 span 单元测试 | Create |
| `tests/test_span_business_invariant.py` | span 业务行为不变回归测试 | Create |
| `tests/scripts/verify_trace_observability.py` | 手动验证 Langfuse trace 结构脚本 | Create |

---

### Task 1: open_span helper

**Files:**
- Modify: `src/finance_agent/langfuse_tracing.py`
- Test: `tests/test_langfuse_tracing.py`

**Interfaces:**
- Consumes: `get_langfuse()`（现有，返回 Langfuse 客户端或 None）
- Produces: `open_span(name: str, input: dict | None = None) -> ContextManager[Optional[Observation]]`，yield observation 对象（已配置）或 None（降级），调用方用 `obs.update(output=...)` 记录 output

- [ ] **Step 1: Write the failing test**

Create `tests/test_langfuse_tracing.py`:

```python
"""langfuse_tracing.open_span 单元测试。

验证 open_span 在三种场景下的行为：
1. Langfuse 已配置时创建 span
2. Langfuse 未配置时优雅降级返回 None
3. span 创建异常时降级不影响业务
"""

from unittest.mock import MagicMock, patch

from finance_agent.langfuse_tracing import open_span


class TestOpenSpan:
    """open_span 优雅降级测试。"""

    def test_langfuse_configured_creates_span(self):
        """Langfuse 已配置时调用 start_as_current_observation 创建 span。"""
        mockClient = MagicMock()
        mockCm = MagicMock()
        mockObs = MagicMock()
        mockClient.start_as_current_observation.return_value = mockCm
        mockCm.__enter__.return_value = mockObs

        with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient):
            with open_span("tool:web_search", {"args": {"query": "test"}}) as obs:
                # 在 span 上下文内，obs 是 observation 对象
                assert obs is mockObs

        # 验证 start_as_current_observation 被正确调用
        mockClient.start_as_current_observation.assert_called_once_with(
            name="tool:web_search", as_type="span", input={"args": {"query": "test"}}
        )
        # 验证 span 上下文正确退出
        mockCm.__exit__.assert_called_once()

    def test_langfuse_not_configured_returns_none(self):
        """Langfuse 未配置时返回 None，不抛异常、不创建 span。"""
        with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None):
            with open_span("tool:web_search", {"args": {}}) as obs:
                assert obs is None

    def test_span_creation_exception_degrades(self):
        """start_as_current_observation 抛异常时降级为 None，业务流程继续。"""
        mockClient = MagicMock()
        mockClient.start_as_current_observation.side_effect = RuntimeError("langfuse down")

        with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient):
            with open_span("tool:web_search", {"args": {}}) as obs:
                # 降级后 obs 为 None，但业务代码仍能继续执行
                assert obs is None

    def test_open_span_allows_output_update(self):
        """调用方可在 span 内用 obs.update 记录 output。"""
        mockClient = MagicMock()
        mockObs = MagicMock()
        mockClient.start_as_current_observation.return_value = MagicMock()
        mockClient.start_as_current_observation.return_value.__enter__.return_value = mockObs

        with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient):
            with open_span("tool:echo", {"args": {"text": "hi"}}) as obs:
                if obs:
                    obs.update(output={"result": "echo: hi"})

        mockObs.update.assert_called_once_with(output={"result": "echo: hi"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_langfuse_tracing.py -v`
Expected: FAIL with `ImportError: cannot import name 'open_span' from 'finance_agent.langfuse_tracing'`

- [ ] **Step 3: Write minimal implementation**

Modify `src/finance_agent/langfuse_tracing.py`，在文件末尾（`get_callback_handler` 之后）追加：

```python
from contextlib import contextmanager
import logging

_span_logger = logging.getLogger("finance_agent.langfuse")


@contextmanager
def open_span(name: str, input: dict | None = None):
    """创建 Langfuse span 上下文管理器；未配置或异常时优雅降级。

    用于工具调用、网络搜索等非 LLM 操作的可观测性追踪。复用
    get_langfuse() 单例，已配置时调用 start_as_current_observation
    建立 span（as_type=span），未配置或异常时降级为 yield None（零开销，
    业务无感知）。调用方可用 obs.update(output=...) 记录 output。

    Args:
        name: span 名称（如 "tool:web_search"、"search_api_call"）
        input: span 的 input 字段（dict）

    Yields:
        observation 对象（已配置时）或 None（降级时）
    """
    client = get_langfuse()
    if client is None:
        yield None
        return
    try:
        cm = client.start_as_current_observation(
            name=name, as_type="span", input=input or {}
        )
    except Exception:
        _span_logger.warning("Langfuse span 创建失败: %s", name, exc_info=True)
        yield None
        return
    obs = cm.__enter__()
    try:
        yield obs
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            _span_logger.warning("Langfuse span 退出失败: %s", name, exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_langfuse_tracing.py -v`
Expected: PASS（4 个测试全过）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/langfuse_tracing.py tests/test_langfuse_tracing.py
git commit -m "feat: 新增 open_span helper 封装 Langfuse span 创建与优雅降级"
```

---

### Task 2: 工具调用 span（loop.py）

**Files:**
- Modify: `src/finance_agent/harness/loop.py:497-563`
- Test: `tests/test_tool_call_span.py`

**Interfaces:**
- Consumes: `open_span` from `finance_agent.langfuse_tracing`（Task 1 产出）
- Produces: 工具执行处包裹 `tool:{tool_name}` span，记录 input(args) / output(result)

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_call_span.py`:

```python
"""工具调用 Langfuse span 测试。

验证 ReAct Agent 执行工具时创建 tool:{name} span。
"""

from unittest.mock import MagicMock, patch

import pytest

from finance_agent.harness import Agent, PermissionMode
from finance_agent.harness.llm_client import LLMResponse


class MockLLMClient:
    """模拟 LLM 客户端，按预设序列返回响应。"""

    def __init__(self, responses):
        self._responses = responses
        self._callIndex = 0

    async def chat_stream(self, messages=None, tools=None, temperature=0.7, tool_choice=None):
        if self._callIndex >= len(self._responses):
            yield LLMResponse(text_delta="", is_finished=True)
            return
        chunks = self._responses[self._callIndex]
        self._callIndex += 1
        for chunk in chunks:
            yield chunk


def _makeToolCall(name, arguments):
    """构造工具调用对象。"""
    from finance_agent.harness.types import ToolCall

    return ToolCall(id="call_test", name=name, arguments=arguments)


@pytest.fixture
def echoTool():
    """简单的回显工具。"""

    async def echo(text: str) -> str:
        """回显输入文本

        Args:
            text: 要回显的文本
        """
        return f"echo: {text}"

    return echo


class TestToolCallSpan:
    """工具调用 span 可观测测试。"""

    @pytest.mark.asyncio
    async def test_tool_execution_creates_span(self, echoTool):
        """工具执行时创建 tool:{name} span，记录 input 与 output。"""
        mockLlm = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="查一下",
                        tool_calls=[_makeToolCall("echo", {"text": "hello"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="结果是 echo: hello", is_finished=True)],
            ]
        )
        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mockLlm,
            tools=[echoTool],
        )

        with patch("finance_agent.harness.loop.open_span") as mockOpenSpan:
            mockObs = MagicMock()
            mockOpenSpan.return_value.__enter__.return_value = mockObs
            async for _ in agent.run():
                pass

        # 验证 open_span 被调用，且 name 为 "tool:echo"
        mockOpenSpan.assert_called()
        spanNames = [
            (c.kwargs.get("name") or c.args[0]) for c in mockOpenSpan.call_args_list
        ]
        assert "tool:echo" in spanNames
        # 验证 input 含 args
        toolCall = [c for c in mockOpenSpan.call_args_list if (c.kwargs.get("name") or c.args[0]) == "tool:echo"][0]
        assert toolCall.kwargs.get("input", {}).get("args") == {"text": "hello"}
        # 验证 obs.update 被调用记录 output
        mockObs.update.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tool_call_span.py -v`
Expected: FAIL（`open_span` 未在 loop.py 中 import，mock 不生效，断言失败）

- [ ] **Step 3: Write minimal implementation**

Modify `src/finance_agent/harness/loop.py`：

首先在文件顶部 import 区追加（找现有 import 位置）：

```python
from finance_agent.langfuse_tracing import open_span
```

然后将工具执行处（约 533-563 行）用 `open_span` 包裹。原代码：

```python
                    # 执行工具：流式工具走 execute_stream，普通工具走 execute
                    if self.tools.is_streaming(tc.name):
                        # 流式工具：透传 PROGRESS / THINK 事件，提取最终 ToolResult
                        result = None
                        async for event in self.tools.execute_stream(tc.id, tc.name, tc.arguments):
                            if isinstance(event, StreamEvent):
                                if event.event_type == ActionType.PROGRESS:
                                    yield event
                                elif event.event_type == ActionType.THINK:
                                    yield event
                                elif (
                                    event.event_type == ActionType.TOOL_RESULT and event.tool_result
                                ):
                                    result = event.tool_result
                                    yield event
                            elif isinstance(event, ToolResult):
                                result = event

                        if result is None:
                            result = ToolResult(
                                tool_call_id=tc.id,
                                name=tc.name,
                                output="[错误] 流式工具未返回结果",
                                is_error=True,
                            )
                    else:
                        # 普通工具
                        result = await self.tools.execute(tc.id, tc.name, tc.arguments)
```

改为（用 `open_span` 包裹整个工具执行块）：

```python
                    # 执行工具：流式工具走 execute_stream，普通工具走 execute
                    # 用 open_span 包裹工具执行，创建 tool:{name} span（挂到 react_loop 下）
                    with open_span(
                        name=f"tool:{tc.name}", input={"args": tc.arguments}
                    ) as _toolObs:
                        if self.tools.is_streaming(tc.name):
                            # 流式工具：透传 PROGRESS / THINK 事件，提取最终 ToolResult
                            result = None
                            async for event in self.tools.execute_stream(tc.id, tc.name, tc.arguments):
                                if isinstance(event, StreamEvent):
                                    if event.event_type == ActionType.PROGRESS:
                                        yield event
                                    elif event.event_type == ActionType.THINK:
                                        yield event
                                    elif (
                                        event.event_type == ActionType.TOOL_RESULT and event.tool_result
                                    ):
                                        result = event.tool_result
                                        yield event
                                elif isinstance(event, ToolResult):
                                    result = event

                            if result is None:
                                result = ToolResult(
                                    tool_call_id=tc.id,
                                    name=tc.name,
                                    output="[错误] 流式工具未返回结果",
                                    is_error=True,
                                )
                        else:
                            # 普通工具
                            result = await self.tools.execute(tc.id, tc.name, tc.arguments)
                        # 记录工具执行结果到 span output
                        if _toolObs:
                            _toolObs.update(output={"result": result.output})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tool_call_span.py -v`
Expected: PASS

同时运行现有 loop 测试确保无回归：

Run: `uv run pytest tests/test_react_loop.py -v`
Expected: PASS（现有测试全过）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/harness/loop.py tests/test_tool_call_span.py
git commit -m "feat: 工具调用补 tool:{name} Langfuse span 实现分层可观测"
```

---

### Task 3: 网络搜索 span（web_search.py）

**Files:**
- Modify: `src/finance_agent/web_search.py:50-90`
- Test: `tests/test_web_search_span.py`

**Interfaces:**
- Consumes: `open_span` from `finance_agent.langfuse_tracing`（Task 1 产出）
- Produces: `tavily_search` 内创建 `search_api_call` span，记录 input(query, max_results) / output(count)

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_search_span.py`:

```python
"""网络搜索 Langfuse span 测试。

验证 tavily_search 执行时创建 search_api_call span。
"""

from unittest.mock import MagicMock, patch

from finance_agent.web_search import tavily_search


class TestSearchApiCallSpan:
    """网络搜索 span 可观测测试。"""

    def test_search_creates_search_api_call_span(self):
        """搜索执行时创建 search_api_call span，记录 input 与 output。"""
        mockTavily = MagicMock()
        mockTavily.search.return_value = {
            "results": [
                {"title": "测试结果", "url": "https://example.com", "content": "内容"}
            ],
            "answer": "AI 摘要",
        }

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=mockTavily),
            patch("finance_agent.web_search.open_span") as mockOpenSpan,
        ):
            mockObs = MagicMock()
            mockOpenSpan.return_value.__enter__.return_value = mockObs
            response = tavily_search("测试查询", max_results=3)

        # 验证 open_span 被调用创建 search_api_call span
        mockOpenSpan.assert_called_once_with(
            name="search_api_call",
            input={"query": "测试查询", "max_results": 3},
        )
        # 验证 output 记录了结果数量
        mockObs.update.assert_called_once_with(output={"count": 1})
        # 验证搜索结果正确
        assert response.count == 1
        assert response.results[0].title == "测试结果"

    def test_search_span_degrades_when_langfuse_unconfigured(self):
        """Langfuse 未配置时 span 降级，搜索仍正常返回结果。"""
        mockTavily = MagicMock()
        mockTavily.search.return_value = {
            "results": [{"title": "t", "url": "http://x", "content": "c"}],
            "answer": None,
        }

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=mockTavily),
            patch("finance_agent.web_search.open_span") as mockOpenSpan,
        ):
            # 模拟 open_span 真实降级行为：yield None
            from contextlib import contextmanager

            @contextmanager
            def _realOpenSpan(name, input=None):
                yield None

            mockOpenSpan.side_effect = _realOpenSpan
            response = tavily_search("降级测试", max_results=5)

        # 即使 span 降级，搜索结果仍正确
        assert response.count == 1
        assert response.query == "降级测试"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web_search_span.py -v`
Expected: FAIL（`open_span` 未在 web_search.py 中 import，mock 不生效）

- [ ] **Step 3: Write minimal implementation**

Modify `src/finance_agent/web_search.py`：

在文件顶部 import 区追加：

```python
from finance_agent.langfuse_tracing import open_span
```

然后将 `tavily_search` 函数（约 50-90 行）用 `open_span` 包裹。原代码：

```python
def tavily_search(query: str, max_results: int = 5) -> SearchResponse:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not configured")

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="basic",
        include_answer=True,
    )

    results: list[SearchResult] = []
    for r in response.get("results", []):
        results.append(
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
            )
        )

    answer = response.get("answer") or None

    return SearchResponse(query=query, results=results, count=len(results), answer=answer)
```

改为：

```python
def tavily_search(query: str, max_results: int = 5) -> SearchResponse:
    """Execute Tavily web search.

    Args:
        query: Search query string
        max_results: Max number of results (default 5)

    Returns:
        SearchResponse with results

    Raises:
        ValueError: If TAVILY_API_KEY not set
        RuntimeError: If Tavily API call fails
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not configured")

    from tavily import TavilyClient

    # 用 open_span 包裹搜索调用，创建 search_api_call span
    # 作为调用方 span（tool:web_search 或规则 pre_search）的子 span
    with open_span(
        name="search_api_call",
        input={"query": query, "max_results": max_results},
    ) as _searchObs:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=True,
        )

        results: list[SearchResult] = []
        for r in response.get("results", []):
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    content=r.get("content", ""),
                )
            )

        answer = response.get("answer") or None
        searchResponse = SearchResponse(
            query=query, results=results, count=len(results), answer=answer
        )
        # 记录搜索结果数量到 span output
        if _searchObs:
            _searchObs.update(output={"count": len(results)})

    return searchResponse
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_web_search_span.py -v`
Expected: PASS

同时运行现有 web_search 测试确保无回归：

Run: `uv run pytest tests/test_web_search_tool.py -v`
Expected: PASS（现有测试全过）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/web_search.py tests/test_web_search_span.py
git commit -m "feat: 网络搜索补 search_api_call Langfuse span 实现分层可观测"
```

---

### Task 4: 业务行为不变验证

**Files:**
- Test: `tests/test_span_business_invariant.py`

**Interfaces:**
- Consumes: Task 1-3 的 `open_span`、工具 span、搜索 span
- Produces: 回归测试，证明 span 对业务行为透明

- [ ] **Step 1: Write the failing test**

Create `tests/test_span_business_invariant.py`:

```python
"""span 业务行为不变回归测试。

验证 span 创建不改变 SSE 事件流、工具执行结果、搜索结果。
"""

from unittest.mock import MagicMock, patch

import pytest

from finance_agent.harness import Agent, PermissionMode
from finance_agent.harness.llm_client import LLMResponse
from finance_agent.web_search import tavily_search, SearchResponse


class MockLLMClient:
    """模拟 LLM 客户端。"""

    def __init__(self, responses):
        self._responses = responses
        self._callIndex = 0

    async def chat_stream(self, messages=None, tools=None, temperature=0.7, tool_choice=None):
        if self._callIndex >= len(self._responses):
            yield LLMResponse(text_delta="", is_finished=True)
            return
        chunks = self._responses[self._callIndex]
        self._callIndex += 1
        for chunk in chunks:
            yield chunk


def _makeToolCall(name, arguments):
    from finance_agent.harness.types import ToolCall

    return ToolCall(id="call_test", name=name, arguments=arguments)


@pytest.fixture
def echoTool():
    async def echo(text: str) -> str:
        """回显

        Args:
            text: 文本
        """
        return f"echo: {text}"

    return echo


class TestSpanBusinessInvariant:
    """span 不改变业务行为测试。"""

    @pytest.mark.asyncio
    async def test_span_transparent_to_sse_events(self, echoTool):
        """有 span 时 SSE 事件流与无 span 时完全一致。"""
        mockLlm = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="查",
                        tool_calls=[_makeToolCall("echo", {"text": "hi"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="done", is_finished=True)],
            ]
        )
        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mockLlm,
            tools=[echoTool],
        )

        # 收集事件流（open_span 真实降级为 None，模拟无 span）
        from contextlib import contextmanager

        @contextmanager
        def _noopSpan(name, input=None):
            yield None

        eventsNoSpan = []
        with patch("finance_agent.harness.loop.open_span", side_effect=_noopSpan):
            async for event in agent.run():
                eventsNoSpan.append((event.event_type, event.content))

        # 重新运行（open_span 真实创建 mock span）
        mockLlm2 = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="查",
                        tool_calls=[_makeToolCall("echo", {"text": "hi"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="done", is_finished=True)],
            ]
        )
        agent2 = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mockLlm2,
            tools=[echoTool],
        )
        mockObs = MagicMock()
        eventsWithSpan = []
        with patch("finance_agent.harness.loop.open_span") as mockOpenSpan:
            mockOpenSpan.return_value.__enter__.return_value = mockObs
            async for event in agent2.run():
                eventsWithSpan.append((event.event_type, event.content))

        # 事件流完全一致（span 不改变业务输出）
        assert eventsNoSpan == eventsWithSpan

    def test_search_result_invariant_with_span_exception(self):
        """span 创建抛异常时，搜索结果仍正确返回。"""
        mockTavily = MagicMock()
        mockTavily.search.return_value = {
            "results": [{"title": "t", "url": "http://x", "content": "c"}],
            "answer": None,
        }

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=mockTavily),
            patch("finance_agent.web_search.open_span") as mockOpenSpan,
        ):
            # 模拟 open_span 内部异常但降级为 None
            from contextlib import contextmanager

            @contextmanager
            def _degradeSpan(name, input=None):
                yield None

            mockOpenSpan.side_effect = _degradeSpan
            response = tavily_search("异常测试", max_results=2)

        # 业务结果不受 span 故障影响
        assert response.count == 1
        assert response.query == "异常测试"
```

- [ ] **Step 2: Run test to verify it fails then passes**

Run: `uv run pytest tests/test_span_business_invariant.py -v`
Expected: PASS（这些是回归测试，验证现有实现的行为不变；如果 Task 1-3 正确实现，应直接通过）

- [ ] **Step 3: Commit**

```bash
git add tests/test_span_business_invariant.py
git commit -m "test: 新增 span 业务行为不变回归测试"
```

---

### Task 5: 质量门禁与人工验证

**Files:**
- Create: `tests/scripts/verify_trace_observability.py`
- Create: `tests/validation/trace-observability-report.md`（人工验证后填写）

**Interfaces:**
- Consumes: Task 1-4 的全部实现
- Produces: 质量门禁通过 + 手动验证脚本 + 人工验证报告

- [ ] **Step 1: Run full test suite + lint + type check**

Run:
```bash
uv run pytest tests/test_langfuse_tracing.py tests/test_tool_call_span.py tests/test_web_search_span.py tests/test_span_business_invariant.py tests/test_react_loop.py tests/test_web_search_tool.py -v
```
Expected: 全部 PASS

Run: `uv run ruff check src/finance_agent/langfuse_tracing.py src/finance_agent/harness/loop.py src/finance_agent/web_search.py`
Expected: 无错误

Run: `uv run mypy src/finance_agent/langfuse_tracing.py src/finance_agent/harness/loop.py src/finance_agent/web_search.py`
Expected: 无错误

- [ ] **Step 2: Create manual verification script**

Create `tests/scripts/verify_trace_observability.py`:

```python
"""手动验证 trace-observability 的 Langfuse trace 结构。

启动服务后运行此脚本，触发一次含工具调用 + 搜索的 chat，
然后拉取 Langfuse trace，断言 trace 含 tool:{name} 与 search_api_call span。

用法:
    uv run python tests/scripts/verify_trace_observability.py

前置条件:
    - 后端服务运行中（http://localhost:8000）
    - Langfuse 运行中（http://localhost:3000）
    - TAVILY_API_KEY 已配置
"""

import httpx
import time

BACKEND_URL = "http://localhost:8000"
LANGFUSE_URL = "http://localhost:3000"


def triggerChatWithSearch():
    """触发一次含时效性关键词的 chat，诱导工具调用 + 搜索。"""
    print("[1/3] 触发 chat 请求（含时效关键词）...")
    with httpx.Client(timeout=60) as client:
        # 发送一个会触发 web_search 工具调用的查询
        response = client.post(
            f"{BACKEND_URL}/api/chat",
            json={"query": "今天 A 股市场有什么最新消息？", "session_id": None},
        )
        sessionId = response.json().get("session_id")
        print(f"    会话 ID: {sessionId}")

        # 等待流式处理完成
        time.sleep(5)
        return sessionId


def fetchLangfuseTrace(sessionId):
    """从 Langfuse 拉取该会话的 trace。"""
    print(f"[2/3] 拉取 Langfuse trace（session={sessionId}）...")
    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{LANGFUSE_URL}/api/public/traces",
            params={"session_id": sessionId},
        )
        traces = response.json().get("data", [])
        if not traces:
            print("    ⚠️ 未找到 trace，请确认 Langfuse 已记录")
            return None
        return traces[0]


def assertSpanStructure(trace):
    """断言 trace 含 tool:{name} 与 search_api_call span。"""
    print("[3/3] 断言 trace span 结构...")
    observations = trace.get("observations", [])
    spanNames = [obs.get("name") for obs in observations]

    hasToolSpan = any(name and name.startswith("tool:") for name in spanNames)
    hasSearchSpan = "search_api_call" in spanNames

    print(f"    span 列表: {spanNames}")
    print(f"    含 tool:* span: {'✅' if hasToolSpan else '❌'}")
    print(f"    含 search_api_call span: {'✅' if hasSearchSpan else '❌'}")

    if hasToolSpan and hasSearchSpan:
        print("\n✅ 验证通过：trace 含工具调用 span 与网络搜索 span，分层可观测")
    else:
        print("\n❌ 验证失败：trace 缺少必要的 span")
        raise SystemExit(1)


def main():
    sessionId = triggerChatWithSearch()
    trace = fetchLangfuseTrace(sessionId)
    if trace:
        assertSpanStructure(trace)
    else:
        print("⚠️ 无法拉取 trace，请人工登录 Langfuse UI 查看")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run manual verification**

启动服务：
```bash
docker compose up -d --build
```

运行验证脚本：
```bash
uv run python tests/scripts/verify_trace_observability.py
```
Expected: 输出 `✅ 验证通过`，trace 含 `tool:*` 与 `search_api_call` span

人工登录 Langfuse UI（http://localhost:3000）确认 trace 树结构：
- `react_loop` span 下有 `tool:web_search` 子 span
- `tool:web_search` 下有 `search_api_call` 子 span
- LLM generation span 与 tool span 并列

- [ ] **Step 4: Write validation report**

Create `tests/validation/trace-observability-report.md`，记录：
- 验证日期、环境
- Langfuse trace 截图（span 树结构）
- span 列表（含 tool:* 与 search_api_call）
- 结论：「LLM 回复 / 工具调用 / 网络搜索」三类操作在 trace 中分层可观测

- [ ] **Step 5: Commit**

```bash
git add tests/scripts/verify_trace_observability.py tests/validation/trace-observability-report.md
git commit -m "test: 新增 trace-observability 手动验证脚本与人工验证报告"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ `工具调用 span 可观测`（3 scenarios）→ Task 2 实现 + Task 2/4 测试
- ✅ `网络搜索 span 可观测`（3 scenarios）→ Task 3 实现 + Task 3/4 测试
- ✅ `open_span helper 优雅降级`（3 scenarios）→ Task 1 实现 + Task 1 测试
- ✅ `span 不改变业务行为`（2 scenarios）→ Task 4 测试

**2. Placeholder scan:** 无 TBD/TODO，每个 step 含完整代码或命令。

**3. Type consistency:** `open_span(name, input)` 签名在 Task 1-4 一致；`_toolObs` / `_searchObs` 变量名 camelCase 一致；mock 对象 `mockObs` 命名一致。
