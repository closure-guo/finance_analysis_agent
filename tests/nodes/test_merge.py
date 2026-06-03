"""merge.py 单元测试 — 验证 pass-through、综合摘要、对比表格。"""

from unittest.mock import patch


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_pass_through_financial(mock_llm):
    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "financial",
        "financial_report": "# FA报告",
        "investment_report": "",
    }
    result = merge_reports(state)

    assert mock_llm.call_count == 0
    assert "# FA报告" in result["final_report"]


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_pass_through_investment(mock_llm):
    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "investment",
        "financial_report": "",
        "investment_report": "# IA报告",
    }
    result = merge_reports(state)

    assert mock_llm.call_count == 0
    assert "# IA报告" in result["final_report"]


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_comprehensive_calls_llm_once(mock_llm):
    mock_llm.return_value = "综合结论内容"

    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "comprehensive",
        "financial_report": "# FA",
        "investment_report": "# IA",
        "financial_analysis": "fa body",
        "investment_analysis": "ia body",
    }
    result = merge_reports(state)

    assert mock_llm.call_count == 1
    assert "综合结论" in result["final_report"]
    assert "综合结论内容" in result["final_report"]
    assert "# FA" in result["final_report"]
    assert "# IA" in result["final_report"]


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_idempotent(mock_llm):
    """多次调用 comprehensive merge，LLM 只触发一次。"""
    mock_llm.return_value = "综合结论"

    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "comprehensive",
        "financial_report": "# FA",
        "investment_report": "# IA",
        "financial_analysis": "fa",
        "investment_analysis": "ia",
    }

    merge_reports(state)
    merge_reports(state)

    assert mock_llm.call_count == 2


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_missing_fa_report(mock_llm):
    """comprehensive 模式下缺少 FA 报告时透传 IA。"""
    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "comprehensive",
        "financial_report": "",
        "investment_report": "# IA",
    }
    result = merge_reports(state)

    assert mock_llm.call_count == 0
    assert "# IA" in result["final_report"]


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_missing_ia_report(mock_llm):
    """comprehensive 模式下缺少 IA 报告时透传 FA。"""
    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "comprehensive",
        "financial_report": "# FA",
        "investment_report": "",
    }
    result = merge_reports(state)

    assert mock_llm.call_count == 0
    assert "# FA" in result["final_report"]


@patch("finance_agent.nodes.merge.call_llm")
def test_merge_comparison_table(mock_llm):
    """comprehensive 模式生成对比表格。"""
    mock_llm.return_value = "综合结论"

    from finance_agent.nodes.merge import merge_reports

    state = {
        "analysis_type": "comprehensive",
        "financial_report": "# FA",
        "investment_report": "# IA",
        "financial_analysis": "fa body",
        "investment_analysis": "ia body",
        "health_score": {
            "total": 78.1,
            "rating": "caution",
            "dimensions": {
                "solvency": 25.0,
                "profitability": 25.0,
                "efficiency": 15.6,
                "cashflow": 12.5,
            },
        },
        "stock_quote": {"PE": 25.5, "PB": 8.2},
        "garp_result": {"pass": True, "failures": [], "details": {}},
    }
    result = merge_reports(state)

    report = result["final_report"]
    assert "核心数据对比" in report
    assert "78.1 分" in report
    assert "25.0 分" in report
    assert "PE 25.50x" in report
    assert "✅ 通过" in report
