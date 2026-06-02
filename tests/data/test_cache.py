"""TDD tests for data/cache.py — SQLite 缓存 + TTL。

TTL 策略（ADR-0004）：
- 三大报表：持久化，TTL = 下个财报季（4/30 或 8/31 或 10/31）
- 行情数据：TTL = 当日收盘（当日 15:00 后过期）
- 行业归属：TTL = 30 天
- 预计算指标：TTL 同报表

接口：get(key) → data | None, set(key, data, ttl_seconds), delete(key)
"""

import time

import pandas as pd
import pytest

from finance_agent.data.cache import DataCache


@pytest.fixture
def cache(tmp_path):
    """每个测试用独立的 SQLite 文件。"""
    db_path = tmp_path / "test_cache.db"
    return DataCache(str(db_path))


class TestBasicOperations:
    def test_set_and_get_dict(self, cache):
        cache.set("test_key", {"a": 1, "b": 2})
        result = cache.get("test_key")
        assert result == {"a": 1, "b": 2}

    def test_set_and_get_dataframe(self, cache):
        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        cache.set("test_df", df)
        result = cache.get("test_df")
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["x", "y"]
        assert len(result) == 2

    def test_get_missing_key(self, cache):
        assert cache.get("nonexistent") is None

    def test_delete(self, cache):
        cache.set("del_me", {"val": 42})
        assert cache.get("del_me") is not None
        cache.delete("del_me")
        assert cache.get("del_me") is None

    def test_overwrite(self, cache):
        cache.set("key", {"v": 1})
        cache.set("key", {"v": 2})
        assert cache.get("key") == {"v": 2}


class TestTTLExpiration:
    def test_not_expired(self, cache):
        cache.set("fresh", {"val": 1}, ttl_seconds=3600)
        assert cache.get("fresh") == {"val": 1}

    def test_expired(self, cache):
        cache.set("stale", {"val": 1}, ttl_seconds=1)
        time.sleep(1.1)
        assert cache.get("stale") is None

    def test_no_ttl_never_expires(self, cache):
        cache.set("permanent", {"val": 1}, ttl_seconds=None)
        time.sleep(0.1)
        assert cache.get("permanent") == {"val": 1}

    def test_ttl_refreshed_on_set(self, cache):
        cache.set("key", {"v": 1}, ttl_seconds=2)
        time.sleep(1.0)
        # re-set before expiry
        cache.set("key", {"v": 2}, ttl_seconds=2)
        time.sleep(1.5)
        # should still be there (new TTL)
        assert cache.get("key") == {"v": 2}


class TestKeyPatterns:
    def test_stock_code_in_key(self, cache):
        cache.set("600519:balance_sheet", {"data": True})
        assert cache.get("600519:balance_sheet") == {"data": True}

    def test_list_all_keys(self, cache):
        cache.set("a", 1)
        cache.set("b", 2)
        keys = cache.keys()
        assert set(keys) == {"a", "b"}


class TestTTLByDate:
    def test_set_with_expire_at(self, cache):
        """set 支持 expire_at 参数（绝对时间戳）。"""
        future = time.time() + 3600
        cache.set("dated", {"v": 1}, expire_at=future)
        assert cache.get("dated") == {"v": 1}

    def test_expire_at_past(self, cache):
        past = time.time() - 1
        cache.set("old", {"v": 1}, expire_at=past)
        assert cache.get("old") is None
