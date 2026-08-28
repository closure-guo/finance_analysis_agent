"""时点截断测试（spec decision-backtest「历史离线回放」Scenario「时点截断」）。"""

import pandas as pd
import pytest
from evals.backtest.data_snapshot import (
    build_snapshot,
    disclosure_deadline,
    truncate_state,
)


class TestDisclosureDeadline:
    def test_annual_report_next_year_april(self):
        assert disclosure_deadline("20241231") == "20250430"

    def test_quarters(self):
        assert disclosure_deadline("20240331") == "20240430"
        assert disclosure_deadline("20240630") == "20240831"
        assert disclosure_deadline("20240930") == "20241031"

    def test_non_quarter_end_month_raises_value_error(self):
        # 非季末月份（如 5 月）→ 显式 ValueError 而非 KeyError (5,)
        with pytest.raises(ValueError, match="季末"):
            disclosure_deadline("20240531")
        with pytest.raises(ValueError, match="季末"):
            disclosure_deadline("20240115")

    def test_dashed_period_end_normalized(self):
        # 真实 fetch_quarterly_income 的报告日为 "2024-09-30"（akshare str[:10] 带横线）
        assert disclosure_deadline("2024-09-30") == "20241031"
        assert disclosure_deadline("2024-12-31") == "20250430"
        assert disclosure_deadline("2024-03-31") == "20240430"

    def test_unnormalizable_period_end_raises_value_error(self):
        # 归一化后非 8 位数字 → 保持显式 ValueError（由截断层捕获并剔除该行）
        with pytest.raises(ValueError):
            disclosure_deadline("N/A")
        with pytest.raises(ValueError):
            disclosure_deadline("")
        with pytest.raises(ValueError):
            disclosure_deadline("2024")


class TestMacroTruncation:
    def test_future_months_truncated(self):
        macro: dict = {
            "cpi": {
                "records": [
                    {"月份": "2024-12", "全国": 0.1},
                    {"月份": "2025-01", "全国": 0.2},
                    {"月份": "2025-02", "全国": 0.3},
                ],
                "as_of_date": "2025-06-01",
                "freshness": "fresh",
            },
            "pmi": [],  # 失败指标为空 list → 原样保留
        }
        out = truncate_state({"macro_indicators": macro}, "2025-01-14")
        cpi = out["macro_indicators"]["cpi"]
        assert [r["月份"] for r in cpi["records"]] == ["2024-12", "2025-01"]
        # 守卫键结构保留,as_of_date/freshness 原样
        assert cpi["as_of_date"] == "2025-06-01"
        assert cpi["freshness"] == "fresh"
        assert out["macro_indicators"]["pmi"] == []
        # 不改调用方对象
        assert len(macro["cpi"]["records"]) == 3

    def test_chinese_month_format_parsed(self):
        macro = {
            "cpi": {
                "records": [
                    {"月份": "2024年12月", "全国": 0.1},
                    {"月份": "2025年1月", "全国": 0.2},
                    {"月份": "2025年2月", "全国": 0.3},
                ],
                "as_of_date": None,
                "freshness": "stale",
            },
        }
        out = truncate_state({"macro_indicators": macro}, "2025-01-14")
        months = [r["月份"] for r in out["macro_indicators"]["cpi"]["records"]]
        assert months == ["2024年12月", "2025年1月"]

    def test_unparseable_month_records_dropped(self):
        macro = {
            "cpi": {
                "records": [
                    {"月份": "N/A", "全国": 0.1},
                    {"月份": "2025-01", "全国": 0.2},
                    {"月份": "", "全国": 0.3},
                ],
                "as_of_date": None,
                "freshness": "stale",
            },
        }
        out = truncate_state({"macro_indicators": macro}, "2025-01-14")
        months = [r["月份"] for r in out["macro_indicators"]["cpi"]["records"]]
        assert months == ["2025-01"]


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

    def test_peer_financials_excluded_as_point_in_time(self):
        peers = pd.DataFrame({"代码": ["600519", "000858"], "市盈率-动态": [30.0, 25.0]})
        state = {"kline": self._kline(), "peer_financials": peers}
        out = truncate_state(state, "2025-01-14")
        assert "peer_financials" not in out

    def test_reports_with_nan_report_date_dropped_without_crash(self):
        bs = pd.DataFrame(
            {"报告日": ["20231231", None, "20241231"], "资产总计": [900.0, 950.0, 1000.0]}
        )
        out = truncate_state({"balance_sheet": bs}, "2025-05-01")
        # NaN 报告日行被剔除（日期不可判 → 保守不保留），其余按披露截止正常截断
        assert list(out["balance_sheet"]["报告日"]) == ["20231231", "20241231"]

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

    def test_undated_news_event_entries_dropped(self):
        # 不变式：所有保留条目日期可判 ≤ T；无日期条目保守剔除（可能前视）
        state = {
            "news_list": [
                {"title": "no-date-field"},
                {"date": "", "title": "empty-date"},
                {"date": "2025-01-10", "title": "a"},
                "bare-string-item",
            ],
            "key_events": [{"title": "undated-event"}, {"date": "2025-01-12", "title": "e1"}],
        }
        out = truncate_state(state, "2025-01-14")
        assert [n["title"] for n in out["news_list"]] == ["a"]
        assert [e["title"] for e in out["key_events"]] == ["e1"]


