# tests/llm/test_probe_cache.py — ProbeCache 缓存键五要素 + TTL 行为（设计档案 §13）
from __future__ import annotations

import threading

import pytest

from finance_agent.llm.probe_cache import (
    ProbeCache,
    _reset_probe_cache_for_tests,
    cache_key,
    get_probe_cache,
)
from finance_agent.llm.probes import build_probe_report


@pytest.fixture(autouse=True)
def _fresh_singleton():
    _reset_probe_cache_for_tests()
    yield
    _reset_probe_cache_for_tests()


def _report(latency: int = 100) -> object:
    return build_probe_report(
        non_stream=True,
        stream=True,
        tool_call=True,
        tool_followup=True,
        json_output=True,
        latency_ms=latency,
    )


def test_put_get_roundtrip() -> None:
    cache = ProbeCache()
    report = _report()
    cache.put("k1", report)  # type: ignore[arg-type]
    assert cache.get("k1") is report


def test_expired_entry_returns_none_and_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ProbeCache()
    report = _report()
    cache.put("k1", report)  # type: ignore[arg-type]
    # 让 monotonic 时间前移超过 TTL
    real_monotonic = __import__("time").monotonic
    monkeypatch.setattr(
        "finance_agent.llm.probe_cache.time.monotonic",
        lambda: real_monotonic() + 86401.0,
    )
    assert cache.get("k1") is None
    # 条目应已被清除
    monkeypatch.undo()
    assert cache.get("k1") is None


def test_reput_same_key_overwrites() -> None:
    cache = ProbeCache()
    r1, r2 = _report(100), _report(200)
    cache.put("k1", r1)  # type: ignore[arg-type]
    cache.put("k1", r2)  # type: ignore[arg-type]
    assert cache.get("k1") is r2


def test_cache_key_five_components(monkeypatch: pytest.MonkeyPatch) -> None:
    base = cache_key(model="openai/glm-5.2", base_url="https://x/v1", api_key="sk-a")
    assert cache_key(model="openai/glm-5.2", base_url="https://x/v1", api_key="sk-a") == base
    # model 变化
    assert cache_key(model="openai/gpt-4o", base_url="https://x/v1", api_key="sk-a") != base
    # base_url 变化
    assert cache_key(model="openai/glm-5.2", base_url="https://y/v1", api_key="sk-a") != base
    # api_key 变化
    assert cache_key(model="openai/glm-5.2", base_url="https://x/v1", api_key="sk-b") != base
    # litellm version 变化
    monkeypatch.setattr("finance_agent.llm.probe_cache._litellm_version", lambda: "9.9.9")
    assert cache_key(model="openai/glm-5.2", base_url="https://x/v1", api_key="sk-a") != base


def test_invalidate_removes_entry() -> None:
    cache = ProbeCache()
    cache.put("k1", _report())  # type: ignore[arg-type]
    cache.invalidate("k1")
    assert cache.get("k1") is None
    cache.invalidate("missing")  # 不存在也不抛错


def test_singleton_and_reset() -> None:
    a = get_probe_cache()
    b = get_probe_cache()
    assert a is b
    _reset_probe_cache_for_tests()
    c = get_probe_cache()
    assert c is not a


def test_thread_safety_smoke() -> None:
    cache = ProbeCache()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            for j in range(50):
                key = f"k{i}-{j}"
                cache.put(key, _report())  # type: ignore[arg-type]
                cache.get(key)
                cache.invalidate(key)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    cache.clear()
    assert cache.get("k0-0") is None
