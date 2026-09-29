"""update-financial-freshness-and-valuation Task 11：新数据键的 citation 解析验证。

覆盖三类 claim 路径：
1. latest_period_snapshot.<键>（fetch 层 dict，直读路径）
2. quarterly_trend.gross_margin[0]（compute 派生，重算路径 + [N] 括号展开）
3. valuation_snapshot.PE_ttm（compute 派生，重算路径）
"""

import pandas as pd
import pytest

from finance_agent.citation import Claim, verify_claims


def _minimal_statements():
    bs = pd.DataFrame(
        {
            "报告日": ["20251231", "20241231"],
            "资产总计": [200.0, 180.0],
            "负债合计": [100.0, 95.0],
            "存货": [50.0, 48.0],
            "流动资产合计": [120.0, 110.0],
        }
    )
    inc = pd.DataFrame(
        {
            "报告日": ["20251231", "20241231"],
            "营业收入": [1000.0, 900.0],
            "营业成本": [600.0, 550.0],
            "归母净利润": [9.27e8, 6.88e8],
        }
    )
    cf = pd.DataFrame(
        {
            "报告日": ["20251231", "20241231"],
            "经营活动产生的现金流量净额": [100.0, 90.0],
        }
    )
    return bs, inc, cf


@pytest.fixture
def state():
    bs, inc, cf = _minimal_statements()
    return {
        "balance_sheet": bs,
        "income_statement": inc,
        "cash_flow_statement": cf,
        "latest_period_snapshot": {
            "报告日": "2026-06-30",
            "期类型": "中报",
            "毛利率(%)": 41.0,
            "资产负债率(%)": 47.85,
            "归母净利润(累计)": 13.43,
            "上年同期归母净利润": 0.94,
        },
        "quarterly_income": pd.DataFrame(
            {
                "季度": ["2026Q2", "2026Q1"],
                "归母净利润(单季)": [7.72e8, 5.71e8],
                "营业收入(单季)": [1.80e9, 1.12e9],
                "营业成本(单季)": [1.07e9, 0.68e9],
                "环比": [35.32, 54.13],
                "同比": [220.08, 488.29],
            }
        ),
        "stock_quote": {"market_cap": 1910.23, "PB": 15.02},
    }


def test_snapshot_dict_path_claim(state):
    claims = [
        Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="latest_period_snapshot.毛利率(%)",
            stated_value=41.0,
            interpretation="中报毛利率 41.0%",
            metric_name="毛利率",
            period="2026H1",
            direction="flat",
        )
    ]
    results = verify_claims(claims, state)
    assert results[0].status == "PASS"


def test_quarterly_gross_margin_bracket_index(state):
    claims = [
        Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="quarterly_trend.gross_margin[0]",
            stated_value=40.56,
            interpretation="2026Q2 单季毛利率 40.56%",
            metric_name="毛利率",
            period="2026Q2",
            direction="flat",
        )
    ]
    results = verify_claims(claims, state)
    assert results[0].status == "PASS"


def test_valuation_snapshot_derived_ttm(state):
    claims = [
        Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="valuation_snapshot.PE_ttm",
            stated_value=87.79,
            interpretation="TTM PE 约 87.8 倍",
            metric_name="PE",
            period="2026Q2",
            direction="flat",
        )
    ]
    results = verify_claims(claims, state)
    assert results[0].status == "PASS"
