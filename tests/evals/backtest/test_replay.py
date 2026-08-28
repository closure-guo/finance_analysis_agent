"""回放与决策一致性测试：mock 编排图，不调 LLM。"""

import evals.backtest.replay as rp
import pandas as pd
from evals.backtest.data_snapshot import SnapshotResult
from evals.backtest.replay import build_decision_record, direction_agreement


def _kline(dates: list[str], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": closes,
            "收盘": closes,
            "最高": [c + 0.5 for c in closes],
            "最低": [c - 0.5 for c in closes],
        }
    )


def _fake_orchestration(monkeypatch, captured: dict) -> None:
    """以桩替换完整编排/compute_metrics/结算，捕获 evaluate_decision 收到的参数。"""

    class FakeGraph:
        def invoke(self, state):
            return {
                "final_trade_decision": {"action": "buy", "stop_loss": 11.0, "target_price": 14.0},
                "final_report": "report",
            }

    monkeypatch.setattr(rp, "build_variant_graph", lambda variant: FakeGraph())
    monkeypatch.setattr(rp, "compute_metrics", lambda state: {})

    def fake_evaluate(record, kline, benchmark):
        captured["benchmark"] = benchmark
        return None

    monkeypatch.setattr(rp, "evaluate_decision", fake_evaluate)


class TestDecisionRecord:
    def test_record_shape_matches_settle_contract(self):
        kline_close_on_t = 12.5
        decision = {
            "action": "buy",
            "entry_price": None,
            "stop_loss": 11.0,
            "target_price": 14.0,
            "confidence": 0.7,
        }
        record = build_decision_record(
            decision, entry_price=kline_close_on_t, decision_date="2025-01-14", code="600519"
        )
        assert record["entry_price"] == 12.5
        assert record["action"] == "buy"
        assert record["timestamp"] == "2025-01-14"
        # 与 outcome.settle.evaluate_decision 契约兼容：直接跑通结算
        import pandas as pd

        from finance_agent.outcome.settle import evaluate_decision

        kline = pd.DataFrame(
            {
                "日期": ["2025-01-15", "2025-01-16"],
                "开盘": [12.6, 13.8],
                "收盘": [12.8, 14.2],
                "最高": [12.9, 14.5],
                "最低": [12.5, 13.5],
            }
        )
        settlement = evaluate_decision(record, kline, None)
        assert settlement is not None
        assert settlement.status == "hit_target"


class TestConsistency:
    def test_full_agreement(self):
        assert direction_agreement(["buy", "buy", "buy"]) == 1.0

    def test_two_of_three(self):
        assert direction_agreement(["buy", "buy", "sell"]) == 2 / 3

    def test_flag_below_threshold(self):
        assert direction_agreement(["buy", "sell", "hold"]) < 2 / 3


class TestActionFallback:
    def test_replay_decision_missing_action_reported_as_unknown(self, monkeypatch):
        captured: dict = {}

        class EmptyDecisionGraph:
            def invoke(self, state):
                return {"final_trade_decision": {}, "final_report": "report"}

        monkeypatch.setattr(rp, "build_variant_graph", lambda variant: EmptyDecisionGraph())
        monkeypatch.setattr(rp, "compute_metrics", lambda state: {})

        def fake_evaluate(record, kline, benchmark):
            captured["called"] = True
            return None

        monkeypatch.setattr(rp, "evaluate_decision", fake_evaluate)
        snap = SnapshotResult(state={"kline": _kline(["2025-01-14"], [10.5])}, metadata={})
        result = rp.replay_decision("600519", "2025-01-14", snapshot=snap)
        # 口径统一：action 缺失 → "unknown"（不再是 ""）
        assert result["action"] == "unknown"
        # 无有效 action 不进入结算
        assert result["settlement"] is None
        assert "called" not in captured

    def test_consistency_counts_missing_action_as_unknown(self, monkeypatch):
        monkeypatch.setattr(
            rp, "replay_decision", lambda *a, **k: {"decision": {}, "settlement": None}
        )
        out = rp.replay_with_consistency(
            "600519", "2025-01-14", n=2, snapshot=SnapshotResult(state={}, metadata={})
        )
        assert out["actions"] == ["unknown", "unknown"]
        assert out["agreement"] == 1.0


