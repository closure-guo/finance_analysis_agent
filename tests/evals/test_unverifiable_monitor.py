"""突升检测纯逻辑测试（spec「UNVERIFIABLE 占比监控」Scenario「占比突升告警」）。"""

from evals.unverifiable_monitor import detect_rise, evaluate_history


class TestDetectRise:
    def test_no_rise_within_threshold(self):
        assert detect_rise([0.10, 0.12], [0.08, 0.10, 0.09]) is None

    def test_rise_over_threshold_alerts(self):
        alert = detect_rise([0.25, 0.26], [0.10, 0.12, 0.11])
        assert alert is not None
        assert alert["level"] == "warning"
        assert alert["baseline_mean"] == 0.11
        assert alert["recent_mean"] == 0.255
        assert alert["rise_pp"] > 0.10

    def test_empty_inputs_return_none(self):
        assert detect_rise([], []) is None
        assert detect_rise([0.5], []) is None


class TestEvaluateHistory:
    def test_history_sorted_and_evaluated(self):
        history = [
            ("2026-08-01", 0.10),
            ("2026-08-02", 0.11),
            ("2026-08-03", 0.12),
            ("2026-08-04", 0.30),
            ("2026-08-05", 0.32),
        ]
        alert = evaluate_history(history, baseline_window=3, recent_window=2)
        assert alert is not None
        assert alert["recent_mean"] == 0.31

    def test_insufficient_history_none(self):
        assert evaluate_history([("d1", 0.5)], baseline_window=3, recent_window=2) is None
