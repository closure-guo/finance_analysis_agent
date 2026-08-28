"""时点截断测试（spec decision-backtest「历史离线回放」Scenario「时点截断」）。"""

import pandas as pd
from evals.backtest.data_snapshot import disclosure_deadline, truncate_state


class TestDisclosureDeadline:
    def test_annual_report_next_year_april(self):
        assert disclosure_deadline("20241231") == "20250430"

    def test_quarters(self):
        assert disclosure_deadline("20240331") == "20240430"
        assert disclosure_deadline("20240630") == "20240831"
        assert disclosure_deadline("20240930") == "20241031"


class TestTruncateState:
    def _kline(self) -> pd.DataFrame:
        dates = [f"2025-01-{d:02d}" for d in range(1, 29)]
        return pd.DataFrame(
            {"日期": dates, "开盘": 10.0, "收盘": 10.5, "最高": 11.0, "最低": 9.5, "成交量": 100.0}
        )

    def test_kline_truncated_to_decision_date(self):
        state = {"kline": self._kline()}
        out = truncate_state(state, "2025-01-14")
        assert out["kline"]["日期"].max() == "2025-01-14"

    def test_financials_by_disclosure_not_period(self):
        bs = pd.DataFrame({"报告日": ["20241231", "20231231"], "资产总计": [1000.0, 900.0]})
        state = {"balance_sheet": bs}
        # 2024 年报披露截止 2025-04-30 → 决策日 2025-03-01 不可得，须剔除
        out = truncate_state(state, "2025-03-01")
        assert list(out["balance_sheet"]["报告日"]) == ["20231231"]
        out2 = truncate_state(state, "2025-05-01")
        assert list(out2["balance_sheet"]["报告日"]) == ["20241231", "20231231"]

    def test_point_in_time_fields_excluded(self):
        state = {"kline": self._kline(), "stock_quote": {"price": 10.0}, "industry_pe": {"pe": 20}}
        out = truncate_state(state, "2025-01-14")
        assert "stock_quote" not in out
        assert "industry_pe" not in out

    def test_news_events_filtered_by_date(self):
        state = {
            "news_list": [
                {"date": "2025-01-10", "title": "a"},
                {"date": "2025-01-20", "title": "b"},
            ],
            "key_events": [
                {"date": "2025-01-12", "title": "e1"},
                {"date": "2025-02-01", "title": "e2"},
            ],
        }
        out = truncate_state(state, "2025-01-14")
        assert [n["title"] for n in out["news_list"]] == ["a"]
        assert [e["title"] for e in out["key_events"]] == ["e1"]
