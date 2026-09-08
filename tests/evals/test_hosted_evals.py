"""enable-hosted-evaluator：降级轮询聚合/告警/口径对齐 测试（fixtures 离线）。"""

from evals.hosted_evals.poll import (
    ScoreRecord,
    aggregate_window,
    align_offline,
)


def _score(value, trace_id="t1", name="quality", config_id="cfg1"):
    return ScoreRecord(
        score_id=f"s-{value}-{trace_id}",
        name=name,
        value=value,
        trace_id=trace_id,
        config_id=config_id,
        created_at="2026-09-04T10:00:00Z",
    )


class TestAggregateWindow:
    def test_avg_and_low_traces(self):
        scores = [_score(4.5), _score(2.0, trace_id="t2"), _score(3.0, trace_id="t3")]
        agg = aggregate_window(scores, alert_threshold=3.5)
        assert agg.total == 3
        assert agg.avg == round((4.5 + 2.0 + 3.0) / 3, 4)
        assert agg.low_count == 2
        assert len(agg.low_traces) == 2
        assert agg.alert is True

    def test_no_alert_above_threshold(self):
        agg = aggregate_window([_score(4.0), _score(4.5)], alert_threshold=3.5)
        assert agg.alert is False
        assert agg.low_count == 0

    def test_empty(self):
        agg = aggregate_window([])
        assert agg.total == 0
        assert agg.avg is None
        assert agg.alert is False


class TestAlignOffline:
    def test_mae_and_drift(self):
        hosted = [_score(4.0, trace_id="t1"), _score(2.0, trace_id="t2")]
        offline = {"t1": 4.0, "t2": 4.0}
        out = align_offline(hosted, offline, max_mae=1.0)
        assert len(out["pairs"]) == 2
        assert out["mae"] == 1.0
        assert out["drift"] is False  # 恰在阈值内

    def test_drift_detected(self):
        hosted = [_score(5.0, trace_id="t1"), _score(1.0, trace_id="t2")]
        offline = {"t1": 5.0, "t2": 5.0}
        out = align_offline(hosted, offline, max_mae=1.0)
        assert out["mae"] == 2.0
        assert out["drift"] is True

    def test_no_pairs(self):
        out = align_offline([_score(4.0)], {})
        assert out["pairs"] == []
        assert out["mae"] is None
        assert out["drift"] is False
