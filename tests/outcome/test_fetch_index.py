"""fetch_index_kline 泛化:任意指数代码;fetch_benchmark_kline 兼容。"""

from unittest.mock import patch

import pandas as pd

from finance_agent.data.akshare_client import AKShareClient


def test_fetch_index_kline_calls_akshare_with_code():
    client = AKShareClient()
    fake_df = pd.DataFrame({"日期": ["2026-08-01"], "收盘": [4000.0]})
    with patch("finance_agent.data.akshare_client.ak") as mock_ak:
        mock_ak.index_zh_a_hist.return_value = fake_df
        result = client.fetch_index_kline("000905", days=30)
    assert mock_ak.index_zh_a_hist.call_args.kwargs["symbol"] == "000905"
    # 与原 fetch_benchmark_kline 行为一致:sort/reset/tail 后返回(非原对象)
    assert list(result["收盘"]) == [4000.0]


def test_fetch_benchmark_kline_still_000300():
    client = AKShareClient()
    fake_df = pd.DataFrame({"日期": ["2026-08-01"], "收盘": [4000.0]})
    with patch("finance_agent.data.akshare_client.ak") as mock_ak:
        mock_ak.index_zh_a_hist.return_value = fake_df
        client.fetch_benchmark_kline(days=30)
    assert mock_ak.index_zh_a_hist.call_args.kwargs["symbol"] == "000300"
