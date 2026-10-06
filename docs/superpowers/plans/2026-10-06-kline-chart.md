# Stock Price K-line Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 报告「股价趋势」图升级为 K 线图——蜡烛主图 + MA5/20/60 均线 + 交易决策价位水平参考线 + 成交量副图，双端（matplotlib PNG / 前端 ECharts）同数据渲染，历史会话 close-only 数据降级兼容。

**Architecture:** 数据层在 `collect_chart_data` 把已在 `state["kline"]` 中的 OHLCV 补进 `chart_data.price.daily`（additive），新增 `price.ma`（收盘价简单移动平均）与 `price.decision_levels`（取自 `final_trade_decision`/`trader_plan`）；服务端 `_chart_stock_price` 重绘蜡烛图（图表 key/文件名不变，导出链路零改动）；前端 `StockPriceChart` 改 ECharts candlestick 双 grid（价格+成交量），缺 OHLC 时走原折线分支。

**Tech Stack:** Python 3.12 + matplotlib + pandas（无新依赖）；React 18 + TS + echarts-for-react；Playwright（管线 stub E2E）。

**Delta:** `openspec/changes/update-price-chart-kline/`（specs/report-kline-chart：数据采集 / 双端渲染 / 历史会话后向兼容三个 requirement）

## Global Constraints

- 图表 key 与 PNG 文件名保持 `chart_stock_price` 不变（导出器族、文件清单、组件映射零改动）
- 取数只用 `akshare_client` 归一化中文列名（日期/开盘/最高/最低/收盘/成交量），禁止列位索引（incident #240 教训）
- 均线口径 = 收盘价简单移动平均，窗口前段为 `None`；先在全量 kline 上计算再切尾 250 对齐
- 价格窗口维持最近 250 个交易日、前复权，与风险指标窗口一致
- 涨跌配色 A 股惯例：收阳（收盘≥开盘）红系、收阴绿系；后端 `_C_RED`/`_C_GREEN`，前端 `theme.coral`/`theme.mint`（取自 CSS 变量，暗色自跟随）
- E2E 红线：selector 真实来源、web-first assertion、禁 `route.fulfill` 业务接口、禁手动取值后断言
- commit 消息后缀 `(update-price-chart-kline)`；先测试后实现（TDD 五步）
- 验证命令：后端 `uv run pytest`、`uv run ruff check`、`uv run mypy`；前端 `cd frontend && npm test`
- 注释用中文；后端变量 snake_case（charts.py 现状），前端 camelCase

---

### Task 1: 后端 K 线图表数据采集契约（collect_chart_data）

**Files:**
- Modify: `src/finance_agent/charts.py`（`collect_chart_data` L82-181 区域 + 新增模块级帮助函数）
- Test: `tests/test_charts_kline_data.py`（新建）

**Interfaces:**
- Consumes: `state["kline"]`（pandas DataFrame，中文列名）；`state["final_trade_decision"]` / `state["trader_plan"]`（dict 或 dataclass，键 `entry_price`/`stop_loss`/`target_price`）
- Produces: `chart_data["price"]` 契约——`daily` 条目 `{date, close, open, high, low, volume}`（OHLCV 为 `float | None`）；`ma` 恒为 `{"ma5": [...], "ma20": [...], "ma60": [...]}`（`(float|None)[]`，与 daily 逐日对齐）；`decision_levels` 仅在至少一个价位在场时携带 `{entry_price?|stop_loss?|target_price?: float}`。Task 2/3 消费此契约

- [ ] **Step 1: Write the failing test**

创建 `tests/test_charts_kline_data.py`：

