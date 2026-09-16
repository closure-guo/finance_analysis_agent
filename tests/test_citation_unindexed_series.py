"""infer-period-for-unindexed-series：未索引序列的期次定位 + 根域术语别名。

真实样本来源（2026-09-14 实测复判，`tests/data/citation_r2_claims.json` /
`citation_r4_claims.json`）：
- r2 6 条 `quarterly_trend.<series>` 裸引用（无索引段）在 `period` 字段缺省时
  恒判 `FAIL path_unresolvable`；带 `period=2026Q2` 的等价 claim PASS——
  判死的是申报形式而非数值对错（incident 026 同型：校验器限制记成分析师错误）。
- r4 1 条 `quarterly_trend.net_profit.0`（招行 385.93 亿元）撞词表内不一致判
  `FAIL semantic_term_mismatch`，数值与真值一致。
"""

from __future__ import annotations

import pandas as pd
import pytest

from finance_agent.citation import Claim, verify_claims


def _quarterly_trend() -> dict:
    """compute.py::_calc_quarterly_trend 真实形状（quarters 平行列表，net_profit 单位亿元）。"""
    return {
        "quarters": ["2025Q3", "2025Q4", "2026Q1", "2026Q2"],
        "net_profit": [100.0, 19.22, 250.22, 385.93],
        "qoq": [-10.0, -74.11, 1200.0, 8.72],
        "yoy": [-5.0, -74.11, -55.38, 36.46],
        "warnings": [],
    }


def _state() -> dict:
    return {"quarterly_trend": _quarterly_trend()}


_BASE_CLAIM: dict = {
    "claim_type": "numerical",
    "source_type": "data",
    "field_ref": "quarterly_trend.yoy",
    "stated_value": 36.46,
    "interpretation": "2026Q2净利润同比增速36.46%",
    "metric_name": "同比",
    "direction": "positive",
}


def _claim(**kw) -> Claim:
    return Claim(**{**_BASE_CLAIM, **kw})


def _one(claim: Claim, state: dict | None = None):
    return verify_claims([claim], state or _state())[0]


class TestUnindexedSeriesPeriodInference:
    """裸序列引用：正文期次用于定位（不放松声明期次校验）。"""

    def test_real_r2_claim_passes_with_period_only_in_interpretation(self):
        # r2 真实样本：field_ref=quarterly_trend.yoy, stated=36.46, period 缺省
        r = _one(_claim(period=None))
        assert r.status == "PASS"
        assert r.ground_truth == pytest.approx(36.46)

    def test_declared_period_still_located(self):
        # 既有语义不回归：period 声明路径照常定位
        r = _one(_claim(period="2026Q2"))
        assert r.status == "PASS"

    def test_no_period_anywhere_degrades_to_unverifiable(self):
        # 期次不可知 → 不得判死（UNVERIFIABLE + 覆盖缺口）
        r = _one(_claim(period=None, interpretation="净利润同比增速36.46%"))
        assert r.status == "UNVERIFIABLE"
        assert r.coverage_gap is True
        assert r.bucket is None

    def test_ambiguous_periods_not_guessed(self):
        # 多个不同季度并存 → 不猜（r2 出现过多期次并列的叙事句）
        r = _one(_claim(period=None, interpretation="2025Q4同比-74.11%，2026Q2同比36.46%"))
        assert r.status == "UNVERIFIABLE"

    def test_wrong_value_with_period_still_fails(self):
        # 期次可定位但数值错 → 仍拦截（修复不得放松真错）
        r = _one(_claim(period=None, stated_value=99.9, interpretation="2026Q2同比99.9%"))
        assert r.status == "FAIL"
        assert r.bucket == "value_mismatch"

    def test_wrong_quarter_prose_against_other_quarter_value_fails(self):
        # 正文指 2026Q2 却写别期的数 → 定位到 Q2（36.46）后值级 FAIL
        r = _one(_claim(period=None, stated_value=15.0, interpretation="2026Q2同比15.0%"))
        assert r.status == "FAIL"
        assert r.bucket == "value_mismatch"

    def test_bare_net_profit_with_quarter_in_prose_passes(self):
        # r2 真实样本（美的）：field_ref 裸序列 + 正文带季度 + metric_name=净利润
        r = _one(
            _claim(
                field_ref="quarterly_trend.net_profit",
                stated_value=385.93,
                interpretation="2026Q2净利润385.93亿元，环比+8.72%",
                metric_name="净利润",
                period=None,
            )
        )
        assert r.status == "PASS", r.bucket

    def test_missing_series_key_still_fails(self):
        # 路径本身不存在（键拼错） → 维持 FAIL，降级不适用于此
        r = _one(
            _claim(
                field_ref="quarterly_trend.net_profitt",
                interpretation="2026Q2净利润同比增速36.46%",
                metric_name=None,
                period=None,
            )
        )
        assert r.status == "FAIL"
        assert r.bucket == "path_unresolvable"

    def test_period_check_still_uses_declared_value_only(self):
        # 声明期次与路径期次冲突 → 仍判 semantic_period_mismatch（推断值不得自我豁免）
        r = _one(
            _claim(
                field_ref="quarterly_trend.yoy.2026Q1",
                stated_value=-55.38,
                interpretation="2026Q2同比-55.38%",
                period="2026Q2",
            )
        )
        assert r.status == "FAIL"
        assert r.bucket == "semantic_period_mismatch"


