"""toolize-price-levels Task 2.1：交易价位 sanity 校验 节点/路由/修正 测试（TDD 先行）。"""

import pytest

from finance_agent.models import TradeDecision
from finance_agent.nodes.validate import correct_prices, validate_trade_prices
from finance_agent.routing import after_validate_trade_prices


def _levels(base=100.0, atr=2.0):
    return {
        "available": True,
        "entry_ref": base,
        "atr": atr,
        "recent_high": base + 5,
        "recent_low": base - 5,
        "stop_band_long": {"low": base - 2 * atr, "high": base - atr},
        "target_band_long": {"low": base + 2 * atr, "high": base + 4 * atr},
        "full_band": [base - 5 - 2 * atr, base + 5 + 2 * atr],
    }


def _state(plan, levels=None, close=100.0, attempts=0):
    kline = pd.DataFrame({"日期": ["2026-06-02"], "收盘": [close]})
    return {
        "trader_plan": plan if isinstance(plan, dict) else plan.model_dump(),
        "price_levels": levels if levels is not None else _levels(),
        "kline": kline,
        "price_check_attempts": attempts,
    }


def _plan(action="buy", entry=100.0, stop=95.0, target=108.0):
    return TradeDecision(
        action=action,
        confidence=0.8,
        reasoning="r",
        entry_price=entry,
        stop_loss=stop,
        target_price=target,
    )


import pandas as pd  # noqa: E402


class TestValidateTradePrices:
    def test_valid_long_passes(self):
        out = validate_trade_prices(_state(_plan()))
        assert out["price_check"]["result"] == "pass"

    def test_relation_violation_fails(self):
        # long：stop > entry → 价格关系违规
        out = validate_trade_prices(_state(_plan(entry=100.0, stop=105.0, target=110.0)))
        assert out["price_check"]["result"] == "fail"
        assert out["price_check_attempts"] == 1
        assert "price_check_feedback" in out

    def test_entry_deviation_fails(self):
        # entry 距现价偏差 50% > 15%
        out = validate_trade_prices(_state(_plan(entry=150.0, stop=140.0, target=160.0)))
        assert out["price_check"]["result"] == "fail"

    def test_band_violation_fails(self):
        # target 220 超出放宽带 [93-4, 105+4] = [89, 109] 附近
        out = validate_trade_prices(_state(_plan(entry=100.0, stop=95.0, target=220.0)))
        assert out["price_check"]["result"] == "fail"

    def test_short_symmetry(self):
        # short：stop > entry > target 合法
        out = validate_trade_prices(
            _state(_plan(action="sell", entry=100.0, stop=106.0, target=92.0))
        )
        assert out["price_check"]["result"] == "pass"
        # short 关系倒置 → fail
        out2 = validate_trade_prices(
            _state(_plan(action="sell", entry=100.0, stop=92.0, target=106.0))
        )
        assert out2["price_check"]["result"] == "fail"

    def test_hold_watch_passes(self):
        plan = TradeDecision(action="hold", confidence=0.5, reasoning="r")
        out = validate_trade_prices(_state(plan))
        assert out["price_check"]["result"] == "pass"

    def test_levels_unavailable_skips(self):
        levels = {"available": False, "reason": "insufficient_kline"}
        out = validate_trade_prices(_state(_plan(), levels=levels))
        assert out["price_check"]["result"] == "pass"
        assert out["price_check"].get("note")  # 如实标注跳过原因

    def test_second_fail_corrects(self):
        out = validate_trade_prices(
            _state(_plan(entry=150.0, stop=140.0, target=160.0), attempts=1)
        )
        assert out["price_check"]["result"] == "corrected"
        corrected = out["trader_plan"]
        assert corrected["price_level_corrected"] is True
        assert corrected["price_level_correction_reason"]
        # 修正后满足价格关系（long：stop < entry < target）
        assert corrected["stop_loss"] < corrected["entry_price"] < corrected["target_price"]


class TestCorrectPrices:
    def test_long_correction_from_bands(self):
        corrected = correct_prices(
            _plan(entry=150.0, stop=140.0, target=160.0).model_dump(), _levels(), "buy"
        )
        assert corrected["entry_price"] == pytest.approx(100.0)  # entry_ref
        assert corrected["stop_loss"] == pytest.approx(
            (96.0 + 98.0) / 2
        )  # stop_band 中值（atr=2 → [96,98]）
        assert corrected["target_price"] == pytest.approx((104.0 + 108.0) / 2)  # target_band 中值
        assert corrected["price_level_corrected"] is True

    def test_short_correction_mirrored(self):
        corrected = correct_prices(
            _plan(action="sell", entry=50.0, stop=45.0, target=60.0).model_dump(), _levels(), "sell"
        )
        assert corrected["stop_loss"] > corrected["entry_price"] > corrected["target_price"]


class TestRouting:
    def test_pass_goes_forward(self):
        state = {"price_check": {"result": "pass"}}
        assert after_validate_trade_prices(state) == "risk_r1_entry"

    def test_corrected_goes_forward(self):
        state = {"price_check": {"result": "corrected"}}
        assert after_validate_trade_prices(state) == "risk_r1_entry"

    def test_fail_goes_back_to_trader(self):
        state = {"price_check": {"result": "fail"}}
        assert after_validate_trade_prices(state) == "trader"


class TestTraderContextInjection:
    def test_price_levels_in_context(self):
        from finance_agent.nodes.trader import _build_trader_context

        state = {
            "analyst_reports": {},
            "price_levels": {"available": True, "entry_ref": 100.0, "atr": 2.0},
        }
        ctx = _build_trader_context(state)
        assert "价位参考" in ctx
        assert "entry_ref" in ctx

    def test_retry_feedback_in_context(self):
        from finance_agent.nodes.trader import _build_trader_context

        state = {
            "analyst_reports": {},
            "price_check_feedback": "entry 距现价偏差超限",
        }
        ctx = _build_trader_context(state)
        assert "价位校验打回意见" in ctx
        assert "entry 距现价偏差超限" in ctx
