"""离线复判模块测试：与 citation.py 当前裁决语义钉死 + 疾病标记。

防漂移：复判公式必须与 citation.py 裁决函数逐条对齐——对每条裁决规则，
构造可解析的合成 state（resolve 到已知 gt），用 verify_claims 的真实裁决
与 rejudge_claim(claim, gt, delta) 的复判做对照，任一语义漂移即红。
"""

from evals.claim_benchmark.rejudge import contract_disease, is_hedged, rejudge_claim

from finance_agent.citation import Claim, verify_claims


def _verify(claim: dict, state: dict) -> str:
    return verify_claims([Claim.model_validate(claim)], state)[0].status


class TestNumericalPin:
    STATE = {"x": 100.0}

    def _claim(self, stated):
        return {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "x",
            "stated_value": stated,
            "interpretation": "",
        }

    def test_exact_match_pass(self):
        c = self._claim(100.0)
        assert _verify(c, self.STATE) == "PASS"
        assert rejudge_claim(c, 100.0, 0.0) == "PASS"

    def test_relative_tolerance_pass(self):
        """100.49（delta 0.49 < 0.5%×100=0.5）：绝对 0.01 不够，相对 0.5% 够。"""
        c = self._claim(100.49)
        assert _verify(c, self.STATE) == "PASS"
        assert rejudge_claim(c, 100.0, 0.49) == "PASS"

    def test_beyond_relative_tolerance_fail(self):
        c = self._claim(101.0)
        assert _verify(c, self.STATE) == "FAIL"
        assert rejudge_claim(c, 100.0, 1.0) == "FAIL"

    def test_small_scale_absolute_tolerance(self):
        """1.005：gt 小量级下绝对容忍 0.01 生效（相对 0.5% 更严）。"""
        state = {"x": 1.0}
        c = self._claim(1.005)
        assert _verify(c, state) == "PASS"  # delta 0.005 < 0.01
        assert rejudge_claim(c, 1.0, 0.005) == "PASS"

    def test_resolve_failed_unverifiable_offline(self):
        """gt=None（词表/索引疾病样本）→ 离线不可复判 UNVERIFIABLE，而非 FAIL。"""
        c = self._claim(100.0)
        assert rejudge_claim(c, None, None) == "UNVERIFIABLE"


class TestComputationalPin:
    """计算型：用注册根键 technical_indicators + 合成 kline，verify_claims 真实重算
    与 rejudge_claim(claim, gt, delta) 对照（钉死相对容差公式）。"""

    @staticmethod
    def _state() -> dict:
        import pandas as pd

        kline = pd.DataFrame(
            {
                "日期": [f"2026{i:02d}01" for i in range(1, 11)],
                "收盘": [10.0 + i for i in range(10)],
                "最高": [10.5 + i for i in range(10)],
                "最低": [9.5 + i for i in range(10)],
            }
        )
        return {"kline": kline}

    def _claim(self, stated):
        return {
            "claim_type": "computational",
            "source_type": "data",
            "field_ref": "technical_indicators.MA.5.-1",
            "stated_value": stated,
            "interpretation": "",
        }

    def test_matches_citation_on_state(self):
        state = self._state()
        # 合成 kline 收盘 10..19，真实最新 MA5 = (15+16+17+18+19)/5 = 17.0
        gt = 17.0
        c_pass = self._claim(17.0)
        assert _verify(c_pass, state) == "PASS"
        assert rejudge_claim(c_pass, gt, 0.0) == "PASS"
        c_fail = self._claim(17.2)  # 相对 1.18% > 0.5% → FAIL
        assert _verify(c_fail, state) == "FAIL"
        assert rejudge_claim(c_fail, gt, 0.2) == "FAIL"


class TestComparative:
    def test_equal_to_delta_reconstructible(self):
        c = {
            "claim_type": "comparative",
            "source_type": "data",
            "field_ref": "a",
            "field_ref_b": "b",
            "stated_value": "equal_to",
            "interpretation": "",
        }
        assert rejudge_claim(c, 10.0, 0.005) == "PASS"
        assert rejudge_claim(c, 10.0, 0.5) == "FAIL"

    def test_greater_less_needs_sign(self):
        c = {
            "claim_type": "comparative",
            "source_type": "data",
            "field_ref": "a",
            "field_ref_b": "b",
            "stated_value": "greater_than",
            "interpretation": "",
        }
        # delta 无符号 → 离线不可判，返回 UNVERIFIABLE（诚实披露而非乱判）
        assert rejudge_claim(c, 10.0, 5.0) == "UNVERIFIABLE"


class TestEvent:
    def test_date_match(self):
        c = {
            "claim_type": "event",
            "source_type": "event",
            "field_ref": "某事件",
            "stated_value": "2026-08-01",
            "interpretation": "",
        }
        assert rejudge_claim(c, "2026-08-01", None) == "PASS"
        assert rejudge_claim(c, "2026-08-02", None) == "FAIL"

    def test_gt_missing_unverifiable(self):
        c = {
            "claim_type": "event",
            "source_type": "event",
            "field_ref": "某事件",
            "stated_value": "2026-08-01",
            "interpretation": "",
        }
        assert rejudge_claim(c, None, None) == "UNVERIFIABLE"


