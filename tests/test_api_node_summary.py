"""_node_summary 桥接摘要回归：DataFrame 值键不得做真值判断。

fix/peer-node-summary-dataframe：add-peer-comparison（#275）激活休眠同业链路后，
fetch_data 节点摘要对 `accumulated["peer_financials"]`（DataFrame）做真值判断，
真实管线首次携带同业数据即崩（`The truth value of a DataFrame is ambiguous`）。
"""

import pandas as pd

from finance_agent.api import _node_summary


def test_fetch_data_summary_with_peer_financials_dataframe():
    """peer_financials 为 DataFrame 时摘要正常生成并含「同业数据」。"""
    accumulated = {
        "stock_name": "贵州茅台",
        "balance_sheet": pd.DataFrame({"资产总计": [1.0]}),
        "peer_financials": pd.DataFrame(
            [{"name": "五粮液", "code": "000858", "PE": None, "PB": 2.3}]
        ),
    }
    summary = _node_summary("fetch_data", accumulated, {})
    assert "同业数据" in summary
    assert "贵州茅台" in summary


def test_fetch_data_summary_without_peer_financials():
    """未携带同业数据时摘要不含「同业数据」（既有语义不变）。"""
    summary = _node_summary(
        "fetch_data", {"stock_code": "600519", "balance_sheet": pd.DataFrame()}, {}
    )
    assert "同业数据" not in summary