```python
"""update-price-chart-kline：K 线图表数据采集契约。

collect_chart_data 的 price 输出自本变更起携带逐日 OHLCV、MA5/20/60
均线（收盘价简单移动平均，窗口前段 None）与交易决策价位（缺失形态
降级不携带）。契约锚定 delta specs/report-kline-chart「K 线图表数据采集」。
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from finance_agent.charts import collect_chart_data


def _synth_kline(n: int, base: float = 10.0) -> pd.DataFrame:
    """构造 akshare_client 归一化中文列名的日 K 线。"""
    rows = []
    for i in range(n):
        close = base + i * 0.1
        rows.append(
            {
                "日期": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                "开盘": close - 0.05,
                "最高": close + 0.2,
                "最低": close - 0.2,
                "收盘": close,
                "成交量": 1000.0 + i,
            }
        )
    return pd.DataFrame(rows)


def _state_with_kline(n: int = 65) -> dict:
    return {"stock_code": "600519", "kline": _synth_kline(n)}


def test_daily_carry_ohlcv():
    chart = collect_chart_data(_state_with_kline())
    first = chart["price"]["daily"][0]
    assert first["open"] is not None
    assert first["high"] is not None
    assert first["low"] is not None
    assert first["volume"] is not None


def test_ohlcv_invariants():
    """OHLC 不变式：high≥max(open,close)、low≤min(open,close)（#240 列位教训守卫）。"""
    chart = collect_chart_data(_state_with_kline(30))
    for d in chart["price"]["daily"]:
        assert d["high"] >= max(d["open"], d["close"])
        assert d["low"] <= min(d["open"], d["close"])


def test_ma_series_aligned_with_warmup_nulls():
    chart = collect_chart_data(_state_with_kline(65))
    ma = chart["price"]["ma"]
    daily = chart["price"]["daily"]
    assert set(ma.keys()) == {"ma5", "ma20", "ma60"}
    assert len(ma["ma5"]) == len(daily) == 65
    assert ma["ma5"][4] == pytest.approx(sum(d["close"] for d in daily[:5]) / 5)
    assert ma["ma60"][58] is None
    assert ma["ma60"][59] == pytest.approx(sum(d["close"] for d in daily[:60]) / 60)


def test_decision_levels_from_dict_decision():
    state = _state_with_kline(20)
    state["final_trade_decision"] = {
        "action": "buy",
        "entry_price": 10.5,
        "stop_loss": 9.8,
        "target_price": 12.0,
    }
    chart = collect_chart_data(state)
    assert chart["price"]["decision_levels"] == {
        "entry_price": 10.5,
        "stop_loss": 9.8,
        "target_price": 12.0,
    }


def test_decision_levels_from_attr_decision():
    """dataclass/属性形态（TradeDecision 路径），半缺价位只携带在场字段。"""
    state = _state_with_kline(20)
    state["final_trade_decision"] = SimpleNamespace(
        action="buy", entry_price=10.5, stop_loss=None, target_price=12.0
    )
    chart = collect_chart_data(state)
    assert chart["price"]["decision_levels"] == {"entry_price": 10.5, "target_price": 12.0}


def test_decision_levels_fallback_to_trader_plan():
    """无最终决策时回退交易员方案（与 report 章节渲染同源优先级）。"""
    state = _state_with_kline(20)
    state["trader_plan"] = {"entry_price": 10.5}
    chart = collect_chart_data(state)
    assert chart["price"]["decision_levels"] == {"entry_price": 10.5}


def test_decision_levels_absent_when_no_prices():
    """neutral/hold 无价位、字段全缺 → 不携带 decision_levels 键。"""
    state = _state_with_kline(20)
    state["final_trade_decision"] = {"action": "neutral", "confidence": 0.4}
    chart = collect_chart_data(state)
    assert "decision_levels" not in chart["price"]


def test_no_kline_degrades_silently():
    chart = collect_chart_data({"stock_code": "600519"})
    assert chart["price"]["daily"] == []
    assert chart["price"]["ma"] == {"ma5": [], "ma20": [], "ma60": []}
    assert "decision_levels" not in chart["price"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_charts_kline_data.py -v`
Expected: FAIL——`test_daily_carry_ohlcv` KeyError 'open'，`test_ma_series_aligned_with_warmup_nulls` KeyError 'ma'，决策价位相关 AssertionError

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/charts.py` 三处修改。

（a）在 `_nan_series` 之后新增模块级帮助函数：

```python
_DECISION_LEVEL_KEYS = ("entry_price", "stop_loss", "target_price")


def _moving_average(values: list[float | None], window: int) -> list[float | None]:
    """简单移动平均：窗口不足或窗口内含 None 的位置为 None。"""
    out: list[float | None] = [None] * len(values)
    for i in range(window - 1, len(values)):
        seg = [v for v in values[i - window + 1 : i + 1] if v is not None]
        if len(seg) < window:
            continue
        out[i] = sum(seg) / window
    return out


def _extract_decision_levels(state: dict) -> dict[str, float]:
    """提取交易决策价位（dict/属性双形态，与 report._format_trade_decision 同源逻辑）。

    缺失/非法价位的字段不携带；决策整体无价位时返回空 dict（调用侧不挂键）。
    """
    decision = state.get("final_trade_decision") or state.get("trader_plan")
    if decision is None:
        return {}
    levels: dict[str, float] = {}
    for key in _DECISION_LEVEL_KEYS:
        raw = decision.get(key) if isinstance(decision, dict) else getattr(decision, key, None)
        val = _safe_float(raw)
        if val is not None:
            levels[key] = val
    return levels
```

（b）`collect_chart_data` 的 `price` 初始化（L89）改为：

```python
        "price": {"daily": [], "earnings_dates": [], "ma": {"ma5": [], "ma20": [], "ma60": []}},
