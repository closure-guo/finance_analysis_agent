"""check_cache 缓存命中完整性测试（修复：HIT 路径丢失时效性数据）。

2026-09-08 二轮审计发现的缺陷：HIT 判定只含 5 key（3 报表+行业+行情），
命中即跳过 fetch_data，但 kline/benchmark_kline/macro_indicators/news_list
不在判定也不附带——同一股票 24h 内二次分析会得到技术面/宏观/舆情
全缺的残缺报告（分析师只能写「数据不足」）。

契约：HIT 的语义 = 分析所需核心数据完整可用。时效性核心数据
（K 线/基准/宏观/新闻）任一缺失或过期 SHALL MISS；HIT SHALL 附带全部
缓存命中的数据（含永久缓存的 quarterly_income）。
"""

from __future__ import annotations

import pandas as pd
import pytest

from finance_agent.data.cache import DataCache
from finance_agent.nodes.cache import check_cache

CODE = "688072"


@pytest.fixture
def cache():
    return DataCache(db_path=":memory:")


def _fill_slow_keys(cache: DataCache, code: str = CODE) -> None:
    """填充慢变 key（报表/行业/行情）——旧 HIT 判定的全部 5 key。"""
    cache.set(f"{code}:balance_sheet", {"bs": 1})
    cache.set(f"{code}:income_statement", {"inc": 1})
    cache.set(f"{code}:cash_flow_statement", {"cf": 1})
    cache.set(f"{code}:industry_info", {"industry": "半导体"})
    cache.set(f"{code}:stock_quote", {"name": "拓荆科技"}, ttl_seconds=86_400)


def _fill_fresh_keys(cache: DataCache, code: str = CODE) -> None:
    """填充时效 key（K 线/基准/宏观/新闻）——修复后纳入 HIT 判定。"""
    cache.set(
        f"{code}:kline", pd.DataFrame({"日期": ["2026-09-08"], "收盘": [632.0]}), ttl_seconds=3600
    )
    cache.set(
        "benchmark_kline",
        pd.DataFrame({"日期": ["2026-09-08"], "收盘": [4000.0]}),
        ttl_seconds=3600,
    )
    cache.set("macro_indicators", {"pmi": [{"v": 49.8}]}, ttl_seconds=86_400)
    cache.set(f"{code}:news", [{"title": "中报净利大增"}], ttl_seconds=3600)


class TestCacheHitCompleteness:
    """HIT = 核心数据完整可用（含时效数据）。"""

    def test_only_slow_keys_misses(self, cache):
        """只有报表/行业/行情命中而 kline 缺失 → MISS（旧实现返回 HIT，丢技术面）。"""
        _fill_slow_keys(cache)
        result = check_cache({"stock_code": CODE}, cache=cache)
        assert result["cache_result"] == "MISS", "kline 缺失仍判 HIT——技术面将全缺"

    def test_kline_expired_misses(self, cache):
        """kline 缓存过期（TTL 已过）→ MISS。"""
        _fill_slow_keys(cache)
        cache.set(f"{CODE}:kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=-1)  # 立即过期
        _fill_fresh_keys_except(cache, "kline")
        result = check_cache({"stock_code": CODE}, cache=cache)
        assert result["cache_result"] == "MISS"

    def test_news_missing_misses(self, cache):
        """news 缺失 → MISS（舆情维度核心数据）。"""
        _fill_slow_keys(cache)
        cache.set(f"{CODE}:kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=3600)
        cache.set("benchmark_kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=3600)
        cache.set("macro_indicators", {"pmi": []}, ttl_seconds=86_400)
        result = check_cache({"stock_code": CODE}, cache=cache)
        assert result["cache_result"] == "MISS", "news 缺失仍判 HIT——舆情将全缺"

    def test_macro_missing_misses(self, cache):
        """macro_indicators 缺失 → MISS。"""
        _fill_slow_keys(cache)
        cache.set(f"{CODE}:kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=3600)
        cache.set("benchmark_kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=3600)
        cache.set(f"{CODE}:news", [], ttl_seconds=3600)
        result = check_cache({"stock_code": CODE}, cache=cache)
        assert result["cache_result"] == "MISS", "宏观缺失仍判 HIT"

    def test_full_hit_carries_all_data(self, cache):
        """全 key 命中 → HIT 且附带 kline/benchmark/macro/news/quarterly。"""
        _fill_slow_keys(cache)
        _fill_fresh_keys(cache)
        cache.set(f"{CODE}:quarterly_income", pd.DataFrame({"季度": ["2026Q2"]}))  # 永久
        result = check_cache({"stock_code": CODE}, cache=cache)

        assert result["cache_result"] == "HIT"
        # 时效数据必须随 HIT 附带（旧实现全缺）
        assert result.get("kline") is not None and not result["kline"].empty
        assert result.get("benchmark_kline") is not None
        assert result.get("macro_indicators") == {"pmi": [{"v": 49.8}]}
        assert result.get("news_list") == [{"title": "中报净利大增"}]
        # 永久缓存的季度数据附带
        assert result.get("quarterly_income") is not None
        # 慢数据照旧附带
        assert result.get("stock_quote", {}).get("name") == "拓荆科技"
        assert result.get("industry_info", {}).get("industry") == "半导体"

    def test_empty_cache_misses(self, cache):
        """空缓存 → MISS（基础回归）。"""
        result = check_cache({"stock_code": CODE}, cache=cache)
        assert result["cache_result"] == "MISS"


def _fill_fresh_keys_except(cache: DataCache, skip: str) -> None:
    """填时效 key 但跳过指定项。"""
    if skip != "kline":
        cache.set(f"{CODE}:kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=3600)
    if skip != "benchmark_kline":
        cache.set("benchmark_kline", pd.DataFrame({"收盘": [1.0]}), ttl_seconds=3600)
    if skip != "macro_indicators":
        cache.set("macro_indicators", {"pmi": []}, ttl_seconds=86_400)
    if skip != "news":
        cache.set(f"{CODE}:news", [{"title": "x"}], ttl_seconds=3600)
