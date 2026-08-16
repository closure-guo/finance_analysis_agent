"""TDD tests for metrics/validate.py — 三大报表勾稽校验 4 条规则。

fixture 手算（2024）：
- 资产=1000, 负债=400, 权益=600 → 资产=负债+权益 ✓
- 利润总额=200, 所得税=30, 净利润=170 → 200-30=170 ✓
- OCF=250, ICF=-100, FCF=-30, 净变动=120 → 250-100-30=120 ✓
- 2024未分配=200, 2023未分配=170, 净利润=170, 分红=50 → 170+170-50=290≠200（偏差）
"""

import pandas as pd

from finance_agent.metrics.validate import validate_financials


def _bs(rows=None):
    """资产负债表 helper。"""
    if rows is None:
        rows = [
            {
                "报告日": "20241231",
                "资产总计": 1000.0,
                "负债合计": 400.0,
                "所有者权益(或股东权益)合计": 600.0,
                "未分配利润": 200.0,
            },
            {
                "报告日": "20231231",
                "资产总计": 900.0,
                "负债合计": 350.0,
                "所有者权益(或股东权益)合计": 550.0,
                "未分配利润": 170.0,
            },
        ]
    return pd.DataFrame(rows)


def _is(rows=None):
    """利润表 helper。"""
    if rows is None:
        rows = [
            {"报告日": "20241231", "利润总额": 200.0, "所得税费用": 30.0, "净利润": 170.0},
            {"报告日": "20231231", "利润总额": 180.0, "所得税费用": 27.0, "净利润": 153.0},
        ]
    return pd.DataFrame(rows)


def _cf(rows=None):
    """现金流量表 helper。"""
    if rows is None:
        rows = [
            {
                "报告日": "20241231",
                "经营活动产生的现金流量净额": 250.0,
                "投资活动产生的现金流量净额": -100.0,
                "筹资活动产生的现金流量净额": -30.0,
                "现金及现金等价物净增加额": 120.0,
                "分配股利、利润或偿付利息所支付的现金": 50.0,
            },
            {
                "报告日": "20231231",
                "经营活动产生的现金流量净额": 220.0,
                "投资活动产生的现金流量净额": -90.0,
                "筹资活动产生的现金流量净额": -20.0,
                "现金及现金等价物净增加额": 110.0,
                "分配股利、利润或偿付利息所支付的现金": 45.0,
            },
        ]
    return pd.DataFrame(rows)


class TestRule1TrialBalance:
    """规则 1：试算平衡（硬等式）"""

    def test_pass_when_balanced(self):
        result = validate_financials(_bs(), _is(), _cf())
        assert result["result"] == "PASS"

    def test_fail_when_unbalanced(self):
        bs = _bs(
            [
                {
                    "报告日": "20241231",
                    "资产总计": 1000.0,
                    "负债合计": 400.0,
                    "所有者权益(或股东权益)合计": 500.0,
                }
            ]
        )  # 400+500=900≠1000
        result = validate_financials(bs, _is(), _cf())
        assert result["result"] == "FAIL"

    def test_fail_warning_contains_year(self):
        bs = _bs(
            [
                {
                    "报告日": "20241231",
                    "资产总计": 1000.0,
                    "负债合计": 400.0,
                    "所有者权益(或股东权益)合计": 500.0,
                }
            ]
        )
        result = validate_financials(bs, _is(), _cf())
        assert any("[2024]" in w for w in result["warnings"])

    def test_skip_when_assets_zero(self):
        bs = _bs(
            [
                {
                    "报告日": "20241231",
                    "资产总计": 0.0,
                    "负债合计": 0.0,
                    "所有者权益(或股东权益)合计": 0.0,
                }
            ]
        )
        result = validate_financials(bs, _is(), _cf())
        assert result["result"] == "PASS"
        assert any("跳过" in d for d in result["details"])