class TestFullBenchmarkChannel:
    def test_replay_decision_settles_against_full_benchmark(self, monkeypatch):
        captured: dict = {}
        _fake_orchestration(monkeypatch, captured)
        truncated_bench = _kline(["2025-01-13"], [3000.0])
        full_bench = _kline(["2025-01-13", "2025-01-20"], [3000.0, 3100.0])
        snap = SnapshotResult(
            state={
                "kline": _kline(["2025-01-13", "2025-01-14"], [10.0, 10.5]),
                "benchmark_kline": truncated_bench,
            },
            metadata={},
        )
        rp.replay_decision("600519", "2025-01-14", snapshot=snap, full_benchmark=full_bench)
        assert captured["benchmark"] is full_bench

    def test_replay_decision_defaults_to_state_benchmark(self, monkeypatch):
        captured: dict = {}
        _fake_orchestration(monkeypatch, captured)
        truncated_bench = _kline(["2025-01-13"], [3000.0])
        snap = SnapshotResult(
            state={
                "kline": _kline(["2025-01-13", "2025-01-14"], [10.0, 10.5]),
                "benchmark_kline": truncated_bench,
            },
            metadata={},
        )
        rp.replay_decision("600519", "2025-01-14", snapshot=snap)
        assert captured["benchmark"] is truncated_bench

    def test_replay_with_consistency_passes_full_benchmark_through(self, monkeypatch):
        received: list = []

        def fake_replay(
            code, decision_date, *, snapshot=None, client=None, full_kline=None, full_benchmark=None
        ):
            received.append(full_benchmark)
            return {"decision": {"action": "buy"}, "settlement": None}

        monkeypatch.setattr(rp, "replay_decision", fake_replay)
        full_bench = _kline(["2025-01-20"], [3100.0])
        rp.replay_with_consistency(
            "600519",
            "2025-01-14",
            n=3,
            snapshot=SnapshotResult(state={}, metadata={}),
            full_benchmark=full_bench,
        )
        assert received == [full_bench, full_bench, full_bench]


class TestFirstReplayPassthrough:
    """Task 10：replay_with_consistency 透传首轮回放的结算上下文（entry_price/action）。"""

    def test_consistency_surfaces_first_replay_entry_and_action(self, monkeypatch):
        settlement = {
            "status": "hit_target",
            "settle_date": "2025-01-20",
            "settle_price": 14.2,
            "hold_days": 4,
            "decision_return": 0.352,
            "benchmark_return": None,
            "decision_excess": None,
            "decision_hit": True,
        }

        def fake_replay(
            code, decision_date, *, snapshot=None, client=None, full_kline=None, full_benchmark=None
        ):
            return {
                "decision": {"action": "buy"},
                "settlement": settlement,
                "entry_price": 10.5,
                "action": "buy",
                "decision_date": decision_date,
                "snapshot_metadata": {},
            }

        monkeypatch.setattr(rp, "replay_decision", fake_replay)
        out = rp.replay_with_consistency(
            "600519", "2025-01-14", n=3, snapshot=SnapshotResult(state={}, metadata={})
        )
        assert out["entry_price"] == 10.5
        assert out["action"] == "buy"
        assert out["decision_date"] == "2025-01-14"
        assert out["settlement"] == settlement

    def test_consistency_passthrough_tolerates_missing_keys(self, monkeypatch):
        """回放失败路径（无 entry_price/action 键）→ 透传 None 而非崩溃。"""

        def fake_replay(
            code, decision_date, *, snapshot=None, client=None, full_kline=None, full_benchmark=None
        ):
            return {"decision": {}, "settlement": None}

        monkeypatch.setattr(rp, "replay_decision", fake_replay)
        out = rp.replay_with_consistency(
            "600519", "2025-01-14", n=1, snapshot=SnapshotResult(state={}, metadata={})
        )
        assert out["entry_price"] is None
        assert out["action"] is None
