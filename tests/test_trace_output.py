"""根 trace 记录会话内容测试（Task 7: root span output 摘要 + react_loop answer）。

缺陷:Langfuse trace/session 级别只显示用户输入(root span output 为 null),
agent 产出需记录到根 span。本测试覆盖:
1. _build_trace_output 纯函数:从 accumulated 构建摘要 dict(截断防体积膨胀)
2. _stream_graph:root_obs_sink 透传根 obs 句柄(供事件循环侧写 output)
"""

from unittest.mock import MagicMock, patch


def _fake_graph():
    """最小 graph mock:stream 返回空迭代器,不真跑管线。"""
    g = MagicMock()
    g.stream.return_value = iter([])
    return g


# ── 纯函数: 从 accumulated 构建根 span output 摘要 ──
def test_build_trace_output_summarizes_agent_outputs():
    from finance_agent.agent_factory import _build_trace_output

    accumulated = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "final_report": "## 投资分析\n完整报告…" + "x" * 600,
        "analyst_reports": {
            "technical": {"summary": "技术面摘要"},
            "fundamental": {"summary": "基本面摘要"},
        },
        "trader_plan": {"decision": "buy", "confidence": 0.8},
    }
    out = _build_trace_output(accumulated)
    assert out["stock_code"] == "600519"
    assert out["stock_name"] == "贵州茅台"
    assert out["final_report_summary"].startswith("## 投资分析")
    assert len(out["final_report_summary"]) <= 600  # 摘要截断防体积膨胀
    assert out["analyst_reports"]["technical"] == "技术面摘要"
    assert out["trader_plan"]["decision"] == "buy"


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
        patch("finance_agent.graph.build_5layer_graph", _fake_graph),
    ):
        list(_stream_graph({"stock_code": "600519"}, session_id="sess-1", root_obs_sink=sink))
    assert sink.get("obs") is mock_root.__enter__.return_value
