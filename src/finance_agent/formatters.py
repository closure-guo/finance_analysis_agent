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


def format_valuation_section(
    relative_valuation: dict | None,
    garp_result: dict | None,
    stock_quote: dict,
    industry_pe: dict | None = None,
) -> str:
    """格式化相对估值 + GARP 为 LLM 可读 Markdown。"""
    lines = []

    # 股票行情头部
    pe = stock_quote.get("PE") or stock_quote.get("pe")
    pe_static = stock_quote.get("PE_static")
    pe_ttm = stock_quote.get("PE_ttm")
    pb = stock_quote.get("PB") or stock_quote.get("pb")
    price = stock_quote.get("price")
    market_cap = stock_quote.get("market_cap")

    lines.append("### 当前估值")
    if price:
        lines.append(f"- 最新价: {price}")
    if market_cap:
        lines.append(f"- 总市值: {market_cap}亿")
    if pe is not None:
        lines.append(f"- PE(动态): {pe:.2f}")
    if pe_ttm is not None:
        lines.append(f"- PE(TTM): {pe_ttm:.2f}")
    if pe_static is not None:
        lines.append(f"- PE(静态): {pe_static:.2f}")
    if pb is not None:
        lines.append(f"- PB: {pb:.2f}")

    # 行业PE
    if industry_pe:
        avg = industry_pe.get("avg_pe")
        median = industry_pe.get("median_pe")
        name = industry_pe.get("industry_name", "所属行业")
        parts = [f"- {name}行业平均PE"]
        if avg is not None:
            parts.append(f"算术平均: {avg:.2f}")
        if median is not None:
            parts.append(f"中位数: {median:.2f}")
        lines.append(" | ".join(parts))
    else:
        lines.append("- 行业平均PE: 数据不可用（未接入行业PE数据源）")

    # 相对估值
    if relative_valuation:
        lines.append("\n### 相对估值（目标公司 vs 同业均值）")
        for metric in ("PE", "PB"):
            rv = relative_valuation.get(metric)
            if not rv:
                continue
            target = rv.get("target")
            avg = rv.get("peer_avg")
            lo = rv.get("peer_min")
            hi = rv.get("peer_max")
            conclusion = rv.get("conclusion", "N/A")

            label_map = {
                "undervalued": "低估",
                "fair": "合理",
                "overvalued": "高估",
                "N/A": "N/A",
            }
            label = label_map.get(conclusion, conclusion)

            parts = [f"- **{metric}**"]
            if target is not None:
                parts.append(f"目标: {target:.2f}")
            if avg is not None:
                parts.append(f"同业均值: {avg:.2f}")
            if lo is not None and hi is not None:
                parts.append(f"同业区间: {lo:.2f}-{hi:.2f}")
            parts.append(f"结论: {label}")
            lines.append(" | ".join(parts))
    else:
        lines.append("\n### 相对估值")
        lines.append("无同业对比数据")

    # GARP 结果
    if garp_result:
        lines.append("\n### GARP 筛选结果")
        passed = garp_result.get("pass", False)
        status = "✅ 通过" if passed else "❌ 未通过"
        lines.append(f"- 综合结果: {status}")
        failures = garp_result.get("failures", [])
        if failures:
            lines.append("- 未满足条件:")
            for f in failures:
                lines.append(f"  - {f}")
        details = garp_result.get("details", {})
        if details:
            lines.append("- 指标详情:")
            for k, v in details.items():
                val = f"{v:.2f}" if isinstance(v, float) else (str(v) if v is not None else "N/A")
                lines.append(f"  - {k}: {val}")
    else:
        lines.append("\n### GARP 筛选结果")
        lines.append("GARP 数据不可用")

    return "\n".join(lines)


def format_quarterly_trend(quarterly_trend: dict | None) -> str:
    if not quarterly_trend:
        return "无季度趋势数据"
    lines = ["### 季度利润趋势（单季归母净利润）"]

    quarters = quarterly_trend.get("quarters", [])
    net_profit = quarterly_trend.get("net_profit", [])
    qoq = quarterly_trend.get("qoq", [])
    yoy = quarterly_trend.get("yoy", [])
    warnings = quarterly_trend.get("warnings", [])

    # 表格
    header = "| 季度 | 归母净利润(亿) | 环比 | 同比 |"
    sep = "| --- | ---: | ---: | ---: |"
    lines.extend([header, sep])
    for i in range(len(quarters)):
        np_val = f"{net_profit[i]:.2f}" if net_profit[i] is not None else "N/A"
        qoq_str = _fmt_pct(qoq[i])
        yoy_str = _fmt_pct(yoy[i])
        lines.append(f"| {quarters[i]} | {np_val} | {qoq_str} | {yoy_str} |")

    # 拐点预警
    if warnings:
        lines.append("\n**季度拐点预警**:")
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("\n**季度拐点预警**: 无显著异常")

    return "\n".join(lines)


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    arrow = "↑" if v > 0 else "↓"
    return f"{arrow} {abs(v):.1f}%"


def _fmt_val(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if abs(v) < 10:
            return f"{v:.2f}"
        return f"{v:.1f}"
    return str(v)


def format_key_events(key_events: list[dict] | None) -> str:
    if not key_events:
        return "暂无重大非财务事件记录。"

    # 检测是否为兜底事件
    if len(key_events) == 1 and key_events[0].get("type") == "数据状态":
        return "### 关键事件\n> 事件数据暂时不可用。当前仅展示预构建库数据。"

    lines = ["### 关键非财务事件"]
    for e in key_events:
        date = e.get("date", "")
        etype = e.get("type", "")
        title = e.get("title", "")
        summary = e.get("summary", "")
        impact = e.get("impact", "neutral")
        level = e.get("level", "L1")
        ongoing = " [持续中]" if e.get("ongoing") else ""
        impact_emoji = {"positive": "▲", "negative": "▼", "neutral": "●"}.get(impact, "●")

        # L2 事件附加前瞻信号标注
        level_tag = "【前瞻信号】" if level == "L2" else ""

        lines.append(f"- **{date}** {impact_emoji} **{etype}**：{title}{ongoing} {level_tag}")
        if summary:
            lines.append(f"  - {summary}")

    return "\n".join(lines)


def _get_light(tl_dim: dict, metric_name: str, year: str | None) -> str:
    if not year:
        return ""
    entry = tl_dim.get(metric_name, {}).get(year, {})
    light = entry.get("final")
    if light and light in LIGHT_EMOJI:
        return f"{LIGHT_EMOJI[light]} {LIGHT_LABEL[light]}"
    return ""
