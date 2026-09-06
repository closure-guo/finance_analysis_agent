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
        # v1.1：pct 限定涨跌语境——只有「涨 5%」命中（contradicted vs 1.0）；
        # ROE 12% 不再被当日涨跌幅误校验（财务比率归 roe 维度，此处 supported）
        assert result.contradicted == 1
        assert result.countable == 3
        assert result.unverifiable == 1
        assert result.rate == round(1 / 3, 4)

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


class TestGate:
    """3.2 门禁：幻觉率上限阈值（宽松初值 10%，env 可配）。"""

    def test_gate_pass_under_threshold(self):
        from evals.hallucination.measure import gate

        text = "股价 100 元，涨 5%，PE 15，PB 2，市值 800 亿，ROE 12%"
        data = {
            "price": 100.0,
            "pct": 5.0,
            "pe": 15.0,
            "pb": 2.0,
            "cap_billion": 800.0,
            "roe": 12.0,
        }
        result = hallucination_rate(verify_claims(extract_claims(text), data))
        g = gate(result)
        assert g["verdict"] == "pass"
        assert g["threshold"] == 0.10

    def test_gate_fail_over_threshold(self):
        from evals.hallucination.measure import gate

        text = "股价 100 元，涨 5%，PE 15，PB 2，市值 800 亿，ROE 12%"
        data = {
            "price": 200.0,
            "pct": 5.0,
            "pe": 15.0,
            "pb": 2.0,
            "cap_billion": 800.0,
            "roe": 12.0,
        }
        result = hallucination_rate(
            verify_claims(extract_claims(text), data)
        )  # 价格证伪 → 1/6 > 10%
        g = gate(result)
        assert g["verdict"] == "fail"

    def test_gate_insufficient_sample_below_min_n(self):
        """样本 < 最小可验证数（默认 5）时不判定，避免小样本单点证伪误报。"""
        from evals.hallucination.measure import gate

        verdicts = verify_claims(extract_claims("股价 100 元"), {"price": 200.0})
        result = hallucination_rate(verdicts)  # countable=1
        g = gate(result)
        assert g["verdict"] == "insufficient_sample"

    def test_gate_threshold_from_env(self, monkeypatch):
        import importlib

        import evals.hallucination.measure as m

        monkeypatch.setenv("HALLUCINATION_MAX_RATE", "0.05")
        importlib.reload(m)
        text = "股价 100 元，涨 5%，PE 15，PB 2，市值 800 亿，ROE 12%"
        data = {
            "price": 100.0,
            "pct": 5.0,
            "pe": 15.0,
            "pb": 2.0,
            "cap_billion": 800.0,
            "roe": 12.0,
        }
        result = m.hallucination_rate(m.verify_claims(m.extract_claims(text), data))
        g = m.gate(result)
        assert g["verdict"] == "pass"
        assert g["threshold"] == 0.05
        monkeypatch.delenv("HALLUCINATION_MAX_RATE")
        importlib.reload(m)

    def test_render_report_contains_gate_section(self):
        from evals.hallucination.measure import render_report

        text = "股价 100 元，涨 5%，PE 15，PB 2，市值 800 亿，ROE 12%"
        data = {
            "price": 100.0,
            "pct": 5.0,
            "pe": 15.0,
            "pb": 2.0,
            "cap_billion": 800.0,
            "roe": 12.0,
        }
        result = run_offline(text, data)
        report = render_report(result)
        assert "门禁判定" in report and "10.0%" in report and "pass" in report


class TestFactualExtraction:
    """4.2 事实型 claim LLM 抽取：无 LLM 时优雅回退为空，有 LLM 时并入结果。"""

    def test_extract_factual_claims_no_llm_graceful(self):
        from evals.hallucination.measure import extract_factual_claims

        claims = extract_factual_claims("公司在合肥新建产能。", llm=None)
        assert claims == []

    def test_extract_factual_claims_with_llm(self):
        from evals.hallucination.measure import extract_factual_claims

        class _FakeLLM:
            def invoke(self, prompt: str) -> str:
                return '[{"raw": "公司在合肥新建产能", "type": "factual"}]'

        claims = extract_factual_claims("公司在合肥新建产能。", llm=_FakeLLM())
        assert len(claims) == 1
        assert claims[0].type == "factual"
        assert "合肥" in claims[0].raw

    def test_extract_factual_claims_bad_json_graceful(self):
        from evals.hallucination.measure import extract_factual_claims

        class _BadLLM:
            def invoke(self, prompt: str) -> str:
                return "不是 JSON"

        assert extract_factual_claims("文本", llm=_BadLLM()) == []

    def test_factual_verdict_unverifiable_without_evidence(self):
        """事实型 claim 无证据源时如实标注 unverifiable（不进分子）。"""
        from evals.hallucination.measure import run_offline

        class _FakeLLM:
            def invoke(self, prompt: str) -> str:
                return '[{"raw": "公司在合肥新建产能", "type": "factual"}]'

        result = run_offline("股价 100 元。公司在合肥新建产能。", {"price": 100.0}, llm=_FakeLLM())
        factual = [v for v in result.verdicts if v.claim.type == "factual"]
        assert len(factual) == 1
        assert factual[0].status == "unverifiable"
