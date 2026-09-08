"""deep 管线 root span 修复测试(ADR-0015 缺陷:deep 缺 root span)。

根因:v4 CallbackHandler 在 LangGraph graph.stream 不建主 trace,deep 模式
_stream_graph / _run_graph_streaming 没有手动 root span,导致内部
generation / 数据源 span 各自成孤立 trace(Langfuse UI 看不到 deep 内容)。
修复:仿 quick react_loop,手动 start_as_current_observation + propagate_attributes。
"""

from unittest.mock import MagicMock, patch


def _fake_graph():
    """最小 graph mock:stream 返回空迭代器,不真跑管线。"""
    g = MagicMock()
    g.stream.return_value = iter([])
    return g


class TestStreamGraphRootSpan:
    """agent_factory._stream_graph(quick→deep 工具路径)。"""

    def test_creates_root_span(self):
        from finance_agent.agent_factory import _stream_graph

        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph),
        ):
            list(
                _stream_graph(
                    {"stock_code": "600519", "stock_name": "贵州茅台"},
                    session_id="sess-1",
                )
            )
        # root span 建立
        mock_lf.start_as_current_observation.assert_called_once()
        kwargs = mock_lf.start_as_current_observation.call_args.kwargs
        assert kwargs["as_type"] == "span"
        assert "deep_analysis" in kwargs["name"]
        assert "贵州茅台" in kwargs["name"]  # name 语义化(非模型名)
        mock_root.__enter__.assert_called_once()
        mock_root.__exit__.assert_called_once()

    def test_propagates_session(self):
        from finance_agent.agent_factory import _stream_graph

        mock_lf = MagicMock()
        mock_lf.start_as_current_observation.return_value = MagicMock()
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph),
            patch("langfuse.propagate_attributes") as mock_prop,
        ):
            mock_prop.return_value = MagicMock()
            list(_stream_graph({"stock_code": "600519"}, session_id="sess-1"))
        mock_prop.assert_called_once_with(session_id="sess-1")

    def test_no_langfuse_no_crash(self):
        from finance_agent.agent_factory import _stream_graph

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph),
        ):
            list(_stream_graph({"stock_code": "600519"}, session_id="sess-1"))  # 不抛


class TestRunGraphStreamingRootSpan:
    """api._run_graph_streaming(直接 deep SSE 入口)。"""

    def test_creates_root_span(self):
        # _run_graph_streaming 是 async generator,验证它建立 root span
        # 通过检查 api 模块的 graph 调用边界是否包了 start_as_current_observation
        # 这里间接验证:模块级应有 root span 建立逻辑(实现后补直接测试)
        pass


def _fake_graph_with_report(report_text: str = "# 贵州茅台分析报告\n完整正文……"):
    """yield 一个带 final_report 的 update chunk（模拟管线产物）。"""
    g = MagicMock()
    g.stream.return_value = iter([("updates", {"after_citation": {"final_report": report_text}})])
    return g


class TestStreamGraphEvalData:
    """deep-trace-eval-data：根 span 携带 query + metadata.report_markdown。"""

    def test_input_has_query_fallback(self):
        """无 query 时 input 含兜底「深度分析 {stock_name}({stock_code})」。"""
        from finance_agent.agent_factory import _stream_graph

        mock_lf = MagicMock()
        mock_lf.start_as_current_observation.return_value = MagicMock()
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph),
        ):
            list(
                _stream_graph(
                    {"stock_code": "600519", "stock_name": "贵州茅台"},
                    session_id="sess-1",
                )
            )
        kwargs = mock_lf.start_as_current_observation.call_args.kwargs
        assert kwargs["input"]["stock_code"] == "600519"
        assert kwargs["input"]["query"] == "深度分析 贵州茅台(600519)"

    def test_metadata_has_report_markdown(self):
        """退出时 metadata.report_markdown 写入完整报告。"""
        from finance_agent.agent_factory import _stream_graph

        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph_with_report),
        ):
            list(
                _stream_graph(
                    {"stock_code": "600519", "stock_name": "贵州茅台"},
                    session_id="sess-1",
                )
            )
        obs = mock_root.__enter__.return_value
        obs.update.assert_called()
        meta = obs.update.call_args.kwargs["metadata"]
        assert meta["report_markdown"] == "# 贵州茅台分析报告\n完整正文……"

    def test_no_langfuse_no_crash(self):
        from finance_agent.agent_factory import _stream_graph

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph_with_report),
        ):
            list(
                _stream_graph(
                    {"stock_code": "600519", "stock_name": "贵州茅台"},
                    session_id="sess-1",
                )
            )  # 不抛


