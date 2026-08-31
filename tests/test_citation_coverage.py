"""TDD tests for citation_coverage.py — 正文数字普查（citation recall 近似）。

≥15 条例化 fixture 钉死归一化与豁免口径（design D1 口径风险对策）。
"""

from finance_agent.citation_coverage import compute_coverage, extract_census_numbers


def _values(text: str) -> list[float]:
    return [n.value for n in extract_census_numbers(text)]


class TestCensusExtraction:
    def test_percent(self):
        assert _values("毛利率 45.2%") == [45.2]

    def test_percent_fullwidth(self):
        assert _values("毛利率 45.2％") == [45.2]

    def test_hedged_percent(self):
        assert _values("毛利率约 45%") == [45.0]

    def test_percentage_point(self):
        assert _values("上升 2 个百分点") == [2.0]

    def test_amount_yi(self):
        assert _values("营收 10.39 亿") == [10.39e8]

    def test_amount_wan(self):
        assert _values("净利润 500 万") == [500e4]

    def test_amount_yuan(self):
        assert _values("股价 5.2 元") == [5.2]

    def test_multiple(self):
        assert _values("PE 2.5 倍") == [2.5]
        assert _values("PE 2.5x") == [2.5]

    def test_negative(self):
        assert _values("同比 -5.2%") == [-5.2]

    def test_year_exempt(self):
        assert _values("2024 年营收增长") == []

    def test_bare_number_exempt(self):
        assert _values("5 层架构与 3 大报表") == []

    def test_indicator_param_exempt(self):
        assert _values("MA5 与 RSI14 金叉") == []

    def test_stock_code_exempt(self):
        assert _values("贵州茅台 600519 上涨") == []

    def test_date_exempt(self):
        assert _values("截至 2026-08-28 收盘") == []

    def test_window_count_exempt(self):
        assert _values("近 60 期均线") == []

    def test_rating_exempt(self):
        assert _values("评级 AAA，得分 85 分") == []

    def test_dedup_same_value(self):
        nums = extract_census_numbers("毛利率 45.2%，净利率低于 45.2% 是常态")
        assert len(nums) == 1


class TestCoverage:
    def test_all_claimed(self):
        md = "毛利率 45.2%，营收 10.39 亿"
        rep = compute_coverage(md, [45.2, 1038756658.94])
        assert rep.coverage == 1.0
        assert rep.total == 2
        assert rep.matched == 2

    def test_dark_number_exposed(self):
        """spec 场景：正文「营收 10.39 亿」无任何 claim 认领 → 覆盖率下降。"""
        md = "毛利率 45.2%，营收 10.39 亿"
        rep = compute_coverage(md, [45.2])
        assert rep.coverage == 0.5
        assert rep.unmatched == ["10.39亿"]

    def test_empty_markdown_full_coverage(self):
        rep = compute_coverage("", [1.0])
        assert rep.total == 0
        assert rep.coverage == 1.0

    def test_stated_in_yi_matches_amount(self):
        """LLM 以「亿」为单位申报 stated（10.39），正文 10.39 亿 → 缩放匹配。"""
        rep = compute_coverage("营收 10.39 亿", [10.39])
        assert rep.coverage == 1.0

    def test_fraction_claim_matches_percent(self):
        """claim stated 为小数形态（0.452），正文 45.2% → 缩放匹配。"""
        rep = compute_coverage("毛利率 45.2%", [0.452])
        assert rep.coverage == 1.0
