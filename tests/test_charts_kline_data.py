"""update-price-chart-kline：K 线图表数据采集契约。

collect_chart_data 的 price 输出自本变更起携带逐日 OHLCV、MA5/20/60
均线（收盘价简单移动平均，窗口前段 None）与交易决策价位（缺失形态
降级不携带）。契约锚定 delta specs/report-kline-chart「K 线图表数据采集」。
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from finance_agent.charts import collect_chart_data


def _synth_kline(n: int, base: float = 10.0) -> pd.DataFrame:
    """构造 akshare_client 归一化中文列名的日 K 线。"""
    rows = []
    for i in range(n):
        close = base + i * 0.1
        rows.append(
            {
                "日期": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                "开盘": close - 0.05,
                "最高": close + 0.2,
                "最低": close - 0.2,
                "收盘": close,
                "成交量": 1000.0 + i,
            }
        )
    return pd.DataFrame(rows)


def _state_with_kline(n: int = 65) -> dict:
    return {"stock_code": "600519", "kline": _synth_kline(n)}


def test_daily_carry_ohlcv():
    chart = collect_chart_data(_state_with_kline())
    first = chart["price"]["daily"][0]
    assert first["open"] is not None
    assert first["high"] is not None
    assert first["low"] is not None
    assert first["volume"] is not None


def test_ohlcv_invariants():
    """OHLC 不变式：high≥max(open,close)、low≤min(open,close)（#240 列位教训守卫）。"""
    chart = collect_chart_data(_state_with_kline(30))
    for d in chart["price"]["daily"]:
        assert d["high"] >= max(d["open"], d["close"])
        assert d["low"] <= min(d["open"], d["close"])


def test_ma_series_aligned_with_warmup_nulls():
    chart = collect_chart_data(_state_with_kline(65))
    ma = chart["price"]["ma"]
    daily = chart["price"]["daily"]
    assert set(ma.keys()) == {"ma5", "ma20", "ma60"}
    assert len(ma["ma5"]) == len(daily) == 65
    assert ma["ma5"][4] == pytest.approx(sum(d["close"] for d in daily[:5]) / 5)
    assert ma["ma60"][58] is None
    assert ma["ma60"][59] == pytest.approx(sum(d["close"] for d in daily[:60]) / 60)


def test_decision_levels_from_dict_decision():
    state = _state_with_kline(20)
    state["final_trade_decision"] = {
        "action": "buy",
        "entry_price": 10.5,
        "stop_loss": 9.8,
        "target_price": 12.0,
    }
    chart = collect_chart_data(state)
    assert chart["price"]["decision_levels"] == {
        "entry_price": 10.5,
        "stop_loss": 9.8,
        "target_price": 12.0,
    }


def test_decision_levels_from_attr_decision():
    """dataclass/属性形态（TradeDecision 路径），半缺价位只携带在场字段。"""
    state = _state_with_kline(20)
    state["final_trade_decision"] = SimpleNamespace(
        action="buy", entry_price=10.5, stop_loss=None, target_price=12.0
    )
    chart = collect_chart_data(state)
    assert chart["price"]["decision_levels"] == {"entry_price": 10.5, "target_price": 12.0}


def test_decision_levels_fallback_to_trader_plan():
    """无最终决策时回退交易员方案（与 report 章节渲染同源优先级）。"""
    state = _state_with_kline(20)
    state["trader_plan"] = {"entry_price": 10.5}
    chart = collect_chart_data(state)
    assert chart["price"]["decision_levels"] == {"entry_price": 10.5}


def test_decision_levels_absent_when_no_prices():
    """neutral/hold 无价位、字段全缺 → 不携带 decision_levels 键。"""
    state = _state_with_kline(20)
    state["final_trade_decision"] = {"action": "neutral", "confidence": 0.4}
    chart = collect_chart_data(state)
    assert "decision_levels" not in chart["price"]


def test_no_kline_degrades_silently():
    chart = collect_chart_data({"stock_code": "600519"})
    assert chart["price"]["daily"] == []
    assert chart["price"]["ma"] == {"ma5": [], "ma20": [], "ma60": []}
    assert "decision_levels" not in chart["price"]