```

（c）「股价日线」段（L156-171）改为：

```python
    # ── 股价日线（update-price-chart-kline：补齐 OHLCV + MA 均线）──
    kline = state.get("kline")
    if kline is not None and not kline.empty:
        # 取最近 250 个交易日（约一年）
        recent = kline.tail(250)
        for _, row in recent.iterrows():
            date_str = str(row.get("日期", row.get("date", "")))[:10]
            close = _safe_float(row.get("收盘", row.get("close")))
            if date_str and close is not None:
                chart_data["price"]["daily"].append(
                    {
                        "date": date_str,
                        "close": close,
                        "open": _safe_float(row.get("开盘", row.get("open"))),
                        "high": _safe_float(row.get("最高", row.get("high"))),
                        "low": _safe_float(row.get("最低", row.get("low"))),
                        "volume": _safe_float(row.get("成交量", row.get("volume"))),
                    }
                )

        # ── MA 均线：全量 kline 计算后切尾对齐（窗口前段 None），口径同技术指标 ──
        if chart_data["price"]["daily"]:
            closes_all: list[float | None] = [_safe_float(v) for v in kline["收盘"]]
            offset = len(closes_all) - len(chart_data["price"]["daily"])
            for w in (5, 20, 60):
                chart_data["price"]["ma"][f"ma{w}"] = _moving_average(closes_all, w)[offset:]

            closes = [d["close"] for d in chart_data["price"]["daily"]]
            chart_data["kpi"]["52w_high"] = max(closes)
            chart_data["kpi"]["52w_low"] = min(closes)

    # ── 交易决策价位（独立于 kline，缺失不携带）──
    decision_levels = _extract_decision_levels(state)
    if decision_levels:
        chart_data["price"]["decision_levels"] = decision_levels
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_charts_kline_data.py tests/test_charts_none_series.py -v`
Expected: PASS（全部新测试 + 既有 None 序列回归）

- [ ] **Step 5: Commit**

```bash
git add tests/test_charts_kline_data.py src/finance_agent/charts.py
git commit -m "feat(charts): collect_chart_data 补齐 OHLCV/MA5·20·60/决策价位采集 (update-price-chart-kline)"
```

---

### Task 2: 服务端 PNG 蜡烛图渲染（_chart_stock_price 重写）

**Files:**
- Modify: `src/finance_agent/charts.py`（`_chart_stock_price` L392-429 重写 + 抽取共用帮助函数）
- Test: `tests/test_charts_kline_data.py`（追加 PNG 测试）

**Interfaces:**
- Consumes: Task 1 的 `chart_data["price"]` 契约（daily OHLCV / ma / decision_levels）
- Produces: `generate_all_charts` 内 `chart_stock_price` 生成器签名不变（`(data: dict, out: str) -> str | None`）；模块级常量 `_STOCK_PRICE_MA_SPECS`、`_DECISION_LEVEL_SPECS`；私有函数 `_chart_stock_price_line`、`_mark_earnings`、`_set_date_ticks`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_charts_kline_data.py`：

```python
# ── PNG 渲染（Task 2）──

from finance_agent.charts import generate_all_charts  # noqa: E402


def _chart_data_with_ohlc(n: int = 30) -> dict:
    """直接构造 OHLC 形态的 chart_data（绕过 state，供 PNG 生成器测试）。"""
    df = _synth_kline(n)
    daily = [
        {
            "date": str(r["日期"]),
            "open": float(r["开盘"]),
            "high": float(r["最高"]),
            "low": float(r["最低"]),
            "close": float(r["收盘"]),
            "volume": float(r["成交量"]),
        }
        for _, r in df.iterrows()
    ]
    closes = [d["close"] for d in daily]

    def _ma(w: int) -> list:
        out: list = [None] * n
        for i in range(w - 1, n):
            out[i] = round(sum(closes[i - w + 1 : i + 1]) / w, 2)
        return out

    return {
        "price": {
            "daily": daily,
            "earnings_dates": [daily[5]["date"]],
            "ma": {"ma5": _ma(5), "ma20": _ma(20), "ma60": _ma(60)},
            "decision_levels": {
                "entry_price": closes[-1] + 0.5,
                "stop_loss": closes[-1] - 0.5,
                "target_price": closes[-1] + 1.5,
            },
        }
    }


def test_stock_price_png_candlestick(tmp_path):
    charts = generate_all_charts(_chart_data_with_ohlc(), str(tmp_path))
    assert "chart_stock_price" in charts
    assert charts["chart_stock_price"].endswith(".png")


def test_stock_price_png_close_only_fallback(tmp_path):
    """仅 close 的历史形态数据降级为收盘折线渲染，不缺图不崩溃。"""
    data = _chart_data_with_ohlc()
    for d in data["price"]["daily"]:
        for k in ("open", "high", "low", "volume"):
            d.pop(k)
    data["price"].pop("ma")
    charts = generate_all_charts(data, str(tmp_path))
    assert "chart_stock_price" in charts


def test_stock_price_png_doji_no_crash(tmp_path):
    """十字星（open==close）零高度实体不得崩溃。"""
    data = _chart_data_with_ohlc(12)
    for d in data["price"]["daily"]:
        d["open"] = d["close"]
    charts = generate_all_charts(data, str(tmp_path))
    assert "chart_stock_price" in charts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_charts_kline_data.py -v -k png`
Expected: `test_stock_price_png_candlestick` PASS（旧折线实现也能出图）但行为未变；`test_stock_price_png_close_only_fallback` PASS。此两测试为行为锚定，真正断言在 Step 4 后由代码审查对照蜡烛实现（PNG 像素级断言无意义，图类型正确性由实现评审 + E2E/人工验证承担）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/charts.py`：在 `_chart_stock_price` 前新增共用帮助函数与常量，然后整体替换 `_chart_stock_price`。

```python
_STOCK_PRICE_MA_SPECS = (("ma5", _C_ORANGE, 1.0), ("ma20", _C_PURPLE, 1.0), ("ma60", _C_CYAN, 1.2))
_DECISION_LEVEL_SPECS = (
    ("entry_price", "入场", _C_BLUE),
    ("stop_loss", "止损", _C_GREEN),
    ("target_price", "目标", _C_RED),
)


def _mark_earnings(ax, daily: list[dict], closes: list, earnings_dates: list[str]) -> None:
    """财报发布日竖线标注（K 线/折线两形态共用）。"""
    for ed in earnings_dates:
        for i, d in enumerate(daily):
            if d["date"] == ed:
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


