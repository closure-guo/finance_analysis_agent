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
        }
    )


class TestQuarterlyTrendExtended:
    def test_revenue_gross_margin_series(self):
        trend = _calc_quarterly_trend(_q_income())
        assert trend["revenue"] == [18.0, 11.2, 21.0, 9.5]
        # 2026Q2: 1 - 10.7/18.0 = 40.56%
        assert trend["gross_margin"][0] == 40.56
        assert trend["gross_margin"][2] == 38.1

    def test_revenue_yoy_same_quarter_prev_year(self):
        trend = _calc_quarterly_trend(_q_income())
        # 2026Q2 vs 2025Q2 缺失 → None；2026Q1 同理；2025Q4/2025Q3 无 2024 数据 → None
        assert trend["revenue_yoy"] == [None, None, None, None]

    def test_missing_cost_yields_none_margin(self):
        df = _q_income()
        df.loc[df["季度"] == "2025Q3", "营业成本(单季)"] = None
        trend = _calc_quarterly_trend(df)
        assert trend["gross_margin"][3] is None

    def test_revenue_yoy_computed_when_prev_year_present(self):
        df = _q_income()
        extra = pd.DataFrame(
            {
                "季度": ["2025Q2"],
                "归母净利润(单季)": [0.94e8],
                "营业收入(单季)": [0.95e9],
                "营业成本(单季)": [0.65e9],
                "环比": [10.0],
                "同比": [50.0],
            }
        )
        trend = _calc_quarterly_trend(pd.concat([df, extra], ignore_index=True))
        # 2026Q2 vs 2025Q2: (18.0 - 9.5) / 9.5 * 100 = 89.47
        assert trend["revenue_yoy"][0] == 89.47
