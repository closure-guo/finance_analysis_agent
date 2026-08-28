"""TDD tests for nodes/citation_node.py — 引用校验图节点。

节点行为：
1. 从 analyst_reports 中提取所有 Claim
2. 调用 verify_claims 校验
3. 返回 citation_report + citation_pass
4. 上报 citation_pass / citation_unverifiable_ratio 两个 Langfuse Score
"""

import logging

from finance_agent.citation import Claim
from finance_agent.models import AnalystReport
from finance_agent.nodes.citation_node import verify_citations


class TestVerifyCitations:
    """引用校验节点测试。"""

    def test_all_claims_pass(self):
        """所有 claim 校验通过时 citation_pass=True。"""
        report = AnalystReport(
            agent_name="fundamental",
            summary="基本面分析",
            key_findings=["资产负债率 40%"],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=40.0,
                    interpretation="资产负债率 40%",
                ),
            ],
            markdown="## 基本面分析",
        )
        state = {
            "analyst_reports": {"fundamental": report},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        assert result["citation_pass"] is True
        assert result["citation_report"]["total"] == 1
        assert result["citation_report"]["passed"] == 1

    def test_claims_with_failure(self):
        """有 claim 校验失败时 citation_pass=False。"""
        report = AnalystReport(
            agent_name="fundamental",
            summary="基本面分析",
            key_findings=["资产负债率 45%"],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=45.0,
                    interpretation="资产负债率 45%",
                ),
            ],
            markdown="## 基本面分析",
        )
        state = {
            "analyst_reports": {"fundamental": report},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        assert result["citation_pass"] is False
        assert result["citation_report"]["failed"] == 1

    def test_no_claims_returns_pass(self):
        """没有 claim 时默认通过。"""
        report = AnalystReport(
            agent_name="macro",
            summary="宏观分析",
            key_findings=["通胀温和"],
            claims=[],
            markdown="## 宏观分析",
        )
        state = {"analyst_reports": {"macro": report}}
        result = verify_citations(state)
        assert result["citation_pass"] is True
        assert result["citation_report"]["total"] == 0

    def test_multiple_reports_claims_aggregated(self):
        """多个 analyst_report 的 claim 被聚合校验。"""
        report_a = AnalystReport(
            agent_name="fundamental",
            summary="基本面",
            key_findings=[],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=40.0,
                    interpretation="",
                ),
            ],
            markdown="",
        )
        report_b = AnalystReport(
            agent_name="technical",
            summary="技术面",
            key_findings=[],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="technical_indicators.MA.5.4",
                    stated_value=13.0,
                    interpretation="",
                ),
            ],
            markdown="",
        )
        state = {
            "analyst_reports": {"fundamental": report_a, "technical": report_b},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
            "technical_indicators": {"MA": {"5": [None, None, None, None, 13.0]}},
        }
        result = verify_citations(state)
        assert result["citation_pass"] is True
        assert result["citation_report"]["total"] == 2

    def test_increments_iteration_count(self):
        """verify_citations 必须递增 iteration_count，否则 after_citation 无限重试（无响应 bug 回归）。"""
        report = AnalystReport(
            agent_name="fundamental",
            summary="基本面分析",
            key_findings=["资产负债率 45%"],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=45.0,
                    interpretation="资产负债率 45%",
                ),
            ],
            markdown="## 基本面分析",
        )
        state = {
            "analyst_reports": {"fundamental": report},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
            "iteration_count": 0,
        }
        result = verify_citations(state)
        assert result["citation_pass"] is False
        assert result["iteration_count"] == 1

    def test_retry_loop_terminates_after_max(self):
        """citation 重试循环必须在 iteration_count 达上限后终止（回归无响应 bug）。"""
        from finance_agent.routing import after_citation

        report = AnalystReport(
            agent_name="fundamental",
            summary="",
            key_findings=[],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=45.0,
                    interpretation="",
                ),
            ],
            markdown="",
        )
        state = {
            "analyst_reports": {"fundamental": report},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        # 模拟图对 verify_citations 的反复调用（每次把返回的 iteration_count 写回 state）
        for expected_count in (1, 2, 3):
            result = verify_citations(state)
            assert result["iteration_count"] == expected_count
            state["iteration_count"] = result["iteration_count"]
            state["citation_pass"] = result["citation_pass"]

        # 重试上限已达 -> after_citation 必须返回 render，不再 retry
        assert state["citation_pass"] is False
        assert after_citation(state) == "render"


class TestUnverifiableRatioScore:
    """spec「UNVERIFIABLE 占比监控」Scenario「占比上报」。"""

    def _run_node(self, claims_payload, state):
        report_dict = {
            "claims": claims_payload,
        }
        state = {**state, "analyst_reports": {"fundamental": report_dict}}
        return verify_citations(state)

    def test_ratio_score_reported(self, monkeypatch):
        from finance_agent.nodes import citation_node

        captured = {}

        class _Client:
            def score_current_trace(self, **kwargs):
                captured[kwargs["name"]] = kwargs

            def update_current_span(self, **kwargs):
                pass

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: _Client())
        claims = [
            {
                "claim_type": "numerical",
                "source_type": "data",
                "field_ref": "solvency_metrics.资产负债率.2024",
                "stated_value": 40.0,
                "interpretation": "",
            },
            {
                "claim_type": "numerical",
                "source_type": "llm_inference",
                "field_ref": "x",
                "stated_value": 1.0,
                "interpretation": "",
            },
        ]
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}
        self._run_node(claims, state)
        assert "citation_unverifiable_ratio" in captured
        assert captured["citation_unverifiable_ratio"]["value"] == 0.5
        assert captured["citation_pass"]["value"] == 1.0

    def test_zero_claims_ratio_is_zero(self, monkeypatch):
        from finance_agent.nodes import citation_node

        captured = {}

        class _Client:
            def score_current_trace(self, **kwargs):
                captured[kwargs["name"]] = kwargs

            def update_current_span(self, **kwargs):
                pass

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: _Client())
        verify_citations({"analyst_reports": {}})
        assert captured["citation_unverifiable_ratio"]["value"] == 0.0

    def test_langfuse_failure_warns_not_raises(self, monkeypatch, caplog):
        from finance_agent.nodes import citation_node

        class _Boom:
            def score_current_trace(self, **kwargs):
                raise RuntimeError("langfuse down")

            def update_current_span(self, **kwargs):
                raise RuntimeError("langfuse down")

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: _Boom())
        state = {
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
            "analyst_reports": {
                "a": {
                    "claims": [
                        {
                            "claim_type": "numerical",
                            "source_type": "data",
                            "field_ref": "solvency_metrics.资产负债率.2024",
                            "stated_value": 40.0,
                            "interpretation": "",
                        }
                    ]
                }
            },
        }
        caplog.set_level(logging.WARNING, logger="finance_agent.citation")
        result = verify_citations(state)  # 不抛异常
        assert result["citation_pass"] is True
        # spec：Langfuse 不可用 SHALL 记 WARN（非 debug）且不阻断业务管线
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Langfuse" in r.message for r in warn_records)

    def test_langfuse_unconfigured_warns_not_raises(self, monkeypatch, caplog):
        """get_langfuse 返回 None（未配置）时 SHALL 记 WARN 且不阻断。"""
        from finance_agent.nodes import citation_node

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: None)
        state = {
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
            "analyst_reports": {
                "a": {
                    "claims": [
                        {
                            "claim_type": "numerical",
                            "source_type": "data",
                            "field_ref": "solvency_metrics.资产负债率.2024",
                            "stated_value": 40.0,
                            "interpretation": "",
                        }
                    ]
                }
            },
        }
        caplog.set_level(logging.WARNING, logger="finance_agent.citation")
        result = verify_citations(state)  # 不抛异常
        assert result["citation_pass"] is True
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Langfuse 未配置" in r.message for r in warn_records)
