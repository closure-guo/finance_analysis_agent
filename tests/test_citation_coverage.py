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


class TestV3CensusRules:
    """refine-citation-coverage-v3 D1：普查四规则（issue #106 人工终裁）。"""

    def test_rounding_tolerance_2pct(self):
        # 91.93 vs 91.18：0.8% 偏差，旧 0.5% 判黑，v3 2% 认领
        rep = compute_coverage("毛利率 91.93%", [91.18])
        assert rep.coverage == 1.0

    def test_direction_word_sign_insensitive(self):
        # 正文「下滑 10.05%」正数，claim -10.05，符号不敏感认领
        rep = compute_coverage("净利率下滑 10.05%", [-10.05])
        assert rep.coverage == 1.0

    def test_inequality_threshold_match(self):
        # 「ROE 超 30%」→ claim 32.53 满足 ≥30，认领
        rep = compute_coverage("ROE 超 30%", [32.53])
        assert rep.coverage == 1.0
        # 「ROE 超 30%」→ claim 20 不满足，不认领
        rep2 = compute_coverage("ROE 超 30%", [20.0])
        assert rep2.coverage == 0.0

    def test_scaffold_text_excluded_from_total(self):
        # 仓位档位说明的 10-20% 不计入普查总数
        md = "position_size 档位：light=试探性仓位（如总资金 10-20%）"
        nums = extract_census_numbers(md)
        assert all(n.kind != "percent" for n in nums) or not nums

    def test_value_mismatch_still_black(self):
        # 1400亿 vs 营收 1720.5亿：18% 偏差、非不等式/方向词 → 保持黑数字
        rep = compute_coverage("账上货币资金+拆出资金合计超过1400亿元", [172054200000.0])
        assert rep.unmatched == ["1400亿"]


class TestV3EventCovered:
    """refine-citation-coverage-v3 D5：事件数字豁免。"""

    def test_event_number_marked_event_covered_not_unmatched(self):
        from finance_agent.citation_coverage import compute_coverage

        md = "出厂价由 969 元上调至 1169 元"  # 无 claim 认领，但命中事件源
        rep = compute_coverage(md, [0.0], event_values=[969.0, 1169.0])
        assert rep.event_covered == ["969元", "1169元"]
        assert rep.unmatched == []

    def test_non_event_number_still_unmatched(self):
        from finance_agent.citation_coverage import compute_coverage

        md = "账上资金超过1400亿元"
        rep = compute_coverage(md, [172054200000.0], event_values=[969.0])
        assert rep.unmatched == ["1400亿"]
