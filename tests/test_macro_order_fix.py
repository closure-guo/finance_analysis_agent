"""复现测试：akshare 宏观/财务数据为降序（最新在前），head() 取最新。

根因：akshare 宏观接口（macro_china_cpi 等）返回降序数据（首行最新），
财务三表/指标同为降序。但代码用 tail()/[-3:] 假设升序 → 取到最老的
2008 年数据，且 citation 校验解析的 cpi[0] 与 claim 引用的 cpi.0 错位。

本文件 mock akshare，不真调网络。TDD：先红后绿。
"""

import json
from unittest.mock import patch

import pandas as pd

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.nodes.analysts import (
    _build_fundamental_context,
    _build_macro_context,
)

# akshare 宏观接口按降序返回（最新在前），模拟 10 期数据：首行最新、尾行最老。
_DESC_MONTHS = [
    "2026年07月份",
    "2026年06月份",
    "2026年05月份",
    "2026年04月份",
    "2026年03月份",
    "2026年02月份",
    "2026年01月份",
    "2025年12月份",
    "2025年11月份",
    "2025年10月份",
]


def _make_desc_macro_df() -> pd.DataFrame:
    """降序宏观 DataFrame（首列 = 月份/日期列）。"""
    return pd.DataFrame(
        {
            "月份": _DESC_MONTHS,
            "全国-当月-同比增长": [10.0 + i * 0.1 for i in range(10)],
        }
    )


class TestFetchMacroIndicators:
    """fetch_macro_indicators 应返回最新 6 期（index 0 = 最新）。"""

    @patch("finance_agent.data.akshare_client.ak")
    def test_fetch_macro_indicators_takes_newest(self, mock_ak):
        """降序输入下应取最新 6 期，result['cpi']['records'][0] 为最新一期（首行值）。"""
        df = _make_desc_macro_df()
        mock_ak.macro_china_cpi.return_value = df
        mock_ak.macro_china_pmi.return_value = df
        mock_ak.macro_china_money_supply.return_value = df
        mock_ak.macro_china_lpr.return_value = df

        result = AKShareClient().fetch_macro_indicators()

        cpi = result["cpi"]["records"]
        assert len(cpi) == 6
        # index 0 应为最新一期（首行 2026年07月份 的值）
        assert cpi[0]["月份"] == "2026年07月份"
        assert cpi[0]["全国-当月-同比增长"] == 10.0
        # 不应包含最老几期（tail(6) 会取到 2025年10月份）
        assert cpi[-1]["月份"] == "2026年02月份"


class TestFetchIndicators:
    """fetch_indicators 应显式降序返回（index 0 = 最新年报）。

    akshare 的 stock_financial_analysis_indicator 内部按日期升序排序
    （sort_values 默认 ascending=True），与「降序、index 0 = 最新」契约冲突；
    fetch 层 SHALL 显式降序后再返回（head = 最新 N 年）。
    """

    @patch("finance_agent.data.akshare_client.ak")
    def test_fetch_indicators_returns_descending(self, mock_ak):
        """升序输入（最老在前）下应返回降序（最新年报在 index 0）。"""
        mock_ak.stock_financial_analysis_indicator.return_value = pd.DataFrame(
            {
                "日期": [
                    "2020-12-31",
                    "2021-12-31",
                    "2022-12-31",
                    "2023-12-31",
                    "2024-12-31",
                ],
                "销售毛利率(%)": [30.0, 31.0, 32.0, 33.0, 34.0],
            }
        )
        result = AKShareClient().fetch_indicators("600519")
        assert list(result["日期"].astype(str)) == [
            "2024-12-31",
            "2023-12-31",
            "2022-12-31",
            "2021-12-31",
            "2020-12-31",
        ]
        # index 0 为最新年报（head(3) 即最新 3 年）
        assert str(result.iloc[0]["日期"]) == "2024-12-31"


class TestBuildMacroContext:
    """_build_macro_context 应展示最新 3 期（从 index 0 开始）。"""

    def test_macro_context_shows_newest_first(self):
        """6 条降序 records（index 0 最新），context 中 3 条应为最新 3 条。"""
        records = [
            {"月份": m, "全国-当月-同比增长": 10.0 + i * 0.1}
            for i, m in enumerate(_DESC_MONTHS[:6])
        ]
        state = {
            "macro_indicators": {
                "cpi": {"as_of_date": "2026-07-01", "freshness": "fresh", "records": records}
            }
        }
        context = _build_macro_context(state)
        payload = context.split("宏观经济指标（近3期）:\n", 1)[1]
        trimmed = json.loads(payload)
        assert [r["月份"] for r in trimmed["cpi"]] == _DESC_MONTHS[:3]
        # fresh 数据不标记滞后，不打扰闭环
        assert "数据滞后" not in context

    def test_macro_context_marks_stale_indicators(self):
        """stale 指标须确定性附加"数据滞后"标注（不依赖 LLM 自觉）。"""
        records = [{"月份": "2025年08月份", "今值": 49.4}]
        state = {
            "macro_indicators": {
                "pmi": {"as_of_date": "2025-08-01", "freshness": "stale", "records": records}
            }
        }
        context = _build_macro_context(state)
        assert "pmi 数据滞后" in context
        assert "2025-08" in context


