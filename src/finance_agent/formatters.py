"""State 数据 → LLM 可读 Markdown 文本。

纯函数模块：输入 dict/DataFrame，输出格式化字符串。
"""

from __future__ import annotations

from typing import Any

LIGHT_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
LIGHT_LABEL = {"green": "优良", "yellow": "关注", "red": "警告"}
RATING_LABEL = {"healthy": "🟢 健康", "caution": "🟡 关注", "warning": "🔴 警告"}


def format_stock_header(stock_quote: dict, industry_info: dict) -> str:
    lines = []
    name = stock_quote.get("name") or industry_info.get("name", "N/A")
    code = stock_quote.get("code", "N/A")
    lines.append(f"**股票名称**: {name}")
    lines.append(f"**股票代码**: {code}")
    industry = industry_info.get("industry", "N/A")
    lines.append(f"**所属行业**: {industry}")
    if stock_quote.get("price"):
        lines.append(f"**最新价**: {stock_quote['price']}")
    if stock_quote.get("market_cap"):
        lines.append(f"**总市值**: {stock_quote['market_cap']}亿")
    return "\n".join(lines)


def format_metrics_table(
    solvency: dict,
    profitability: dict,
    efficiency: dict,
    cashflow: dict,
    traffic_lights: dict,
) -> str:
    dimensions = {
        "偿债能力": ("solvency", solvency),
        "盈利能力": ("profitability", profitability),
        "运营效率": ("efficiency", efficiency),
        "现金流": ("cashflow", cashflow),
    }
    sections = []
    for dim_label, (dim_key, metrics) in dimensions.items():
        sections.append(f"### {dim_label}")
        tl_dim = traffic_lights.get(dim_key, {})

        years = sorted(
            {y for v in metrics.values() for y in v},
            reverse=True,
        )
        header = "| 指标 | " + " | ".join(years) + " | 灯色 |"
        sep = "| --- | " + " | ".join(["---:"] * len(years)) + " | --- |"
        rows = [header, sep]

        for metric_name, year_values in metrics.items():
            cells = []
            for y in years:
                v = year_values.get(y)
                cells.append(_fmt_val(v))
            latest = years[0] if years else None
            light = _get_light(tl_dim, metric_name, latest)
            rows.append(f"| {metric_name} | " + " | ".join(cells) + f" | {light} |")

        sections.append("\n".join(rows))

    return "\n\n".join(sections)


def format_dupont_tree(dupont_tree: dict) -> str:
    if not dupont_tree:
        return "无杜邦数据"
    lines = ["### 杜邦分解"]
    for level_key in ("L1", "L2", "L3"):
        level = dupont_tree.get(level_key, {})
        if not level:
            continue
        indent = "  " * {"L1": 0, "L2": 1, "L3": 2}[level_key]
        lines.append(f"{indent}**{level_key}**:")
        for name, year_vals in level.items():
            latest_year = max(year_vals.keys()) if year_vals else "N/A"
            val = year_vals.get(latest_year)
            lines.append(f"{indent}- {name}: {_fmt_val(val)} ({latest_year})")
    return "\n".join(lines)


def format_health_score(score: dict) -> str:
    if not score:
        return "无评分数据"
    total = score.get("total", 0)
    rating = score.get("rating", "N/A")
    label = RATING_LABEL.get(rating, rating)
    lines = [f"### 健康度评分：{total}/100 {label}"]
    dims = score.get("dimensions", {})
    if dims:
        for dim, pts in dims.items():
            lines.append(f"- {dim}: {pts}/25")
    return "\n".join(lines)


def format_risk_summary(traffic_lights: dict, anomalies: list[str]) -> str:
    lines = []
    red_metrics = []
    for dim_name, dim_metrics in traffic_lights.items():
        for metric_name, year_data in dim_metrics.items():
            for year, entry in year_data.items():
                if entry.get("final") == "red":
                    red_metrics.append(f"- {dim_name}.{metric_name} ({year})")
    if red_metrics:
        lines.append("### 🔴 红灯指标")
        lines.extend(red_metrics)
    if anomalies:
        lines.append("### 异常变动")
        for a in anomalies:
            lines.append(f"- {a}")
    return "\n".join(lines) if lines else "无风险指标触发"


def format_growth_rates(growth_rates: dict) -> str:
    if not growth_rates:
        return "无增长率数据"
    lines = ["### 同比变化率"]
    for dim_name, metrics in growth_rates.items():
        for metric_name, rate in metrics.items():
            if rate is not None:
                arrow = "↑" if rate > 0 else "↓"
                lines.append(f"- {dim_name}.{metric_name}: {arrow} {abs(rate):.1%}")
    return "\n".join(lines)


def _fmt_val(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if abs(v) < 10:
            return f"{v:.2f}"
        return f"{v:.1f}"
    return str(v)


def _get_light(tl_dim: dict, metric_name: str, year: str | None) -> str:
    if not year:
        return ""
    entry = tl_dim.get(metric_name, {}).get(year, {})
    light = entry.get("final")
    if light and light in LIGHT_EMOJI:
        return f"{LIGHT_EMOJI[light]} {LIGHT_LABEL[light]}"
    return ""
