"""run_deep_analysis 流式工具测试。

验证流式工具正确包装 5 层管线，yield PROGRESS 事件和最终 TOOL_RESULT with metadata。
"""

from unittest.mock import patch

import pytest

from finance_agent.agent_factory import _make_run_deep_analysis
from finance_agent.harness import ActionType


class FakeGraph:
    """模拟 LangGraph 的流式输出。"""

    def __init__(self, chunks: list[dict]):
        """chunks 是 graph.stream() 的输出序列。"""
        self._chunks = chunks
        self.last_input: dict | None = None

    def stream(self, initial_state, config=None, stream_mode="updates"):
        """同步流式输出。stream_mode 可以是 list（如 ["updates", "custom"]）。"""
        self.last_input = initial_state
        for chunk in self._chunks:
            yield ("updates", chunk)


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
