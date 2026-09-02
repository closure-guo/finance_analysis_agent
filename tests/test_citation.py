"""TDD tests for citation.py — 确定性引用校验器。

校验器是纯 Python 实现（不调 LLM），复用 metrics/ 纯函数对 Agent 产出的
Claim 进行重算比对。参考 ADR-0011 和 FinGround 六类分类法。

fixture 数据手算验证（来自 conftest.py）：
- 2024: 资产总计=1000, 负债合计=400 → 资产负债率 = 40%
"""

import pandas as pd
import pytest

from finance_agent.citation import CitationReport, Claim, verify_claims
from finance_agent.metrics.dupont import calc_dupont


class TestVerifyClaims:
    """引用校验器测试。"""

    def test_numerical_claim_pass(self):
        """数值型 claim 值匹配时返回 PASS。"""
        state = {
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="资产负债率为 40%，杠杆水平适中",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "PASS"


class TestCitationReport:
    """CitationReport 批量汇总测试。"""

    def test_report_summarizes_mixed_results(self):
        """多 claim 混合结果：1 PASS + 1 FAIL + 1 UNVERIFIABLE。"""
        state = {
            "solvency_metrics": {"资产负债率": {"2024": 40.0, "2023": 38.0}},
        }
        claims = [
            Claim(
                claim_type="numerical",
                source_type="data",
                field_ref="solvency_metrics.资产负债率.2024",
                stated_value=40.0,
                interpretation="",
            ),
            Claim(
                claim_type="numerical",
                source_type="data",
                field_ref="solvency_metrics.资产负债率.2023",
                stated_value=50.0,
                interpretation="",
            ),
            Claim(
                claim_type="numerical",
                source_type="llm_inference",
                field_ref="solvency_metrics.资产负债率.2024",
                stated_value=40.0,
                interpretation="",
            ),
        ]
        results = verify_claims(claims, state)
        report = CitationReport.from_results(results)
        assert report.total == 3
        assert report.passed == 1
        assert report.failed == 1
        assert report.unverifiable == 1
        assert not report.all_passed

    def test_report_all_passed(self):
        """全部 PASS 时 all_passed=True。"""
        state = {
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        claims = [
            Claim(
                claim_type="numerical",
                source_type="data",
                field_ref="solvency_metrics.资产负债率.2024",
                stated_value=40.0,
                interpretation="",
            ),
        ]
        results = verify_claims(claims, state)
        report = CitationReport.from_results(results)
        assert report.passed == 1
        assert report.failed == 0
        assert report.all_passed

    def test_llm_inference_claim_skipped(self):
        """source_type=llm_inference 的 claim 跳过校验，返回 UNVERIFIABLE。"""
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}
        claim = Claim(
            claim_type="numerical",
            source_type="llm_inference",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="行业惯例资产负债率约 40%",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "UNVERIFIABLE"

    def test_computational_claim_dupont_roe_fail(self, balance_sheet, income_statement):
        """计算型 claim：杜邦 ROE 重算不匹配时返回 FAIL。"""
        dupont_tree = calc_dupont(balance_sheet, income_statement)
        state = {
            "balance_sheet": balance_sheet,
            "income_statement": income_statement,
            "dupont_tree": dupont_tree,
        }
        # 实际 ROE ≈ 0.2833，声称 0.50
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="dupont_tree.L1.2024.ROE",
            stated_value=0.50,
            interpretation="杜邦分解 ROE 为 50%",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "FAIL"
        assert results[0].ground_truth is not None
        assert abs(results[0].ground_truth - 0.2833) < 0.01

    def test_comparative_claim_pass(self):
        """比较型 claim：比较方向正确时返回 PASS。

        stated_value 为比较方向: "greater_than" / "less_than" / "equal_to"
        field_ref_b 指向被比较的第二个值。
        """
        state = {
            "profitability_metrics": {"ROE": {"2024": 28.0, "2023": 25.0}},
        }
        claim = Claim(
            claim_type="comparative",
            source_type="data",
            field_ref="profitability_metrics.ROE.2024",
            stated_value="greater_than",
            interpretation="2024 年 ROE 高于 2023 年",
            field_ref_b="profitability_metrics.ROE.2023",
            stated_value_b=25.0,
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_event_claim_pass(self):
        """事件型 claim：引用的事件存在于 key_events 时返回 PASS。"""
        state = {
            "key_events": [
                {"title": "茅台提价", "date": "2024-01-15"},
                {"title": "新品发布", "date": "2024-06-01"},
            ],
        }
        claim = Claim(
            claim_type="temporal",
            source_type="event",
            field_ref="茅台提价",
            stated_value="2024-01-15",
            interpretation="茅台于 2024 年 1 月提价",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_numerical_claim_with_list_index(self):
        """数值型 claim 的 field_ref 包含 list index 时也能正确解析。

        technical_indicators.MA.5.4 → state["technical_indicators"]["MA"]["5"][4]
        """
        state = {
            "technical_indicators": {
                "MA": {"5": [None, None, None, None, 13.0, 14.0]},
            },
        }
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.4",
            stated_value=13.0,
            interpretation="MA5 为 13.0",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_numerical_claim_fail_wrong_value(self):
        """数值型 claim 值不匹配时返回 FAIL，附带 ground_truth 和 delta。"""
        state = {
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=45.0,
            interpretation="资产负债率为 45%",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "FAIL"
        assert results[0].ground_truth == 40.0
        assert results[0].delta == 5.0

    def test_computational_claim_dupont_roe_pass(self, balance_sheet, income_statement):
        """计算型 claim：杜邦 ROE 重算匹配时返回 PASS。

        2024: ROE = (170/1000) × (1000/1000) × (1000/600) ≈ 0.2833
        """
        dupont_tree = calc_dupont(balance_sheet, income_statement)
        state = {
            "balance_sheet": balance_sheet,
            "income_statement": income_statement,
            "dupont_tree": dupont_tree,
        }
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="dupont_tree.L1.2024.ROE",
            stated_value=0.2833,
            interpretation="杜邦分解 ROE 为 28.33%",
        )
        results = verify_claims([claim], state)
        assert len(results) == 1
        assert results[0].status == "PASS"


class TestNumericalRobustness:
    """数值 claim 解析鲁棒性（baseline-v2 r3 炸行回归）。

    GLM 生成的 field_ref 可能指到 dict/list 等非数值字段，
    float(dict) 抛 TypeError 炸整条管线 → 应按 FAIL（无法核验）处理。
    """

    def test_field_ref_resolves_to_dict_fails_gracefully(self):
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率",  # 指到 dict 而非叶子数值
            stated_value=40.0,
            interpretation="x",
        )
        results = verify_claims([claim], state)
        assert results[0].status == "FAIL"
        assert results[0].ground_truth is None

    def test_field_ref_resolves_to_list_fails_gracefully(self):
        state = {"kline": [1700.0, 1710.0]}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="kline",
            stated_value=1700.0,
            interpretation="x",
        )
        results = verify_claims([claim], state)
        assert results[0].status == "FAIL"


class TestMacroClaimNewStructure:
    """fetch 守卫新结构下 macro claim 的 field_ref 解析回归（final review Critical #1）。

    旧结构 macro_indicators.cpi 为 list；新守卫结构为
    {"as_of_date", "freshness", "records"}。_resolve_field_ref 须在遇到含
    records 键的 dict 时自动下钻 records，保持后续 .index.column 路径语义，
    否则 cpi.0 取 dict.get("0") = None → 数值校验 FAIL → 全分析师 3 倍重试。
    """

    def _state(self) -> dict:
        return {
            "macro_indicators": {
                "cpi": {
                    "as_of_date": "2026-07-01",
                    "freshness": "fresh",
                    "records": [{"月份": "2026年07月份", "全国-当月-同比增长": 0.4}],
                }
            }
        }

    def test_macro_claim_resolves_in_new_structure(self):
        from finance_agent.citation import _resolve_field_ref

        val = _resolve_field_ref("macro_indicators.cpi.0.全国-当月-同比增长", self._state())
        assert val == 0.4

    def test_macro_numerical_claim_pass(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.cpi.0.全国-当月-同比增长",
            stated_value=0.4,
            interpretation="CPI 环比 0.4%",
        )
        results = verify_claims([claim], self._state())
        assert len(results) == 1
        assert results[0].status == "PASS"


class TestFieldRefRecordsGuard:
    """field_ref 显式引用 records 键仍可解析（守卫结构向后兼容）。"""

    def test_explicit_records_key_still_resolves(self):
        from finance_agent.citation import _resolve_field_ref

        val = _resolve_field_ref(
            "macro_indicators.cpi.records.0.全国-当月-同比增长", self_cpi_state()
        )
        assert val == 0.4

    def test_plain_dict_behavior_unchanged(self):
        from finance_agent.citation import _resolve_field_ref

        # 普通 dict 无 records 键时按原样 get，不破坏既有行为
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}
        assert _resolve_field_ref("solvency_metrics.资产负债率.2024", state) == 40.0
        assert _resolve_field_ref("solvency_metrics.资产负债率", state) == {"2024": 40.0}


def self_cpi_state() -> dict:
    """TestFieldRefRecordsGuard 用 state fixture（避免重复构建）。"""
    return {
        "macro_indicators": {
            "cpi": {
                "as_of_date": "2026-07-01",
                "freshness": "fresh",
                "records": [{"月份": "2026年07月份", "全国-当月-同比增长": 0.4}],
            }
        }
    }


class TestComputationalRegistryCoverage:
    """注册表全覆盖：metrics/ 全部纯函数指标族可重算（spec 计算型声明重算注册表全覆盖）。"""

    def _state(self, balance_sheet, income_statement, cash_flow, indicators):
        kline = pd.DataFrame(
            {
                "日期": pd.date_range("2025-01-01", periods=80, freq="D").strftime("%Y-%m-%d"),
                "开盘": [10.0] * 80,
                "收盘": [10.0 + i * 0.1 for i in range(80)],
                "最高": [10.5 + i * 0.1 for i in range(80)],
                "最低": [9.5 + i * 0.1 for i in range(80)],
                "成交量": [1000.0] * 80,
            }
        )
        bench = kline.copy()
        return {
            "balance_sheet": balance_sheet,
            "income_statement": income_statement,
            "cash_flow_statement": cash_flow,
            "financial_indicators": indicators,
            "kline": kline,
            "benchmark_kline": bench,
        }

    def test_registry_covers_all_metric_families(self):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        expected = {
            "dupont_tree",
            "solvency_metrics",
            "profitability_metrics",
            "efficiency_metrics",
            "cashflow_metrics",
            "technical_indicators",
            "risk_metrics",
        }
        assert expected <= set(_COMPUTATIONAL_RECALC)

    def test_solvency_recalc_pass_and_fail(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        from finance_agent.citation import _COMPUTATIONAL_RECALC
        from finance_agent.metrics.solvency import calc_solvency

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["solvency_metrics"](state)
        assert (
            truth["资产负债率"]["2024"]
            == calc_solvency(balance_sheet, income_statement, indicators)["资产负债率"]["2024"]
        )
        ok = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=float(truth["资产负债率"]["2024"]),
            interpretation="",
        )
        bad = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=float(truth["资产负债率"]["2024"]) * 2,
            interpretation="",
        )
        results = verify_claims([ok, bad], state)
        assert results[0].status == "PASS"
        assert results[1].status == "FAIL"

    def test_profitability_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["profitability_metrics"](state)
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="profitability_metrics.净利率.2024",
            stated_value=float(truth["净利率"]["2024"]),
            interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_efficiency_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["efficiency_metrics"](state)
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="efficiency_metrics.总资产周转率.2024",
            stated_value=float(truth["总资产周转率"]["2024"]),
            interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_cashflow_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["cashflow_metrics"](state)
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="cashflow_metrics.经营现金流/净利润.2024",
            stated_value=float(truth["经营现金流/净利润"]["2024"]),
            interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_technical_recalc_with_list_index(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        """technical_indicators 值为等长 list，子路径须支持 list index。"""
        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        from finance_agent.metrics.technical import calc_technical

        truth = calc_technical(state["kline"])
        ma5_last = truth["MA"]["5"][-1]
        assert ma5_last is not None
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref=f"technical_indicators.MA.5.{len(truth['MA']['5']) - 1}",
            stated_value=float(ma5_last),
            interpretation="",
        )
        result = verify_claims([claim], state)[0]
        assert result.status == "PASS"
        assert result.ground_truth == pytest.approx(ma5_last)

    def test_risk_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["risk_metrics"](state)
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="risk_metrics.max_drawdown",
            stated_value=float(truth["max_drawdown"]),
            interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_unregistered_root_counts_coverage_gap(self):
        state = {"balance_sheet": pd.DataFrame(), "income_statement": pd.DataFrame()}
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="unknown_metrics.某指标.2024",
            stated_value=1.0,
            interpretation="",
        )
        results = verify_claims([claim], state)
        report = CitationReport.from_results(results)
        assert results[0].status == "UNVERIFIABLE"
        assert report.coverage_gaps == 1

    def test_registered_root_no_coverage_gap(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["dupont_tree"](state)
        # harden-citation-semantic-coverage D5：未申报 metric_name/period 也计覆盖缺口，
        # 故本用例全申报（与 field_ref 一致），仅钉「已注册根键 → 不计缺口」语义。
        claim = Claim(
            claim_type="computational",
            source_type="data",
            field_ref="dupont_tree.L1.2024.ROE",
            stated_value=float(truth["L1"]["2024"]["ROE"]),
            interpretation="",
            metric_name="ROE",
            period="2024",
        )
        results = verify_claims([claim], state)
        report = CitationReport.from_results(results)
        assert results[0].status == "PASS"
        assert report.coverage_gaps == 0


class TestComparativeBaseDeclaration:
    """refine-citation-coverage-v3 D3：comparative 基期值双端申报与校验。"""

    _STATE = {"profitability_metrics": {"净利率": {"2025": 19.07, "2024": 21.93}}}

    def _claim(self, **kw):
        base = {
            "claim_type": "comparative",
            "source_type": "data",
            "field_ref": "profitability_metrics.净利率.2025",
            "stated_value": "less_than",
            "interpretation": "2025 净利率较 2024 下滑",
            "field_ref_b": "profitability_metrics.净利率.2024",
        }
        base.update(kw)
        return Claim(**base)

    def test_base_value_correct_passes(self):
        (r,) = verify_claims([self._claim(stated_value_b=21.93)], self._STATE)
        assert r.status == "PASS"

    def test_base_value_mismatch_fails_value_mismatch(self):
        # 正文「较2024年21.93%下滑」但申报基期 28.0（错值）→ FAIL
        (r,) = verify_claims([self._claim(stated_value_b=28.0)], self._STATE)
        assert r.status == "FAIL"
        assert r.bucket == "value_mismatch"

    def test_base_not_declared_fails(self):
        # 基期裸奔：field_ref_b 设而 stated_value_b 缺 → FAIL（拦截）
        (r,) = verify_claims([self._claim()], self._STATE)
        assert r.status == "FAIL"
        assert r.bucket == "path_unresolvable"
