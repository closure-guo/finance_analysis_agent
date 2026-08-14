"""复现测试：财务三表 fetch 显式降序（data-ordering 契约：index 0 = 最新年报）。

根因：fetch_balance_sheet / fetch_income_statement / fetch_cash_flow 依赖
`_sina_report` 返回降序（最新在前），未显式排序——一旦源序变化会静默取到
旧年份（_trim_years 的 head(N) 语义随之错位）。契约要求 fetch 层**显式**
降序，不依赖数据源隐藏顺序。

本文件 mock akshare，不真调网络。TDD：先红后绿。
"""

from unittest.mock import patch

import pandas as pd
import pytest

from finance_agent.data.akshare_client import AKShareClient


def _make_ascending_annual() -> pd.DataFrame:
    """升序年报：20181231 → 20251231（最老在前），模拟源序倒转的边界情况。"""
    years = [f"{y}1231" for y in range(2018, 2026)]  # 20181231 ... 20251231
    return pd.DataFrame(
        {
            "报告日": years,
            "资产总计": [1000.0 + i for i in range(len(years))],
            "营业收入": [100.0 + i for i in range(len(years))],
            "经营活动产生的现金流量净额": [50.0 + i for i in range(len(years))],
        }
    )


class TestFinancialStatementsDescending:
    """三表 fetch 应显式降序：升序输入 → 返回 index 0 = 最新年报（20251231）。"""

    @pytest.mark.parametrize(
        "fetch_method",
        ["fetch_balance_sheet", "fetch_income_statement", "fetch_cash_flow"],
    )
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_newest_first(self, mock_ak, fetch_method):
        """升序输入下应返回降序，index 0 = 最新年报。"""
        mock_ak.stock_financial_report_sina.return_value = _make_ascending_annual()

        result = getattr(AKShareClient(), fetch_method)("600519")

        assert list(result["报告日"]) == sorted(result["报告日"], reverse=True), (
            f"{fetch_method} 应按报告日降序返回"
        )
        assert result.iloc[0]["报告日"] == "20251231", (
            f"{fetch_method} index 0 应为最新年报 20251231（修复前无排序 → index 0 = 20181231）"
        )
        # _trim_years 的 head(years) 语义：降序下 head(3) = 最新 3 年
        assert result.iloc[0]["报告日"] != "20181231"