class TestRunGraphStreamingEvalData:
    """deep-trace-eval-data：api 快路径根 span 携带 query + metadata.report_markdown。"""

    def test_input_has_query(self):
        from finance_agent.api import AnalyzeRequest, _run_graph_streaming

        mock_lf = MagicMock()
        mock_lf.start_as_current_observation.return_value = MagicMock()
        req = AnalyzeRequest(query="深度分析600519", stock_code="600519")
        fake = MagicMock()
        fake.stream.return_value = iter([])
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.api.graph", fake),
            patch("langfuse.propagate_attributes") as mock_prop,
        ):
            mock_prop.return_value = MagicMock()
            list(_run_graph_streaming("600519", "贵州茅台", req, "aid-1", 0.0, session_id="sess-1"))
        kwargs = mock_lf.start_as_current_observation.call_args.kwargs
        assert kwargs["input"]["stock_code"] == "600519"
        assert kwargs["input"]["query"] == "深度分析600519"

    def test_metadata_has_report_markdown(self):
        from finance_agent.api import AnalyzeRequest, _run_graph_streaming

        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root
        req = AnalyzeRequest(query="深度分析600519", stock_code="600519")
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.api.graph", _fake_graph_with_report()),
            patch("langfuse.propagate_attributes") as mock_prop,
        ):
            mock_prop.return_value = MagicMock()
            list(_run_graph_streaming("600519", "贵州茅台", req, "aid-1", 0.0, session_id="sess-1"))
        obs = mock_root.__enter__.return_value
        obs.update.assert_called()
        meta = obs.update.call_args.kwargs["metadata"]
        assert meta["report_markdown"] == "# 贵州茅台分析报告\n完整正文……"

    def test_no_langfuse_no_crash(self):
        from finance_agent.api import AnalyzeRequest, _run_graph_streaming

        req = AnalyzeRequest(query="深度分析600519", stock_code="600519")
        fake = MagicMock()
        fake.stream.return_value = iter([])
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.api.graph", fake),
            patch("langfuse.propagate_attributes") as mock_prop,
        ):
            mock_prop.return_value = MagicMock()
            list(
                _run_graph_streaming("600519", "贵州茅台", req, "aid-1", 0.0, session_id="sess-1")
            )  # 不抛


def _analyst_report_obj(name: str):
    from finance_agent.models import AnalystReport

    return AnalystReport(
        agent_name=name,
        summary=f"{name} 摘要",
        key_findings=[f"{name} 关键发现"],
        claims=[],
        markdown=f"## {name} 完整报告\n全文正文……",
    )


def _debate_msg_obj(role: str, round_: int):
    from finance_agent.models import DebateMessage

    return DebateMessage(
        role=role, round=round_, content=f"{role} r{round_} 论点", key_arguments=[]
    )


def _fake_graph_full_eval():
    """yield 全量评估字段（analyst_reports/debate_history/RM 结论/risk 裁决）。"""
    g = MagicMock()
    g.stream.return_value = iter(
        [
            (
                "updates",
                {
                    "after_citation": {
                        "analyst_reports": {"technical": _analyst_report_obj("technical")},
                        "debate_history": [_debate_msg_obj("bull", 1)],
                    }
                },
            ),
            (
                "updates",
                {"research_manager": {"research_manager_conclusion": "RM 结论：谨慎看多"}},
            ),
            (
                "updates",
                {"risk_judge": {"final_trade_decision": {"action": "buy", "confidence": 0.7}}},
            ),
            ("updates", {"after_report": {"final_report": "# 报告\n全文"}}),
        ]
    )
    return g


