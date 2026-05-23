"""fa.py 单元测试 — mock LLM，验证双阶段调用和报告组装。"""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def fa_state(balance_sheet, income_statement, cash_flow, indicators):
    from finance_agent.metrics.solvency import calc_solvency
    from finance_agent.metrics.profitability import calc_profitability
    from finance_agent.metrics.efficiency import calc_efficiency
    from finance_agent.metrics.cashflow import calc_cashflow
    from finance_agent.metrics.dupont import calc_dupont
    from finance_agent.metrics.traffic_light import assess_traffic_lights

    solv = calc_solvency(balance_sheet, income_statement, indicators)
    prof = calc_profitability(balance_sheet, income_statement, indicators)
    eff = calc_efficiency(balance_sheet, income_statement, indicators)
    cf = calc_cashflow(balance_sheet, income_statement, cash_flow)
    dupont = calc_dupont(balance_sheet, income_statement)
    all_m = {"solvency": solv, "profitability": prof, "efficiency": eff, "cashflow": cf}
    tl = assess_traffic_lights(all_m)

    return {
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台", "code": "600519"},
        "industry_info": {"industry": "白酒"},
        "solvency_metrics": solv,
        "profitability_metrics": prof,
        "efficiency_metrics": eff,
        "cashflow_metrics": cf,
        "dupont_tree": dupont,
        "traffic_lights": tl,
        "anomalies": [],
        "growth_rates": {},
        "income_statement": income_statement,
    }


@patch("finance_agent.nodes.fa.call_llm")
def test_fa_analyze_calls_llm_twice(mock_llm, fa_state):
    mock_llm.side_effect = ["## 第3章\n正文内容", "这是执行摘要"]

    from finance_agent.nodes.fa import fa_analyze

    result = fa_analyze(fa_state)

    assert mock_llm.call_count == 2
    assert "financial_analysis" in result
    assert "financial_report" in result


@patch("finance_agent.nodes.fa.call_llm")
def test_fa_report_contains_chapters(mock_llm, fa_state):
    mock_llm.side_effect = ["## 第3章\n正文内容", "这是执行摘要"]

    from finance_agent.nodes.fa import fa_analyze

    result = fa_analyze(fa_state)
    report = result["financial_report"]

    assert "贵州茅台" in report
    assert "600519" in report
    assert "执行摘要" in report
    assert "免责声明" in report
    assert "正文内容" in report


@patch("finance_agent.nodes.fa.call_llm")
def test_fa_analysis_is_body_text(mock_llm, fa_state):
    mock_llm.side_effect = ["## 第3章\n正文", "摘要"]

    from finance_agent.nodes.fa import fa_analyze

    result = fa_analyze(fa_state)
    assert result["financial_analysis"] == "## 第3章\n正文"