class TestThreeStateContract:
    def test_llm_inference_skipped(self):
        c = {
            "claim_type": "numerical",
            "source_type": "llm_inference",
            "field_ref": "x",
            "stated_value": 5.0,
            "interpretation": "",
        }
        assert rejudge_claim(c, 5.0, 0.0) == "UNVERIFIABLE"

    def test_entity_else_branch(self):
        c = {
            "claim_type": "entity",
            "source_type": "data",
            "field_ref": "company.name",
            "stated_value": "某公司",
            "interpretation": "",
        }
        assert rejudge_claim(c, "某公司", None) == "UNVERIFIABLE"


class TestDiseaseMarking:
    def _claim(self, field_ref: str) -> dict:
        return {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": field_ref,
            "stated_value": 1.0,
            "interpretation": "",
        }

    def test_index_disease_pre_fix(self):
        assert (
            contract_disease(self._claim("technical_indicators.MA.5.59"), pre_fix=True) == "index"
        )

    def test_index_disease_ignored_post_fix(self):
        assert contract_disease(self._claim("technical_indicators.MA.5.59"), pre_fix=False) is None

    def test_negative_index_no_disease(self):
        assert contract_disease(self._claim("technical_indicators.MA.5.-1"), pre_fix=True) is None

    def test_wordlist_disease(self):
        assert contract_disease(self._claim("盈利能力.毛利率.2025"), pre_fix=True) == "wordlist"
        assert contract_disease(self._claim("events[0].title"), pre_fix=True) == "wordlist"

    def test_english_root_clean(self):
        assert (
            contract_disease(self._claim("profitability_metrics.毛利率.2025"), pre_fix=True) is None
        )


class TestHedged:
    def test_hedge_words(self):
        for interp in ("约为 12", "接近 10", "大约 8", "MA20 左右"):
            assert is_hedged({"stated_value": "", "interpretation": interp})
        assert not is_hedged({"stated_value": "12.5", "interpretation": "精确值"})


class TestRejudgeSemantic:
    def test_term_mismatch_rejudged_fail(self):
        """metric_name 与 field_ref 指标段不一致 → 离线复判 FAIL（数值正确也拦）。"""
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "profitability_metrics.毛利率.2024",
            "stated_value": 45.2,
            "interpretation": "净利率 45.2%",
            "metric_name": "净利率",
            "period": None,
        }
        assert rejudge_claim(claim, 45.2, 0.0) == "FAIL"

    def test_period_mismatch_rejudged_fail(self):
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "profitability_metrics.毛利率.2024",
            "stated_value": 45.2,
            "interpretation": "2023 年毛利率 45.2%",
            "metric_name": "毛利率",
            "period": "2023",
        }
        assert rejudge_claim(claim, 45.2, 0.0) == "FAIL"

    def test_semantic_control_rejudged_pass(self):
        """正确申报的 term/period → 语义检查通过，回落到容差复判 PASS。"""
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "profitability_metrics.毛利率.2024",
            "stated_value": 45.2,
            "interpretation": "2024 年毛利率 45.2%",
            "metric_name": "毛利率",
            "period": "2024",
        }
        assert rejudge_claim(claim, 45.2, 0.0) == "PASS"

    def test_legacy_claim_without_semantic_fields_unchanged(self):
        """v1 旧行（无新字段）复判行为不回归。"""
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": 40.0,
            "interpretation": "资产负债率 40%",
        }
        assert rejudge_claim(claim, 40.0, 0.0) == "PASS"


class TestRejudgeSemanticOutOfVocab:
    """镜像同步：词表外 metric_name 离线复判同样不判 FAIL（与管线 D5 扩展口径一致）。"""

    def test_out_of_vocab_term_not_failed_offline(self):
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "health_score.total",
            "stated_value": 78.1,
            "interpretation": "综合健康度评分78.1分",
            "metric_name": "健康度评分",
            "period": "2025",
        }
        assert rejudge_claim(claim, 78.1, 0.0) == "PASS"


class TestRejudgeComparativeBase:
    """refine v1.2：rejudge 镜像 D3 comparative 双端（基期值申报与校验）。"""

    def _comp(self, **kw):
        c = {
            "claim_type": "comparative",
            "source_type": "data",
            "field_ref": "profitability_metrics.净利率.2025",
            "stated_value": "less_than",
            "interpretation": "2025 净利率较 2024 下滑",
            "field_ref_b": "profitability_metrics.净利率.2024",
        }
        c.update(kw)
        return c

    def test_base_correct_passes(self):
        # stated_value_b=21.93, gt_b=21.93 → 方向 equal_to 可判，PASS
        c = self._comp(stated_value="equal_to", stated_value_b=21.93)
        assert rejudge_claim(c, 19.07, 2.86, ground_truth_b=21.93) == "PASS"

    def test_base_missing_fails(self):
        # field_ref_b is set but stated_value_b is missing → FAIL (base period running loose)
        c = self._comp(stated_value="equal_to")
        assert rejudge_claim(c, 19.07, 2.86, ground_truth_b=21.93) == "FAIL"

    def test_base_wrong_value_fails(self):
        c = self._comp(stated_value="equal_to", stated_value_b=28.0)
        assert rejudge_claim(c, 19.07, 2.86, ground_truth_b=21.93) == "FAIL"

    def test_growth_rounding_passes(self):
        # D2/D4 rounding-aware tolerance: stated=0.50 vs truth=0.504 (0.5pp) → PASS
        c = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "growth_rates.cashflow.FCF",
            "stated_value": 0.50,
            "interpretation": "FCF grew 50% YoY",
        }
        assert rejudge_claim(c, 0.504, 0.004) == "PASS"