class TestStreamGraphEvalFullData:
    """deep-trace-eval-full-data：根 span metadata 含全量评估段。"""

    def test_metadata_has_full_eval_fields(self):
        from finance_agent.agent_factory import _stream_graph

        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph_full_eval),
        ):
            list(
                _stream_graph(
                    {"stock_code": "600519", "stock_name": "贵州茅台"},
                    session_id="sess-1",
                )
            )
        obs = mock_root.__enter__.return_value
        obs.update.assert_called()
        meta = obs.update.call_args.kwargs["metadata"]
        # 全量分析师报告（含 markdown 全文，非摘要）
        assert "analyst_reports" in meta
        assert meta["analyst_reports"]["technical"]["markdown"] == (
            "## technical 完整报告\n全文正文……"
        )
        assert meta["analyst_reports"]["technical"]["summary"] == "technical 摘要"
        # 辩论记录
        assert "debate_history" in meta
        assert meta["debate_history"][0]["role"] == "bull"
        assert meta["debate_history"][0]["content"] == "bull r1 论点"
        # RM 结论与风险裁决
        assert meta["research_manager_decision"] == "RM 结论：谨慎看多"
        assert meta["risk_judgment"] == {"action": "buy", "confidence": 0.7}
        # 既有 report_markdown 不回归
        assert meta["report_markdown"] == "# 报告\n全文"

    def test_missing_fields_omitted(self):
        from finance_agent.agent_factory import _stream_graph

        g = MagicMock()
        g.stream.return_value = iter([("updates", {"after_report": {"final_report": "# 报告"}})])
        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", g),
        ):
            list(_stream_graph({"stock_code": "600519"}, session_id="sess-1"))
        obs = mock_root.__enter__.return_value
        obs.update.assert_called()
        meta = obs.update.call_args.kwargs["metadata"]
        assert "debate_history" not in meta
        assert "research_manager_decision" not in meta
        assert "risk_judgment" not in meta
        assert "report_markdown" in meta  # 仍写（可为空串）


class TestRunGraphStreamingEvalFullData:
    """deep-trace-eval-full-data：api 快路径 metadata 含全量评估段。"""

    def test_metadata_has_full_eval_fields(self):
        from finance_agent.api import AnalyzeRequest, _run_graph_streaming

        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root
        req = AnalyzeRequest(query="深度分析600519", stock_code="600519")
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.api.graph", _fake_graph_full_eval()),
            patch("langfuse.propagate_attributes") as mock_prop,
        ):
            mock_prop.return_value = MagicMock()
            list(_run_graph_streaming("600519", "贵州茅台", req, "aid-1", 0.0, session_id="sess-1"))
        obs = mock_root.__enter__.return_value
        obs.update.assert_called()
        meta = obs.update.call_args.kwargs["metadata"]
        assert "analyst_reports" in meta
        assert meta["analyst_reports"]["technical"]["markdown"].startswith("## technical")
        assert "debate_history" in meta
        assert meta["research_manager_decision"] == "RM 结论：谨慎看多"
        assert meta["risk_judgment"] == {"action": "buy", "confidence": 0.7}


class TestRunGraphStreamingRootOutput:
    """api._run_graph_streaming 根 span 必须写 output（agent_factory 已写，api 漏写
    ——langfuse-trace-agent-attribution 4.5/4.6「不再 output=null」；线上复现：
    deep_analysis 根 span output 为 null）。"""

    def test_root_span_update_carries_output_summary(self):
        from unittest.mock import MagicMock, patch

        from finance_agent import api

        mock_lf = MagicMock()
        mock_root = MagicMock()
        mock_root.__enter__.return_value = mock_root
        mock_lf.start_as_current_observation.return_value = mock_root

        def _fake_graph():
            g = MagicMock()
            g.stream.return_value = iter([])
            return g

        req = api.AnalyzeRequest(
            stock_code="600519", query="全面分析", analysis_type="comprehensive"
        )
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mock_lf),
            patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
            patch("finance_agent.graph.build_5layer_graph", _fake_graph),
            patch("langfuse.propagate_attributes") as mock_prop,
        ):
            mock_prop.return_value = MagicMock()
            list(
                api._run_graph_streaming(
                    "600519", "贵州茅台", req, analysis_id="a1", start_time=0.0, session_id="s1"
                )
            )
        calls = [c for c in mock_root.update.call_args_list if "output" in (c.kwargs or {})]
        outs = [c.kwargs["output"] for c in calls if "stock_code" in (c.kwargs.get("output") or {})]
        assert outs, "根 span update 应携带 output 摘要（当前 api 路径漏写）"