def _set_date_ticks(ax, dates: list[str]) -> None:
    n = len(dates)
    step = max(1, n // 8)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=30, ha="right")


def _chart_stock_price_line(daily: list[dict], dates: list[str], earnings_dates: list[str], out: str) -> str:
    """历史形态（仅 close）的收盘折线渲染（升级前行为，原样保留）。"""
    closes = [d["close"] for d in daily]
    fig, ax = plt.subplots(figsize=_FIGSIZE_WIDE)
    ax.plot(dates, closes, color=_C_BLUE, linewidth=1.5)
    ax.fill_between(range(len(dates)), closes, alpha=0.1, color=_C_BLUE)
    ax.set_ylabel("股价（元）", fontsize=10)
    ax.set_xlabel("日期", fontsize=10)
    _style_ax(ax, "股价趋势")
    _mark_earnings(ax, daily, closes, earnings_dates)
    _set_date_ticks(ax, dates)
    fig.tight_layout()
    return _save_fig(fig, out, "chart_stock_price")


def _chart_stock_price(data: dict, out: str) -> str | None:
    """股价 K 线图（update-price-chart-kline）：蜡烛主图 + MA 均线 + 决策价位线 + 成交量副图。

    历史形态（缺 OHLC 字段）降级为收盘折线，保持升级前渲染。
    """
    daily = data.get("price", {}).get("daily", [])
    if len(daily) < 10:
        return None
    dates = [d["date"] for d in daily]
    earnings_dates = data.get("price", {}).get("earnings_dates", [])
    has_ohlc = all(
        d.get("open") is not None and d.get("high") is not None and d.get("low") is not None
        for d in daily
    )
    if not has_ohlc:
        return _chart_stock_price_line(daily, dates, earnings_dates, out)

    ma = data.get("price", {}).get("ma", {})
    levels = data.get("price", {}).get("decision_levels", {})

    x = np.arange(len(dates))
    opens = [d["open"] for d in daily]
    highs = [d["high"] for d in daily]
    lows = [d["low"] for d in daily]
    closes = [d["close"] for d in daily]
    colors = [_C_RED if c >= o else _C_GREEN for o, c in zip(opens, closes)]
    # 蜡烛实体宽度随样本数自适应（250 根时约 0.12）；十字星给最小可见高度
    candle_w = max(0.12, min(0.8, 30.0 / len(dates)))
    price_range = max(highs) - min(lows) or 1.0
    body = [max(abs(c - o), candle_w * 1e-3 * price_range) for o, c in zip(opens, closes)]

    fig = plt.figure(figsize=(_FIGSIZE_WIDE[0], _FIGSIZE_WIDE[1] + 1.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.06)
    ax = fig.add_subplot(gs[0])
    ax_vol = fig.add_subplot(gs[1])

    ax.vlines(x, lows, highs, colors=colors, linewidth=0.7)
    ax.bar(x, body, bottom=[min(o, c) for o, c in zip(opens, closes)], width=candle_w, color=colors)

    for key, color, lw in _STOCK_PRICE_MA_SPECS:
        series = ma.get(key) or []
        if len(series) == len(dates):
            ax.plot(x, _nan_series(series), color=color, linewidth=lw, label=key.upper())
    if any(len(ma.get(key) or []) == len(dates) for key, _, _ in _STOCK_PRICE_MA_SPECS):
        ax.legend(fontsize=8, loc="upper left")

    for key, label, color in _DECISION_LEVEL_SPECS:
        if key in levels:
            ax.axhline(y=levels[key], color=color, linewidth=1.0, linestyle="--", alpha=0.85)
            ax.annotate(
                label,
                xy=(1.0, levels[key]),
                xycoords=("axes fraction", "data"),
                xytext=(3, 0),
                textcoords="offset points",
                fontsize=8,
                color=color,
                va="center",
            )

    _mark_earnings(ax, daily, closes, earnings_dates)
    ax.set_ylabel("股价（元）", fontsize=10)
    _style_ax(ax, "股价 K 线（MA5/20/60，虚线为决策价位）")
    ax.tick_params(labelbottom=False)

    volumes = [d.get("volume") or 0 for d in daily]
    ax_vol.bar(x, volumes, width=candle_w, color=colors, alpha=0.7)
    ax_vol.set_ylabel("成交量", fontsize=9)
    ax_vol.set_xlabel("日期", fontsize=10)
    _style_ax(ax_vol)
    _set_date_ticks(ax_vol, dates)

    fig.tight_layout()
    return _save_fig(fig, out, "chart_stock_price")
```

注意：`_style_ax(ax_vol)` 不传 title（避免副图出现第二标题），其余样式（facecolor/grid/spines）由 `_style_ax` 统一处理。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_charts_kline_data.py tests/test_charts_none_series.py tests/test_charts_cjk_font.py -v`
Expected: PASS（新测试全绿 + 既有图表回归）

- [ ] **Step 5: Lint + type check + Commit**

```bash
uv run ruff check src/finance_agent/charts.py tests/test_charts_kline_data.py
uv run mypy src/finance_agent/charts.py
git add tests/test_charts_kline_data.py src/finance_agent/charts.py
git commit -m "feat(charts): 股价图 PNG 重绘蜡烛+成交量副图+MA+决策价位线, close-only 降级保留 (update-price-chart-kline)"
```

---

### Task 3: 前端类型扩展 + StockPriceChart K 线双分支

**Files:**
- Modify: `frontend/src/types.ts`（ChartData.price 类型，L186-192）
- Modify: `frontend/src/Charts.tsx`（ChartCard L49-54 加 testId prop；StockPriceChart L204-236 重写）
- Test: `frontend/src/test/stockPriceKline.test.tsx`（新建）；`frontend/src/test/chartsMarkLine.test.tsx`（baseData 补足 12 条使其非空断言）

**Interfaces:**
- Consumes: Task 1 产出的 chart_data JSON 契约（`price.ma`/`price.decision_levels`/`daily[].open|high|low|volume`）
- Produces: `ChartData` 类型新字段（optional，历史数据合法）；`ChartCard` 新 optional prop `testId?: string`；`data-testid="chart-stock-price"` 挂在股价图卡片根 div（Task 4 E2E selector）

- [ ] **Step 1: Write the failing test**

创建 `frontend/src/test/stockPriceKline.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { StockPriceChart } from '../Charts'
import type { ChartData } from '../types'

// update-price-chart-kline：股价图 K 线双分支契约。
// OHLC 在场 → candlestick（数据序 [open,close,low,high]）+ 成交量副图 + MA 叠加
// + 决策价位 markLine（yAxis 坐标）；仅收盘价（历史会话）→ 收盘折线降级，不报错。

const captured: unknown[] = []
vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: unknown }) => {
    captured.push(option)
    return null
  },
}))

type DailyEntry = ChartData['price']['daily'][number]

function makeDaily(n: number, withOHLC: boolean): DailyEntry[] {
  return Array.from({ length: n }, (_, i) => {
    const close = 10 + i * 0.1
    const entry: DailyEntry = {
      date: `2026-01-${String(i + 1).padStart(2, '0')}`,
      close,
    }
    if (withOHLC) {
      entry.open = close - 0.05
      entry.high = close + 0.2
      entry.low = close - 0.2
      entry.volume = 1000 + i
    }
    return entry
  })
}

function baseData(withOHLC: boolean): ChartData {
  return {
    stock_code: '600519',
    stock_name: '贵州茅台',
    annual: [],
    growth: { years: [], revenue_growth: [], profit_growth: [] },
    price: {
      daily: makeDaily(12, withOHLC),
      earnings_dates: ['2026-01-03'],
      ma: withOHLC
        ? { ma5: Array.from({ length: 12 }, (_, i) => (i >= 4 ? 10.1 : null)), ma20: [], ma60: [] }
        : undefined,
      decision_levels: withOHLC
        ? { entry_price: 11.2, stop_loss: 9.9, target_price: 12.5 }
        : undefined,
    },
    kpi: {},
    market_share: null,
  } as ChartData
}

function seriesOf(opt: any): any[] {
  return Array.isArray(opt?.series) ? opt.series : [opt?.series]
}

describe('StockPriceChart K 线分支', () => {
  beforeEach(() => {
    captured.length = 0
  })

  it('OHLC 在场渲染 candlestick + 成交量副图 + MA 叠加 + 决策价位 markLine', () => {
    render(<StockPriceChart data={baseData(true)} />)
    const opt: any = captured[captured.length - 1]
    const candle = seriesOf(opt).find((s) => s?.type === 'candlestick')
    expect(candle).toBeDefined()
    // ECharts 蜡烛数据序 [open, close, low, high]
    expect(candle.data[0]).toEqual([9.95, 10, 9.8, 10.2])
    expect(seriesOf(opt).some((s) => s?.name === '成交量' && s?.type === 'bar')).toBe(true)
    expect(seriesOf(opt).filter((s) => typeof s?.name === 'string' && s.name.startsWith('MA')).length).toBe(3)
    const mlItems: any[] = candle.markLine.data
    expect(mlItems.filter((i) => 'xAxis' in i).length).toBe(1) // 财报日
    expect(mlItems.filter((i) => i?.yAxis === 11.2).length).toBe(1) // 入场
    expect(mlItems.filter((i) => i?.yAxis === 9.9).length).toBe(1) // 止损
    expect(mlItems.filter((i) => i?.yAxis === 12.5).length).toBe(1) // 目标
  })

  it('仅收盘价（历史会话）降级为收盘折线，无 candlestick', () => {
    render(<StockPriceChart data={baseData(false)} />)
    const opt: any = captured[captured.length - 1]
    expect(seriesOf(opt).some((s) => s?.type === 'candlestick')).toBe(false)
    expect(seriesOf(opt)[0]?.type).toBe('line')
  })

  it('OHLC 半缺（open 缺失）按降级处理', () => {
    const d = baseData(true)
    ;(d.price.daily as any[]).forEach((e) => delete e.open)
    render(<StockPriceChart data={d} />)
    const opt: any = captured[captured.length - 1]
    expect(seriesOf(opt).some((s) => s?.type === 'candlestick')).toBe(false)
  })

  it('决策价位半缺只画在场价位', () => {
    const d = baseData(true)
    d.price.decision_levels = { entry_price: 11.2 }
    render(<StockPriceChart data={d} />)
    const opt: any = captured[captured.length - 1]
    const candle = seriesOf(opt).find((s) => s?.type === 'candlestick')
    const yItems: any[] = candle.markLine.data.filter((i: any) => 'yAxis' in i)
    expect(yItems.length).toBe(1)
    expect(yItems[0].yAxis).toBe(11.2)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/stockPriceKline.test.tsx`
Expected: FAIL——现实现只有 line 分支，candlestick 断言不通过

- [ ] **Step 3: Write minimal implementation**

（a）`frontend/src/types.ts` 的 `ChartData.price`（L186-192）替换为：

```ts
  price: {
    daily: Array<{
      date: string
      close: number
      open?: number | null
      high?: number | null
      low?: number | null
      volume?: number | null
    }>
    earnings_dates: string[]
    ma?: { ma5: (number | null)[]; ma20: (number | null)[]; ma60: (number | null)[] }
    decision_levels?: { entry_price?: number; stop_loss?: number; target_price?: number }
  }
```

（b）`frontend/src/Charts.tsx` 的 `ChartCard`（L49-54）加 testId prop：

```tsx
function ChartCard({
  title,
  children,
  testId,
}: {
  title: string
  children: React.ReactNode
  testId?: string
}) {
  return (
    <div className="border rounded-xl p-4" style={{ background: 'var(--card)', borderColor: 'var(--border-neutral-l1)' }} data-testid={testId}>
      <h4 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-default)' }}>{title}</h4>
      {children}
    </div>
  )
}
```

（c）`StockPriceChart`（L204-236）整体替换：

```tsx
// ── P1: Stock price（update-price-chart-kline：K 线主图+MA 均线+决策价位线+成交量副图；
// 历史 chartData 仅含收盘价时降级为收盘折线）──
export function StockPriceChart({ data }: { data: ChartData }) {
  const daily = data.price.daily
  if (daily.length < 10) return null
  const dates = daily.map(d => d.date)
  const hasOHLC = daily[0].open != null && daily[0].high != null && daily[0].low != null
  const theme = getChartTheme()

  if (!hasOHLC) {
    const closes = daily.map(d => d.close)
    const markLines = data.price.earnings_dates.map(ed => ({
      xAxis: ed,
      label: { show: false },
      lineStyle: { color: theme.coral, type: 'dashed', opacity: 0.5 },
    }))
    const option = {
      ...baseOption(theme),
      xAxis: { type: 'category', data: dates, axisLabel: { color: theme.axisLabelColor, fontSize: 9, rotate: 30 }, axisLine: { lineStyle: { color: theme.splitLine } } },
      yAxis: { type: 'value', name: '元', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 15, bottom: 0 }],
      series: [{ type: 'line', data: closes, itemStyle: { color: theme.brand }, areaStyle: { opacity: 0.08 }, symbol: 'none', markLine: { data: markLines, symbol: 'none' } }],
    }
    return (
      <ChartCard title="股价趋势（红色虚线为年报发布日）" testId="chart-stock-price">
        <ReactECharts option={option} style={{ height: '300px' }} />
      </ChartCard>
    )
  }

  // K 线分支：ECharts 蜡烛数据序 [open, close, low, high]
  const ohlc = daily.map(d => [d.open, d.close, d.low, d.high])
  const volumes = daily.map(d => ({
    value: d.volume ?? 0,
    itemStyle: { color: (d.close ?? 0) >= (d.open ?? 0) ? theme.coral : theme.mint, opacity: 0.7 },
  }))
  const markLineData: unknown[] = data.price.earnings_dates.map(ed => ({
    xAxis: ed,
    label: { show: false },
    lineStyle: { color: theme.coral, type: 'dashed', opacity: 0.5 },
  }))
  const levels = data.price.decision_levels
  if (levels?.entry_price != null) {
    markLineData.push({ yAxis: levels.entry_price, label: { formatter: '入场', position: 'insideEndTop', color: theme.sky }, lineStyle: { color: theme.sky, type: 'dashed' } })
  }
  if (levels?.stop_loss != null) {
    markLineData.push({ yAxis: levels.stop_loss, label: { formatter: '止损', position: 'insideEndBottom', color: theme.mint }, lineStyle: { color: theme.mint, type: 'dashed' } })
  }
  if (levels?.target_price != null) {
    markLineData.push({ yAxis: levels.target_price, label: { formatter: '目标', position: 'insideEndTop', color: theme.coral }, lineStyle: { color: theme.coral, type: 'dashed' } })
  }
  const maLine = (key: 'ma5' | 'ma20' | 'ma60', color: string) => ({
    name: key.toUpperCase(),
    type: 'line',
    xAxisIndex: 0,
    yAxisIndex: 0,
    data: data.price.ma?.[key] ?? [],
    symbol: 'none',
    lineStyle: { width: 1, color },
    itemStyle: { color },
  })

  const option = {
    ...baseOption(theme),
    legend: { data: ['MA5', 'MA20', 'MA60'], bottom: 20, textStyle: { color: theme.textColor, fontSize: 10 } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipTextColor },
      axisPointer: { type: 'cross' },
    },
    grid: [
      { left: '8%', right: '8%', top: '6%', height: '58%' },
      { left: '8%', right: '8%', top: '72%', height: '14%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: theme.splitLine } } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { color: theme.axisLabelColor, fontSize: 9, rotate: 30 }, axisLine: { lineStyle: { color: theme.splitLine } } },
    ],
    yAxis: [
      { type: 'value', scale: true, gridIndex: 0, name: '元', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
      { type: 'value', gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1] },
      { type: 'slider', xAxisIndex: [0, 1], height: 15, bottom: 0 },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        itemStyle: { color: theme.coral, color0: theme.mint, borderColor: theme.coral, borderColor0: theme.mint },
        markLine: { data: markLineData, symbol: 'none' },
      },
      maLine('ma5', theme.amber),
      maLine('ma20', theme.violet),
      maLine('ma60', theme.teal),
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes },
    ],
  }

  return (
    <ChartCard title="股价 K 线（MA5/20/60；虚线为入场/止损/目标价）" testId="chart-stock-price">
      <ReactECharts option={option} style={{ height: '380px' }} />
    </ChartCard>
  )
}
```

（d）`frontend/src/test/chartsMarkLine.test.tsx` 的 `baseData.price.daily` 由 2 条扩为 12 条（原测试对 StockPriceChart 是空断言——组件因 `length < 10` 直接返回 null，markLine 断言空洞；扩足后断言真实生效）：

```tsx
  price: {
    daily: Array.from({ length: 12 }, (_, i) => ({
      date: `2026-08-${String(i + 1).padStart(2, '0')}`,
      close: 1700 + i,
    })),
    earnings_dates: ['2026-08-01'],
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/stockPriceKline.test.tsx src/test/chartsMarkLine.test.tsx && npx tsc -p tsconfig.json --noEmit`
Expected: PASS + 无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/Charts.tsx frontend/src/test/stockPriceKline.test.tsx frontend/src/test/chartsMarkLine.test.tsx
git commit -m "feat(frontend): 股价图 K 线双分支(candlestick+成交量+MA+决策价位线/close-only 降级) (update-price-chart-kline)"
```

---

### Task 4: E2E spec——深度分析完成后报告渲染股价 K 线图

**Files:**
- Create: `tests/e2e/playwright/tests/report-kline-chart.spec.ts`
- Modify: `tests/e2e/playwright/playwright.timeline.config.ts`（testMatch 登记新 spec）
- Modify: `tests/e2e/playwright/playwright.config.ts`（testIgnore 排除——依赖 pipeline 后端 8002）

**Interfaces:**
- Consumes: Task 3 的 `data-testid="chart-stock-price"`；与 `report-export.spec.ts` 相同的管线端口对（前端 5175 → 后端 8002，`STUB_SCENARIO=pipeline`，`playwright.timeline.config.ts` 拉起）及其已真实探索的 selector（模式下拉 / `send-button` / 报告卡标题「贵州茅台（600519）」）
- Produces: E2E 门禁用例；timeline config 新 spec 注册项

**Selector 来源说明**：复用 report-export.spec.ts 注释中记录的真实 DOM 探索结论（同一流程）；图表卡片 selector 为本 delta 在 Task 3 新增的 testid（testid 优先级，符合红线）。历史会话（仅 close）降级分支由 Task 3 组件测试覆盖——管线 stub 恒产 OHLC，E2E 无法构造历史形态会话，不作虚假覆盖（delta tasks.md 已按此口径修订）。

- [ ] **Step 1: Write the failing E2E spec**

创建 `tests/e2e/playwright/tests/report-kline-chart.spec.ts`：

```ts
import { test, expect } from '@playwright/test'

/**
 * 股价 K 线图 E2E（update-price-chart-kline delta）
 *
 * 覆盖：深度分析管线完成后，报告图表区渲染「股价 K 线」卡片
 *（data-testid=chart-stock-price，ECharts candlestick 落地为 canvas）。
 * 卡片标题 /股价 K 线/ 断言证明前端走的是 K 线分支而非折线降级
 * （折线分支标题为「股价趋势（红色虚线为年报发布日）」）。
 *
 * 环境：与 report-export.spec.ts 同一管线端口对（5175 → 8002
 * STUB_SCENARIO=pipeline，playwright.timeline.config.ts 拉起）；
 * selector 复用该 spec 已真实探索的 DOM 结论 + 本 delta 新增 testid。
 *
 * 历史会话（仅 close）降级分支由组件测试 stockPriceKline.test.tsx 覆盖
 *（管线 stub 恒产 OHLC，E2E 无法构造历史形态会话，不作虚假覆盖）。
 */

test.setTimeout(240_000)

test('深度分析完成后报告渲染股价 K 线图', async ({ page }) => {
  // 1. 进入应用并注入测试 API Key（管线端口对 5175 → 8002）
  await page.goto('http://localhost:5175')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-kline-chart')
  })
  await page.reload()

  // 2. 显式选中深度研究模式（EmptyState 两步下拉）
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()

  // 3. 发送深度分析请求（stub 确定性触发 5 层管线）
  await page.getByPlaceholder(/输入/).fill('深度分析600519')
  await page.getByTestId('send-button').click()

  // 4. 报告完成终态：报告卡标题出现
  await expect(
    page.getByRole('heading', { name: '贵州茅台（600519）' }),
  ).toBeVisible({ timeout: 150_000 })

  // 5. 股价 K 线卡片可见，标题证明 K 线分支（非折线降级）
  const klineCard = page.getByTestId('chart-stock-price')
  await expect(klineCard).toBeVisible({ timeout: 30_000 })
  await expect(klineCard.getByRole('heading', { name: /股价 K 线/ })).toBeVisible()
  // ECharts 成功挂载时 canvas 渲染（toBeVisible 自带非零包围盒断言；
  // option 构造崩溃时 ECharts 不产 canvas，本断言变红）
  await expect(klineCard.locator('canvas').first()).toBeVisible()
})
```

- [ ] **Step 2: Register the spec in both configs**

`tests/e2e/playwright/playwright.timeline.config.ts` 的 `testMatch` 数组，在 `'report-export.spec.ts',` 条目后追加：

```ts
  // 股价 K 线图：依赖 STUB_SCENARIO=pipeline 的 5 层管线后端（8002/5175），
  // 与 report-export 同环境（update-price-chart-kline）
  'report-kline-chart.spec.ts',
