import pandas as pd

from finance_agent.nodes.compute import _calc_quarterly_trend


def _q_income() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "季度": ["2026Q2", "2026Q1", "2025Q4", "2025Q3"],
            "归母净利润(单季)": [7.72e8, 5.71e8, 3.70e8, 4.62e8],
            "营业收入(单季)": [1.80e9, 1.12e9, 2.10e9, 0.95e9],
            "营业成本(单季)": [1.07e9, 0.68e9, 1.30e9, 0.65e9],
            "环比": [35.32, 54.13, -19.91, 91.60],
            "同比": [220.08, 488.29, -11.20, 225.07],
            # fetch 层宽窗口算好随行携带；object dtype 保留 None 语义
            "营收同比": pd.Series([89.47, None, None, None], dtype=object),
        }
    )


class TestQuarterlyTrendExtended:
    def test_revenue_gross_margin_series(self):
        trend = _calc_quarterly_trend(_q_income())
        assert trend["revenue"] == [18.0, 11.2, 21.0, 9.5]
        # 2026Q2: 1 - 10.7/18.0 = 40.56%
        assert trend["gross_margin"][0] == 40.56
        assert trend["gross_margin"][2] == 38.1

    def test_revenue_yoy_passthrough(self):
        trend = _calc_quarterly_trend(_q_income())
        # 营收同比由 fetch 层在宽窗口（截断前）算好随行携带，compute 仅透传
        assert trend["revenue_yoy"] == [89.47, None, None, None]

    def test_missing_cost_yields_none_margin(self):
        df = _q_income()
        df.loc[df["季度"] == "2025Q3", "营业成本(单季)"] = None
        trend = _calc_quarterly_trend(df)
        assert trend["gross_margin"][3] is None
