"""根 trace 记录会话内容测试（Task 7: root span output 摘要 + react_loop answer）。

缺陷:Langfuse trace/session 级别只显示用户输入(root span output 为 null),
agent 产出需记录到根 span。本测试覆盖:
1. _build_trace_output 纯函数:从 accumulated 构建摘要 dict(截断防体积膨胀)
2. _stream_graph:在根 span 退出前(同一管线线程)写 root span output,
   修复 #67 跨线程 post-exit update 被 Langfuse v4 丢弃 → output=null
"""

from unittest.mock import MagicMock, patch


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


# ── _stream_graph: 根 span output 在退出前同线程写入 ──
def test_root_span_output_written_before_exit():
    """修复 #67 缺陷:output 须在根 span 退出前、同一(管线)线程写入。

    跨线程 post-exit update 被 Langfuse v4 丢弃 → deep_analysis 根 span
    output 恒 null。修复后:_stream_graph 本地累计 updates 摘要,finally 内、
    _root_cm.__exit__ 之前写 _root_obs.update(output=...)。
    """
    from finance_agent.agent_factory import _stream_graph

    mock_lf = MagicMock()
    mock_root = MagicMock()
    mock_lf.start_as_current_observation.return_value = mock_root
    fake_g = MagicMock()
    fake_g.stream.return_value = iter(
        [
            (
                "updates",
                {
                    "technical_analyst": {
                        "analyst_reports": {"technical": {"summary": "技术面摘要"}}
                    }
                },
            ),
            ("updates", {"generate_report": {"final_report": "## 投资分析\n正文内容"}}),
        ]
    )
    with (
        patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
        patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
        patch("finance_agent.graph.build_5layer_graph", return_value=fake_g),
    ):
        chunks = list(
            _stream_graph(
                {
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "analysis_type": "comprehensive",
                },
                session_id="sess-1",
            )
        )
    # 事件流透传不丢失
    assert len(chunks) == 2
    assert chunks[0][0] == "updates"

    # 根 obs 收到 output(修复前 _stream_graph 不写 → 本断言红)
    obs = mock_root.__enter__.return_value
    obs.update.assert_called_once()
    output = obs.update.call_args.kwargs["output"]
    assert output["stock_code"] == "600519"
    assert output["stock_name"] == "贵州茅台"
    assert output["analysis_type"] == "comprehensive"
    assert output["analyst_reports"]["technical"] == "技术面摘要"
    assert output["final_report_summary"].startswith("## 投资分析")

    # 写入发生在根 span 退出前(finally 内 __exit__ 之前)
    calls = [str(c) for c in mock_root.mock_calls]
    update_idx = next(i for i, s in enumerate(calls) if "update(output=" in s)
    exit_idx = calls.index("call.__exit__(None, None, None)")
    assert update_idx < exit_idx
