"""run_deep_analysis 流式工具测试。

验证流式工具正确包装 5 层管线，yield PROGRESS 事件和最终 TOOL_RESULT with metadata。
"""

from unittest.mock import patch

import pytest

from finance_agent.agent_factory import _make_run_deep_analysis
from finance_agent.harness import ActionType


class FakeGraph:
    """模拟 LangGraph 的流式输出。"""

    def __init__(self, chunks: list[dict], custom_chunks: list | None = None):
        """chunks 是 graph.stream() 的 updates 输出序列。

        custom_chunks 是 custom 流输出序列（node_start/node_end/thinking 等
        生命周期事件），与 updates 交错 yield（真实 LangGraph 双模式流行为）。
        每个元素可以是单个 custom 事件 dict，或事件 dict 的 list（在对应
        updates chunk 之前依次 yield），用于模拟 start→chunk→end 的真实交错。
        """
        self._chunks = chunks
        self._custom_chunks = custom_chunks or []
        self.last_input: dict | None = None

    def stream(self, initial_state, config=None, stream_mode="updates"):
        """同步流式输出。stream_mode 可以是 list（如 ["updates", "custom"]）。"""
        self.last_input = initial_state
        # 真实双流交错：custom(node_start) → updates(chunk) → custom(node_end)。
        # 每对 (custom_events, chunk) 顺序 yield；custom_events 为 list 时逐个 yield。
        for i, chunk in enumerate(self._chunks):
            if i < len(self._custom_chunks):
                customs = self._custom_chunks[i]
                if isinstance(customs, dict):
                    customs = [customs]
                for c in customs:
                    yield ("custom", c)
            yield ("updates", chunk)


def _node_lifecycle(node_id: str, start_ts: int, end_ts: int) -> list[dict]:
    """构造某节点的 custom 生命周期事件对（node_start + node_end）。"""
    return [
        {"type": "node_start", "node": node_id, "ts": start_ts},
        {"type": "node_end", "node": node_id, "ts": end_ts, "duration_ms": end_ts - start_ts},
    ]


def _make_node_chunk(node_name: str, **updates) -> dict:
    """创建一个 graph.stream 的 chunk。"""
    return {node_name: updates}


def _make_final_chunk(report: str, chart_data: dict, analyst_reports: dict) -> dict:
    """创建包含最终报告的 chunk。"""
    return {
        "generate_report": {
            "final_report": report,
            "chart_data": chart_data,
            "analyst_reports": analyst_reports,
        }
    }


