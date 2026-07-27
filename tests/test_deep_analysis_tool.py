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
        """同步流式输出。"""
        self.last_input = initial_state
        yield from self._chunks


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

        # 验证进度事件包含节点名
        contents = [e.content for e in progress_events]
        assert any("check_cache" in c for c in contents)
        assert any("fetch_data" in c for c in contents)

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
