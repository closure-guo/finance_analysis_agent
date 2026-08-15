"""TDD tests for nodes/fetch.py — fetch_data 节点。

fetch_data 职责：
1. Step1 并行拉取无依赖数据（三大报表 + 行情 + 行业归属 + 预计算指标）
2. Step2 拉取同业数据（依赖 Step1 的行业归属）
3. 拉取后写入缓存
4. 数据降级：三大报表缺失 → 报错终止；同业缺失 → 标记 N/A 继续
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pandas as pd
import pytest

import finance_agent.nodes.fetch as fetch_mod
from finance_agent.nodes.fetch import fetch_data


def _make_balance_sheet():
    return pd.DataFrame({"报告日": ["20241231", "20231231"], "资产总计": [1000.0, 900.0]})


def _make_income():
    return pd.DataFrame({"报告日": ["20241231", "20231231"], "营业收入": [1000.0, 900.0]})


def _make_cashflow():
    return pd.DataFrame(
        {"报告日": ["20241231", "20231231"], "经营活动产生的现金流量净额": [250.0, 220.0]}
    )


def _make_indicators():
    return pd.DataFrame({"日期": ["2024-12-31", "2023-12-31"], "销售毛利率(%)": [40.0, 38.0]})


def _setup_client():
    mock = MagicMock()
    mock.fetch_balance_sheet.return_value = _make_balance_sheet()
    mock.fetch_income_statement.return_value = _make_income()
    mock.fetch_cash_flow.return_value = _make_cashflow()
    mock.fetch_indicators.return_value = _make_indicators()
    mock.fetch_industry.return_value = {"industry": "白酒", "name": "贵州茅台"}
    mock.fetch_stock_quote.return_value = {"price": 1800.0, "name": "贵州茅台", "code": "600519"}
    return mock


class TestFetchDataBasic:
    def test_fills_all_state_fields(self):
        mock_client = _setup_client()
        mock_cache = MagicMock()
        state = {"stock_code": "600519"}
        result = fetch_data(state, cache=mock_cache, client=mock_client)

        assert result["balance_sheet"] is not None
        assert result["income_statement"] is not None
        assert result["cash_flow_statement"] is not None
        assert result["financial_indicators"] is not None
        assert result["industry_info"]["industry"] == "白酒"
        assert result["stock_quote"]["price"] == 1800.0

    def test_writes_to_cache(self):
        mock_client = _setup_client()
        mock_cache = MagicMock()
        state = {"stock_code": "600519"}
        fetch_data(state, cache=mock_cache, client=mock_client)

        assert mock_cache.set.call_count >= 3
        cached_keys = [call[0][0] for call in mock_cache.set.call_args_list]
        assert "600519:balance_sheet" in cached_keys
        assert "600519:income_statement" in cached_keys
        assert "600519:cash_flow_statement" in cached_keys


class TestFetchDataDegradation:
    def test_required_data_missing_raises(self):
        """三大报表拉取失败应报错终止。"""
        mock_client = MagicMock()
        mock_client.fetch_balance_sheet.side_effect = Exception("API error")
        mock_cache = MagicMock()
        state = {"stock_code": "600519"}
        with pytest.raises(Exception, match="API error"):
            fetch_data(state, cache=mock_cache, client=mock_client)

    def test_peer_data_missing_marks_na(self):
        """同业数据拉取失败时标记 N/A 继续。"""
        mock_client = _setup_client()
        mock_client.fetch_peer_data.side_effect = Exception("no peers")
        mock_cache = MagicMock()
        state = {"stock_code": "600519", "peer_codes": ["000858"]}
        result = fetch_data(state, cache=mock_cache, client=mock_client)
        assert result.get("peer_financials") is None


class TestFetchDataSpanObservability:
    """span 命名与失败 level 追踪（spec trace-observability：data_source:{source} 约定）。

    AKShare 子 span SHALL 命名为 `data_source:akshare:{label}`，失败 SHALL 标
    `level="ERROR"`，使 incident 008 类卡死/失败可定位到具体子调用。
    """

    def test_span_naming_uses_data_source_prefix(self, monkeypatch):
        """span 名以 data_source:akshare: 前缀（spec data_source:{source} 约定）。"""
        mock_client = _setup_client()
        captured: list[str] = []

        @contextmanager
        def _spy_span(name, input=None):
            captured.append(name)
            yield MagicMock()

        monkeypatch.setattr(fetch_mod, "open_span", _spy_span)

        fetch_mod.fetch_data(
            {"stock_code": "600519", "stock_name": "贵州茅台"},
            cache=MagicMock(),
            client=mock_client,
        )

        assert captured, "未捕获任何 span"
        # 收紧：fetch.py 内所有 span SHALL 都用 data_source: 前缀
        assert all(s.startswith("data_source:") for s in captured), (
            f"非所有 span 都用 data_source 前缀: {captured}"
        )
        assert any(s.startswith("data_source:akshare:") for s in captured), (
            f"未捕获 data_source:akshare: 前缀 span: {captured}"
        )

    def test_span_marked_error_on_subcall_failure(self, monkeypatch):
        """AKShare 非必需子调用失败时，对应 span 标 level=ERROR。"""
        mock_client = _setup_client()
        # 非必需指标拉取抛异常 → 走 warning 降级（不 raise），span 应标 ERROR
        mock_client.fetch_indicators.side_effect = RuntimeError("timeout")

        updates: list[dict] = []

        class _FakeObs:
            def update(self, **kwargs):
                updates.append(kwargs)

        @contextmanager
        def _spy_span(name, input=None):
            yield _FakeObs()

        monkeypatch.setattr(fetch_mod, "open_span", _spy_span)

        fetch_mod.fetch_data(
            {"stock_code": "600519", "stock_name": "贵州茅台"},
            cache=MagicMock(),
            client=mock_client,
        )

        assert any(u.get("level") == "ERROR" for u in updates), (
            f"失败 span 未标 level=ERROR: {updates}"
        )

    def test_span_output_summarizes_dataframe_returns(self, monkeypatch):
        """DataFrame 返回时 span output 含 rows + columns 摘要。

        spec trace-observability「DataFrame 返回只记摘要」：AKShare 返回
        pandas DataFrame 时，span output SHALL 只记 {"rows": N, "columns": [...]}
        摘要，且不尝试序列化完整 DataFrame。
        """
        mock_client = _setup_client()
        captured: list[tuple[str, dict]] = []

        class _FakeObs:
            def __init__(self, name):
                self._name = name

            def update(self, **kwargs):
                captured.append((self._name, kwargs))

        @contextmanager
        def _spy_span(name, input=None):
            yield _FakeObs(name)

        monkeypatch.setattr(fetch_mod, "open_span", _spy_span)

        fetch_mod.fetch_data(
            {"stock_code": "600519", "stock_name": "贵州茅台"},
            cache=MagicMock(),
            client=mock_client,
        )

        # balance_sheet 经 _setup_client mock 返回 2 行 DataFrame（报告日 + 资产总计）
        bs_outputs = [
            kwargs["output"]
            for (n, kwargs) in captured
            if n == "data_source:akshare:balance_sheet" and "output" in kwargs
        ]
        assert bs_outputs, f"balance_sheet span output 未捕获: {captured}"
        output = bs_outputs[0]
        assert output["status"] == "success", f"成功路径 status 应为 success: {output}"
        assert output["rows"] == 2, f"balance_sheet 行数应为 2: {output}"
        assert "报告日" in output["columns"], f"columns 缺报告日: {output}"
        assert "资产总计" in output["columns"], f"columns 缺资产总计: {output}"
        # 关键约束：不序列化完整 DataFrame（output 不含任何 DataFrame 引用）
        assert not any(isinstance(v, pd.DataFrame) for v in output.values()), (
            f"output 误含完整 DataFrame: {output}"
        )
