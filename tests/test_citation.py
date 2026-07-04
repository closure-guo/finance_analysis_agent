"""TDD tests for citation.py — 确定性引用校验器。

校验器是纯 Python 实现（不调 LLM），复用 metrics/ 纯函数对 Agent 产出的
Claim 进行重算比对。参考 ADR-0011 和 FinGround 六类分类法。

fixture 数据手算验证（来自 conftest.py）：
- 2024: 资产总计=1000, 负债合计=400 → 资产负债率 = 40%
"""

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
