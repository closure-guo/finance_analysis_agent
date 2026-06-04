"""双重阈值红黄绿灯矩阵 + 四维度健康度评分。

评判规则（ADR-0003）：
- 绝对值水平：各指标硬编码阈值
- 同比变化率：<20%🟢 / 20-50%🟡 / >50%🔴
- 最终灯色 = max(绝对值灯, 变化率灯)

评分：四维度各 25 分，🟢=满分 🟡=半分 🔴=零分
85-100=healthy | 60-84=caution | <60=warning
"""

from __future__ import annotations

# ── 绝对值阈值表 ──
# 格式: (green_threshold, yellow_threshold, higher_is_better)
# higher_is_better=True: 值>=green → 🟢, 值<yellow → 🔴
# higher_is_better=False: 值<=green → 🟢, 值>yellow → 🔴

# 格式: (green_threshold, yellow_threshold, higher_is_better)
# higher_is_better=True: 值>=green → 🟢, 值<yellow → 🔴
# higher_is_better=False: 值<=green → 🟢, 值>yellow → 🔴

ABSOLUTE_THRESHOLDS: dict[str, tuple] = {
    # 偿债
    "资产负债率": (40, 65, False),
    "流动比率": (2.0, 1.0, True),
    "速动比率": (1.5, 0.8, True),
    "利息覆盖倍数": (6, 2, True),
    "净债务/EBITDA": (0, 2, False),
    # 盈利
    "毛利率": (30, 15, True),
    "净利率": (15, 5, True),
    "ROE": (15, 8, True),
    "ROA": (10, 3, True),
    "ROIC": (12, 6, True),
    # 运营（通用阈值，行业覆盖见下方）
    "存货周转率": (5, 2, True),
    "应收账款周转率": (8, 3, True),
    "总资产周转率": (0.8, 0.3, True),
    "应付账款周转率": (6, 3, True),
    # 现金流
    "经营现金流/净利润": (1.0, 0.5, True),
    "FCF": (0, None, True),
    "资本支出/折旧": (3, 1, True),
    "现金流覆盖比率": (1.0, 0.5, True),
    "FCF收益率": (0.05, 0.02, True),
    "留存现金流比率": (0.5, 0.2, True),
}

# ── 行业阈值覆盖 ──
# key 为行业名称子串（模糊匹配），值为 {指标名: 阈值三元组}
INDUSTRY_OVERRIDES: dict[str, dict[str, tuple]] = {
    "白酒": {
        "存货周转率": (0.5, 0.2, True),  # 基酒需 3-5 年陈酿，周转率天然低
    },
    "酿酒": {
        "存货周转率": (0.5, 0.2, True),
    },
}

LIGHT_ORDER = {"green": 0, "yellow": 1, "red": 2}

SAFETY_FLOOR_MULTIPLIER = 10


def assess_change_rate(change_rate: float) -> str:
    """评判同比变化率灯色。取绝对值：<20%🟢 / 20-50%🟡 / >50%🔴。"""
    abs_rate = abs(change_rate)
    if abs_rate < 0.20:
        return "green"
    elif abs_rate <= 0.50:
        return "yellow"
    else:
        return "red"


def _get_thresholds(metric_name: str, industry: str | None) -> tuple | None:
    """获取指标阈值，优先使用行业覆盖。"""
    if not industry:
        return ABSOLUTE_THRESHOLDS.get(metric_name)
    for key, overrides in INDUSTRY_OVERRIDES.items():
        if key in industry and metric_name in overrides:
            return overrides[metric_name]
    return ABSOLUTE_THRESHOLDS.get(metric_name)


def _assess_absolute(metric_name: str, value: float, industry: str | None = None) -> str | None:
    """评判绝对值灯色。"""
    thresholds = _get_thresholds(metric_name, industry)
    if thresholds is None:
        return None

    green_thresh, yellow_thresh, higher_is_better = thresholds

    if metric_name == "FCF":
        return "green" if value > 0 else ("yellow" if value == 0 else "red")

    if higher_is_better:
        if value >= green_thresh:
            return "green"
        elif value >= yellow_thresh:
            return "yellow"
        else:
            return "red"
    else:
        if value <= green_thresh:
            return "green"
        elif value <= yellow_thresh:
            return "yellow"
        else:
            return "red"


def _compute_change_rate(current: float, previous: float) -> float | None:
    """计算同比变化率。"""
    if previous == 0:
        return None
    return (current - previous) / abs(previous)


