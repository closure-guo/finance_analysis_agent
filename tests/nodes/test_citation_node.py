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


class TestFailRateHistory:
    """citation-retry-policy delta：verify_citations 记录各轮失败率供路由降级。"""

    def _failing_state(self, prior_rates: list | None = None, iteration: int = 1) -> dict:
        report = AnalystReport(
            agent_name="fundamental",
            summary="基本面分析",
            key_findings=["资产负债率 45%"],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=45.0,  # 与数据 40.0 不符 → FAIL
                    interpretation="资产负债率 45%",
                ),
            ],
            markdown="## 基本面分析",
        )
        state = {
            "analyst_reports": {"fundamental": report},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
            "iteration_count": iteration,
        }
        if prior_rates is not None:
            state["citation_fail_rates"] = prior_rates
        return state

    def test_appends_fail_rate_to_history(self):
        result = verify_citations(self._failing_state(prior_rates=[0.35]))
        assert result["citation_fail_rates"] == [0.35, 1.0]
        assert result["iteration_count"] == 2

    def test_pass_records_zero_rate(self):
        state = {
            "analyst_reports": {},  # 零 claim → all_passed=True
            "iteration_count": 1,
        }
        result = verify_citations(state)
        assert result["citation_pass"] is True
        assert result["citation_fail_rates"] == [0.0]

    def test_deescalation_marks_span(self, monkeypatch):
        """降级触发时 verify_citations SHALL 在 span 上留可判读标记。"""
        from finance_agent.nodes import citation_node

        marks: list[dict] = []

        def fake_update_span(**kwargs):
            marks.append(kwargs)

        monkeypatch.setattr(citation_node, "update_current_span", fake_update_span)

        # 上一轮 0.5，本轮 1.0（≥ 0.5×0.8 且轮次未达上限）→ 路由将降级放行
        verify_citations(self._failing_state(prior_rates=[0.5], iteration=1))

        degraded = [m for m in marks if m.get("metadata", {}).get("citation_retry_deescalated")]
        assert degraded, f"降级决策须落 span 标记，实际 marks: {marks}"
        assert degraded[0]["metadata"]["fail_rates"] == [0.5, 1.0]


class TestCitationMinorFail:
    """skip-citation-retry-on-minor-failures：FAIL≤1 且失败率≤5% 免重试标志。"""

    _M2_STATE = {"macro_indicators": {"m2": [{"货币和准货币(M2)-同比增长": 17.37}]}}

    def _claims(self, n_total: int, n_fail: int) -> list[dict]:
        return [
            {
                "claim_type": "numerical",
                "source_type": "data",
                "field_ref": "macro_indicators.m2.0.货币和准货币(M2)-同比增长",
                "stated_value": 16.19 if i < n_fail else 17.37,
                "interpretation": "",
            }
            for i in range(n_total)
        ]

    def _state(self, claims: list[dict]) -> dict:
        return {
            "analyst_reports": {
                "technical": {
                    "agent_name": "technical",
                    "summary": "",
                    "key_findings": [],
                    "claims": claims,
                    "markdown": "",
                }
            },
            **self._M2_STATE,
        }

    def test_minor_fail_sets_flag_and_marks_span(self, monkeypatch):
        """40 条中 1 条 FAIL（2.5% ≤ 5%）：设置 citation_minor_fail 并落 span 标记。"""
        from finance_agent.nodes import citation_node

        marks: list[dict] = []

        def fake_update_span(**kwargs):
            marks.append(kwargs)

        monkeypatch.setattr(citation_node, "update_current_span", fake_update_span)

        result = citation_node.verify_citations(self._state(self._claims(40, 1)))
        assert result["citation_minor_fail"] is True
        marked = [m for m in marks if m.get("metadata", {}).get("citation_minor_fail_deescalated")]
        assert marked, f"轻微失败须落 span 标记，实际 marks: {marks}"

    def test_many_fails_no_minor_flag(self, monkeypatch):
        """失败数/失败率超阈值（13 条全 FAIL，100%）不设 minor_fail。"""
        from finance_agent.nodes import citation_node

        monkeypatch.setattr(citation_node, "update_current_span", lambda **kw: None)
        result = citation_node.verify_citations(self._state(self._claims(13, 13)))
        assert result["citation_minor_fail"] is False

    def test_all_pass_no_flag(self, monkeypatch):
        """全 PASS 不设 minor_fail（渲染由 citation_pass 走既有路径）。"""
        from finance_agent.nodes import citation_node

        monkeypatch.setattr(citation_node, "update_current_span", lambda **kw: None)
        result = citation_node.verify_citations(self._state(self._claims(5, 0)))
        assert result["citation_minor_fail"] is False


