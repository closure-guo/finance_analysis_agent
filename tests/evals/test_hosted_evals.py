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


class TestEvalSourceFilter:
    """3.225.7 实证：hosted evaluator 分数 config_id=NULL、source=EVAL；
    API 写入的离线 judge 分 source=API。configId 不可作判别键（r7 修复）。"""

    def _rec(self, value, trace_id="t1", source="API", config_id=None):
        return ScoreRecord(
            score_id=f"s-{value}-{trace_id}-{source}",
            name="debate_quality（辩论质量）",
            value=value,
            trace_id=trace_id,
            config_id=config_id,
            created_at="2026-09-08T11:09:38Z",
            source=source,
        )

    def test_keeps_only_eval_source(self):
        from evals.hosted_evals.poll import filter_eval_source

        records = [self._rec(2, "t1", source="EVAL"), self._rec(5, "t2", source="API")]
        out = filter_eval_source(records)
        assert [r.trace_id for r in out] == ["t1"]

    def test_missing_source_dropped(self):
        from evals.hosted_evals.poll import filter_eval_source

        records = [self._rec(4, "t3", source=None)]
        assert filter_eval_source(records) == []

    def test_score_record_has_source_field(self):
        rec = self._rec(4, "t4", source="EVAL")
        assert rec.source == "EVAL"
