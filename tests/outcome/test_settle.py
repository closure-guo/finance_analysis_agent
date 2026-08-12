"""结算纯函数:止损/目标/同日/超期/方向符号化/一字板递延/停牌顺延/基准缺失。"""

import pandas as pd

from finance_agent.outcome.settle import evaluate_decision


def _kline(rows: list[dict]) -> pd.DataFrame:
    """rows: {日期, 开盘, 收盘, 最高, 最低}"""
    return pd.DataFrame(rows)


def _decision(**overrides):
    base = {
        "decision_id": "d1",
        "action": "buy",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "target_price": 120.0,
        "timestamp": "2026-07-01T15:00:00",
    }
    base.update(overrides)
    return base


def _day(date, open_, close, high=None, low=None):
    return {
        "日期": date,
        "开盘": open_,
        "收盘": close,
        "最高": high if high is not None else max(open_, close),
        "最低": low if low is not None else min(open_, close),
    }


class TestStopAndTarget:
    def test_hit_stop(self):
        kline = _kline([_day("2026-07-02", 99, 98), _day("2026-07-03", 95, 94, low=89)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_stop"
        assert result.settle_price == 90.0
        assert result.hold_days == 2
        assert result.decision_return == -0.1
        assert result.decision_hit is False

    def test_hit_target(self):
        kline = _kline([_day("2026-07-02", 101, 110, high=121)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_target"
        assert result.settle_price == 120.0
        assert result.decision_return == 0.2
        assert result.decision_hit is True

    def test_same_day_stop_priority(self):
        # 同日触及止损和目标 → 止损优先(保守)
        kline = _kline([_day("2026-07-02", 100, 100, high=125, low=85)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_stop"
        assert result.settle_price == 90.0


class TestExpired:
    def test_expired_at_max_hold_days(self):
        kline = _kline([_day(f"2026-07-{d:02d}", 100, 101) for d in range(2, 22)])  # 20 行
        result = evaluate_decision(_decision(), kline, None, max_hold_days=20)
        assert result.status == "expired"
        assert result.hold_days == 20
        assert result.settle_price == 101.0

    def test_not_enough_rows_returns_none(self):
        kline = _kline([_day("2026-07-02", 100, 101)])
        assert evaluate_decision(_decision(), kline, None, max_hold_days=20) is None


class TestDirection:
    def test_sell_direction_negated(self):
        # sell 后跌为正
        kline = _kline([_day("2026-07-02", 99, 95)])
        result = evaluate_decision(
            _decision(action="sell", stop_loss=None, target_price=None),
            kline,
            None,
            max_hold_days=1,
        )
        assert result.decision_return == 0.05
        assert result.decision_hit is True

    def test_hold_watch_same_as_sell(self):
        for action in ("hold", "watch"):
            kline = _kline([_day("2026-07-02", 99, 105)])
            result = evaluate_decision(
                _decision(action=action, stop_loss=None, target_price=None),
                kline,
                None,
                max_hold_days=1,
            )
            assert result.decision_return == -0.05


class TestOneWordBoard:
    def test_limit_down_board_defers_settlement(self):
        # 一字跌停(开=高=低=收)触及止损但未成交 → 递延至打开首日开盘价
        kline = _kline(
            [
                _day("2026-07-02", 95, 95),  # 普通日,未触及
                _day("2026-07-03", 88, 88, high=88, low=88),  # 一字跌停,触及止损但未成交
                _day("2026-07-04", 88, 88, high=88, low=88),  # 继续一字
                _day("2026-07-05", 85, 86),  # 打开,首个可成交价=开盘 85
            ]
        )
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_stop"
        assert result.settle_price == 85.0  # 实际可成交价,非 stop_loss 90
        assert result.hold_days == 4  # 含等待日
        assert abs(result.decision_return - (-0.15)) < 1e-9

    def test_board_unbroken_returns_none(self):
        # 一直一字板未打开 → 本批不结算
        kline = _kline(
            [
                _day("2026-07-02", 88, 88, high=88, low=88),
                _day("2026-07-03", 88, 88, high=88, low=88),
            ]
        )
        assert evaluate_decision(_decision(), kline, None) is None


class TestSuspension:
    def test_suspension_days_not_counted(self):
        # 停牌无 K 线行:hold_days 只数有数据的行,周期自然顺延
        kline = _kline(
            [
                _day("2026-07-02", 99, 98),
                # 07-03 ~ 07-10 停牌,无行
                _day("2026-07-11", 97, 110, high=121),  # 复牌首日,触及目标
            ]
        )
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_target"
        assert result.hold_days == 2  # 停牌日不计入


class TestBenchmark:
    def _bench(self):
        return _kline(
            [
                _day("2026-07-01", 4000, 4000),
                _day("2026-07-02", 4040, 4040),
            ]
        )

    def test_excess_computed(self):
        kline = _kline([_day("2026-07-02", 101, 110, high=121)])
        result = evaluate_decision(_decision(), kline, self._bench())
        assert result.benchmark_return == 0.01
        assert abs(result.decision_excess - (0.2 - 0.01)) < 1e-9

    def test_benchmark_missing_gives_none(self):
        kline = _kline([_day("2026-07-02", 101, 110, high=121)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.benchmark_return is None
        assert result.decision_excess is None
        assert result.decision_return == 0.2  # 自身收益仍记

    def test_benchmark_also_negated_for_sell(self):
        kline = _kline([_day("2026-07-02", 99, 95)])
        result = evaluate_decision(
            _decision(action="sell", stop_loss=None, target_price=None),
            kline,
            self._bench(),
            max_hold_days=1,
        )
        assert result.decision_return == 0.05
        assert result.benchmark_return == -0.01  # 基准也取负
        assert abs(result.decision_excess - 0.06) < 1e-9
