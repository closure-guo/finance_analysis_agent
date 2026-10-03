"""fetch_data 数据覆盖接线测试（update-financial-freshness-and-valuation Task 4）。

latest_period_snapshot（最新报告期快照，Task 3 提供）接入 fetch_data 并行抓取：
- 成功 → state 键 latest_period_snapshot 携带快照 dict，30 天 TTL 落缓存
- 失败 → 降级空 dict + ERROR 日志（区别于其他 optional 数据源的 warning）

FakeClient 契约：三大报表是必需数据（失败 raise 终止管线），故返回最小合法
DataFrame（2 行年报 + 报告日列）；其余方法经 __getattr__ 抛 ConnectionError
走 optional 降级。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.nodes.fetch import fetch_data

CODE = "688072"


class _FakeClient:
    """最小 client stub：必需数据成功 + 快照成功，其余全部降级。"""

    def fetch_balance_sheet(self, code: str) -> pd.DataFrame:
        return pd.DataFrame({"报告日": ["20241231", "20231231"], "资产总计": [1000.0, 900.0]})

    def fetch_income_statement(self, code: str) -> pd.DataFrame:
        return pd.DataFrame({"报告日": ["20241231", "20231231"], "营业收入": [1000.0, 900.0]})

    def fetch_cash_flow(self, code: str) -> pd.DataFrame:
        return pd.DataFrame(
            {"报告日": ["20241231", "20231231"], "经营活动产生的现金流量净额": [80.0, 72.0]}
        )

    def fetch_latest_period_snapshot(self, code: str) -> dict:
        return {"报告日": "2026-06-30", "期类型": "中报", "毛利率(%)": 41.0, "missing": []}

    def __getattr__(self, name: str):
        def _raise(*args, **kwargs):
            raise ConnectionError(f"{name} unavailable")

        return _raise


class _BrokenSnapshotClient(_FakeClient):
    """快照源故障：snapshot 抛错，其余行为同 _FakeClient。"""

    def fetch_latest_period_snapshot(self, code: str) -> dict:
        raise ConnectionError("snapshot source down")


def test_fetch_wires_snapshot(monkeypatch):
    """快照成功 → result 携带快照 dict，且以 30 天 TTL 落缓存。"""
    monkeypatch.delenv("TESTING", raising=False)
    cache = MagicMock()
    result = fetch_data(
        {"stock_code": CODE, "enable_web_search": False}, cache=cache, client=_FakeClient()
    )
    assert result["latest_period_snapshot"]["毛利率(%)"] == 41.0
    cached = {call[0][0]: call[1] for call in cache.set.call_args_list}
    assert cached[f"{CODE}:latest_period_snapshot"].get("ttl_seconds") == 2_592_000


def test_fetch_snapshot_failure_degrades_to_empty_dict(monkeypatch, caplog):
    """快照失败 → 降级空 dict + ERROR 日志（非 optional 常规 warning）。"""
    monkeypatch.delenv("TESTING", raising=False)
    with caplog.at_level("ERROR"):
        result = fetch_data(
            {"stock_code": CODE, "enable_web_search": False},
            cache=MagicMock(),
            client=_BrokenSnapshotClient(),
        )
    assert result["latest_period_snapshot"] == {}
    assert any(
        "latest_period_snapshot" in r.getMessage() for r in caplog.records if r.levelname == "ERROR"
    ), "快照失败应以 ERROR 级别记录且含 label"


class TestSnapshotYoYRawPrecision:
    """快照同比用 raw 值计算（#190 根因修复，与毛利率 raw 修复同款）。

    688072 实证：归母 13.4275 亿 / 基期 0.9429 亿——round 后基期 0.94 算出
    1328.72%（传播误差），精确基期算出 1324.10%（与外部引用一致的精确值）。
    同一函数里毛利率已按 raw 值计算（截断误差注释先例），同比必须同款。
    """

    @staticmethod
    def _income_df() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "报告日": ["20260630", "20250630"],
                "营业总收入": [2912864261.46, 1954150000.0],
                "营业成本": [1718464963.55, 1329640000.0],
                "归母净利润": [1342753981.0, 94287965.0],
            }
        )

    @staticmethod
    def _balance_df() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "报告日": ["20260630"],
                "资产总计": [5000000000.0],
                "负债合计": [2392500000.0],
                "存货": [100000000.0],
                "合同负债": [50000000.0],
            }
        )

    def test_np_yoy_uses_raw_precision(self):
        client = AKShareClient()

        def _fake_report(stock: str, symbol: str) -> pd.DataFrame:
            return self._income_df() if symbol == "利润表" else self._balance_df()

        with patch("finance_agent.data.akshare_client._sina_report", _fake_report):
            snap = client.fetch_latest_period_snapshot("688072")
        # 精确：(13.4275 - 0.9429) / 0.9429 = 1324.10%；舍入基期会算出 1328.72%
        assert snap["归母净利同比(%)"] == 1324.1
        assert snap["上年同期归母净利润"] == 0.94288  # 元级精度（round6），复算=同比值

    def test_rev_yoy_uses_raw_precision(self):
        client = AKShareClient()

        def _fake_report(stock: str, symbol: str) -> pd.DataFrame:
            return self._income_df() if symbol == "利润表" else self._balance_df()

        with patch("finance_agent.data.akshare_client._sina_report", _fake_report):
            snap = client.fetch_latest_period_snapshot("688072")
        # 精确：(29.1286 - 19.5415) / 19.5415 = 49.06%；若用 round 后 29.13/19.54 会漂
        assert snap["营收同比(%)"] == 49.06