class TestRule2IncomeStatement:
    """规则 2：利润表内部勾稽（软等式）"""

    def test_pass_when_matched(self):
        result = validate_financials(_bs(), _is(), _cf())
        assert not any("利润表勾稽偏差" in w for w in result["warnings"])

    def test_warning_when_large_deviation(self):
        is_ = _is([{"报告日": "20241231", "利润总额": 2e8, "所得税费用": 3e7, "净利润": 1e8}])
        # 2e8-3e7=1.7e8, 实际1e8, diff=7e7 > threshold=max(1e7, 1e6)=1e7
        result = validate_financials(_bs(), is_, _cf())
        assert any("利润表勾稽偏差" in w for w in result["warnings"])

    def test_pass_with_small_deviation(self):
        is_ = _is([{"报告日": "20241231", "利润总额": 200.0, "所得税费用": 30.0, "净利润": 170.5}])
        # 200-30=170, 实际170.5, diff=0.5 < threshold
        result = validate_financials(_bs(), is_, _cf())
        assert not any("利润表勾稽偏差" in w for w in result["warnings"])

    def test_skip_when_total_profit_zero(self):
        is_ = _is([{"报告日": "20241231", "利润总额": 0.0, "所得税费用": 0.0, "净利润": 0.0}])
        result = validate_financials(_bs(), is_, _cf())
        assert any("规则2跳过" in d for d in result["details"])


class TestRule3CashFlow:
    """规则 3：现金流量表内部勾稽（软等式）"""

    def test_pass_when_matched(self):
        result = validate_financials(_bs(), _is(), _cf())
        assert not any("现金流量表勾稽偏差" in w for w in result["warnings"])

    def test_warning_when_large_deviation(self):
        cf = _cf(
            [
                {
                    "报告日": "20241231",
                    "经营活动产生的现金流量净额": 2.5e8,
                    "投资活动产生的现金流量净额": -1e8,
                    "筹资活动产生的现金流量净额": -3e7,
                    "现金及现金等价物净增加额": 0.0,
                    "分配股利、利润或偿付利息所支付的现金": 5e7,
                }
            ]
        )
        # 2.5e8-1e8-3e7=1.2e8, 实际0, diff=1.2e8 > threshold=max(1.25e7, 1e6)=1.25e7
        result = validate_financials(_bs(), _is(), cf)
        assert any("现金流量表勾稽偏差" in w for w in result["warnings"])


