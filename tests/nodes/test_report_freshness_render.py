"""Task 12：报告渲染层确定性呈现最新报告期快照/估值快照/健康度行业口径。

spec industry-threshold-coverage「健康度评分行业口径披露」：报告渲染层 SHALL 使
读者可见评分所用口径——不能只依赖 LLM markdown 引用（三轮实跑证明其方差）。
"""

from finance_agent.nodes.report import _format_freshness_section


def test_full_section_with_industry_override():
    state = {
        "latest_period_snapshot": {
            "报告日": "2026-06-30",
            "期类型": "中报",
            "毛利率(%)": 41.0,
            "资产负债率(%)": 47.85,
            "存货": 88.33,
            "合同负债": 51.31,
            "营收同比(%)": 49.08,
            "归母净利同比(%)": 1328.72,
            "missing": [],
        },
        "valuation_snapshot": {
            "market_cap": 1918.64,
            "PE": None,
            "PE_ttm": 88.17,
            "PE_caliber": "derived_ttm",
            "PB": 15.09,
            "missing_reasons": [],
        },
        "health_score": {
            "total": 48.8,
            "rating": "warning",
            "industry_override": {
                "industry": "半导体设备",
                "metrics": ["存货周转率", "速动比率", "应付账款周转率"],
            },
        },
    }
    section = _format_freshness_section(state)
    assert section is not None
    assert "最新报告期快照" in section and "2026-06-30" in section and "中报" in section
    assert "41.0" in section and "47.85" in section and "88.33" in section and "51.31" in section
    assert "累计口径" in section
    assert "1918.64" in section and "88.17" in section and "TTM 推导口径" in section
    assert "48.8" in section
    assert "半导体设备" in section and "存货周转率" in section and "行业口径" in section


def test_generic_caliber_when_no_override():
    state = {
        "health_score": {
            "total": 55.0,
            "rating": "caution",
            "industry_override": {"industry": None, "metrics": []},
        }
    }
    section = _format_freshness_section(state)
    assert section is not None
    assert "通用口径" in section and "55.0" in section


def test_valuation_missing_declared():
    state = {
        "valuation_snapshot": {
            "market_cap": None,
            "PE": None,
            "PE_ttm": None,
            "PE_caliber": None,
            "PB": None,
            "missing_reasons": ["market_cap 缺失", "快照缺失"],
        },
    }
    section = _format_freshness_section(state)
    assert section is not None
    assert "估值数据缺失" in section and "market_cap 缺失" in section


def test_empty_state_returns_none():
    assert _format_freshness_section({}) is None