```

`tests/e2e/playwright/playwright.config.ts` 的 `testIgnore` 数组，在 `'report-export.spec.ts',` 条目后追加：

```ts
    // 股价 K 线图同依赖 pipeline 环境（8002/5175），timeline config 运行，默认排除
    'report-kline-chart.spec.ts',
```

- [ ] **Step 3: Run the E2E spec**

Run: `cd tests/e2e/playwright && npx playwright test --config playwright.timeline.config.ts report-kline-chart`
Expected: PASS（240s 预算内完成管线 + 图表渲染；600519 真实行情经 fetch_kline 三级回退取得）

- [ ] **Step 4: Run scan + review toolchain（E2E 任务卡附加门禁）**

Run: `bash scripts/e2e/scan.sh tests/e2e/playwright/tests/report-kline-chart.spec.ts 2>/dev/null || npx skills run e2e-skills scan tests/e2e/playwright/tests/report-kline-chart.spec.ts`（以实际安装的 scan.sh 路径为准；无脚本时由 task-reviewer 执行 e2e-reviewer 深审）
Expected: P0 反模式为零（本 spec 无恒真断言、无 waitForTimeout、无 route.fulfill、无手动取值断言）

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/playwright/tests/report-kline-chart.spec.ts tests/e2e/playwright/playwright.timeline.config.ts tests/e2e/playwright/playwright.config.ts
git commit -m "test(e2e): 深度分析报告股价 K 线图渲染 spec + 双 config 登记 (update-price-chart-kline)"
```