class TestBuildFundamentalContext:
    """_build_fundamental_context 应展示最新 3 年（2025/2024/2023）。"""

    def _make_desc_financials(self) -> dict:
        # 财务三表降序：最新在前（与 akshare stock_financial_report_sina 一致）
        years = ["20251231", "20241231", "20231231", "20221231", "20211231"]
        statements = {
            "balance_sheet": pd.DataFrame(
                {"报告日": years, "资产总计": [1000 + i for i in range(5)]}
            ),
            "income_statement": pd.DataFrame(
                {"报告日": years, "营业收入": [500 + i for i in range(5)]}
            ),
            "cash_flow_statement": pd.DataFrame(
                {"报告日": years, "经营活动产生的现金流量净额": [250 + i for i in range(5)]}
            ),
        }
        # financial_indicators 由降序财报计算，继承降序
        statements["financial_indicators"] = pd.DataFrame(
            {
                "日期": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31", "2021-12-31"],
                "销售毛利率(%)": [40.0 + i for i in range(5)],
            }
        )
        return statements

    def test_fundamental_context_shows_newest_years(self):
        """降序财报下「近3年」应为 2025/2024/2023，而非 2021/2022/2023。"""
        state = {"stock_code": "600519", "stock_name": "贵州茅台"}
        state.update(self._make_desc_financials())

        context = _build_fundamental_context(state)

        # 三大报表近 3 年应为最新三年
        for date in ["20251231", "20241231", "20231231"]:
            assert date in context, f"近3年应包含 {date}"
        for date in ["20211231", "20221231"]:
            assert date not in context, f"近3年不应包含最老年份 {date}"

        # 预计算财务指标同理
        for date in ["2025-12-31", "2024-12-31", "2023-12-31"]:
            assert date in context, f"财务指标近3年应包含 {date}"
        for date in ["2021-12-31", "2022-12-31"]:
            assert date not in context, f"财务指标近3年不应包含最老年份 {date}"


class TestMacroFreshness:
    """fetch_macro_indicators 时效守卫：as_of_date + freshness。"""

    def _fresh_df(self):
        # 首列为"月份"字符串（akshare 真实格式：2026年07月份），第一条 = 本月
        cur = pd.Timestamp.now()
        m1 = f"{cur.year}年{cur.month:02d}月份"
        prev = cur - pd.DateOffset(months=1)
        m2 = f"{prev.year}年{prev.month:02d}月份"
        return pd.DataFrame({"月份": [m1, m2], "制造业-指数": [50.2, 49.8]})

    def _stale_df(self):
        # 首列"月份"，最新一条距今 > 90 天
        old = pd.Timestamp.now() - pd.DateOffset(months=5)
        older = old - pd.DateOffset(months=1)
        return pd.DataFrame(
            {
                "月份": [
                    f"{old.year}年{old.month:02d}月份",
                    f"{older.year}年{older.month:02d}月份",
                ],
                "制造业-指数": [49.4, 49.1],
            }
        )

    def test_mark_fresh_and_stale_by_recency(self):
        import finance_agent.data.akshare_client as m

        orig = m._call_ak
        try:

            def fake_call(func, *a, **k):
                if func.__name__ == "macro_china_pmi":
                    return self._stale_df()
                return self._fresh_df()

            m._call_ak = fake_call
            client = AKShareClient()
            result = client.fetch_macro_indicators()
            assert result["pmi"]["freshness"] == "stale"
            assert result["m2"]["freshness"] == "fresh"
            assert result["cpi"]["freshness"] == "fresh"
            # as_of_date 解析出年份月份（stale 那条 = 5 个月前）
            assert result["pmi"]["as_of_date"].startswith(
                str((pd.Timestamp.now() - pd.DateOffset(months=5)).year)
            )
        finally:
            m._call_ak = orig

    def test_failure_returns_empty_list(self):
        import finance_agent.data.akshare_client as m

        orig = m._call_ak
        try:
            m._call_ak = lambda func, *a, **k: None
            client = AKShareClient()
            result = client.fetch_macro_indicators()
            assert result["cpi"] == []
        finally:
            m._call_ak = orig

    def test_iso_date_first_column_fresh(self):
        """首列为 ISO 日期（今天往前 5 天）也能解析 → fresh，as_of_date 归一到当月 1 号。"""
        import finance_agent.data.akshare_client as m

        cur = pd.Timestamp.now()
        iso = (cur - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        prev_iso = (cur - pd.Timedelta(days=35)).strftime("%Y-%m-%d")
        df = pd.DataFrame({"TRADE_DATE": [iso, prev_iso], "LPR1Y": [3.0, 3.0]})
        orig = m._call_ak
        try:

            def fake_call(func, *a, **k):
                if func.__name__ == "macro_china_lpr":
                    return df
                # 其它指标给当前月份 df，全部 fresh，避免干扰断言
                mth = f"{cur.year}年{cur.month:02d}月份"
                prev_m = (cur - pd.DateOffset(months=1)).strftime("%Y年%m月份")
                return pd.DataFrame({"月份": [mth, prev_m], "指数": [50.0, 49.0]})

            m._call_ak = fake_call
            client = AKShareClient()
            result = client.fetch_macro_indicators()
            assert result["lpr"]["freshness"] == "fresh"
            expected = (cur - pd.Timedelta(days=5)).replace(day=1).date().isoformat()
            assert result["lpr"]["as_of_date"] == expected
        finally:
            m._call_ak = orig

    def test_parse_failure_marks_stale(self):
        """首列无法解析（如 unknown）→ stale + as_of_date=None（fail-safe）。"""
        import finance_agent.data.akshare_client as m

        orig = m._call_ak
        try:
            df = pd.DataFrame(
                {"month": ["unknown", "also-not-a-date"], "制造业-指数": [49.4, 49.1]}
            )
            m._call_ak = lambda func, *a, **k: df
            client = AKShareClient()
            result = client.fetch_macro_indicators()
            assert result["cpi"]["freshness"] == "stale"
            assert result["cpi"]["as_of_date"] is None
        finally:
            m._call_ak = orig
