"""规则基线：Buy-and-Hold / MACD / KDJ / RSI（复用 metrics/technical.py，不另造指标）。

仓位为 0/1 逐日序列（1=持仓）；RSI 为反转策略（<30 买入、>70 平仓，其余维持），
MACD/KDJ 为趋势策略（快线在慢线上方持仓）。所有信号 T-1 收盘生成、T 生效
（见 strategy_returns，无前视）。
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from finance_agent.metrics.technical import calc_technical

Strategy = Literal["buy_hold", "macd", "kdj", "rsi"]


def baseline_positions(kline: pd.DataFrame, strategy: Strategy) -> pd.Series:
    """返回逐日仓位（1=持仓, 0=空仓），长度与 kline 相同。"""
    if strategy == "buy_hold":
        return pd.Series(1, index=kline.index)
    tech = calc_technical(kline)
    if strategy == "macd":
        dif = pd.Series(tech["MACD"]["DIF"], dtype=float)
        dea = pd.Series(tech["MACD"]["DEA"], dtype=float)
        raw = (dif > dea).astype(float)
    elif strategy == "kdj":
        k = pd.Series(tech["KDJ"]["K"], dtype=float)
        d = pd.Series(tech["KDJ"]["D"], dtype=float)
        raw = (k > d).astype(float)
    elif strategy == "rsi":
        # metrics/technical.py 仅提供 RSI 14（Wilder 平滑），无 6 日快线
        rsi = pd.Series(tech["RSI"]["14"], dtype=float)
        position = 0.0
        values: list[float] = []
        for v in rsi:
            if pd.notna(v):
                if v < 30:
                    position = 1.0
                elif v > 70:
                    position = 0.0
            values.append(position)
        raw = pd.Series(values, dtype=float)
    else:
        raise ValueError(f"未知基线策略: {strategy}")
    positions = raw.fillna(0.0)
    return positions.reset_index(drop=True)


def strategy_returns(kline: pd.DataFrame, positions: pd.Series) -> list[float]:
    """日收益 = 前一日仓位 × 当日涨跌（T-1 信号 T 生效，无前视）。

    返回长度 len(kline)-1（首日无前仓收益）。
    """
    close = kline["收盘"].astype(float).reset_index(drop=True)
    pct = close.pct_change().fillna(0.0)
    prev_pos = positions.reset_index(drop=True).shift(1).fillna(0.0)
    return list((prev_pos * pct)[1:])
