"""TDD tests for graph.py build_5layer_graph — ADR-0011 五层架构图拓扑。

测试图节点注册和边连接是否正确。
"""

from finance_agent.graph import build_5layer_graph


class TestBuild5LayerGraph:
    """5 层架构图构建测试。"""

    def test_graph_compiles(self):
        """图能成功编译。"""
        graph = build_5layer_graph()
        assert graph is not None

    def test_has_prep_nodes(self):
        """包含 PREP 阶段节点。"""
        graph = build_5layer_graph()
        nodes = set(graph.nodes.keys())
        assert "compute_metrics" in nodes

    def test_has_analyst_nodes(self):
        """包含 Layer I 分析师节点。"""
        graph = build_5layer_graph()
        nodes = set(graph.nodes.keys())
        assert "technical_analyst" in nodes

    def test_has_debate_nodes(self):
        """包含 Layer II 辩论节点（两轮）。"""
        graph = build_5layer_graph()
        nodes = set(graph.nodes.keys())
        assert "bull_r1" in nodes
        assert "bear_r1" in nodes
        assert "bull_r2" in nodes
        assert "bear_r2" in nodes
        assert "research_manager" in nodes

    def test_has_trader_and_risk_nodes(self):
        """包含 Layer III/IV 节点。"""
        graph = build_5layer_graph()
        nodes = set(graph.nodes.keys())
        assert "trader" in nodes
        assert "risk_judge" in nodes
        assert "aggressive_r1" in nodes
        assert "conservative_r1" in nodes
        assert "neutral_r1" in nodes

    def test_has_fund_manager_and_report(self):
        """包含 Layer V 和报告生成节点。"""
        graph = build_5layer_graph()
        nodes = set(graph.nodes.keys())
        assert "fund_manager" in nodes
        assert "generate_report" in nodes

    def test_has_citation_verification(self):
        """包含引用校验节点。"""
        graph = build_5layer_graph()
        nodes = set(graph.nodes.keys())
        assert "verify_citations" in nodes


class TestFmReturnReasoningContract:
    """calibrate-fm-approval 回路契约（线上 4.3 复现修复）：

    FM return 的 reasoning 必须被 state schema 声明——未声明键会被 LangGraph
    节点输出合并时丢弃，trader 重跑上下文拿不到退回意见（实测重跑输入与首跑
    逐字节相同，注入条件 ``and fm_reasoning`` 恒为假）。
    """

    def test_state_schema_declares_reasoning_key(self):
        from finance_agent.state import AnalysisState

        assert "fund_manager_decision_reasoning" in AnalysisState.__annotations__

    def test_compiled_graph_channel_keeps_reasoning(self):
        from finance_agent.graph import build_5layer_graph

        graph = build_5layer_graph()
        assert "fund_manager_decision_reasoning" in graph.channels
