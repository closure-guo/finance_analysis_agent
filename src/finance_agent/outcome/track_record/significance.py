"""结算显著性与信号一致性统计（add-prediction-pool-integrity；口径预登记 metrics.md §1.9-v2）。

纯函数模块：IC 月度序列 / ICIR / 敞口对齐蒙特卡洛零模型。输入方（API/结算报告）负责
只喂日主口径行（duplicate_of_day 永不进入）；本模块按 direction/status 二次防御过滤。
阈值与公式以 §1.9-v2 为准，禁止在调用方另写拷贝。
"""

from __future__ import annotations

import random

IC_MIN_SAMPLE = 10  # 单期可判定样本 < 10 → 该期「样本不足」，不进 ICIR
ICIR_MIN_PERIODS = 6  # 有效期数 < 6 → ICIR 不展示
MC_DEFAULT_N = 10_000  # 零模型抽样次数


def monthly_ic(rows: list[dict], kind: str = "direction") -> list[dict]:
    """按结算月（resolved_at[:7]）聚合月度读数（§1.9-v2）。

    kind="direction"（默认）：long/short 的 resolved_win/resolved_loss；
    kind="avoidance"：neutral 的 avoidance_win/avoidance_loss（回避类单独成列，
    SHALL NOT 混入方向 IC）。其余状态（resolved_neutral/unresolvable）与
    duplicate_of_day 行不进分子分母（防御性再过滤，输入方仍须只喂日主行）。
    返回按月升序：[{month, wins, losses, sample, ic, insufficient}]。
    """
    want_status = (
        ("resolved_win", "resolved_loss")
        if kind == "direction"
        else ("avoidance_win", "avoidance_loss")
    )
    want_dirs = ("long", "short") if kind == "direction" else ("neutral",)
    win_status, loss_status = want_status
    agg: dict[str, list[int]] = {}
    for r in rows:
        if r.get("direction") not in want_dirs:
            continue
        if r.get("status") not in want_status:
            continue
        month = str(r["resolved_at"])[:7]
        slot = agg.setdefault(month, [0, 0])
        slot[0 if r["status"] == win_status else 1] += 1
    out: list[dict] = []
    for month in sorted(agg):
        wins, losses = agg[month]
        sample = wins + losses
        out.append(
            {
                "month": month,
                "wins": wins,
                "losses": losses,
                "sample": sample,
                "ic": round(wins / sample, 4) if sample else None,
                "insufficient": sample < IC_MIN_SAMPLE,
            }
        )
    return out


def icir(ic_series: list[dict]) -> float | None:
    """mean(ic)/std(ic, population)；剔除 insufficient 期后期数 < ICIR_MIN_PERIODS → None。"""
    values: list[float] = [
        s["ic"] for s in ic_series if not s.get("insufficient") and s.get("ic") is not None
    ]
    if len(values) < ICIR_MIN_PERIODS:
        return None
    n = len(values)
    mu: float = sum(values) / n
    sd: float = (sum((v - mu) ** 2 for v in values) / n) ** 0.5
    if sd <= 0:
        return None
    return round(mu / sd, 4)


def simulate_random_excess(
    universe: list[str],
    long_counts: dict[str, int],
    short_counts: dict[str, int],
    closes: dict[str, dict[str, float]],
    entry_map: dict[str, str],
    exit_date: str,
    benchmark_return: float,
    n_sims: int = MC_DEFAULT_N,
    seed: int = 20261006,
) -> list[float]:
    """敞口对齐零模型：同 universe 随机替换选股，保持每归属日每方向注数一致（§1.9-v2）。

    closes: symbol → {date: close}（至少含各 entry 实际交易日与 exit_date 两档）；
    entry_map: 归属日 → 实际入场交易日（与真实组合 settle_entry_price 派生同源）。
    每次模拟：各归属日按注数无放回抽取（RNG 共享、种子注入、复现确定）；每注收益 =
    sign × (exit_close/entry_close − 1)；组合收益 = 全注等权均值；模拟超额 = 组合收益 −
    benchmark_return（与真实读数同基准同窗）。返回长度 n_sims 的模拟超额列表。
    """
    rng = random.Random(seed)  # noqa: S311  蒙特卡洛零模型非密码用途；种子注入保证复现
    plans: list[tuple[str, str, float]] = []
    for day, n in long_counts.items():
        plans += [(day, entry_map[day], 1.0)] * int(n)
    for day, n in short_counts.items():
        plans += [(day, entry_map[day], -1.0)] * int(n)
    if not plans:
        return []
    pool = [s for s in universe if s in closes]
    out: list[float] = []
    for _ in range(n_sims):
        picks = [
            rng.choice(pool) for _ in plans
        ]  # 有放回近似（池≥注数×10 时差异可忽略；§1.9-v2 简化口径）
        rets = []
        for (_day, entry, sign), sym in zip(plans, picks, strict=True):
            entry_close = closes[sym].get(entry)
            exit_close = closes[sym].get(exit_date)
            if not entry_close or not exit_close:
                continue  # 行情缺失注剔除（与真实读数的缺失处理一致）
            rets.append(sign * (exit_close / entry_close - 1.0))
        if not rets:
            continue
        out.append(sum(rets) / len(rets) - benchmark_return)
    return out


def excess_quantile(real_excess: float, sim_excess: list[float]) -> dict:
    """真实读数在零模型分布中的右尾定位；p 值含真实读数本身（保守）。

    quantile = 模拟中 ≤ 真实读数的比例；p_value = (严格大于真实读数的模拟数 + 1)
    / (n_sims + 1)——自身计入分母的保守 p（真实读数打败全部模拟时 p = 1/(n+1) 而非 0）。
    """
    if not sim_excess:
        return {"quantile": None, "p_value": None, "n_sims": 0}
    ranked = sorted(sim_excess)
    less_equal = sum(1 for v in ranked if v <= real_excess)
    greater = len(ranked) - less_equal
    quantile = less_equal / len(ranked)
    p_value = (greater + 1) / (len(ranked) + 1)
    return {
        "quantile": round(quantile, 4),
        "p_value": round(p_value, 4),
        "n_sims": len(ranked),
    }
