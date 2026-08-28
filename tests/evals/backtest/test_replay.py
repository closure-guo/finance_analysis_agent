"""回放与决策一致性测试：mock 编排图，不调 LLM。"""

from evals.backtest.replay import build_decision_record, direction_agreement


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
