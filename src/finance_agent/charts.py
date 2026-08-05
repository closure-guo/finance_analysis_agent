"""图表数据收集 + matplotlib PNG 生成。

collect_chart_data(state) → dict: 从 state 提取结构化财务/股价序列
generate_all_charts(chart_data, output_dir) → dict[name, path]: 生成全部 PNG
"""

from __future__ import annotations

import logging
import os

import matplotlib
import pandas as pd

matplotlib.use("Agg")  # 非交互后端，适配服务器环境

import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

# ── 中文字体 ──
# 回退链覆盖 Windows（微软雅黑/黑体）、macOS（Arial Unicode MS）与 Linux 容器
# （Noto Sans CJK SC，由 Dockerfile 安装 fonts-noto-cjk 提供）
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "Arial",
]
plt.rcParams["axes.unicode_minus"] = False

# ── 配色 ──
_C_BLUE = "#2563eb"
_C_RED = "#dc2626"
_C_GREEN = "#059669"
_C_PURPLE = "#7c3aed"
_C_ORANGE = "#ea580c"
_C_CYAN = "#0891b2"
_C_LIME = "#65a30d"
_C_PINK = "#db2777"
_C_BG = "#fafafa"
_C_GRID = "#e5e7eb"


# ════════════════════════════════════════════════════════
#  数据收集
# ════════════════════════════════════════════════════════


def _safe_float(val, default=None):
    """安全转 float，处理 None/NaN/空字符串。"""
    if val is None:
        return default
    if isinstance(val, float) and pd.isna(val):
        return default
    try:
        v = float(val)
        if np.isinf(v) or np.isnan(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def _year_from_date(date_str) -> str:
    return str(date_str)[:4]


def collect_chart_data(state: dict) -> dict:
    """从 state 提取结构化图表数据，返回 JSON-serializable dict。"""
    chart_data: dict = {
        "stock_code": state.get("stock_code", ""),
        "stock_name": state.get("stock_name", ""),
        "annual": [],
        "growth": {"years": [], "revenue_growth": [], "profit_growth": []},
        "price": {"daily": [], "earnings_dates": []},
        "kpi": {},
        "market_share": None,
    }

    income = state.get("income_statement")
    balance = state.get("balance_sheet")
    cashflow = state.get("cash_flow_statement")
    profitability = state.get("profitability_metrics") or {}
    solvency = state.get("solvency_metrics") or {}

    # ── 年度财务数据 ──
    if income is not None and not income.empty:
        years = [_year_from_date(d) for d in income["报告日"]]
        for i, year in enumerate(years):
            row_is = income.iloc[i]
            row_bs = balance.iloc[i] if balance is not None and i < len(balance) else None
            row_cf = cashflow.iloc[i] if cashflow is not None and i < len(cashflow) else None

            annual_entry = {
                "year": year,
                "revenue": _safe_float(row_is.get("营业收入")),
                "net_profit": _safe_float(row_is.get("归母净利润"))
                or _safe_float(row_is.get("净利润")),
                "gross_margin": _safe_float(profitability.get("毛利率", {}).get(year)),
                "net_margin": _safe_float(profitability.get("净利率", {}).get(year)),
                "roe": _safe_float(profitability.get("ROE", {}).get(year)),
                "roa": _safe_float(profitability.get("ROA", {}).get(year)),
                "ocf": _safe_float(row_cf.get("经营活动产生的现金流量净额"))
                if row_cf is not None
                else None,
                "total_assets": _safe_float(row_bs.get("资产总计")) if row_bs is not None else None,
                "equity": _safe_float(row_bs.get("归母所有者权益")) if row_bs is not None else None,
                "contract_liab": _safe_float(row_bs.get("合同负债"))
                if row_bs is not None
                else None,
                "cip": _safe_float(row_bs.get("在建工程")) if row_bs is not None else None,
                "debt_ratio": _safe_float(solvency.get("资产负债率", {}).get(year)),
            }
            chart_data["annual"].append(annual_entry)

        # ── 同比增速 ──
        annual = chart_data["annual"]
        for i in range(len(annual) - 1):
            curr = annual[i]
            prev = annual[i + 1]
            chart_data["growth"]["years"].append(curr["year"])
            rev_g = None
            profit_g = None
            if prev["revenue"] and curr["revenue"] and prev["revenue"] != 0:
                rev_g = round((curr["revenue"] - prev["revenue"]) / abs(prev["revenue"]) * 100, 2)
            if prev["net_profit"] and curr["net_profit"] and prev["net_profit"] != 0:
                profit_g = round(
                    (curr["net_profit"] - prev["net_profit"]) / abs(prev["net_profit"]) * 100, 2
                )
            chart_data["growth"]["revenue_growth"].append(rev_g)
            chart_data["growth"]["profit_growth"].append(profit_g)

    # ── KPI ──
    quote = state.get("stock_quote") or {}
    chart_data["kpi"] = {
        "current_price": _safe_float(quote.get("price")),
        "market_cap": _safe_float(quote.get("market_cap")),
        "pe": _safe_float(quote.get("PE")) or _safe_float(quote.get("PE_ttm")),
        "pb": _safe_float(quote.get("PB")),
    }

    # ── 股价日线 ──
    kline = state.get("kline")
    if kline is not None and not kline.empty:
        # 取最近 250 个交易日（约一年）
        recent = kline.tail(250)
        for _, row in recent.iterrows():
            date_str = str(row.get("日期", row.get("date", "")))[:10]
            close = _safe_float(row.get("收盘", row.get("close")))
            if date_str and close is not None:
                chart_data["price"]["daily"].append({"date": date_str, "close": close})

        # 52周高低
        if chart_data["price"]["daily"]:
            closes = [d["close"] for d in chart_data["price"]["daily"]]
            chart_data["kpi"]["52w_high"] = max(closes)
            chart_data["kpi"]["52w_low"] = min(closes)

    # ── 财报发布日期（从年报报告日推算）──
    if income is not None and not income.empty:
        for d in income["报告日"]:
            date_str = str(d)
            if len(date_str) == 8:
                formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                formatted = date_str[:10]
            chart_data["price"]["earnings_dates"].append(formatted)

    return chart_data


# ════════════════════════════════════════════════════════
#  PNG 生成
# ════════════════════════════════════════════════════════

_DPI = 150
_FIGSIZE_WIDE = (10, 5)
_FIGSIZE_SQUARE = (8, 6)


def _style_ax(ax, title: str = ""):
    """统一坐标系样式。"""
    ax.set_facecolor(_C_BG)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_C_GRID)
    ax.spines["bottom"].set_color(_C_GRID)
    ax.tick_params(colors="#666", labelsize=9)
    ax.yaxis.grid(True, color=_C_GRID, linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color="#333", pad=12)