class TestRule4RetainedEarnings:
    """规则 4：留存收益勾稽（软等式）"""

    def test_pass_when_matched(self):
        # 2024: 期初170 + 净利润170 - 分红50 = 290, 实际200, diff=90
        # threshold = max(200*0.05, 1M) = 1M, 90 < 1M → pass (soft threshold)
        result = validate_financials(_bs(), _is(), _cf())
        assert not any("留存收益勾稽偏差" in w for w in result["warnings"])

    def test_warning_when_large_deviation(self):
        # 期初=170, 净利润=170, 分红=50 → expected=290, 实际=50, diff=240
        # 但 threshold = max(50*0.05, 1M) = 1M → 还是 pass
        # 需要用更大的数字才能超过 1M 兜底
        bs = _bs(
            [
                {
                    "报告日": "20241231",
                    "资产总计": 1e9,
                    "负债合计": 4e8,
                    "所有者权益(或股东权益)合计": 6e8,
                    "未分配利润": 2e8,
                },
                {
                    "报告日": "20231231",
                    "资产总计": 9e8,
                    "负债合计": 3.5e8,
                    "所有者权益(或股东权益)合计": 5.5e8,
                    "未分配利润": 1.7e8,
                },
            ]
        )
        is_ = _is(
            [
                {"报告日": "20241231", "利润总额": 2e8, "所得税费用": 3e7, "净利润": 1.7e8},
                {"报告日": "20231231", "利润总额": 1.8e8, "所得税费用": 2.7e7, "净利润": 1.53e8},
            ]
        )
        cf = _cf(
            [
                {
                    "报告日": "20241231",
                    "经营活动产生的现金流量净额": 2.5e8,
                    "投资活动产生的现金流量净额": -1e8,
                    "筹资活动产生的现金流量净额": -3e7,
                    "现金及现金等价物净增加额": 1.2e8,
                    "分配股利、利润或偿付利息所支付的现金": 5e7,
                },
                {
                    "报告日": "20231231",
                    "经营活动产生的现金流量净额": 2.2e8,
                    "投资活动产生的现金流量净额": -9e7,
                    "筹资活动产生的现金流量净额": -2e7,
                    "现金及现金等价物净增加额": 1.1e8,
                    "分配股利、利润或偿付利息所支付的现金": 4.5e7,
                },
            ]
        )
        # 期初1.7e8 + 净利润1.7e8 - 分红5e7 = 2.9e8, 实际2e8, diff=9e7
        # threshold = max(2e8*0.05, 1e6) = 1e7, 9e7 > 1e7 → warning
        result = validate_financials(bs, is_, cf)
        assert any("留存收益勾稽偏差" in w for w in result["warnings"])

    def test_skip_oldest_year(self):
        bs = _bs(
            [
                {
                    "报告日": "20241231",
                    "资产总计": 1000.0,
                    "负债合计": 400.0,
                    "所有者权益(或股东权益)合计": 600.0,
                    "未分配利润": 200.0,
                }
            ]
        )
        is_ = _is([{"报告日": "20241231", "利润总额": 200.0, "所得税费用": 30.0, "净利润": 170.0}])
        cf = _cf(
            [
                {
                    "报告日": "20241231",
                    "经营活动产生的现金流量净额": 250.0,
                    "投资活动产生的现金流量净额": -100.0,
                    "筹资活动产生的现金流量净额": -30.0,
                    "现金及现金等价物净增加额": 120.0,
                    "分配股利、利润或偿付利息所支付的现金": 50.0,
                }
            ]
        )
        result = validate_financials(bs, is_, cf)
        assert any("规则4跳过" in d for d in result["details"])


class TestReturnStructure:
    """返回值结构验证"""

    def test_has_result_key(self):
        result = validate_financials(_bs(), _is(), _cf())
        assert "result" in result
        assert result["result"] in ("PASS", "FAIL")

    def test_has_warnings_list(self):
        result = validate_financials(_bs(), _is(), _cf())
        assert isinstance(result["warnings"], list)

    def test_has_details_list(self):
        result = validate_financials(_bs(), _is(), _cf())
        assert isinstance(result["details"], list)
        assert len(result["details"]) > 0


# ── 银行结构兼容（无「所有者权益合计」列，用 负债及股东权益总计 - 负债 推导）──
def test_trial_balance_bank_structure_passes():
    """银行资产负债表无「所有者权益(或股东权益)合计」列，但有「负债及股东权益总计」。

    权益应从 负债及股东权益总计 - 负债合计 推导，试算平衡应 PASS。
    （真实案例：招商银行 600036，缺失该列导致权益按 0 算、差 ~10% 误判 FAIL）
    """
    bs = _bs(
        [
            {
                "报告日": "20241231",
                "资产总计": 1000.0,
                "负债合计": 400.0,
                "负债及股东权益总计": 1000.0,  # 银行结构：无 所有者权益合计
                "未分配利润": 200.0,
            },
            {
                "报告日": "20231231",
                "资产总计": 900.0,
                "负债合计": 350.0,
                "负债及股东权益总计": 900.0,
                "未分配利润": 170.0,
            },
        ]
    )
    result = validate_financials(bs, _is(), _cf())
    # 修复前：权益=0 → 负债+权益=400 ≠ 1000 → FAIL（红）
    # 修复后：权益=1000-400=600 → PASS（绿）
    assert result["result"] == "PASS", result["warnings"]