---

### Task 5: 全量验证与 delta 收尾

**Files:**
- Modify: `openspec/changes/update-price-chart-kline/tasks.md`（回填勾选）
- Create: `tests/validation/2026-10-06-update-price-chart-kline-validation.md`（人工验证报告骨架，实跑后补结论）

**Interfaces:**
- Consumes: Task 1-4 全部完成后的工作区
- Produces: 验证证据（命令输出）、勾选完毕的 tasks.md、人工验证报告（待 owner 实跑补「验证人/结论」）

- [ ] **Step 1: 后端全量回归**

Run: `uv run ruff check && uv run mypy && uv run pytest -x -q`
Expected: 全绿（全量 pytest 需 Docker/Langfuse 在线——若卡 2% 先查容器，见 docs/incidents 惯例）

- [ ] **Step 2: 前端全量回归**

Run: `cd frontend && npm test && npm run build`
Expected: 全绿 + 构建成功

- [ ] **Step 3: E2E 门禁（交互类变更硬关卡）**

Run: `cd tests/e2e/playwright && npx playwright test --config playwright.timeline.config.ts && npx playwright test`
Expected: 两套配置全绿；失败先 `playwright-debugger` 诊断再修复，禁止带病进人工验证

- [ ] **Step 4: 回填 tasks.md + 落验证报告骨架**

