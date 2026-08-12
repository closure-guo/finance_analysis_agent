"""结算 job:结算+落库+上报、幂等、行情缺失跳过、data_stale、trace 不可查容错。"""

import logging
from unittest.mock import MagicMock

import pandas as pd

from finance_agent.outcome import store
from finance_agent.outcome.job import report_outcome_scores, settle_open_decisions
from finance_agent.outcome.settle import Settlement


def _open_decision(**overrides):
    base = {
        "decision_id": "d1",
        "session_id": "s1",
        "langfuse_trace_id": "trace-1",
        "timestamp": "2026-07-01T15:00:00",
        "ticker": "600519",
        "name": "茅台",
        "action": "buy",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "target_price": 120.0,
        "confidence": 0.8,
        "position_size": 0.3,
    }
    base.update(overrides)
    return base


def _kline_hit_target():
    return pd.DataFrame(
        [
            {"日期": "2026-07-02", "开盘": 101, "收盘": 110, "最高": 121, "最低": 100},
        ]
    )


def _bench():
    return pd.DataFrame(
        [
            {"日期": "2026-07-01", "开盘": 4000, "收盘": 4000, "最高": 4000, "最低": 4000},
            {"日期": "2026-07-02", "开盘": 4040, "收盘": 4040, "最高": 4040, "最低": 4040},
        ]
    )


class TestSettleJob:
    def test_settles_and_reports(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)

        client = MagicMock()
        client.fetch_kline.return_value = _kline_hit_target()
        client.fetch_index_kline.return_value = _bench()
        langfuse = MagicMock()

        result = settle_open_decisions(client=client, db_path=db, langfuse=langfuse)
        assert result["settled"] == 1
        assert result["scores_reported"] == 3
        assert store.get_open_decisions(db) == []
        # 3 个 score 按 trace_id 反向上报
        names = {c.kwargs["name"] for c in langfuse.create_score.call_args_list}
        assert names == {"decision_hit", "decision_return", "decision_excess"}
        for c in langfuse.create_score.call_args_list:
            assert c.kwargs["trace_id"] == "trace-1"

    def test_idempotent_no_double_settle(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.return_value = _kline_hit_target()
        client.fetch_index_kline.return_value = _bench()
        langfuse = MagicMock()

        first = settle_open_decisions(client=client, db_path=db, langfuse=langfuse)
        second = settle_open_decisions(client=client, db_path=db, langfuse=langfuse)
        assert first["settled"] == 1
        assert second["settled"] == 0  # 不重复结算/上报
        assert langfuse.create_score.call_count == 3

    def test_unsettled_stays_open(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.return_value = pd.DataFrame(
            [{"日期": "2026-07-02", "开盘": 100, "收盘": 101, "最高": 102, "最低": 99}]
        )
        client.fetch_index_kline.return_value = _bench()

        result = settle_open_decisions(client=client, db_path=db, langfuse=MagicMock())
        assert result["settled"] == 0
        assert len(store.get_open_decisions(db)) == 1

    def test_fetch_failure_skips_decision(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.side_effect = RuntimeError("network")

        result = settle_open_decisions(client=client, db_path=db, langfuse=MagicMock())
        assert result["settled"] == 0
        assert result["errors"] == 1
        assert len(store.get_open_decisions(db)) == 1  # 下次重试

    def test_data_stale_warned(self, tmp_path, caplog):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        # 决策日久远,K 线无新数据,但基准已到 07-30
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.return_value = pd.DataFrame(
            [{"日期": "2026-06-01", "开盘": 100, "收盘": 100, "最高": 100, "最低": 100}]
        )
        client.fetch_index_kline.return_value = pd.DataFrame(
            [
                {"日期": f"2026-07-{d:02d}", "开盘": 4000, "收盘": 4000, "最高": 4000, "最低": 4000}
                for d in range(1, 31)
            ]
        )

        with caplog.at_level(logging.WARNING):
            result = settle_open_decisions(client=client, db_path=db, langfuse=MagicMock())
        assert result["stale"] == 1
        assert any("data_stale" in r.message for r in caplog.records)


class TestReportScores:
    def _settlement(self):
        return Settlement(
            status="hit_target",
            settle_date="2026-07-02",
            settle_price=120.0,
            hold_days=1,
            decision_return=0.2,
            benchmark_return=0.01,
            decision_excess=0.19,
            decision_hit=True,
        )

    def test_three_scores_with_comment(self):
        langfuse = MagicMock()
        count = report_outcome_scores(langfuse, _open_decision(), self._settlement())
        assert count == 3
        by_name = {c.kwargs["name"]: c.kwargs for c in langfuse.create_score.call_args_list}
        assert by_name["decision_hit"]["data_type"] == "BOOLEAN"
        assert by_name["decision_hit"]["value"] == 1.0
        assert by_name["decision_return"]["value"] == 0.2
        assert by_name["decision_excess"]["value"] == 0.19
        assert "120" in by_name["decision_return"]["comment"]  # 结算价在 comment

    def test_trace_missing_warns_not_raises(self, caplog):
        langfuse = MagicMock()
        langfuse.create_score.side_effect = RuntimeError("trace not found")
        with caplog.at_level(logging.WARNING):
            count = report_outcome_scores(langfuse, _open_decision(), self._settlement())
        assert count == 0  # 不阻断,记 WARN

    def test_none_trace_id_skips(self):
        count = report_outcome_scores(
            MagicMock(), _open_decision(langfuse_trace_id=None), self._settlement()
        )
        assert count == 0

    def test_excess_none_skips_excess_score(self):
        settlement = self._settlement()
        settlement.decision_excess = None
        settlement.benchmark_return = None
        langfuse = MagicMock()
        count = report_outcome_scores(langfuse, _open_decision(), settlement)
        assert count == 2  # excess 为 None 不上报