def _save_fig(fig, output_dir: str, name: str) -> str:
    """保存图表，返回绝对路径。"""
    path = os.path.join(output_dir, f"{name}.png")
    fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _chart_revenue_profit(data: dict, out: str) -> str | None:
    """P0: 营业收入与归母净利润（双轴柱状图）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    revenue = [a.get("revenue") or 0 for a in annual]
    profit = [a.get("net_profit") or 0 for a in annual]

    fig, ax1 = plt.subplots(figsize=_FIGSIZE_WIDE)
    x = np.arange(len(years))
    w = 0.35
    ax1.bar(x - w / 2, revenue, w, label="营业收入", color=_C_BLUE, alpha=0.85)
    ax1.set_ylabel("营业收入（亿元）", color=_C_BLUE, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=_C_BLUE)
    ax1.set_xticks(x)
    ax1.set_xticklabels(years)

    ax2 = ax1.twinx()
    ax2.bar(x + w / 2, profit, w, label="归母净利润", color=_C_RED, alpha=0.85)
    ax2.set_ylabel("归母净利润（亿元）", color=_C_RED, fontsize=10)
    ax2.tick_params(axis="y", labelcolor=_C_RED)
    ax2.spines["top"].set_visible(False)

    _style_ax(ax1, "营业收入与归母净利润")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)
    fig.tight_layout()
    return _save_fig(fig, out, "chart_revenue_profit")


def _chart_growth(data: dict, out: str) -> str | None:
    """P0: 同比增速（折线图）。"""
    growth = data.get("growth", {})
    years = growth.get("years", [])
    if len(years) < 2:
        return None
    rev_g = growth.get("revenue_growth", [])
    profit_g = growth.get("profit_growth", [])

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.plot(years, rev_g, marker="o", color=_C_BLUE, linewidth=2, label="营收增速")
    ax.plot(years, profit_g, marker="s", color=_C_RED, linewidth=2, label="净利润增速")
    ax.axhline(y=0, color="#999", linewidth=0.8, linestyle="--")
    ax.set_ylabel("同比增长率（%）", fontsize=10)
    ax.set_xlabel("年份", fontsize=10)
    _style_ax(ax, "同比增速")
    ax.legend(fontsize=9, loc="best")
    # 标注数值
    for i, (r, p) in enumerate(zip(rev_g, profit_g, strict=False)):
        if r is not None:
            ax.annotate(
                f"{r:.1f}%",
                (i, r),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=7,
                color=_C_BLUE,
            )
        if p is not None:
            ax.annotate(
                f"{p:.1f}%",
                (i, p),
                textcoords="offset points",
                xytext=(0, -12),
                ha="center",
                fontsize=7,
                color=_C_RED,
            )
    fig.tight_layout()
    return _save_fig(fig, out, "chart_growth")


def _chart_margin(data: dict, out: str) -> str | None:
    """P0: 毛利率与净利率（平滑折线图）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    gm = [a.get("gross_margin") for a in annual]
    nm = [a.get("net_margin") for a in annual]

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.plot(years, gm, marker="o", color=_C_GREEN, linewidth=2.5, label="毛利率")
    ax.plot(years, nm, marker="s", color=_C_PURPLE, linewidth=2.5, label="净利率")
    ax.set_ylabel("百分比（%）", fontsize=10)
    ax.set_xlabel("年份", fontsize=10)
    _style_ax(ax, "毛利率与净利率")
    ax.legend(fontsize=9, loc="best")
    for i, (g, n) in enumerate(zip(gm, nm, strict=False)):
        if g is not None:
            ax.annotate(
                f"{g:.1f}%",
                (i, g),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=7,
                color=_C_GREEN,
            )
        if n is not None:
            ax.annotate(
                f"{n:.1f}%",
                (i, n),
                textcoords="offset points",
                xytext=(0, -12),
                ha="center",
                fontsize=7,
                color=_C_PURPLE,
            )
    fig.tight_layout()
    return _save_fig(fig, out, "chart_margin")


