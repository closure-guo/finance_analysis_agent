"""端到端测试: 5 层架构图全流程 (mocked LLM + mocked PREP)。

验证 build_5layer_graph() 的完整图流：
  PREP → Layer I → Citation → Layer II → Layer III → Layer IV → Layer V → Report
"""

import json
from contextlib import ExitStack
from unittest.mock import patch

from finance_agent.graph import build_5layer_graph

# ── Mock LLM 响应 ──


def _analyst_report_json() -> str:
    return json.dumps(
        {
            "agent_name": "technical",
            "summary": "技术面偏多，MA5 上穿 MA20",
            "key_findings": ["MA5 上穿 MA20", "MACD 金叉"],
            "claims": [],  # 无 claim → citation_pass=True
            "markdown": "## 技术面分析\n短期趋势向上。",
        },
        ensure_ascii=False,
    )


def _bull_msg() -> str:
    return json.dumps(
        {
            "role": "bull",
            "round": 1,
            "content": "基本面强劲，建议买入",
            "key_arguments": ["ROE 28%", "负债率低"],
        },
        ensure_ascii=False,
    )


def _bear_msg() -> str:
    return json.dumps(
        {
            "role": "bear",
            "round": 1,
            "content": "估值偏高，存在回调风险",
            "key_arguments": ["PE 处于历史高位"],
        },
        ensure_ascii=False,
    )


def _risk_msg(role: str) -> str:
    return json.dumps(
        {
            "role": role,
            "round": 1,
            "content": f"{role} 视角分析",
            "key_arguments": ["论点"],
        },
        ensure_ascii=False,
    )


def _trade_decision_json() -> str:
    return json.dumps(
        {
            "action": "buy",
            "confidence": 0.7,
            "reasoning": "基本面强劲，技术面偏多",
            "position_size": "moderate",
        },
        ensure_ascii=False,
    )


def _fund_manager_json() -> str:
    return json.dumps(
        {"decision": "approve", "reasoning": "风险可控"},
        ensure_ascii=False,
    )


def _make_mock_llm():
    """根据 system prompt 内容返回不同的 mock 响应。"""

    def _mock(prompt, system="", **kwargs):
        s = system.lower() if system else ""
        if "技术面" in system:
            return _analyst_report_json()
        if "fund manager" in s:
            return _fund_manager_json()
        if "bull" in s:
            return _bull_msg()
        if "bear" in s:
            return _bear_msg()
        if "research manager" in s:
            return "综合多空观点，基本面强劲但需关注估值。"
        if "trader" in s:
            return _trade_decision_json()
        if "aggressive" in s:
            return _risk_msg("aggressive")
        if "conservative" in s:
            return _risk_msg("conservative")
        if "neutral" in s:
            return _risk_msg("neutral")
        if "risk judge" in s:
            return _trade_decision_json()
        return '{"error": "unknown agent"}'

    return _mock


def _mock_check_cache(state):
    return {"cache_result": "HIT"}


def _mock_validate(state):
    return {"validation_result": "PASS", "validation_warnings": []}


def _mock_compute(state):
    return {
        "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        "profitability_metrics": {"ROE": {"2024": 28.33}},
        "dupont_tree": {"L1": {"2024": {"ROE": 0.2833}}},
        "technical_indicators": {"MA": {"5": [None, None, None, None, 13.0]}},
        "risk_metrics": {"max_drawdown": 0.1, "volatility": 0.2, "var_95": 0.03},
    }


def _mock_generate_file(state):
    return {"file_path": None, "file_paths": None}


# ── 补丁路径 ──

_LLM_PATCHES = [
    "finance_agent.nodes.analysts.call_llm",
    "finance_agent.nodes.debate.call_llm",
    "finance_agent.nodes.research_manager.call_llm",
    "finance_agent.nodes.trader.call_llm",
    "finance_agent.nodes.risk.call_llm",
    "finance_agent.nodes.fund_manager.call_llm",
]