def _max_light(a: str | None, b: str | None) -> str | None:
    """取两个灯色中更差的那个。"""
    if a is None:
        return b
    if b is None:
        return a
    return a if LIGHT_ORDER[a] >= LIGHT_ORDER[b] else b


def _apply_safety_floor(
    metric_name: str,
    value: float,
    abs_light: str | None,
    change_light: str | None,
    industry: str | None = None,
) -> str | None:
    """绝对值远超优良阈值时，将变化率灯色上限降为绿色。"""
    if abs_light != "green" or change_light == "green":
        return change_light

    thresholds = _get_thresholds(metric_name, industry)
    if thresholds is None:
        return change_light

    green_thresh, _, higher_is_better = thresholds

    if green_thresh == 0:
        return change_light

    if higher_is_better:
        if value >= green_thresh * SAFETY_FLOOR_MULTIPLIER:
            return "green"
    else:
        if value <= green_thresh / SAFETY_FLOOR_MULTIPLIER:
            return "green"

    return change_light


def assess_traffic_lights(
    metrics: dict[str, dict[str, dict[str, float | None]]],
    industry: str | None = None,
) -> dict[str, dict[str, dict[str, dict]]]:
    """对全部指标做双重阈值评判。

    Parameters
    ----------
    metrics : dict
        {dimension: {metric_name: {year: value}}}
        dimension: solvency, profitability, efficiency, cashflow
    industry : str | None
        行业名称，用于加载行业特定阈值覆盖。

    Returns
    -------
    dict
        {dimension: {metric_name: {year: {absolute, change, final}}}}
    """
    result: dict[str, dict[str, dict[str, dict]]] = {}
    all_years: set[str] = set()

    # 收集所有年份
    for dim_metrics in metrics.values():
        for metric_values in dim_metrics.values():
            all_years.update(metric_values.keys())
    sorted_years = sorted(all_years, reverse=True)

    for dim_name, dim_metrics in metrics.items():
        result[dim_name] = {}
        for metric_name, year_values in dim_metrics.items():
            if metric_name.endswith("_source"):
                continue
            result[dim_name][metric_name] = {}

            for idx, year in enumerate(sorted_years):
                val = year_values.get(year)
                if val is None:
                    result[dim_name][metric_name][year] = {
                        "absolute": None,
                        "change": None,
                        "final": None,
                    }
                    continue

                abs_light = _assess_absolute(metric_name, val, industry)

                # 变化率：与上一年比较
                prev_year_idx = idx + 1  # sorted_years 是最新在前
                if prev_year_idx < len(sorted_years):
                    prev_year = sorted_years[prev_year_idx]
                    prev_val = year_values.get(prev_year)
                    if prev_val is not None and prev_val != 0:
                        change_rate = _compute_change_rate(val, prev_val)
                        change_light = (
                            assess_change_rate(change_rate) if change_rate is not None else None
                        )
                    else:
                        change_light = None
                else:
                    change_light = None

                change_light = _apply_safety_floor(
                    metric_name, val, abs_light, change_light, industry
                )

                final_light = _max_light(abs_light, change_light)

                result[dim_name][metric_name][year] = {
                    "absolute": abs_light,
                    "change": change_light,
                    "final": final_light,
                }

    return result


def compute_health_score(
    traffic_lights: dict[str, dict[str, dict[str, dict]]],
    year: str,
) -> dict:
    """计算四维度健康度评分。

    四维度各 25 分，🟢=满分 🟡=半分 🔴=零分。
    None 不计入。
    """
    dimension_weight = 25
    dimension_scores = {}
    red_metrics = []

    for dim_name, dim_metrics in traffic_lights.items():
        points = 0.0
        count = 0
        for metric_name, year_data in dim_metrics.items():
            entry = year_data.get(year)
            if entry is None or entry.get("final") is None:
                continue
            count += 1
            light = entry["final"]
            if light == "green":
                points += 1.0
            elif light == "yellow":
                points += 0.5
            else:
                red_metrics.append(f"{dim_name}.{metric_name}")

        if count > 0:
            dimension_scores[dim_name] = points / count * dimension_weight
        else:
            dimension_scores[dim_name] = 0.0

    total = sum(dimension_scores.values())

    if total >= 85:
        rating = "healthy"
    elif total >= 60:
        rating = "caution"
    else:
        rating = "warning"

    return {
        "total": round(total, 1),
        "rating": rating,
        "dimensions": {k: round(v, 1) for k, v in dimension_scores.items()},
        "red_metrics": red_metrics,
    }
