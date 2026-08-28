"""绩效四指标：CR / ARR / Sharpe / MDD（TradingAgents 指标选型）。rf=0、252 交易日。

Sharpe 复用 evals.stats.sharpe（单一口径，不另造定义）；常数序列 std=0 → 安全 0.0。
数值不取整：测试以 1e-9 容差断言，报告侧如需展示精度自行格式化。
"""

from __future__ import annotations

from collections.abc import Sequence

from evals.stats import sharpe as _sharpe


def perf_metrics(daily_returns: Sequence[float]) -> dict[str, float]:
    """日收益序列 → {"CR", "ARR", "Sharpe", "MDD"}。

    CR = 期末财富 - 1；ARR = 财富^(252/n) - 1（财富归零记 -1）；
    MDD = 峰值到谷值的最大回撤比例；空序列全零。
    """
    if not daily_returns:
        return {"CR": 0.0, "ARR": 0.0, "Sharpe": 0.0, "MDD": 0.0}
    wealth = 1.0
    peak = 1.0
    mdd = 0.0
    for r in daily_returns:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        mdd = max(mdd, (peak - wealth) / peak)
    cr = wealth - 1.0
    n = len(daily_returns)
    arr = wealth ** (252 / n) - 1 if wealth > 0 else -1.0
    return {
        "CR": float(cr),
        "ARR": float(arr),
        "Sharpe": float(_sharpe(daily_returns)),
        "MDD": float(mdd),
    }
