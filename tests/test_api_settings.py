"""Agent 设置中心（add-agent-settings-center）Task 6：API 端点集成测试。

覆盖缓存统计/清理、能力探测缓存清除、会话清空、run-info、数据源状态。
安全红线：`GET /api/run-info` 绝不含 apiKey；`POST /api/cache/clear` scope=all
未带 confirm=true 必须 400。
"""

from fastapi.testclient import TestClient

from finance_agent.api import app
from finance_agent.data.cache import get_shared_cache


def test_cache_stats_and_clear_all_requires_confirm():
    client = TestClient(app)
    # 造一个条目
    get_shared_cache().set("600519:news", {"n": 1})
    s = client.get("/api/cache/stats").json()
    assert s["data"]["entries"] >= 1
    # 全清不带 confirm → 400
    assert client.post("/api/cache/clear", json={"scope": "all"}).status_code == 400
    # 带 confirm → 成功且清空
    r = client.post("/api/cache/clear", json={"scope": "all", "confirm": True})
    assert r.status_code == 200
    assert get_shared_cache().keys() == []


def test_cache_clear_by_type_and_code():
    """按类别/按代码清空只删目标条目，其余保留。"""
    client = TestClient(app)
    # 按类别清空：仅删该类条目，其余类别保留
    get_shared_cache().set("600519:news", {"n": 1})
    get_shared_cache().set("600519:kline", {"n": 2})
    get_shared_cache().set("000001:news", {"n": 3})
    r = client.post("/api/cache/clear", json={"scope": "type", "data_type": "news"})
    assert r.status_code == 200 and r.json()["removed"] == 2
    assert get_shared_cache().get("600519:kline") == {"n": 2}
    assert get_shared_cache().get("600519:news") is None
    # 复位后测按代码清空：仅删该代码全部类别，其余代码保留
    client.post("/api/cache/clear", json={"scope": "all", "confirm": True})
    get_shared_cache().set("600519:news", {"n": 1})
    get_shared_cache().set("000001:kline", {"n": 4})
    r = client.post("/api/cache/clear", json={"scope": "code", "code": "600519"})
    assert r.status_code == 200 and r.json()["removed"] == 1
    assert get_shared_cache().get("600519:news") is None
    assert get_shared_cache().get("000001:kline") == {"n": 4}
    # 复位，避免污染其他测试
    client.post("/api/cache/clear", json={"scope": "all", "confirm": True})


def test_cache_clear_missing_param_400():
    """scope=type 缺 data_type / scope=code 缺 code / 未知 scope → 400。"""
    client = TestClient(app)
    assert client.post("/api/cache/clear", json={"scope": "type"}).status_code == 400
    assert client.post("/api/cache/clear", json={"scope": "code"}).status_code == 400
    assert client.post("/api/cache/clear", json={"scope": "nope"}).status_code == 400


def test_run_info_never_exposes_api_key():
    client = TestClient(app)
    body = client.get("/api/run-info").json()
    assert "apiKey" not in body
    assert "api_key" not in body
    assert "model" in body and "base_url" in body


def test_data_source_status_shape():
    client = TestClient(app)
    body = client.get("/api/data-source/status").json()
    assert "monitor" in body and "freshness" in body


def test_sessions_clear_all_and_probe_clear():
    client = TestClient(app)
    assert client.post("/api/sessions/clear-all").status_code == 200
    assert client.post("/api/cache/probe-cache/clear").status_code == 200
