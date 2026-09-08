"""价位预算计算（toolize-price-levels）：近期高低点 / ATR / 止损与目标参考带。

由 K 线确定性计算（LLM 只解读引用，不做数值计算）：
- entry_ref：最新收盘（参考入场基准）
- recent_high/low：近 window 日最高/最低
- atr：ATR(atr_period)（TrueRange 均值）
- stop_band_long：[close-2*ATR, close-1*ATR]（long 止损参考带）
- target_band_long：[close+2*ATR, close+4*ATR]（long 目标参考带）
- full_band：[recent_low-2*ATR, recent_high+2*ATR]（sanity 放宽带）

数据不足（行数 < atr_period+1）时返回 available=False + reason，字段不伪造。
short 方向由校验节点按对称规则镜像，本模块只产 long 语义基准。
"""

from __future__ import annotations

import pandas as pd

_ATR_PERIOD = 14
_WINDOW = 60


def calc_price_levels(
    kline: pd.DataFrame | None,
    window: int = _WINDOW,
    atr_period: int = _ATR_PERIOD,
) -> dict:
    """计算价位参考。kline 需含 日期/开盘/收盘/最高/最低 列（AKShare 格式）。"""
    if kline is None or len(kline) < atr_period + 1:
        return {"available": False, "reason": "insufficient_kline"}

    close_series = kline["收盘"].astype(float)
    high = kline["最高"].astype(float)
    low = kline["最低"].astype(float)
    close = float(close_series.iloc[-1])

    # ── ATR(atr_period)：TrueRange 均值（首行 TR=high-low）──
    prev_close = close_series.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr = tr.fillna(high - low)
    atr = float(tr.tail(atr_period).mean())

    recent = kline.tail(window)
    recent_high = float(recent["最高"].max())
    recent_low = float(recent["最低"].min())

    def _round(v: float) -> float:
        return round(v, 4)

    return {
        "available": True,
        "entry_ref": _round(close),
        "recent_high": _round(recent_high),
        "recent_low": _round(recent_low),
        "atr": _round(atr),
        "stop_band_long": {"low": _round(close - 2 * atr), "high": _round(close - atr)},
        "target_band_long": {"low": _round(close + 2 * atr), "high": _round(close + 4 * atr)},
        # sanity 放宽带：价位落带外即显著偏离近期交易区间
        "full_band": [_round(recent_low - 2 * atr), _round(recent_high + 2 * atr)],
    }
