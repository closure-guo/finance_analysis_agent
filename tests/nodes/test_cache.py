"""TDD tests for nodes/cache.py — check_cache 节点。

check_cache 职责：
1. 查缓存是否有该股票的持久化数据（三大报表）
2. HIT → cache_result="HIT", 填充已有数据到 state
3. MISS → cache_result="MISS", 不填充
"""

from unittest.mock import MagicMock

import pandas as pd

from finance_agent.nodes.cache import check_cache


class TestCheckCacheMiss:
    def test_returns_miss_when_no_cache(self):
        """缓存中没有数据时返回 MISS。"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        state = {"stock_code": "600519"}
        result = check_cache(state, cache=mock_cache)
        assert result["cache_result"] == "MISS"

    def test_miss_no_data_filled(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        state = {"stock_code": "600519"}
        result = check_cache(state, cache=mock_cache)
        assert "balance_sheet" not in result
        assert "income_statement" not in result


class TestCheckCacheHit:
    def test_returns_hit_when_all_cached(self):
        mock_cache = MagicMock()

        def fake_get(key):
            data = {
                "600519:balance_sheet": pd.DataFrame({"报告日": ["20241231"]}),
                "600519:income_statement": pd.DataFrame({"报告日": ["20241231"]}),
                "600519:cash_flow_statement": pd.DataFrame({"报告日": ["20241231"]}),
            }
            return data.get(key)

        mock_cache.get.side_effect = fake_get
        state = {"stock_code": "600519"}
        result = check_cache(state, cache=mock_cache)
        assert result["cache_result"] == "HIT"

    def test_hit_fills_data(self):
        mock_cache = MagicMock()
        bs = pd.DataFrame({"报告日": ["20241231"], "资产总计": [1000.0]})
        is_df = pd.DataFrame({"报告日": ["20241231"], "营业收入": [100.0]})
        cf = pd.DataFrame({"报告日": ["20241231"], "OCF": [50.0]})

        def fake_get(key):
            return {
                "600519:balance_sheet": bs,
                "600519:income_statement": is_df,
                "600519:cash_flow_statement": cf,
            }.get(key)

        mock_cache.get.side_effect = fake_get
        state = {"stock_code": "600519"}
        result = check_cache(state, cache=mock_cache)
        assert result["cache_result"] == "HIT"
        assert result["balance_sheet"].equals(bs)
        assert result["income_statement"].equals(is_df)
        assert result["cash_flow_statement"].equals(cf)


class TestCheckCachePartial:
    def test_partial_returns_miss(self):
        """只有部分报表缓存时仍返回 MISS。"""
        mock_cache = MagicMock()

        def fake_get(key):
            if key == "600519:balance_sheet":
                return pd.DataFrame({"报告日": ["20241231"]})
            return None

        mock_cache.get.side_effect = fake_get
        state = {"stock_code": "600519"}
        result = check_cache(state, cache=mock_cache)
        assert result["cache_result"] == "MISS"
