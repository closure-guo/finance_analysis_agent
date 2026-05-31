"""ia.py 单元测试 — mock LLM，验证双阶段调用和报告组装。"""

from unittest.mock import patch

import pytest


@pytest.fixture
def ia_state():
    return {
        "stock_code": "600519",
        "stock_quote": {
            "name": "贵州茅台",
            "code": "600519",
            "PE": 25.0,
            "PB": 8.0,
            "price": 1700.0,
            "market_cap": 21000.0,
        },
        "industry_info": {"industry": "白酒"},
        "relative_valuation": {
            "PE": {"target": 25.0, "peer_avg": 30.0, "peer_min": 20.0, "peer_max": 40.0, "conclusion": "undervalued"},
            "PB": {"target": 8.0, "peer_avg": 9.0, "peer_min": 6.0, "peer_max": 12.0, "conclusion": "fair"},
        },
        "garp_result": {
            "pass": True,
            "failures": [],
            "details": {"PE": 25.0, "净利润增长率": 0.18, "ROE": 0.28, "负债率": 0.40},
        },
        "growth_rates": {},
        "traffic_lights": {},
        "anomalies": [],
        "peer_comparison": {"available": True},
        "income_statement": None,
    }


@patch("finance_agent.nodes.ia.call_llm")
def test_ia_analyze_calls_llm_twice(mock_llm, ia_state):
    mock_llm.side_effect = ["## 第3章\n行业概况", "这是执行摘要"]

    from finance_agent.nodes.ia import ia_analyze

    result = ia_analyze(ia_state)

    assert mock_llm.call_count == 2
    assert "investment_analysis" in result
    assert "investment_report" in result


@patch("finance_agent.nodes.ia.call_llm")
def test_ia_report_contains_chapters(mock_llm, ia_state):
    mock_llm.side_effect = ["## 第3章\n正文内容", "这是执行摘要"]

    from finance_agent.nodes.ia import ia_analyze

    result = ia_analyze(ia_state)
    report = result["investment_report"]

    assert "贵州茅台" in report
    assert "600519" in report
    assert "执行摘要" in report
    assert "免责声明" in report
    assert "正文内容" in report


@patch("finance_agent.nodes.ia.call_llm")
def test_ia_analysis_is_body_text(mock_llm, ia_state):
    mock_llm.side_effect = ["## 第3章\n正文", "摘要"]

    from finance_agent.nodes.ia import ia_analyze

    result = ia_analyze(ia_state)
    assert result["investment_analysis"] == "## 第3章\n正文"