class Test5LayerPipelineE2E:
    """5 层架构图端到端测试。"""

    def test_full_pipeline_produces_report(self):
        """完整 5 层流程：PREP → 5 层 Agent → 报告生成。"""
        mock_llm = _make_mock_llm()

        with ExitStack() as stack:
            for p in _LLM_PATCHES:
                stack.enter_context(patch(p, side_effect=mock_llm))
            stack.enter_context(
                patch("finance_agent.nodes.cache.check_cache", side_effect=_mock_check_cache)
            )
            stack.enter_context(
                patch("finance_agent.nodes.validate.validate_node", side_effect=_mock_validate)
            )
            stack.enter_context(
                patch("finance_agent.nodes.compute.compute_metrics", side_effect=_mock_compute)
            )
            stack.enter_context(
                patch("finance_agent.nodes.output.generate_file", side_effect=_mock_generate_file)
            )

            graph = build_5layer_graph()
            initial_state = {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
            }
            result = graph.invoke(initial_state, config={"recursion_limit": 100})

        # 验证最终输出
        assert result is not None
        assert "final_report" in result
        assert "贵州茅台" in result["final_report"]
        assert "fund_manager_decision" in result
        assert result["fund_manager_decision"] == "approve"

    def test_pipeline_has_analyst_reports(self):
        """Layer I 产出了 analyst_reports。"""
        mock_llm = _make_mock_llm()

        with ExitStack() as stack:
            for p in _LLM_PATCHES:
                stack.enter_context(patch(p, side_effect=mock_llm))
            stack.enter_context(
                patch("finance_agent.nodes.cache.check_cache", side_effect=_mock_check_cache)
            )
            stack.enter_context(
                patch("finance_agent.nodes.validate.validate_node", side_effect=_mock_validate)
            )
            stack.enter_context(
                patch("finance_agent.nodes.compute.compute_metrics", side_effect=_mock_compute)
            )
            stack.enter_context(
                patch("finance_agent.nodes.output.generate_file", side_effect=_mock_generate_file)
            )

            graph = build_5layer_graph()
            result = graph.invoke(
                {"stock_code": "600519", "stock_name": "贵州茅台"},
                config={"recursion_limit": 100},
            )

        assert "analyst_reports" in result
        assert "technical" in result["analyst_reports"]

    def test_pipeline_has_debate_history(self):
        """Layer II 产出了 debate_history（2 轮 Bull/Bear）。"""
        mock_llm = _make_mock_llm()

        with ExitStack() as stack:
            for p in _LLM_PATCHES:
                stack.enter_context(patch(p, side_effect=mock_llm))
            stack.enter_context(
                patch("finance_agent.nodes.cache.check_cache", side_effect=_mock_check_cache)
            )
            stack.enter_context(
                patch("finance_agent.nodes.validate.validate_node", side_effect=_mock_validate)
            )
            stack.enter_context(
                patch("finance_agent.nodes.compute.compute_metrics", side_effect=_mock_compute)
            )
            stack.enter_context(
                patch("finance_agent.nodes.output.generate_file", side_effect=_mock_generate_file)
            )

            graph = build_5layer_graph()
            result = graph.invoke(
                {"stock_code": "600519", "stock_name": "贵州茅台"},
                config={"recursion_limit": 100},
            )

        assert "debate_history" in result
        # 2 轮 × 2 方 = 4 条消息
        assert len(result["debate_history"]) == 4

    def test_pipeline_has_trade_decision(self):
        """Layer III/IV 产出了交易决策。"""
        mock_llm = _make_mock_llm()

        with ExitStack() as stack:
            for p in _LLM_PATCHES:
                stack.enter_context(patch(p, side_effect=mock_llm))
            stack.enter_context(
                patch("finance_agent.nodes.cache.check_cache", side_effect=_mock_check_cache)
            )
            stack.enter_context(
                patch("finance_agent.nodes.validate.validate_node", side_effect=_mock_validate)
            )
            stack.enter_context(
                patch("finance_agent.nodes.compute.compute_metrics", side_effect=_mock_compute)
            )
            stack.enter_context(
                patch("finance_agent.nodes.output.generate_file", side_effect=_mock_generate_file)
            )

            graph = build_5layer_graph()
            result = graph.invoke(
                {"stock_code": "600519", "stock_name": "贵州茅台"},
                config={"recursion_limit": 100},
            )

        assert "final_trade_decision" in result
        decision = result["final_trade_decision"]
        assert decision.action == "buy"