`openspec/changes/update-price-chart-kline/tasks.md` 七项全勾（人工验证项勾选待报告落盘后）；创建 `tests/validation/2026-10-06-update-price-chart-kline-validation.md`，含：验证项表（K 线 PNG 观感/前端交互/暗色可读/历史会话回放降级/决策价位线位置合理性）、E2E 门禁证据路径、结论区（待 owner 实跑后填写）。

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/update-price-chart-kline/tasks.md tests/validation/2026-10-06-update-price-chart-kline-validation.md
git commit -m "test(validation): update-price-chart-kline 全量验证收尾+人工验证报告骨架 (update-price-chart-kline)"
```

---

## Self-Review 记录

1. **Spec 覆盖**：Requirement「K 线图表数据采集」→ Task 1（OHLCV/MA/决策价位/降级逐 scenario 有测试）；「K 线图双端渲染」→ Task 2（PNG：蜡烛+副图+均线+价位线+财报标注）+ Task 3（前端：candlestick/tooltip/dataZoom/markLine/红涨绿跌/主题变量）+ Task 4（E2E 集成）；「历史会话后向兼容」→ Task 2（PNG close-only 降级）+ Task 3（折线降级分支测试 + 半缺测试）。无缺口。
2. **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码；Step 4 的 scan.sh 调用给出命令与兜底（工具链实际路径执行时确认）。
3. **类型一致性**：`chart_data["price"]["ma"]` 键名 ma5/ma20/ma60 贯穿 Task 1/2/3；`decision_levels` 键名 entry_price/stop_loss/target_price 贯穿 Task 1/2/3（与 state 键同名）；`testId` prop 与 `data-testid="chart-stock-price"` 贯穿 Task 3/4；`_chart_stock_price_line`/`_mark_earnings`/`_set_date_ticks` 签名在 Task 2 内自洽。