class TestRunDeepAnalysisStreaming:
    """run_deep_analysis 流式工具行为测试。"""

    @pytest.mark.asyncio
    async def test_yields_progress_events_for_each_node(self):
        """工具为每个管线节点 yield PROGRESS 事件。"""
        chunks = [
            _make_node_chunk("check_cache", status="done"),
            _make_node_chunk("fetch_data", stock_quote={"name": "贵州茅台"}),
            _make_node_chunk("compute_metrics", metrics={"pe": 30}),
            _make_final_chunk(
                report="# 贵州茅台报告",
                chart_data={"price": [1800, 1850]},
                analyst_reports={"technical": "看多"},
            ),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519", stock_name="贵州茅台"):
                events.append(event)

        progress_events = [e for e in events if e.event_type == ActionType.PROGRESS]
        assert len(progress_events) >= 3  # check_cache, fetch_data, compute_metrics

        # 验证进度事件包含节点名（通过 metadata.node 而非 content）
        nodes = [e.metadata.get("node") for e in progress_events]
        assert "check_cache" in nodes
        assert "fetch_data" in nodes

    @pytest.mark.asyncio
    async def test_final_event_has_tool_result_with_report(self):
        """最终事件是 TOOL_RESULT，包含报告 Markdown。"""
        chunks = [
            _make_node_chunk("check_cache"),
            _make_final_chunk(
                report="# 贵州茅台深度分析报告\n\n## 1. 封面",
                chart_data={"price": [1800]},
                analyst_reports={"technical": "看多"},
            ),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        # 最后一个事件应该是 TOOL_RESULT
        assert events[-1].event_type == ActionType.TOOL_RESULT
        tool_result = events[-1].tool_result
        assert tool_result is not None
        assert "贵州茅台" in tool_result.output
        assert "# 贵州茅台深度分析报告" in tool_result.output

    @pytest.mark.asyncio
    async def test_final_event_has_metadata_with_chart_data(self):
        """最终事件的 metadata 包含 chart_data。"""
        chart_data = {"price": [1800, 1850], "volume": [10000, 12000]}
        chunks = [
            _make_node_chunk("check_cache"),
            _make_final_chunk(
                report="# 报告",
                chart_data=chart_data,
                analyst_reports={"technical": "看多"},
            ),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        tool_result = events[-1].tool_result
        assert tool_result.metadata is not None
        assert "chart_data" in tool_result.metadata
        assert tool_result.metadata["chart_data"] == chart_data

    @pytest.mark.asyncio
    async def test_final_event_metadata_contains_file_paths(self):
        """最终事件 metadata 包含 file_paths（ReAct 报告产物链路）。

        生产链路中 file_paths 由 generate_file 节点更新写入 graph 状态，
        _merge_update 合并进 accumulated，最终透传到 TOOL_RESULT metadata。
        """
        file_paths = {
            "md": "/tmp/600519_x_report.md",  # noqa: S108  fixture 值非真实临时文件
            "docx": "/tmp/600519_x_report.docx",  # noqa: S108  fixture 值非真实临时文件
        }
        chunks = [
            _make_node_chunk("check_cache"),
            _make_node_chunk("generate_file", file_paths=file_paths),
            _make_final_chunk(report="# 报告", chart_data={}, analyst_reports={}),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        tool_result = events[-1].tool_result
        assert tool_result.metadata is not None
        assert "file_paths" in tool_result.metadata
        assert tool_result.metadata["file_paths"] == file_paths

    @pytest.mark.asyncio
    async def test_node_start_emitted_before_node_complete(self):
        """agent 路径：每个图节点首次出现时先产出 node_start，再产出 node_complete。"""
        chunks = [
            _make_node_chunk("check_cache", status="done"),
            _make_node_chunk("fetch_data", stock_quote={"name": "贵州茅台"}),
            _make_node_chunk("compute_metrics", metrics={"pe": 30}),
            _make_final_chunk(report="# 报告", chart_data={}, analyst_reports={}),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        progress_events = [e for e in events if e.event_type == ActionType.PROGRESS]
        # 每个节点应有 node_start + node_complete 两个 PROGRESS 事件
        starts = [e for e in progress_events if e.metadata.get("sse_type") == "node_start"]
        completes = [e for e in progress_events if e.metadata.get("sse_type") == "node_complete"]

        start_nodes = [e.metadata.get("node") for e in starts]
        complete_nodes = [e.metadata.get("node") for e in completes]

        assert "check_cache" in start_nodes
        assert "fetch_data" in start_nodes
        assert "compute_metrics" in start_nodes
        assert "check_cache" in complete_nodes
        assert "fetch_data" in complete_nodes

        # node_start 必须携带 node/layer/desc
        for e in starts:
            assert e.metadata.get("node")
            assert e.metadata.get("layer")
            assert e.metadata.get("desc")

        # 事件顺序：对同一节点，node_start 先于 node_complete
        seq = [(e.metadata.get("node"), e.metadata.get("sse_type")) for e in progress_events]
        first_start = seq.index(("check_cache", "node_start"))
        first_complete = seq.index(("check_cache", "node_complete"))
        assert first_start < first_complete

    @pytest.mark.asyncio
    async def test_node_start_not_repeated_for_same_node(self):
        """同一节点多次出现（多轮 updates chunk）时，node_start 只发一次。"""
        chunks = [
            _make_node_chunk("bull_r1", round=1),
            _make_node_chunk("bull_r1", round=1, extra="dup"),
            _make_node_chunk("bear_r1", round=1),
            _make_final_chunk(report="# 报告", chart_data={}, analyst_reports={}),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        progress_events = [e for e in events if e.event_type == ActionType.PROGRESS]
        starts = [
            e
            for e in progress_events
            if e.metadata.get("sse_type") == "node_start" and e.metadata.get("node") == "bull_r1"
        ]
        assert len(starts) == 1

    @pytest.mark.asyncio
    async def test_layer1_parallel_analysts_emit_independent_events(self):
        """Layer I 4 个并行分析师各自产出独立 node_start/node_complete（redesign delta task 1.1）。"""
        chunks = [
            _make_node_chunk("technical_analyst", summary="技术面"),
            _make_node_chunk("fundamental_analyst", summary="基本面"),
            _make_node_chunk("macro_analyst", summary="宏观"),
            _make_node_chunk("sentiment_analyst", summary="舆情"),
            _make_final_chunk(report="# 报告", chart_data={}, analyst_reports={}),
        ]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        progress_events = [e for e in events if e.event_type == ActionType.PROGRESS]
        complete_nodes = [
            e.metadata.get("node")
            for e in progress_events
            if e.metadata.get("sse_type") == "node_complete"
        ]
        # 4 个分析师各自有独立 node_complete
        for analyst in (
            "technical_analyst",
            "fundamental_analyst",
            "macro_analyst",
            "sentiment_analyst",
        ):
            assert analyst in complete_nodes, f"{analyst} 缺少独立 node_complete"

    @pytest.mark.asyncio
    async def test_node_end_emits_node_timing_event(self):
        """node_end 到达时下发 node_timing 事件携带真实耗时（task 1.4）。

        真实时序：custom node_start 在 updates chunk 前到达，node_end 在其后到达。
        node_complete 由 updates chunk 驱动（此刻 node_end 未到、duration 不可得），
        故真实耗时经独立 node_timing 事件下发，前端据此覆盖 updates 近似值。
        """
        chunks = [
            _make_node_chunk("check_cache", status="done"),
            _make_final_chunk(report="# 报告", chart_data={}, analyst_reports={}),
        ]
        custom_chunks = [
            # 第 1 对（check_cache chunk 前）：node_start
            {"type": "node_start", "node": "check_cache", "ts": 1_700_000_001_000},
            # 第 2 对（final chunk 前）：check_cache 的 node_end
            {"type": "node_end", "node": "check_cache", "ts": 1_700_000_001_020, "duration_ms": 20},
        ]
        fake_graph = FakeGraph(chunks, custom_chunks=custom_chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        timings = [
            e
            for e in events
            if e.event_type == ActionType.PROGRESS and e.metadata.get("sse_type") == "node_timing"
        ]
        cache_timing = next(e for e in timings if e.metadata.get("node_id") == "check_cache")
        assert cache_timing.metadata.get("server_start_ts") == 1_700_000_001_000
        assert cache_timing.metadata.get("server_end_ts") == 1_700_000_001_020
        assert cache_timing.metadata.get("server_duration_ms") == 20

    @pytest.mark.asyncio
    async def test_node_start_carries_server_start_ts(self):
        """node_start 事件附加后端真实入口时间戳（task 1.4）。

        custom node_start 在其 updates chunk 之前到达，故 node_start 事件可附加
        server_start_ts，供前端"当前节点已运行时长"基于真实入口计算。
        """
        chunks = [
            _make_node_chunk("check_cache", status="done"),
            _make_final_chunk(report="# 报告", chart_data={}, analyst_reports={}),
        ]
        custom_chunks = [
            {"type": "node_start", "node": "check_cache", "ts": 1_700_000_001_000},
            {"type": "node_end", "node": "check_cache", "ts": 1_700_000_001_020, "duration_ms": 20},
        ]
        fake_graph = FakeGraph(chunks, custom_chunks=custom_chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(api_key="test")
            events = []
            async for event in tool_fn(stock_code="600519"):
                events.append(event)

        starts = [
            e
            for e in events
            if e.event_type == ActionType.PROGRESS and e.metadata.get("sse_type") == "node_start"
        ]
        cache_start = next(e for e in starts if e.metadata.get("node_id") == "check_cache")
        assert cache_start.metadata.get("server_start_ts") == 1_700_000_001_000

    @pytest.mark.asyncio
    async def test_closure_params_injected_into_graph_input(self):
        """闭包参数（analysis_type, peer_codes, enable_web_search）注入到 graph 初始状态。"""
        chunks = [_make_final_chunk(report="# 报告", chart_data={}, analyst_reports={})]
        fake_graph = FakeGraph(chunks)

        with patch("finance_agent.graph.build_5layer_graph", return_value=fake_graph):
            tool_fn = _make_run_deep_analysis(
                api_key="test",
                analysis_type="technical",
                peer_codes=["000858"],
                enable_web_search=True,
            )
            async for _ in tool_fn(stock_code="600519", stock_name="贵州茅台"):
                pass

        assert fake_graph.last_input is not None
        assert fake_graph.last_input["stock_code"] == "600519"
        assert fake_graph.last_input["stock_name"] == "贵州茅台"
        assert fake_graph.last_input["analysis_type"] == "technical"
        assert fake_graph.last_input["peer_codes"] == ["000858"]
        assert fake_graph.last_input["enable_web_search"] is True
