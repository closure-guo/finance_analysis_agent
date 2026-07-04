"""风控指标计算 — 最大回撤 / 波动率 / Beta / VaR。

输入为 K 线 DataFrame，可选基准 K 线（沪深 300）用于 Beta 计算。
输出为标量 dict，各指标汇总整个周期。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_risk(
    kline: pd.DataFrame,
    benchmark_kline: pd.DataFrame | None = None,
) -> dict[str, float]:
    """计算风控指标。

    Parameters
    ----------
    kline : DataFrame
        个股 K 线数据，需含 收盘 列。
    benchmark_kline : DataFrame, optional
        基准 K 线（沪深 300），需含 收盘 列。用于 Beta 计算。

    Returns
    -------
    dict
        {"max_drawdown": float, "volatility": float, "var_95": float, ["beta": float]}
    """
    close = kline["收盘"]

    # ── 最大回撤 ──
    cummax = close.cummax()
    drawdown = (close - cummax) / cummax
    max_drawdown = float(abs(drawdown.min())) if not drawdown.empty else 0.0

    # ── 日收益率 ──
    returns = close.pct_change().dropna()

    # ── 年化波动率 ──
    volatility = float(returns.std() * np.sqrt(252)) if len(returns) > 1 else 0.0

    # ── VaR(95%) — 历史模拟法 ──
    var_95 = float(abs(np.percentile(returns, 5))) if len(returns) > 0 else 0.0

    result: dict[str, float] = {
        "max_drawdown": max_drawdown,
        "volatility": volatility,
        "var_95": var_95,
    }

    # ── Beta（需要基准数据）──
    if benchmark_kline is not None:
        bench_returns = benchmark_kline["收盘"].pct_change().dropna()
        min_len = min(len(returns), len(bench_returns))
        if min_len > 1:
            stock_r = returns.iloc[-min_len:]
            bench_r = bench_returns.iloc[-min_len:]
            cov_matrix = np.cov(stock_r, bench_r)
            cov_sb = float(cov_matrix[0, 1])
            var_b = float(np.var(bench_r, ddof=1))
            result["beta"] = cov_sb / var_b if var_b != 0 else 1.0

    return result
