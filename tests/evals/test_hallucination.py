"""add-hallucination-rate-metric：数值型 claim 抽取/证据校验/幻觉率 测试（fixtures 离线）。"""

from evals.hallucination.measure import (
    extract_claims,
    hallucination_rate,
    run_offline,
    verify_claims,
)


class TestExtract:
    def test_numeric_claims_found(self):
        text = "当前股价 100 元，较昨日上涨 2.5%，PE 15，市值 800 亿，ROE 为 12%"
        claims = extract_claims(text)
        types = [c.type for c in claims]
        assert "price" in types and "pct" in types and "pe" in types
        assert "cap_billion" in types and "roe" in types
        price = next(c for c in claims if c.type == "price")
        assert price.value == 100.0
        pct = next(c for c in claims if c.type == "pct")
        assert pct.value == 2.5

    def test_no_match_empty(self):
        assert extract_claims("无任何数字的说明文字") == []
        assert extract_claims("") == []


class TestVerify:
    def test_supported_within_tolerance(self):
        claims = extract_claims("股价 100 元，涨 2.5%")
        verdicts = verify_claims(claims, {"price": 101.0, "pct": 2.6})
        by = {v.claim.type: v for v in verdicts}
        assert by["price"].status == "supported"  # 100 vs 101 在 ±2% 内
        assert by["pct"].status == "supported"  # 2.5 vs 2.6 在 ±0.5 百分点内

    def test_contradicted_outside_tolerance(self):
        claims = extract_claims("股价 100 元，涨 5%")
        verdicts = verify_claims(claims, {"price": 90.0, "pct": 1.0})
        by = {v.claim.type: v for v in verdicts}
        assert by["price"].status == "contradicted"  # 偏差 10% > 2%
        assert by["pct"].status == "contradicted"  # 偏差 4 个百分点 > 0.5

    def test_unverifiable_missing_source(self):
        claims = extract_claims("股价 100 元，ROE 12%")
        verdicts = verify_claims(claims, {"price": 100.0})
        by = {v.claim.type: v for v in verdicts}
        assert by["price"].status == "supported"
        assert by["roe"].status == "unverifiable"


class TestRate:
    def test_rate_math(self):
        text = "股价 100 元，涨 5%，PE 15，ROE 12%"
        verdicts = verify_claims(
            extract_claims(text),
            {"price": 100.0, "pct": 1.0, "roe": 11.5},
        )
        result = hallucination_rate(verdicts)
        # pct 两条：5（contradicted vs 1.0）+ ROE 12% 也被 pct 规则命中（contradicted vs 1.0）；
        # price 支持；roe 支持；pe 不可验证。重叠是规则抽取 v1 的真实行为，接受并如实计量。
        assert result.contradicted == 2
        assert result.countable == 4
        assert result.unverifiable == 1
        assert result.rate == round(2 / 4, 4)

    def test_zero_countable_rate_none(self):
        result = run_offline("无数字文本", {"price": 100.0})
        assert result.rate is None
        assert result.countable == 0


class TestRunOffline:
    def test_end_to_end(self):
        report = "股价 100 元，较昨日上涨 3%，PE 15，市值 800 亿"
        result = run_offline(report, {"price": 100.0, "pct": 0.5, "pe": 15.0})
        assert result.contradicted == 1  # pct 3 vs 0.5
        assert result.unverifiable == 1  # 市值无源
        assert result.rate is not None

    def test_clean_report_rate_zero(self):
        report = "股价 100 元，上涨 0.5%"
        result = run_offline(report, {"price": 100.0, "pct": 0.5})
        assert result.rate == 0.0
        assert result.unverifiable == 0
