"""PE/PB 相对估值 — 目标公司 vs 同业均值比较。

结论判定：
- target < avg * 0.85 → undervalued（低估）
- target 在 avg±15% 内 → fair（合理）
- target > avg * 1.15 → overvalued（高估）
"""

from __future__ import annotations

from statistics import mean


def calc_relative_valuation(
    target: dict[str, float | None],
    peers: list[dict],
) -> dict[str, dict]:
    """计算 PE/PB 相对估值。

    Parameters
    ----------
    target : dict
        {"PE": float|None, "PB": float|None}
    peers : list[dict]
        [{"name": str, "PE": float, "PB": float}, ...]

    Returns
    -------
    dict
        {"PE": {target, peer_avg, peer_min, peer_max, conclusion}, "PB": ...}
    """
    result = {}
    for metric in ["PE", "PB"]:
        target_val = target.get(metric)

        peer_values = [p[metric] for p in peers if p.get(metric) is not None]

        if not peer_values or target_val is None:
            result[metric] = {
                "target": target_val,
                "peer_avg": None,
                "peer_min": None,
                "peer_max": None,
                "conclusion": "N/A",
            }
            continue

        avg = mean(peer_values)
        lo = avg * 0.85
        hi = avg * 1.15

        if target_val < lo:
            conclusion = "undervalued"
        elif target_val > hi:
            conclusion = "overvalued"
        else:
            conclusion = "fair"

        result[metric] = {
            "target": target_val,
            "peer_avg": round(avg, 2),
            "peer_min": min(peer_values),
            "peer_max": max(peer_values),
            "conclusion": conclusion,
        }

    return result
