"""formatters.py 单元测试。"""


def test_format_stock_header():
    from finance_agent.formatters import format_stock_header

    result = format_stock_header(
        {"name": "贵州茅台", "code": "600519", "price": 1800},
        {"industry": "白酒"},
    )
    assert "贵州茅台" in result
    assert "600519" in result
    assert "白酒" in result


def test_format_metrics_table():
    from finance_agent.formatters import format_metrics_table

    solvency = {"资产负债率": {"2024": 40.0, "2023": 38.9}}
    profitability = {"ROE": {"2024": 28.0, "2023": 27.0}}
    efficiency = {"存货周转率": {"2024": 6.0, "2023": 5.0}}
    cashflow = {"FCF": {"2024": 100.0, "2023": 80.0}}
    tl = {
        "solvency": {"资产负债率": {"2024": {"final": "green"}}},
        "profitability": {"ROE": {"2024": {"final": "green"}}},
        "efficiency": {},
        "cashflow": {},
    }

    result = format_metrics_table(solvency, profitability, efficiency, cashflow, tl)
    assert "偿债能力" in result
    assert "盈利能力" in result
    assert "资产负债率" in result
    assert "2024" in result


def test_format_dupont_tree():
    from finance_agent.formatters import format_dupont_tree

    tree = {
        "L1": {"ROE": {"2024": 28.0, "2023": 27.0}},
        "L2": {"净利率": {"2024": 17.0}},
        "L3": {},
    }
    result = format_dupont_tree(tree)
    assert "杜邦分解" in result
    assert "ROE" in result


def test_format_health_score():
    from finance_agent.formatters import format_health_score

    score = {
        "total": 85.0,
        "rating": "healthy",
        "dimensions": {"solvency": 22.0, "profitability": 21.5},
    }
    result = format_health_score(score)
    assert "85" in result
    assert "健康" in result


def test_format_risk_summary_with_red():
    from finance_agent.formatters import format_risk_summary

    tl = {
        "solvency": {
            "资产负债率": {"2024": {"final": "red"}},
        },
    }
    result = format_risk_summary(tl, ["solvency.资产负债率: 红灯"])
    assert "红灯" in result


def test_format_risk_summary_empty():
    from finance_agent.formatters import format_risk_summary

    result = format_risk_summary({}, [])
    assert "无风险" in result


def test_format_growth_rates():
    from finance_agent.formatters import format_growth_rates

    rates = {"solvency": {"资产负债率": 0.15, "流动比率": -0.05}}
    result = format_growth_rates(rates)
    assert "15.0%" in result


def test_format_growth_rates_empty():
    from finance_agent.formatters import format_growth_rates

    assert "无增长率" in format_growth_rates({})