def _chart_roe(data: dict, out: str) -> str | None:
    """P0: ROE 变化（面积折线图 + 15% 优秀线）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    roe = [a.get("roe") for a in annual]

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.fill_between(range(len(years)), roe, alpha=0.15, color=_C_ORANGE)
    ax.plot(years, roe, marker="o", color=_C_ORANGE, linewidth=2.5, label="ROE")
    ax.axhline(y=15, color="#999", linewidth=1, linestyle="--", label="优秀线 15%")
    ax.set_ylabel("ROE（%）", fontsize=10)
    ax.set_xlabel("年份", fontsize=10)
    _style_ax(ax, "ROE 变化趋势")
    ax.legend(fontsize=9, loc="best")
    for i, r in enumerate(roe):
        if r is not None:
            ax.annotate(
                f"{r:.1f}%",
                (i, r),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=7,
                color=_C_ORANGE,
            )
    fig.tight_layout()
    return _save_fig(fig, out, "chart_roe")


def _chart_cashflow(data: dict, out: str) -> str | None:
    """P0: 经营现金流净额（柱状图）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    ocf = [a.get("ocf") or 0 for a in annual]

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    colors = [_C_BLUE if v >= 0 else _C_RED for v in ocf]
    ax.bar(years, ocf, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.set_ylabel("经营现金流净额（亿元）", fontsize=10)
    ax.set_xlabel("年份", fontsize=10)
    _style_ax(ax, "经营现金流净额")
    for i, v in enumerate(ocf):
        ax.annotate(
            f"{v:.1f}",
            (i, v),
            textcoords="offset points",
            xytext=(0, 5),
            ha="center",
            fontsize=8,
            color="#333",
        )
    fig.tight_layout()
    return _save_fig(fig, out, "chart_cashflow")


def _chart_stock_price(data: dict, out: str) -> str | None:
    """P1: 股价趋势（含财报标注）。"""
    daily = data.get("price", {}).get("daily", [])
    if len(daily) < 10:
        return None
    dates = [d["date"] for d in daily]
    closes = [d["close"] for d in daily]
    earnings_dates = data.get("price", {}).get("earnings_dates", [])

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.plot(dates, closes, color=_C_BLUE, linewidth=1.5)
    ax.fill_between(range(len(dates)), closes, alpha=0.1, color=_C_BLUE)
    ax.set_ylabel("股价（元）", fontsize=10)
    ax.set_xlabel("日期", fontsize=10)
    _style_ax(ax, "股价趋势")

    # 标注财报发布日
    for ed in earnings_dates:
        for i, d in enumerate(dates):
            if d == ed:
                ax.axvline(x=i, color=_C_RED, linewidth=0.8, linestyle="--", alpha=0.5)
                ax.annotate(
                    "财报",
                    (i, closes[i]),
                    textcoords="offset points",
                    xytext=(5, 5),
                    fontsize=7,
                    color=_C_RED,
                )
                break

    # X 轴日期格式化（只显示少量标签）
    n = len(dates)
    step = max(1, n // 8)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=30, ha="right")
    fig.tight_layout()
    return _save_fig(fig, out, "chart_stock_price")


def _chart_growth_vs_price(data: dict, out: str) -> str | None:
    """P1: 财务增速 vs 股价涨幅对比。"""
    annual = data.get("annual", [])
    daily = data.get("price", {}).get("daily", [])
    if len(annual) < 3 or len(daily) < 10:
        return None

    # 计算各年股价涨跌幅
    years = [a["year"] for a in annual]
    rev_g = data.get("growth", {}).get("revenue_growth", [])
    profit_g = data.get("growth", {}).get("profit_growth", [])

    # 计算年度股价涨跌幅
    price_changes: list[float | None] = []
    for _i, year in enumerate(years):
        year_prices = [d["close"] for d in daily if d["date"].startswith(year)]
        prev_year = str(int(year) - 1)
        prev_prices = [d["close"] for d in daily if d["date"].startswith(prev_year)]
        if year_prices and prev_prices:
            change = (year_prices[-1] - prev_prices[-1]) / prev_prices[-1] * 100
            price_changes.append(round(change, 2))
        else:
            price_changes.append(None)

    # 对齐：growth 的 years 比 annual 少一年
    growth_years = data.get("growth", {}).get("years", [])

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    x = np.arange(len(growth_years))
    w = 0.25

    rev_vals = rev_g[: len(growth_years)]
    profit_vals = profit_g[: len(growth_years)]
    # 股价涨跌幅需要对齐到 growth_years
    price_vals = []
    for gy in growth_years:
        idx = years.index(gy) if gy in years else -1
        if idx >= 0 and idx < len(price_changes):
            price_vals.append(price_changes[idx])
        else:
            price_vals.append(None)

    ax.bar(x - w, rev_vals, w, label="营收增速", color=_C_BLUE, alpha=0.85)
    ax.bar(x, profit_vals, w, label="净利润增速", color=_C_RED, alpha=0.85)
    ax.bar(x + w, price_vals, w, label="股价涨幅", color=_C_GREEN, alpha=0.85)
    ax.set_ylabel("变化率（%）", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(growth_years)
    ax.axhline(y=0, color="#999", linewidth=0.8, linestyle="--")
    _style_ax(ax, "财务增速 vs 股价涨幅")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _save_fig(fig, out, "chart_growth_vs_price")


def _chart_assets(data: dict, out: str) -> str | None:
    """P1: 总资产与归母权益（柱状图）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    assets = [a.get("total_assets") or 0 for a in annual]
    equity = [a.get("equity") or 0 for a in annual]

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    x = np.arange(len(years))
    w = 0.35
    ax.bar(x - w / 2, assets, w, label="总资产", color=_C_CYAN, alpha=0.85)
    ax.bar(x + w / 2, equity, w, label="归母权益", color=_C_LIME, alpha=0.85)
    ax.set_ylabel("金额（亿元）", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(years)
    _style_ax(ax, "总资产与归母权益")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _save_fig(fig, out, "chart_assets")


def _chart_contract_liab(data: dict, out: str) -> str | None:
    """P1: 合同负债（柱状图）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    cl = [a.get("contract_liab") for a in annual]
    if all(v is None for v in cl):
        return None
    cl = [v or 0 for v in cl]

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.bar(years, cl, color=_C_PINK, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.set_ylabel("合同负债（亿元）", fontsize=10)
    ax.set_xlabel("年份", fontsize=10)
    _style_ax(ax, "合同负债")
    for i, v in enumerate(cl):
        ax.annotate(
            f"{v:.1f}",
            (i, v),
            textcoords="offset points",
            xytext=(0, 5),
            ha="center",
            fontsize=8,
            color="#333",
        )
    fig.tight_layout()
    return _save_fig(fig, out, "chart_contract_liab")


def _chart_debt_ratio(data: dict, out: str) -> str | None:
    """P1: 资产负债率趋势。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None
    years = [a["year"] for a in annual]
    dr = [a.get("debt_ratio") for a in annual]
    if all(v is None for v in dr):
        return None

    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.plot(years, dr, marker="o", color=_C_RED, linewidth=2.5)
    ax.fill_between(range(len(years)), dr, alpha=0.1, color=_C_RED)
    ax.set_ylabel("资产负债率（%）", fontsize=10)
    ax.set_xlabel("年份", fontsize=10)
    _style_ax(ax, "资产负债率趋势")
    for i, v in enumerate(dr):
        if v is not None:
            ax.annotate(
                f"{v:.1f}%",
                (i, v),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=7,
                color=_C_RED,
            )
    fig.tight_layout()
    return _save_fig(fig, out, "chart_debt_ratio")


def _chart_heatmap(data: dict, out: str) -> str | None:
    """P2: 财报发布窗口期股价变化热力图。"""
    daily = data.get("price", {}).get("daily", [])
    earnings_dates = data.get("price", {}).get("earnings_dates", [])
    if len(earnings_dates) < 2 or len(daily) < 30:
        return None

    # 计算每个财报日前后 N 天的收益率
    windows = [-5, -1, 0, 1, 5, 10, 30]
    years_labels = []
    heatmap_data = []

    for ed in earnings_dates:
        ed_dt = pd.to_datetime(ed)
        year_label = ed_dt.strftime("%Y年报")
        years_labels.append(year_label)
        row = []
        for offset in windows:
            target = ed_dt + pd.Timedelta(days=offset)
            # 找最近交易日
            target_str = target.strftime("%Y-%m-%d")
            base_idx = None
            for i, d in enumerate(daily):
                if d["date"] == target_str:
                    base_idx = i
                    break
            if base_idx is None:
                # 找最近的
                for i, d in enumerate(daily):
                    if d["date"] <= target_str:
                        base_idx = i
                    else:
                        break
            if base_idx is not None and base_idx > 0:
                prev_close = daily[max(0, base_idx - 1)]["close"]
                curr_close = daily[base_idx]["close"]
                if prev_close != 0:
                    ret = (curr_close - prev_close) / prev_close * 100
                    row.append(round(ret, 2))
                else:
                    row.append(0.0)
            else:
                row.append(0.0)
        heatmap_data.append(row)

    if not heatmap_data:
        return None

    arr = np.array(heatmap_data)
    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    im = ax.imshow(arr, cmap="RdYlGn", aspect="auto", vmin=-8, vmax=8)
    ax.set_xticks(range(len(windows)))
    ax.set_xticklabels([f"T{w:+d}" if w != 0 else "T0" for w in windows])
    ax.set_yticks(range(len(years_labels)))
    ax.set_yticklabels(years_labels)
    ax.set_title(
        "年报发布窗口期股价变化（%）", fontsize=13, fontweight="bold", color="#333", pad=12
    )
    # 标注数值
    for i in range(len(years_labels)):
        for j in range(len(windows)):
            val = arr[i, j]
            color = "white" if abs(val) > 5 else "#333"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=8, color=color)
    fig.colorbar(im, ax=ax, shrink=0.8, label="收益率（%）")
    fig.tight_layout()
    return _save_fig(fig, out, "chart_heatmap")


def _chart_dashboard(data: dict, out: str) -> str | None:
    """P2: 综合仪表盘（多子图拼图）。"""
    annual = data.get("annual", [])
    if len(annual) < 2:
        return None

    years = [a["year"] for a in annual]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    fig.suptitle("财务指标综合仪表盘", fontsize=16, fontweight="bold", color="#333", y=0.98)

    # 1. 营收 & 利润
    ax = axes[0, 0]
    ax.bar(years, [a.get("revenue") or 0 for a in annual], color=_C_BLUE, alpha=0.7, label="营收")
    ax.bar(
        years, [a.get("net_profit") or 0 for a in annual], color=_C_RED, alpha=0.7, label="净利润"
    )
    _style_ax(ax, "营收 & 净利润")
    ax.legend(fontsize=7)

    # 2. 毛利率 & 净利率
    ax = axes[0, 1]
    ax.plot(
        years,
        [a.get("gross_margin") or 0 for a in annual],
        marker="o",
        color=_C_GREEN,
        label="毛利率",
    )
    ax.plot(
        years,
        [a.get("net_margin") or 0 for a in annual],
        marker="s",
        color=_C_PURPLE,
        label="净利率",
    )
    _style_ax(ax, "利润率")
    ax.legend(fontsize=7)

    # 3. ROE
    ax = axes[0, 2]
    ax.plot(years, [a.get("roe") or 0 for a in annual], marker="o", color=_C_ORANGE)
    ax.axhline(y=15, color="#999", linewidth=0.8, linestyle="--")
    _style_ax(ax, "ROE")

    # 4. 现金流
    ax = axes[1, 0]
    ax.bar(years, [a.get("ocf") or 0 for a in annual], color=_C_CYAN, alpha=0.85)
    _style_ax(ax, "经营现金流")

    # 5. 资产负债率
    ax = axes[1, 1]
    dr = [a.get("debt_ratio") or 0 for a in annual]
    ax.plot(years, dr, marker="o", color=_C_RED)
    ax.fill_between(range(len(years)), dr, alpha=0.1, color=_C_RED)
    _style_ax(ax, "资产负债率")

    # 6. 增速
    ax = axes[1, 2]
    growth = data.get("growth", {})
    gy = growth.get("years", [])
    if gy:
        ax.bar(
            np.arange(len(gy)) - 0.15,
            growth.get("revenue_growth", []),
            0.3,
            color=_C_BLUE,
            alpha=0.7,
            label="营收增速",
        )
        ax.bar(
            np.arange(len(gy)) + 0.15,
            growth.get("profit_growth", []),
            0.3,
            color=_C_RED,
            alpha=0.7,
            label="利润增速",
        )
        ax.set_xticks(range(len(gy)))
        ax.set_xticklabels(gy)
        ax.axhline(y=0, color="#999", linewidth=0.5, linestyle="--")
        ax.legend(fontsize=7)
    _style_ax(ax, "同比增速")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _save_fig(fig, out, "chart_dashboard")


def _chart_market_share(data: dict, out: str) -> str | None:
    """P2: 市场份额（占位图，数据不可得时生成说明图）。"""
    market_share = data.get("market_share")
    fig, ax = plt.subplots(figsize=_FIGSIZE_SQUARE)
    ax.set_facecolor(_C_BG)
    ax.axis("off")

    if market_share and isinstance(market_share, dict) and market_share.get("shares"):
        shares = market_share["shares"]
        labels = [s["name"] for s in shares]
        sizes = [s["value"] for s in shares]
        colors = plt.cm.Set2(np.linspace(0, 1, len(labels)))
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90
        )
        ax.set_title("全球市场份额", fontsize=13, fontweight="bold", color="#333", pad=12)
    else:
        ax.text(
            0.5,
            0.5,
            "市场份额数据暂不可得\n（需额外数据源）",
            ha="center",
            va="center",
            fontsize=14,
            color="#999",
            transform=ax.transAxes,
        )
        ax.set_title("全球市场份额", fontsize=13, fontweight="bold", color="#333", pad=12)

    fig.tight_layout()
    return _save_fig(fig, out, "chart_market_share")


# ════════════════════════════════════════════════════════
#  统一入口
# ════════════════════════════════════════════════════════


def generate_all_charts(chart_data: dict, output_dir: str) -> dict[str, str]:
    """生成全部图表 PNG，返回 {chart_name: file_path}。"""
    os.makedirs(output_dir, exist_ok=True)
    charts: dict[str, str] = {}

    generators = [
        ("chart_revenue_profit", _chart_revenue_profit),
        ("chart_growth", _chart_growth),
        ("chart_margin", _chart_margin),
        ("chart_roe", _chart_roe),
        ("chart_cashflow", _chart_cashflow),
        ("chart_stock_price", _chart_stock_price),
        ("chart_growth_vs_price", _chart_growth_vs_price),
        ("chart_assets", _chart_assets),
        ("chart_contract_liab", _chart_contract_liab),
        ("chart_debt_ratio", _chart_debt_ratio),
        ("chart_heatmap", _chart_heatmap),
        ("chart_dashboard", _chart_dashboard),
        ("chart_market_share", _chart_market_share),
    ]

    for name, gen_func in generators:
        try:
            path = gen_func(chart_data, output_dir)
            if path:
                charts[name] = path
        except Exception as e:
            logger.warning("图表 %s 生成失败: %s", name, e)

    return charts
