"""TDD tests: 图表数据完整性（add-chart-data-integrity R3/R4/R5）。

背景（2026-10-05 光大银行 601818 报告）：
- 年度图横轴倒序（2025 在左），同比增速图视觉上把「恶化」读成「改善」；
- 热力图 2021–2024 四行缺数据被填 0.0 渲染；
- 增速vs股价图股价涨幅序列整体缺失时静默只画一半；
- 现金流/总资产图数据标签为原始元（162907000000.0），轴标却是「亿元」。

通过 monkeypatch `_save_fig` 捕获 figure 做断言（生成器保存后即 close）。
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pytest

from finance_agent import charts


@pytest.fixture
def capture_figs(monkeypatch, tmp_path):
    """捕获各图表函数构建的 figure，供断言内部绘制内容。"""
    captured: dict[str, plt.Figure] = {}

    def fake_save(fig, output_dir, name):
        captured[name] = fig
        plt.close(fig)
        return os.path.join(output_dir, f"{name}.png")

    monkeypatch.setattr(charts, "_save_fig", fake_save)
    return captured


def _annual_desc() -> list[dict]:
    """按数据契约构造降序年度序列（index 0 = 最新）。金额单位：元。"""
    return [
        {
            "year": "2025",
            "revenue": 1.26311e11,
            "net_profit": 3.8826e10,
            "ocf": 1.62907e11,
            "total_assets": 7.165319e12,
            "equity": 5.00451e11,
            "gross_margin": 30.0,
            "net_margin": 30.7,
            "roe": 7.0,
            "debt_ratio": 91.5,
            "contract_liab": None,
        },
        {
            "year": "2024",
            "revenue": 1.35413e11,
            "net_profit": 4.1696e10,
            "ocf": -2.04802e11,
            "total_assets": 6.96368e12,
            "equity": 4.80451e11,
            "gross_margin": 30.9,
            "net_margin": 30.8,
            "roe": 7.93,
            "debt_ratio": 91.5,
            "contract_liab": None,
        },
        {
            "year": "2023",
            "revenue": 1.45685e11,
            "net_profit": None,
            "ocf": None,
            "total_assets": 6.77295e12,
            "equity": None,
            "gross_margin": None,
            "net_margin": 28.0,
            "roe": None,
            "debt_ratio": 91.8,
            "contract_liab": None,
        },
        {
            "year": "2022",
            "revenue": 1.51632e11,
            "net_profit": 4.4804e10,
            "ocf": -5.6398e10,
            "total_assets": 6.30510e12,
            "equity": 4.40451e11,
            "gross_margin": 29.9,
            "net_margin": 29.6,
            "roe": 10.27,
            "debt_ratio": 91.9,
            "contract_liab": None,
        },
        {
            "year": "2021",
            "revenue": 1.52751e11,
            "net_profit": 4.3407e10,
            "ocf": -1.12242e11,
            "total_assets": 5.90207e12,
            "equity": 4.20451e11,
            "gross_margin": 28.6,
            "net_margin": 28.4,
            "roe": 9.28,
            "debt_ratio": 91.8,
            "contract_liab": None,
        },
    ]


def _chart_data(**overrides) -> dict:
    data = {
        "annual": _annual_desc(),
        "growth": {
            "years": ["2025", "2024", "2023", "2022"],
            "revenue_growth": [-6.72, -7.05, -3.92, -0.73],
            "profit_growth": [-6.87, 2.03, -8.8, 3.21],
        },
        "price": {"daily": [], "earnings_dates": []},
        "kpi": {},
    }
    data.update(overrides)
    return data


# ── R3: 年度图表时间轴升序 ──


class TestAscendingTimeAxis:
    def test_roe_line_ascending(self, capture_figs):
        charts._chart_roe(_chart_data(), "out")
        fig = capture_figs["chart_roe"]
        ax = fig.axes[0]
        assert [t.get_text() for t in ax.get_xticklabels()] == [
            "2021",
            "2022",
            "2023",
            "2024",
            "2025",
        ]

    def test_revenue_profit_bars_ascending(self, capture_figs):
        charts._chart_revenue_profit(_chart_data(), "out")
        fig = capture_figs["chart_revenue_profit"]
        ax1 = fig.axes[0]
        labels = [t.get_text() for t in ax1.get_xticklabels()]
        assert labels == ["2021", "2022", "2023", "2024", "2025"]
        # 营收柱从左到右对应 2021→2025 的原始值 /1e8
        heights = [p.get_height() for p in ax1.patches[:5]]
        assert heights == pytest.approx([1527.51, 1516.32, 1456.85, 1354.13, 1263.11], rel=1e-4)

    def test_cashflow_bars_ascending(self, capture_figs):
        charts._chart_cashflow(_chart_data(), "out")
        fig = capture_figs["chart_cashflow"]
        ax = fig.axes[0]
        assert [t.get_text() for t in ax.get_xticklabels()] == [
            "2021",
            "2022",
            "2023",
            "2024",
            "2025",
        ]

    def test_growth_lines_ascending(self, capture_figs):
        charts._chart_growth(_chart_data(), "out")
        fig = capture_figs["chart_growth"]
        ax = fig.axes[0]
        xdata = list(ax.lines[0].get_xdata())
        assert xdata == ["2022", "2023", "2024", "2025"]
        # 数值随序反转：2022 最旧 → -0.73
        assert list(ax.lines[0].get_ydata()) == [-0.73, -3.92, -7.05, -6.72]

    def test_growth_vs_price_ascending(self, capture_figs):
        daily = [{"date": f"2025-06-{d:02d}", "close": 3.0 + d * 0.01} for d in range(1, 11)]
        daily += [{"date": f"2026-06-{d:02d}", "close": 3.2 + d * 0.01} for d in range(1, 11)]
        data = _chart_data(price={"daily": daily, "earnings_dates": []})
        charts._chart_growth_vs_price(data, "out")
        fig = capture_figs["chart_growth_vs_price"]
        ax = fig.axes[0]
        assert [t.get_text() for t in ax.get_xticklabels()] == ["2022", "2023", "2024", "2025"]

    def test_heatmap_rows_ascending(self, capture_figs):
        daily = [{"date": f"2026-06-{d:02d}", "close": 3.0} for d in range(1, 32)]
        data = _chart_data(
            price={
                "daily": daily,
                "earnings_dates": ["2025-12-31", "2024-12-31", "2023-12-31"],
            }
        )
        charts._chart_heatmap(data, "out")
        fig = capture_figs["chart_heatmap"]
        ax = fig.axes[0]
        labels = [t.get_text() for t in ax.get_yticklabels()]
        assert labels == ["2023年报", "2024年报", "2025年报"]

    def test_dashboard_ascending(self, capture_figs):
        charts._chart_dashboard(_chart_data(), "out")
        fig = capture_figs["chart_dashboard"]
        roe_ax = fig.axes[2]
        xdata = list(roe_ax.lines[0].get_xdata())
        assert xdata == ["2021", "2022", "2023", "2024", "2025"]


# ── R4: 缺数据禁止填 0 ──


class TestMissingDataSemantics:
    def test_heatmap_missing_cells_not_zero(self, capture_figs):
        """K 线只覆盖近一月：2023/2024 年报行窗口全缺 → 「缺」标注，MUST NOT 0.0。"""
        daily = [{"date": f"2026-06-{d:02d}", "close": 3.0 + d * 0.01} for d in range(1, 32)]
        data = _chart_data(
            price={
                "daily": daily,
                "earnings_dates": ["2025-12-31", "2024-12-31", "2023-12-31"],
            }
        )
        charts._chart_heatmap(data, "out")
        fig = capture_figs["chart_heatmap"]
        ax = fig.axes[0]
        texts = [t.get_text() for t in ax.texts]
        assert "缺" in texts, "窗口外单元格应渲染缺失标注"
        assert "0.0" not in texts, "缺数据不得渲染为 0.0"

    def test_growth_vs_price_all_missing_price_shows_placeholder(self, capture_figs):
        """股价涨幅序列整体缺失 → 图内占位说明，不得静默只画一半。"""
        daily = [{"date": f"2025-06-{d:02d}", "close": 3.0 + d * 0.01} for d in range(1, 11)]
        data = _chart_data(price={"daily": daily, "earnings_dates": []})
        charts._chart_growth_vs_price(data, "out")
        fig = capture_figs["chart_growth_vs_price"]
        ax = fig.axes[0]
        placeholder = " ".join(t.get_text() for t in ax.texts)
        assert "股价涨幅" in placeholder and "不足" in placeholder
        # 财务增速柱仍正常渲染
        finite = [p for p in ax.patches if np.isfinite(p.get_height())]
        assert finite, "营收/净利增速柱不应受股价涨幅缺失影响"

    def test_bars_skip_missing_value_not_zero(self, capture_figs):
        """序列级缺失（2023 ocf=None）→ 该年无柱，不得画 0 高柱。"""
        charts._chart_cashflow(_chart_data(), "out")
        fig = capture_figs["chart_cashflow"]
        ax = fig.axes[0]
        heights = [p.get_height() for p in ax.patches]
        assert np.isnan(heights[2]), "2023 年 ocf 缺失应无柱（nan），实际渲染为 0 高柱"
        # 数据标签跳过缺失年
        labels = [t.get_text() for t in ax.texts]
        assert all("nan" not in s.lower() for s in labels)

    def test_revenue_profit_skip_missing_value(self, capture_figs):
        charts._chart_revenue_profit(_chart_data(), "out")
        fig = capture_figs["chart_revenue_profit"]
        ax2 = fig.axes[1]  # 归母净利润轴
        heights = [p.get_height() for p in ax2.patches]
        assert np.isnan(heights[2]), "2023 净利润缺失（None）应无柱"


# ── R5: 金额单位一致（亿元） ──


class TestYiUnitConsistency:
    def test_cashflow_values_and_labels_in_yi(self, capture_figs):
        charts._chart_cashflow(_chart_data(), "out")
        fig = capture_figs["chart_cashflow"]
        ax = fig.axes[0]
        heights = [p.get_height() for p in ax.patches]
        assert heights[-1] == pytest.approx(1629.07, rel=1e-4), (
            "162907000000.0 元应渲染为 1629.07 亿元（升序后 2025 在最右）"
        )
        assert "亿元" in ax.get_ylabel()
        # 最新年（2025，最右柱）数据标签为亿元
        label_2025 = next(t.get_text() for t in ax.texts if t.get_text().startswith("1629"))
        assert label_2025 == "1629.1"

    def test_revenue_profit_values_in_yi(self, capture_figs):
        charts._chart_revenue_profit(_chart_data(), "out")
        fig = capture_figs["chart_revenue_profit"]
        ax1, ax2 = fig.axes[0], fig.axes[1]
        rev_h = [p.get_height() for p in ax1.patches[:5]]
        assert rev_h[-1] == pytest.approx(1263.11, rel=1e-4)
        profit_h = [p.get_height() for p in ax2.patches]
        assert profit_h[0] == pytest.approx(434.07, rel=1e-4), "4.3407e10 元应渲染为 434.07 亿元"
        assert "亿元" in ax1.get_ylabel() and "亿元" in ax2.get_ylabel()
        # 无科学计数偏移量纲
        assert ax1.get_yaxis().get_offset_text().get_text() == ""

    def test_assets_values_in_yi(self, capture_figs):
        charts._chart_assets(_chart_data(), "out")
        fig = capture_figs["chart_assets"]
        ax = fig.axes[0]
        heights = [p.get_height() for p in ax.patches]
        # 总资产 2021: 5.90207e12 元 → 59020.7 亿
        assert heights[0] == pytest.approx(59020.7, rel=1e-4)
        assert heights[5] == pytest.approx(4204.51, rel=1e-4), "归母权益 4.20451e11 元 → 4204.51 亿"