def _report(agent: str, claims: list[Claim], markdown: str) -> AnalystReport:
    return AnalystReport(
        agent_name=agent,
        summary=f"{agent} 分析",
        key_findings=[],
        claims=claims,
        markdown=markdown,
    )


class TestFailBucketAggregation:
    def test_value_mismatch_produces_retry_target_and_feedback(self):
        """基本面 1 条值级 FAIL → 仅基本面进重试目标，反馈带 gt 明细。"""
        good = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="资产负债率 40%",
        )
        bad = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2023",
            stated_value=99.0,
            interpretation="2023 年资产负债率 99%",
        )
        state = {
            "analyst_reports": {
                "fundamental": _report("fundamental", [good, bad], "资产负债率 40%"),
                "macro": _report("macro", [], "CPI 温和"),
            },
            "solvency_metrics": {"资产负债率": {"2024": 40.0, "2023": 38.0}},
        }
        result = verify_citations(state)
        assert result["citation_retry_targets"] == ["fundamental"]
        fb = result["citation_retry_feedback"]["fundamental"]
        assert len(fb) == 1
        assert fb[0]["field_ref"] == "solvency_metrics.资产负债率.2023"
        assert fb[0]["ground_truth"] == 38.0
        assert fb[0]["stated_value"] == 99.0
        assert result["citation_fail_buckets"] == {"value_mismatch": 1}

    def test_format_class_fail_no_retry_target(self):
        """纯格式类 FAIL（路径不可解析）→ 无重试目标，桶计数照记。"""
        bad = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.不存在.2024",
            stated_value=40.0,
            interpretation="x",
        )
        state = {
            "analyst_reports": {"fundamental": _report("fundamental", [bad], "x")},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        assert result["citation_retry_targets"] == []
        assert result["citation_retry_feedback"] == {}
        assert result["citation_fail_buckets"] == {"path_unresolvable": 1}
        assert result["citation_pass"] is False

    def test_semantic_fail_no_retry_target(self):
        """术语张冠李戴 → 格式类桶，不触发重试。"""
        bad = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="净利率为 45.2%",
            metric_name="净利率",
        )
        state = {
            "analyst_reports": {"fundamental": _report("fundamental", [bad], "净利率 45.2%")},
            "profitability_metrics": {"毛利率": {"2024": 45.2}},
        }
        result = verify_citations(state)
        assert result["citation_retry_targets"] == []
        assert result["citation_fail_buckets"] == {"semantic_term_mismatch": 1}


class TestCoverageScore:
    def test_coverage_computed_from_markdown(self):
        """markdown 黑数字拉低 citation_coverage。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="资产负债率 40%",
        )
        state = {
            "analyst_reports": {
                "fundamental": _report("fundamental", [claim], "资产负债率 40%，营收 10.39 亿")
            },
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        # 40% 被认领、10.39 亿未认领 → 1/2
        assert result["citation_coverage"] == 0.5

    def test_coverage_full_when_no_dark_numbers(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="资产负债率 40%",
        )
        state = {
            "analyst_reports": {"fundamental": _report("fundamental", [claim], "资产负债率 40%")},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        assert result["citation_coverage"] == 1.0

    def test_coverage_reported_to_langfuse(self, monkeypatch):
        """citation_coverage 作为 NUMERIC Score 上报；<0.8 产生告警 metadata。"""
        import finance_agent.nodes.citation_node as cn

        calls: list[dict] = []

        class _FakeClient:
            def score_current_trace(self, **kwargs):
                calls.append(kwargs)

            def update_current_span(self, **kwargs):
                calls.append(kwargs)

        monkeypatch.setattr(cn, "get_langfuse", lambda: _FakeClient())
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="资产负债率 40%",
        )
        state = {
            "analyst_reports": {
                "fundamental": _report("fundamental", [claim], "资产负债率 40%，营收 10.39 亿")
            },
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        verify_citations(state)
        score = next(c for c in calls if c.get("name") == "citation_coverage")
        assert score["data_type"] == "NUMERIC"
        assert score["value"] == 0.5
        span = next(
            c for c in calls if "metadata" in c and "citation_coverage_alert" in c["metadata"]
        )
        assert span["metadata"]["citation_coverage_alert"] is True
        assert span["level"] == "WARNING"
