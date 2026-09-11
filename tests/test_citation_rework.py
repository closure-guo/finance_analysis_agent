"""rework-citation-gate-attribution 阶段 1–3：校验器归一、派生字段注册、文本 claim 分型。

fixture 依据 r2 真实失败样本（tests/data/citation_r2_claims.json，incident 026）：
39 个 FAIL 抽样无一为数字写错——日期显示格式、季度标签、单位量级、真实列名、
恒正水平量的符号校验；98 个 UNVERIFIABLE 中 75 条舆情文本 claim、23 条未注册派生字段。
"""

from __future__ import annotations

import pandas as pd
import pytest

from finance_agent.citation import Claim, _resolve_field_ref, verify_claims


def _income_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "报告日": "20251231",
                "营业总收入": 5.8394610072e10,
                "归属于母公司的净利润": 5.040734e9,
            },
            {"报告日": "20241231", "营业总收入": 5.779557e10, "归属于母公司的净利润": 4.5e9},
        ]
    )


def _one(claim: Claim, state: dict):
    return verify_claims([claim], state)[0]


class TestPathNormalization:
    def test_display_date_row_key_resolves(self):
        """r2 24 条 path_unresolvable 之一：context 经 render_date 显示 2025-12-31，行键存 20251231。"""
        state = {"income_statement": _income_df()}
        assert (
            _resolve_field_ref("income_statement.2025-12-31.营业总收入", state) == 5.8394610072e10
        )
        assert _resolve_field_ref("income_statement.20251231.营业总收入", state) == 5.8394610072e10

    def test_quarter_label_maps_to_position(self):
        """quarterly_trend 22/31 失败：LLM 照抄标签 2026Q2，校验器要位置索引。"""
        state = {
            "quarterly_trend": {
                "quarters": ["2025Q4", "2026Q1", "2026Q2"],
                "yoy": [19.0, 241.0, 29.664],
            }
        }
        assert _resolve_field_ref("quarterly_trend.yoy.2026Q2", state) == 29.664
        assert _resolve_field_ref("quarterly_trend.yoy.2", state) == 29.664
        assert _resolve_field_ref("quarterly_trend.yoy.2027Q1", state) is None


class TestMagnitudeUnitNormalization:
    def _claim(self, stated: float, interp: str) -> Claim:
        return Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="income_statement.20251231.营业总收入",
            stated_value=stated,
            interpretation=interp,
            metric_name="营业总收入",
            period="20251231",
            direction="flat",
        )

    def test_yi_unit_scaled_before_tolerance(self):
        r = _one(
            self._claim(583.95, "2025年营业总收入583.95亿元"), {"income_statement": _income_df()}
        )
        assert r.status == "PASS"
        assert r.unit_normalized == "亿"

    def test_wan_unit_scaled(self):
        df = pd.DataFrame([{"报告日": "20251231", "应收账款": 2609048.49}])
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="balance_sheet.20251231.应收账款",
            stated_value=260.9,
            interpretation="2025年末应收账款约260.90万元",
            direction="flat",
        )
        r = _one(c, {"balance_sheet": df})
        assert r.status == "PASS" and r.unit_normalized == "万"

    def test_no_unit_word_ratio_fallback_marked_inferred(self):
        r = _one(self._claim(583.95, "2025年营业总收入583.95"), {"income_statement": _income_df()})
        assert r.status == "PASS"
        assert r.unit_normalized == "inferred"

    def test_wrong_value_after_scaling_stays_fail(self):
        r = _one(
            self._claim(400.0, "2025年营业总收入400.00亿元"), {"income_statement": _income_df()}
        )
        assert r.status == "FAIL" and r.bucket == "value_mismatch"

    def test_raw_match_needs_no_normalization(self):
        r = _one(
            self._claim(5.8394610072e10, "营业总收入 58394610072 元"),
            {"income_statement": _income_df()},
        )
        assert r.status == "PASS" and r.unit_normalized is None


class TestTermRealColumnName:
    def test_real_column_name_is_consistent(self):
        """r2 5 条 semantic_term_mismatch：照抄真实列名「归属于母公司的净利润」被词表拒绝。"""
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="income_statement.20251231.归属于母公司的净利润",
            stated_value=50.40734,
            interpretation="2025年归母净利润50.41亿元",
            metric_name="归属于母公司的净利润",
            period="20251231",
            direction="flat",
        )
        r = _one(c, {"income_statement": _income_df()})
        assert r.status == "PASS", r

    def test_canonical_alias_to_real_column(self):
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="income_statement.20251231.归属于母公司的净利润",
            stated_value=50.40734,
            interpretation="2025年归母净利润50.41亿元",
            metric_name="归母净利润",
            period="20251231",
            direction="flat",
        )
        assert _one(c, {"income_statement": _income_df()}).status == "PASS"


class TestSignedGating:
    def test_level_metric_negative_declaration_not_fail(self):
        """r2 5 条 direction_mismatch：LLM 把「PMI 49.8 低于荣枯线」填 negative，恒正水平量比符号无意义。"""
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.pmi.1.制造业-指数",
            stated_value=49.8,
            interpretation="8月制造业PMI为49.8，低于荣枯线50",
            metric_name="PMI",
            period="2026-08",
            direction="negative",
        )
        state = {"macro_indicators": {"pmi": [{"制造业-指数": 49.2}, {"制造业-指数": 49.8}]}}
        r = _one(c, state)
        assert r.status == "PASS" and r.bucket is None
        assert r.coverage_gap is True  # 申报错位记缺口提示，不判 FAIL

    def test_growth_metric_sign_still_checked(self):
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.归母净利润.2025",
            stated_value=10.05,
            interpretation="归母净利润下滑10.05%",
            metric_name="归母净利润",
            period="2025",
            direction="positive",
        )
        r = _one(c, {"growth_rates": {"归母净利润": {"2025": -10.05}}})
        assert r.status == "FAIL" and r.bucket == "direction_mismatch"