class TestReferenceFormNormalization:
    """解析形态归一收口（r2/r4 语料重放暴露的三处真实误判）。"""

    def test_column_unit_suffix_normalized(self):
        """列名带单位后缀（真实列 `股息发放率(%)`），claim 省略后缀 → SHALL 命中。

        真实列名实测：`cache.db` 600519:indicators 存在 `加权每股收益(元)` /
        `净资产收益率(%)` / `股息发放率(%)`。r2 语料
        `financial_indicators.2025-12-31.股息发放率`（stated 20.4354）判
        path_unresolvable——该域无词表别名，缺口在列名单位后缀。
        """
        frame = pd.DataFrame(
            [
                {"日期": "2025-12-31", "股息发放率(%)": 20.4354},
                {"日期": "2024-12-31", "股息发放率(%)": 18.0},
            ]
        )
        r = _one(
            _claim(
                field_ref="financial_indicators.2025-12-31.股息发放率",
                stated_value=20.4354,
                interpretation="2025年股息发放率约20.44%",
                metric_name=None,
                period="2025",
                direction="flat",
            ),
            {"financial_indicators": frame},
        )
        assert r.status == "PASS", r.bucket

    def test_column_suffix_normalization_does_not_mix_metrics(self):
        """后缀归一不得把不同指标混同（摊薄 vs 加权 每股收益）。"""
        frame = pd.DataFrame(
            [{"日期": "2025-12-31", "加权每股收益(元)": 5.70, "摊薄每股收益(元)": 5.60}]
        )
        r = _one(
            _claim(
                field_ref="financial_indicators.2025-12-31.摊薄每股收益",
                stated_value=5.70,
                interpretation="2025年摊薄每股收益5.70元",
                metric_name=None,
                period="2025",
                direction="flat",
            ),
            {"financial_indicators": frame},
        )
        assert r.status == "FAIL"
        assert r.bucket == "value_mismatch"

    def test_term_containment_at_script_boundary_accepted(self):
        """术语包含（脚本体边界）：FCF ⊂ FCF收益率 / ROE ⊂ 加权ROE SHALL 接受。

        r4 语料：`cashflow_metrics.FCF收益率.2025`（metric=FCF，2.4）与
        `financial_indicators.2025-12-31.加权净资产收益率`（metric=ROE，13.44）
        判 semantic_term_mismatch，数值与真值一致。
        """
        r = _one(
            _claim(
                field_ref="cashflow_metrics.FCF收益率.2025",
                stated_value=2.4,
                interpretation="2025年FCF收益率为2.40%",
                metric_name="FCF",
                period="2025",
                direction="flat",
            ),
            {"cashflow_metrics": {"FCF收益率": {"2025": 0.024}}},
        )
        assert r.status == "PASS", r.bucket

    def test_term_containment_within_latin_token_still_rejected(self):
        """同为拉丁文段的包含不豁免（MA ⊄ MACD）：张冠李戴拦截面不变。"""
        r = _one(
            _claim(
                field_ref="technical_indicators.MACD.DIF.-1",
                stated_value=1.0,
                interpretation="最新 DIF 为 1.00",
                metric_name="MA",
                period=None,
                direction="flat",
            )
        )
        assert r.status == "FAIL"
        assert r.bucket == "semantic_term_mismatch"

    def test_no_row_key_uses_latest_row_in_producer_order(self):
        """路径止于列名：state 报表 DataFrame 为生产者降序（最新在前——`compute.py`
        以 `iloc[0]` 取最新），解析 SHALL 取最新行（修复前取 `iloc[-1]` = 最旧行）。"""
        frame = pd.DataFrame(
            [
                {"报告日": "20251231", "货币资金": 500.0},
                {"报告日": "20241231", "货币资金": 400.0},
            ]
        )
        r = _one(
            _claim(
                field_ref="balance_sheet.货币资金",
                stated_value=500.0,
                interpretation="货币资金 500.00 亿元",
                metric_name="货币资金",
                period=None,
                direction="flat",
            ),
            {"balance_sheet": frame},
        )
        assert r.status == "PASS", (r.status, r.bucket, r.ground_truth)

    def test_nan_ground_truth_degrades_to_unverifiable(self):
        """真值为 NaN（该期未披露/不适用）→ 数据层缺失，SHALL 降级 UNVERIFIABLE，
        SHALL NOT 判 value_mismatch（实测 600519 真实 `股息发放率(%)` 最新期为 NaN）。"""
        frame = pd.DataFrame([{"报告日": "20251231", "股息发放率(%)": float("nan")}])
        r = _one(
            _claim(
                field_ref="financial_indicators.20251231.股息发放率",
                stated_value=20.44,
                interpretation="股息发放率约20.44%",
                metric_name=None,
                period="2025",
                direction="flat",
            ),
            {"financial_indicators": frame},
        )
        assert r.status == "UNVERIFIABLE"
        assert r.coverage_gap is True
        assert r.bucket is None


