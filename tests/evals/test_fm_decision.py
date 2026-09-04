"""calibrate-fm-approval：FM 决策分布/风控否决召回/理由完整 度量测试。

数据形态来自 Langfuse `fund_manager` trace（output.answer = ```json 包裹的
{"decision", "reasoning"}），fixtures 离线断言（不依赖网络）。
"""

from evals.fm_decision.measure import (
    TraceSample,
    aggregate,
    extract_samples,
    parse_answer,
    reason_complete,
    run_offline,
    veto_recall,
)


class TestParseAnswer:
    def test_code_fenced_json(self):
        ans = '```json\n{"decision": "reject", "reasoning": "风控超标"}\n```'
        assert parse_answer(ans) == {"decision": "reject", "reasoning": "风控超标"}

    def test_bare_json(self):
        assert parse_answer('{"decision": "approve", "reasoning": "合格"}') == {
            "decision": "approve",
            "reasoning": "合格",
        }

    def test_invalid_returns_none(self):
        assert parse_answer("") is None
        assert parse_answer("not json at all") is None

    def test_missing_decision_returns_none(self):
        assert parse_answer('{"reasoning": "x"}') is None


class TestExtractSamples:
    def test_parse_fail_counted(self):
        traces = [
            {
                "id": "t1",
                "timestamp": "2026-09-03T10:00:00Z",
                "output": {"answer": '{"decision": "approve", "reasoning": "ok"}'},
            },
            {"id": "t2", "timestamp": "2026-09-03T10:01:00Z", "output": {}},
        ]
        samples, parse_fail = extract_samples(traces)
        assert len(samples) == 1
        assert samples[0].decision == "approve"
        assert parse_fail == 1


class TestAggregate:
    def test_counts_and_by_day(self):
        samples = [
            TraceSample(decision="approve", reasoning="r", timestamp="2026-09-03T10:00:00Z"),
            TraceSample(decision="return", reasoning="r", timestamp="2026-09-03T11:00:00Z"),
            TraceSample(decision="reject", reasoning="r", timestamp="2026-09-04T10:00:00Z"),
            TraceSample(decision="approve", reasoning="r", timestamp="2026-09-04T11:00:00Z"),
        ]
        agg = aggregate(samples)
        assert agg["total"] == 4
        assert agg["counts"] == {"approve": 2, "return": 1, "reject": 1}
        assert agg["by_day"]["2026-09-03"] == {"approve": 1, "return": 1, "reject": 0}

    def test_empty(self):
        agg = aggregate([])
        assert agg["total"] == 0
        assert agg["counts"] == {}
        assert agg["by_day"] == {}


class TestVetoRecall:
    def test_high_risk_approve_is_violation(self):
        samples = [
            TraceSample(
                decision="approve", reasoning="r", trace_id="v1", max_drawdown=0.41, volatility=0.76
            )
        ]
        out = veto_recall(samples)
        assert out["checked"] == 1
        assert out["violation_count"] == 1
        assert out["violations"][0]["trace_id"] == "v1"

    def test_high_risk_reject_is_ok(self):
        samples = [
            TraceSample(decision="reject", reasoning="r", max_drawdown=0.41, volatility=0.76)
        ]
        out = veto_recall(samples)
        assert out["checked"] == 1
        assert out["violation_count"] == 0
        assert out["violation_rate"] == 0.0

    def test_no_risk_samples_skipped(self):
        samples = [TraceSample(decision="approve", reasoning="r", trace_id="n1")]
        out = veto_recall(samples)
        assert out["checked"] == 0
        assert out["violation_rate"] is None

    def test_threshold_below_boundary_ok(self):
        samples = [
            TraceSample(decision="approve", reasoning="r", max_drawdown=0.25, volatility=0.4)
        ]
        out = veto_recall(samples)
        assert out["violation_count"] == 0


class TestReasonComplete:
    def test_missing_reasoning_detected(self):
        samples = [
            TraceSample(
                decision="reject", reasoning="", trace_id="m1", timestamp="2026-09-03T10:00:00Z"
            ),
            TraceSample(decision="approve", reasoning="有理由", trace_id="m2"),
        ]
        out = reason_complete(samples)
        assert out["checked"] == 2
        assert out["missing_count"] == 1
        assert out["missing"][0]["trace_id"] == "m1"

    def test_all_complete(self):
        out = reason_complete([TraceSample(decision="return", reasoning="改进要求", trace_id="x")])
        assert out["missing_count"] == 0


class TestRunOffline:
    def test_end_to_end_with_fixture_traces(self):
        traces = [
            {
                "id": "t-appr",
                "timestamp": "2026-09-03T10:00:00Z",
                "output": {
                    "answer": '```json\n{"decision": "approve", "reasoning": "风险可控"}\n```'
                },
            },
            {
                "id": "t-rej",
                "timestamp": "2026-09-03T11:00:00Z",
                "output": {"answer": '{"decision": "reject", "reasoning": "回撤 41% 超标"}'},
            },
            {"id": "t-fail", "timestamp": "2026-09-03T12:00:00Z", "output": {"answer": "非 JSON"}},
        ]
        result = run_offline(traces)
        assert result["parse_fail"] == 1
        assert result["aggregate"]["counts"] == {"approve": 1, "reject": 1}
        assert result["aggregate"]["by_day"]["2026-09-03"] == {
            "approve": 1,
            "reject": 1,
            "return": 0,
        }
        assert result["reason_complete"]["missing_count"] == 0
