"""结算报告（issue #250）：§1.9-v2 预登记口径的消费端。

IC/ICIR 与蒙特卡洛零模型的真读数在此拼装为对外结算报告：
collect（读库取结算日主行）→ build_report_data（纯函数组装读数，红线先判）
→ render_marketing_report（markdown 渲染）。本模块只读，不写库。

红线（§1.9-v2）：可判定日主样本 < 10 → 零模型 SHALL NOT 产出（首批 T+20 结算
样本可能 <10，这是最常见路径而非异常，报告必须优雅降级）；「跑赢/跑输」类结论
必须附分位读数，单独出现的点估计 = 口径违规。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finance_agent.outcome.track_record.judgment import derive_attribution_date
from finance_agent.outcome.track_record.model import list_predictions
from finance_agent.outcome.track_record.significance import (
    MC_DEFAULT_N,
    excess_quantile,
    icir,
    monthly_ic,
    simulate_random_excess,
)

SETTLED_MC_MIN_SAMPLE = 10  # §1.9-v2：可判定日主样本 < 10 → 零模型 SHALL NOT 产出


def collect_settled_day_masters(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """读取已结算日主行（§1.9-v2 样本口径）。

    list_predictions 全量读取（上限 100_000，见 model.list_predictions P1 注记）
    后防御性过滤：resolution_rule 为空（未结算 open 行）或 'duplicate_of_day'
    （同日重复关闭行）不进报告——结算行本应只含日主，防御照做。返回行不做状态级
    过滤（unresolvable/avoidance 等由下游按读数可用性处理）。
    """
    rows = list_predictions(limit=100_000, db_path=db_path)
    return [r for r in rows if r.get("resolution_rule") not in (None, "", "duplicate_of_day")]


def build_report_data(
    settled: list[dict[str, Any]],
    universe_by_day: dict[str, list[str]],
    closes: dict[str, dict[str, float]],
    benchmark_closes: dict[str, float],
    exit_date: str,
    n_sims: int = MC_DEFAULT_N,
    seed: int = 20261006,
) -> dict[str, Any]:
    """组装结算报告读数（纯函数；口径 §1.9-v2，顶层 caliber 引用预登记版本）。

    settled: collect_settled_day_masters 的输出（已结算日主行）；
    universe_by_day/closes/benchmark_closes/exit_date: 零模型行情面板（语义见
    simulate_random_excess）；n_sims/seed: 零模型抽样次数与种子（预登记默认
    10_000 / 20261006）。

    IC/ICIR：方向 IC（long/short 的 resolved_win/loss）与回避序列（neutral）
    分别成列；icir 剔除样本不足期后期数 <6 → None。
    蒙特卡洛（红线先判）：可判定日主样本 = settled 中 long/short 且 excess_return
    非空的行数（unresolvable 等无读数行不是「可判定」样本）——< 10 → 零模型段
    available=False + reason（引用 §1.9-v2 与样本数），不产出任何零模型读数。
    ≥ 10 执行：真实读数 = 可判定行 excess_return 等权均值（与零模型的「平均槽位
    超额」同构可比——两侧都是逐槽 T+20 超额均值）；posture = 可判定行按归属日
    （derive_attribution_date(created_at, calendar)，calendar 取基准交易日升序
    列表 = sorted(benchmark_closes)）分组计数；零模型 entry_map = {归属日: 归属日}
    （归属日已按日历吸附为交易日，与 settle_entry_price 派生同源）。

    返回 dict：caliber / ic_series / avoidance_series / icir / sample / monte_carlo
    （available=True 时含 real_excess / quantile / p_value / n_sims / seed /
    months_covered）。
    """
    calendar = sorted(benchmark_closes)
    ic_series = monthly_ic(settled, kind="direction")
    avoidance_series = monthly_ic(settled, kind="avoidance")
    slots = [
        r
        for r in settled
        if r.get("direction") in ("long", "short") and r.get("excess_return") is not None
    ]
    sample = len(slots)
    data: dict[str, Any] = {
        "caliber": "§1.9-v2",
        "ic_series": ic_series,
        "avoidance_series": avoidance_series,
        "icir": icir(ic_series),
        "sample": sample,
    }
    if sample < SETTLED_MC_MIN_SAMPLE:
        data["monte_carlo"] = {
            "available": False,
            "reason": (f"可判定日主样本 {sample}<10（§1.9-v2 settled<10 红线），不产出零模型读数"),
        }
        return data
    real_excess = sum(float(r["excess_return"]) for r in slots) / sample
    long_counts: dict[str, int] = {}
    short_counts: dict[str, int] = {}
    for r in slots:
        day = derive_attribution_date(str(r["created_at"]), calendar)
        counts = long_counts if r["direction"] == "long" else short_counts
        counts[day] = counts.get(day, 0) + 1
    sims = simulate_random_excess(
        universe_by_day,
        long_counts,
        short_counts,
        closes,
        {day: day for day in long_counts | short_counts},
        exit_date,
        benchmark_closes,
        n_sims=n_sims,
        seed=seed,
    )
    q = excess_quantile(real_excess, sims)
    data["monte_carlo"] = {
        "available": True,
        "real_excess": round(real_excess, 6),
        "quantile": q["quantile"],
        "p_value": q["p_value"],
        "n_sims": q["n_sims"],
        "seed": seed,
        "months_covered": len({str(r["resolved_at"])[:7] for r in slots}),
    }
    return data