class TestTextualClaims:
    def test_news_title_echo_hit_passes(self):
        """75 条舆情 claim：标题子串命中即 PASS(echo)。"""
        c = Claim(
            claim_type="entity",
            source_type="data",
            field_ref="news_list.0.title",
            stated_value="比亚迪2026年中报净利润123.25亿元、同比下降20.54%",
            interpretation="核心业绩利空，为舆情面最主要的负面因素",
        )
        state = {"news_list": [{"title": "比亚迪2026年中报净利润123.25亿元、同比下降20.54%"}]}
        r = _one(c, state)
        assert r.status == "PASS"
        assert r.ground_truth == "比亚迪2026年中报净利润123.25亿元、同比下降20.54%"

    def test_echo_miss_is_unverifiable_without_gap(self):
        c = Claim(
            claim_type="entity",
            source_type="data",
            field_ref="news_list.3.title",
            stated_value="完全不存在的新闻",
            interpretation="x",
        )
        r = _one(c, {"news_list": [{"title": "别的"}]})
        assert r.status == "UNVERIFIABLE" and r.coverage_gap is False and r.bucket is None

    def test_event_claim_echo_against_key_events(self):
        c = Claim(
            claim_type="temporal",
            source_type="event",
            field_ref="key_events.1",
            stated_value="泰国工厂投产、年产能约15万辆，全球化进入本地化生产阶段",
            interpretation="L2级持续利好事件",
        )
        state = {
            "key_events": [
                {"title": "荣耀版"},
                {"title": "泰国工厂投产、年产能约15万辆，全球化进入本地化生产阶段"},
            ]
        }
        assert _one(c, state).status == "PASS"


class TestSnapshotDerivedRegistry:
    def _state(self) -> dict:
        from finance_agent.nodes.compute import compute_metrics

        bs = pd.DataFrame(
            [{"报告日": "20251231", "资产总计": 1.0e11, "负债合计": 3.3e10, "货币资金": 4.36e10}]
        )
        inc = pd.DataFrame(
            [
                {
                    "报告日": "20251231",
                    "营业总收入": 6.73e10,
                    "归属于母公司的净利润": 5.04e9,
                    "净利润": 5.04e9,
                }
            ]
        )
        cf = pd.DataFrame([{"报告日": "20251231", "经营活动产生的现金流量净额": 2.0e10}])
        base = {"balance_sheet": bs, "income_statement": inc, "cash_flow_statement": cf}
        computed = compute_metrics(base)
        return {**base, **computed}

    def test_garp_flag_recomputed(self):
        state = self._state()
        garp = state.get("garp_result") or {}
        c = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="garp_result.pass",
            stated_value=1 if garp.get("pass") else 0,
            interpretation="GARP估值结论",
            direction="flat",
        )
        r = _one(c, state)
        assert r.status in ("PASS", "UNVERIFIABLE")
        assert r.status != "FAIL"
        if garp:
            assert r.status == "PASS"

    def test_anomalies_echo(self):
        state = self._state()
        anomalies = state.get("anomalies") or ["盈利能力.ROE: 红灯"]
        state["anomalies"] = anomalies
        c = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="anomalies",
            stated_value="",
            interpretation=f"异常检测提示：{anomalies[0]}",
            direction="flat",
        )
        assert _one(c, state).status == "PASS"


class TestInjectionDrill:
    """归一上线后门禁仍会开火：故意改错一个数字（非单位/非格式）必须 FAIL。"""

    @pytest.mark.parametrize("factor", [0.9, 1.1])
    def test_perturbed_value_fails(self, factor):
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="income_statement.2025-12-31.营业总收入",
            stated_value=round(583.95 * factor, 2),
            interpretation=f"2025年营业总收入{round(583.95 * factor, 2)}亿元",
            metric_name="营业总收入",
            period="20251231",
            direction="flat",
        )
        r = _one(c, {"income_statement": _income_df()})
        assert r.status == "FAIL" and r.bucket == "value_mismatch"


class TestR4ResidualTolerances:
    """r4 残余 FAIL 归因（tests/data/citation_r4_claims.json）：5 条 direction_mismatch 全为
    「stated 已带负号 + direction=negative」的双重否定；8 条 path_unresolvable 中
    quarterly_trend 序列缺季度段但 claim.period 携带季度标签。两者事实无歧义，校验器容忍。"""

    def test_double_negative_declaration_is_sign_consistent(self):
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.营业收入",
            stated_value=-10.397764,
            interpretation="2025年营收同比下降10.40%",
            metric_name="营业收入",
            period="2025",
            direction="negative",
        )
        r = _one(c, {"growth_rates": {"profitability": {"营业收入": -0.10397764}}})
        assert r.status == "PASS", r
        assert r.bucket is None

    def test_quarter_series_without_segment_uses_claim_period(self):
        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="quarterly_trend.yoy",
            stated_value=6.9,
            interpretation="2026Q2归母净利润同比下降6.9%",
            metric_name="同比",
            period="2026Q2",
            direction="negative",
        )
        state = {"quarterly_trend": {"quarters": ["2026Q1", "2026Q2"], "yoy": [-55.38, -6.9]}}
        r = _one(c, state)
        assert r.status == "PASS", r
