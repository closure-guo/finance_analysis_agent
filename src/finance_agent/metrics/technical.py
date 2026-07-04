"""技术指标计算 — MA / MACD / RSI / BOLL / KDJ。

输入为 AKShare 格式的 K 线 DataFrame（日期/开盘/收盘/最高/最低/成交量）。
输出为分组 dict，各指标值为与 K 线等长的 list（前 N 天为 None）。
"""

from __future__ import annotations

import pandas as pd


def calc_technical(kline: pd.DataFrame) -> dict[str, dict[str, list[float | None]]]:
    """计算全部技术指标。

    Parameters
    ----------
    kline : DataFrame
        AKShare K 线数据，需含 收盘 列。

    Returns
    -------
    dict
        {"MA": {"5": [...], "10": [...], ...}, ...}
    """
    close = kline["收盘"]
    result: dict[str, dict[str, list[float | None]]] = {}

    # ── MA（简单移动平均）──
    ma_result: dict[str, list[float | None]] = {}
    for period in (5, 10, 20, 60):
        if len(close) >= period:
            ma = close.rolling(window=period).mean()
            ma_result[str(period)] = [None if pd.isna(v) else float(v) for v in ma]
        else:
            ma_result[str(period)] = [None] * len(close)
    result["MA"] = ma_result

    # ── MACD（指数移动平均收敛发散）──
    # DIF = EMA12 - EMA26, DEA = EMA9(DIF), histogram = 2*(DIF-DEA)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = 2 * (dif - dea)
    result["MACD"] = {
        "DIF": [float(v) for v in dif],
        "DEA": [float(v) for v in dea],
        "histogram": [float(v) for v in hist],
    }

    # ── RSI（相对强弱指数，Wilder 平滑）──
    delta = close.diff().fillna(0)
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rsi = pd.Series(100.0, index=close.index)
    mask = avg_loss > 0
    rsi[mask] = 100 - 100 / (1 + avg_gain[mask] / avg_loss[mask])
    rsi_period = 14
    rsi_list: list[float | None] = [
        None if i < rsi_period else float(rsi.iloc[i]) for i in range(len(close))
    ]
    result["RSI"] = {"14": rsi_list}

    # ── BOLL（布林带，20 日 ±2σ）──
    boll_period = 20
    ma20 = close.rolling(window=boll_period).mean()
    std20 = close.rolling(window=boll_period).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20
    result["BOLL"] = {
        "upper": [None if pd.isna(v) else float(v) for v in upper],
        "middle": [None if pd.isna(v) else float(v) for v in ma20],
        "lower": [None if pd.isna(v) else float(v) for v in lower],
    }

    # ── KDJ（随机指标，9 日）──
    kdj_period = 9
    low_9 = kline["最低"].rolling(window=kdj_period).min()
    high_9 = kline["最高"].rolling(window=kdj_period).max()
    denom = high_9 - low_9
    rsv = ((close - low_9) / denom.replace(0, float("nan")) * 100).fillna(50)
    # K/D 初始值 50，ewm(alpha=1/3) ≈ 2/3 前值 + 1/3 当前
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    j = 3 * k - 2 * d
    kdj_first = kdj_period - 1  # 前 8 天无值
    result["KDJ"] = {
        "K": [None if i < kdj_first else float(k.iloc[i]) for i in range(len(close))],
        "D": [None if i < kdj_first else float(d.iloc[i]) for i in range(len(close))],
        "J": [None if i < kdj_first else float(j.iloc[i]) for i in range(len(close))],
    }

    return result