class TestRealDataFormats:
    """真实 akshare 输出格式兼容：横线报告日 / 「日期」列名 / datetime 键。

    fixture 均按 src/finance_agent/data/akshare_client.py 实际产出构造。
    """

    def test_quarterly_income_dashed_report_date_truncated(self):
        # fetch_quarterly_income 报告日 "2024-09-30" 带横线，此前 int(period_end[4:6]) 得 0 → 崩
        qi = pd.DataFrame(
            {"报告日": ["2024-09-30", "2023-06-30"], "归母净利润(单季)": [100.0, 80.0]}
        )
        out = truncate_state({"quarterly_income": qi}, "2024-08-31")
        # 2024 Q3 披露截止 2024-10-31 > 决策日 → 剔除；2023 H1 截止 2023-08-31 ≤ 决策日 → 保留
        assert list(out["quarterly_income"]["报告日"]) == ["2023-06-30"]

    def test_reports_with_bad_date_rows_dropped_without_crash(self):
        # 单行日期非法（如 "N/A"/空串）→ 剔除该行继续，不让整表崩溃（宁缺勿前视）
        qi = pd.DataFrame(
            {"报告日": ["N/A", "2024-09-30", ""], "归母净利润(单季)": [1.0, 2.0, 3.0]}
        )
        out = truncate_state({"quarterly_income": qi}, "2025-03-01")
        assert list(out["quarterly_income"]["报告日"]) == ["2024-09-30"]

    def test_financial_indicators_date_column_truncated(self):
        # fetch_indicators 输出列名为「日期」（值 "2024-12-31" 年报期末），无「报告日」列
        fi = pd.DataFrame({"日期": ["2024-12-31", "2023-12-31"], "净资产收益率": [20.0, 18.0]})
        state = {"financial_indicators": fi}
        # 2024 年报披露截止 2025-04-30 > 决策日 2025-03-01 → 剔除，只剩 2023
        out = truncate_state(state, "2025-03-01")
        assert list(out["financial_indicators"]["日期"]) == ["2023-12-31"]
        out2 = truncate_state(state, "2025-05-01")
        assert list(out2["financial_indicators"]["日期"]) == ["2024-12-31", "2023-12-31"]

    def test_news_with_datetime_key_filtered_by_date(self):
        # fetch_news 输出日期键名为 datetime（col_map 发布时间→datetime）
        state = {
            "news_list": [
                {"title": "old", "datetime": "2025-01-10 09:30:00"},
                {"title": "future", "datetime": "2025-01-20 08:00:00"},
            ]
        }
        out = truncate_state(state, "2025-01-14")
        assert [n["title"] for n in out["news_list"]] == ["old"]


class TestBuildSnapshotMetadata:
    def test_metadata_contains_prompt_versions_and_model(self, monkeypatch):
        monkeypatch.setattr(
            "finance_agent.nodes.fetch.fetch_data",
            lambda base, client=None: {"kline": None},
        )
        monkeypatch.setenv("LLM_MODEL", "glm-test-4.7")
        result = build_snapshot("600519", "2025-01-14")
        assert result.metadata["model"] == "glm-test-4.7"
        assert isinstance(result.metadata["prompt_versions"], dict)
        assert len(result.metadata["prompt_versions"]) > 0

    def test_metadata_model_unspecified_without_env(self, monkeypatch):
        monkeypatch.setattr(
            "finance_agent.nodes.fetch.fetch_data",
            lambda base, client=None: {"kline": None},
        )
        monkeypatch.delenv("LLM_MODEL", raising=False)
        result = build_snapshot("600519", "2025-01-14")
        assert result.metadata["model"] == "unspecified"

    def test_metadata_excluded_fields_covers_point_in_time(self, monkeypatch):
        monkeypatch.setattr(
            "finance_agent.nodes.fetch.fetch_data",
            lambda base, client=None: {"kline": None},
        )
        result = build_snapshot("600519", "2025-01-14")
        assert set(result.metadata["excluded_fields"]) >= {
            "stock_quote",
            "industry_pe",
            "peer_financials",
        }