class TestQuarterlyTrendRootTermAlias:
    """quarterly_trend 根域序列键的术语接受（r4 招行 385.93 真实样本）。"""

    def test_net_profit_accepts_jinglirun(self):
        r = _one(
            _claim(
                field_ref="quarterly_trend.net_profit.0",
                stated_value=100.0,
                interpretation="2025Q3净利100.00亿元",
                metric_name="净利润",
                direction="flat",
            )
        )
        assert r.status == "PASS", r.bucket

    def test_net_profit_accepts_guimujinglirun(self):
        r = _one(
            _claim(
                field_ref="quarterly_trend.net_profit.0",
                stated_value=100.0,
                interpretation="2025Q3归母净利润100.00亿元",
                metric_name="归母净利润",
                direction="flat",
            )
        )
        assert r.status == "PASS", r.bucket

    def test_other_series_keys_unchanged(self):
        # yoy/qoq 术语判定不回归（同比/环比 canonical 本就命中）
        r = _one(
            _claim(
                field_ref="quarterly_trend.yoy.3",
                stated_value=36.46,
                interpretation="2026Q2同比36.46%",
                metric_name="同比",
                direction="positive",
            )
        )
        assert r.status == "PASS", r.bucket

    def test_root_alias_does_not_merge_report_domain(self):
        # 防全局合并：利润表域「净利润」仍不得放行到归母列（张冠李戴拦截面不变）
        frame = pd.DataFrame([{"报告日": "20251231", "归属于母公司的净利润": 1.0e9}])
        r = _one(
            _claim(
                field_ref="income_statement.20251231.归属于母公司的净利润",
                stated_value=1.0e9,
                interpretation="2025年净利润10亿元",
                metric_name="净利润",
                direction="flat",
            ),
            {"income_statement": frame},
        )
        assert r.status == "FAIL"
        assert r.bucket == "semantic_term_mismatch"
