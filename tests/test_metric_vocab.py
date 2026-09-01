"""TDD tests for metric_vocab.py — 指标词表与期次/数值归一化。"""

from finance_agent.metric_vocab import (
    canonical_metric,
    field_ref_metric_segments,
    field_ref_period_segment,
    normalize_period,
    period_matches,
)


class TestCanonicalMetric:
    def test_chinese_canonical_passthrough(self):
        assert canonical_metric("毛利率") == "毛利率"

    def test_english_alias_maps_to_chinese(self):
        assert canonical_metric("gross_margin") == "毛利率"
        assert canonical_metric("净利率") == "净利率"
        assert canonical_metric("net margin") == "净利率"

    def test_roe_aliases(self):
        assert canonical_metric("净资产收益率") == "ROE"
        assert canonical_metric("roe") == "ROE"

    def test_technical_aliases(self):
        assert canonical_metric("MA5") == "MA"
        assert canonical_metric("布林带") == "BOLL"
        assert canonical_metric("相对强弱指数") == "RSI"

    def test_macro_aliases(self):
        assert canonical_metric("CPI") == "cpi"
        assert canonical_metric("贷款市场报价利率") == "lpr"

    def test_unknown_returns_none(self):
        assert canonical_metric("不存在的指标") is None
        assert canonical_metric(None) is None
        assert canonical_metric("") is None


class TestFieldRefSegments:
    def test_metric_dict_ref(self):
        assert field_ref_metric_segments("profitability_metrics.毛利率.2024") == ["毛利率"]

    def test_technical_ref_drops_index_and_param(self):
        assert field_ref_metric_segments("technical_indicators.MA.5.-1") == ["MA"]
        assert field_ref_metric_segments("technical_indicators.MACD.DIF.-1") == ["MACD", "DIF"]

    def test_macro_ref(self):
        assert field_ref_metric_segments("macro_indicators.cpi.0.全国-同比增长") == [
            "cpi",
            "全国-同比增长",
        ]

    def test_statement_ref_drops_date_rowkey(self):
        assert field_ref_metric_segments("income_statement.20251231.营业总收入") == ["营业总收入"]

    def test_period_segment_detection(self):
        assert field_ref_period_segment("profitability_metrics.毛利率.2024") == "2024"
        assert field_ref_period_segment("income_statement.20251231.营业总收入") == "20251231"
        assert field_ref_period_segment("technical_indicators.MA.5.-1") is None
        assert field_ref_period_segment("risk_metrics.max_drawdown") is None


class TestNormalizePeriod:
    def test_year_forms(self):
        assert normalize_period("2024") == "2024"
        assert normalize_period("2024年") == "2024"
        assert normalize_period("2024年报") == "2024"

    def test_quarter_forms(self):
        assert normalize_period("2025Q2") == "2025Q2"
        assert normalize_period("2025年二季度") == "2025Q2"
        assert normalize_period("2025q3") == "2025Q3"

    def test_date_forms(self):
        assert normalize_period("2026-08-28") == "2026-08-28"
        assert normalize_period("2026/8/5") == "2026-08-05"
        assert normalize_period("20260828") == "2026-08-28"

    def test_month_forms(self):
        assert normalize_period("2026年07月份") == "2026-07"
        assert normalize_period("2026-07") == "2026-07"

    def test_garbage_returns_none(self):
        assert normalize_period("最近") is None
        assert normalize_period("") is None


class TestPeriodMatches:
    def test_exact(self):
        assert period_matches("2024", "2024")

    def test_year_prefix_of_date(self):
        assert period_matches("2025", "20251231")
        assert period_matches("2025", "2025-12-31")
        assert period_matches("2026-08", "2026-08-28")

    def test_mismatch(self):
        assert not period_matches("2023", "2024")
        assert not period_matches("2025Q1", "2025Q2")
        assert not period_matches("2026-07", "2026-08-01")
