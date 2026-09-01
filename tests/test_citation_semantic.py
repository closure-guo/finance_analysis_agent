"""TDD tests for citation.py — 术语/期次一致性校验（语义层张冠李戴拦截）。"""

import pandas as pd

from finance_agent.citation import Claim, verify_claims


def _state() -> dict:
    return {
        "profitability_metrics": {"毛利率": {"2024": 45.2}, "净利率": {"2024": 18.0}},
        "technical_indicators": {"MA": {"5": [100.0, 101.0, 102.0]}},
        "kline": pd.DataFrame({"日期": ["2026-08-26", "2026-08-27", "2026-08-28"]}),
        "macro_indicators": {
            "cpi": {
                "records": [{"月份": "2026年07月份", "全国-同比增长": 0.4}],
                "as_of_date": "2026-07-01",
                "freshness": "fresh",
            }
        },
    }


class TestSemanticTermCheck:
    def test_term_mismatch_fails_even_when_value_correct(self):
        """spec 场景：field_ref 指向毛利率，metric_name 写净利率 → FAIL。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="净利率",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_term_mismatch"

    def test_term_match_passes(self):
        # 全申报（metric_name + period 均与 field_ref 一致）→ 无覆盖缺口的 PASS 钉。
        # （brief 原稿未申报 period 却断言 coverage_gap is False，与 D5「任一字段
        # 缺失即计缺口」及 openspec spec 冲突；补全 period 申报以保持原测试意图。）
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="毛利率",
            period="2024",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is False

    def test_term_alias_match_passes(self):
        """metric_name 用英文别名，canonical 化后与中文指标段一致 → 过。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="gross_margin",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_unknown_term_fails(self):
        """词表外术语 = 契约违规 → FAIL（不静默放行）。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="神秘指标",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_term_mismatch"

    def test_missing_metric_name_skips_and_counts_gap(self):
        """D5：缺省 → 跳过检查 + 覆盖缺口，不静默 PASS 语义（值级检查照常）。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is True


class TestSemanticPeriodCheck:
    def test_period_mismatch_fails(self):
        """年报值说成其他年份 → FAIL semantic_period_mismatch。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="2023 年毛利率为 45.2%",
            metric_name="毛利率",
            period="2023",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_period_mismatch"

    def test_period_match_passes(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="2024 年毛利率为 45.2%",
            metric_name="毛利率",
            period="2024年",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_technical_index_period_resolved_from_kline(self):
        """索引锚定（-1）→ 从 kline 解析实际交易日比对期次。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.-1",
            stated_value=102.0,
            interpretation="2026-08-28 MA5 为 102.0",
            metric_name="MA",
            period="2026-08-28",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_technical_index_period_mismatch_fails(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.-1",
            stated_value=102.0,
            interpretation="2026-08-01 MA5 为 102.0",
            metric_name="MA",
            period="2026-08-01",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_period_mismatch"

    def test_macro_index_period_resolved_from_records(self):
        """macro 4 段式（索引在 parts[2]）→ 从 records[idx]["月份"] 解析期次比对。

        coverage_gap is False 钉住「解析真正发生」：解析不出会走缺口路径，
        只断言 PASS 时该用例会空转（T3 修复前即如此）。
        """
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.cpi.0.全国-同比增长",
            stated_value=0.4,
            interpretation="2026 年 7 月 CPI 同比 0.4%",
            metric_name="CPI",
            period="2026-07",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is False

    def test_macro_index_period_bracket_form_on_key(self):
        """macro 键上括号形式 macro_indicators.cpi[0].<列> → 同样解析 records[0] 期次。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.cpi[0].全国-同比增长",
            stated_value=0.4,
            interpretation="2026 年 7 月 CPI 同比 0.4%",
            metric_name="CPI",
            period="2026-07",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is False

    def test_macro_index_period_mismatch_fails(self):
        """值正确但申报期次与 records[idx]["月份"] 不符 → FAIL semantic_period_mismatch。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.cpi.0.全国-同比增长",
            stated_value=0.4,
            interpretation="2026 年 6 月 CPI 同比 0.4%",
            metric_name="CPI",
            period="2026-06",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_period_mismatch"

    def test_quarterly_index_period_resolved_from_quarters(self):
        """quarterly_trend 括号形式（quarters 降序：idx 1 = 次近季）→ 期次比对。

        quarters = ["2025Q4", "2025Q3"]：yoy[1] 锚定 2025Q3。申报 2025Q3 → PASS
        且无覆盖缺口；申报 2025Q4（idx 0 的期次，张冠李戴）→ FAIL。
        """
        state = {"quarterly_trend": {"quarters": ["2025Q4", "2025Q3"], "yoy": [1.0, 2.0]}}
        base = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "quarterly_trend.yoy[1]",
            "stated_value": 2.0,
            "metric_name": "yoy",
        }
        ok = Claim(**base, interpretation="2025Q3 同比 2.0%", period="2025Q3")
        bad = Claim(**base, interpretation="2025Q4 同比 2.0%", period="2025Q4")
        r_ok, r_bad = verify_claims([ok, bad], state)
        assert r_ok.status == "PASS"
        assert r_ok.coverage_gap is False
        assert r_bad.status == "FAIL"
        assert r_bad.bucket == "semantic_period_mismatch"

    def test_index_period_unresolvable_counts_gap_not_fail(self):
        """state 缺 kline 时索引期次解析不出 → 缺口计数，不 FAIL。"""
        state = _state()
        del state["kline"]
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.-1",
            stated_value=102.0,
            interpretation="MA5 为 102.0",
            metric_name="MA",
            period="2026-08-28",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"
        assert r.coverage_gap is True

    def test_garbage_period_counts_gap_not_fail(self):
        """period 无法归一化（"最近"）→ 缺口，不 FAIL。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="毛利率",
            period="最近",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is True


class TestResolveIndexPeriodDatetime:
    def test_datetime64_date_normalized(self):
        """终审 finding 3：kline 日期为 datetime64 时须渲染为 ISO 日期，
        否则 normalize_period 解析失败会把缺口语义扭曲成系统性 FAIL。"""
        from finance_agent.citation import _resolve_index_period

        state = {"kline": pd.DataFrame({"日期": pd.to_datetime(["2026-08-27", "2026-08-28"])})}
        assert _resolve_index_period("technical_indicators.rsi.-1", state) == "2026-08-28"

    def test_string_date_unchanged(self):
        from finance_agent.citation import _resolve_index_period

        state = {"kline": pd.DataFrame({"日期": ["2026-08-27", "2026-08-28"]})}
        assert _resolve_index_period("technical_indicators.rsi.-1", state) == "2026-08-28"
