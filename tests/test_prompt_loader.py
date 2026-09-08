"""prompt loader 单元测试（agent-trace-content-fidelity Task 4 + add-prompt-hot-reload Task 1）。

覆盖：
- `load_prompt_with_meta` 从 Langfuse 拉取时携带 version
- 本地兜底分支 version="local"
- `load_prompt`（旧接口）行为不变（向后兼容回归）
- TTL 热更新：production 切换后过期生效、窗口内用缓存、恢复后跟随、两接口共享缓存
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_prompt_cache():
    """每个用例前清空 loader 进程内 TTL 缓存（防用例间串味）。"""
    from finance_agent.prompts import loader

    loader._clear_cache()
    yield
    loader._clear_cache()


def test_load_prompt_with_meta_langfuse_version():
    """Langfuse 取得 prompt 时，PromptInfo 含 version。"""
    fake_prompt = MagicMock()
    fake_prompt.prompt = "模板内容"
    fake_prompt.version = 3
    fake_client = MagicMock()
    fake_client.get_prompt.return_value = fake_prompt
    with patch("finance_agent.prompts.loader._get_client", return_value=fake_client):
        from finance_agent.prompts.loader import PromptInfo, load_prompt_with_meta

        info = load_prompt_with_meta("technical_analyst")
    assert isinstance(info, PromptInfo)
    assert info.template == "模板内容"
    assert info.prompt_name == "technical_analyst"
    assert info.prompt_version == 3


def test_load_prompt_with_meta_local_fallback():
    """Langfuse 拉取失败回退本地时，version='local'。"""
    fake_client = MagicMock()
    fake_client.get_prompt.return_value = None
    with patch("finance_agent.prompts.loader._get_client", return_value=fake_client):
        from finance_agent.prompts.loader import load_prompt_with_meta

        info = load_prompt_with_meta("technical_analyst")
    assert info.prompt_version == "local"
    assert info.prompt_name == "technical_analyst"
    # 本地文件读到内容
    assert len(info.template) > 0


def test_load_prompt_with_meta_no_langfuse_client():
    """未配置 Langfuse（_get_client 返回 None）时走本地兜底。"""
    with patch("finance_agent.prompts.loader._get_client", return_value=None):
        from finance_agent.prompts.loader import load_prompt_with_meta

        info = load_prompt_with_meta("trader")
    assert info.prompt_version == "local"
    assert info.prompt_name == "trader"
    assert len(info.template) > 0


def test_load_prompt_with_meta_langfuse_exception_falls_back():
    """client.get_prompt 抛异常时降级到本地（不传播异常）。"""
    fake_client = MagicMock()
    fake_client.get_prompt.side_effect = RuntimeError("langfuse 5xx")
    with patch("finance_agent.prompts.loader._get_client", return_value=fake_client):
        from finance_agent.prompts.loader import load_prompt_with_meta

        info = load_prompt_with_meta("trader")
    assert info.prompt_version == "local"
    assert info.prompt_name == "trader"
    assert len(info.template) > 0


def test_load_prompt_legacy_returns_str_unchanged():
    """向后兼容回归：旧 load_prompt 仍返回 str（PromptInfo 不影响旧调用点）。"""
    fake_client = MagicMock()
    fake_client.get_prompt.return_value = None
    with patch("finance_agent.prompts.loader._get_client", return_value=fake_client):
        from finance_agent.prompts.loader import load_prompt

        result = load_prompt("trader")
    assert isinstance(result, str)
    assert len(result) > 0


# ── add-prompt-hot-reload Task 1：TTL 热更新 ──────────────────────────


def _fake_client_returning(text: str, version: int):
    fake_prompt = MagicMock()
    fake_prompt.prompt = text
    fake_prompt.version = version
    client = MagicMock()
    client.get_prompt.return_value = fake_prompt
    return client


class TestTtlHotReload:
    def test_ttl_expiry_follows_production_switch(self, monkeypatch):
        """production 切到 v2 且等待超过 TTL → 后续加载返回 v2 内容与版本。"""
        from finance_agent.prompts import loader

        monkeypatch.setattr(loader, "_CACHE_TTL", 0.05)
        v1 = _fake_client_returning("v1 内容", 1)
        with patch(loader.__name__ + "._get_client", return_value=v1):
            assert loader.load_prompt("trader") == "v1 内容"
        # production 切换:换 client(返回 v2),TTL 过期后应跟随
        time.sleep(0.06)
        v2 = _fake_client_returning("v2 内容", 2)
        with patch(loader.__name__ + "._get_client", return_value=v2):
            info = loader.load_prompt_with_meta("trader")
        assert info.template == "v2 内容"
        assert info.prompt_version == 2

    def test_within_ttl_uses_cache(self, monkeypatch):
        """TTL 窗口内:即使 Langfuse 已切换,仍用缓存旧内容(可接受收敛延迟)。"""
        from finance_agent.prompts import loader

        monkeypatch.setattr(loader, "_CACHE_TTL", 30.0)
        v1 = _fake_client_returning("v1 内容", 1)
        with patch(loader.__name__ + "._get_client", return_value=v1):
            loader.load_prompt("trader")
        v2 = _fake_client_returning("v2 内容", 2)
        with patch(loader.__name__ + "._get_client", return_value=v2):
            assert loader.load_prompt("trader") == "v1 内容"

    def test_fallback_then_recovery_follows_production(self, monkeypatch):
        """拉取失败回退本地(进缓存),TTL 过期后 Langfuse 恢复则回到 production。"""
        from finance_agent.prompts import loader

        monkeypatch.setattr(loader, "_CACHE_TTL", 0.05)
        broken = MagicMock()
        broken.get_prompt.side_effect = RuntimeError("down")
        with patch(loader.__name__ + "._get_client", return_value=broken):
            info1 = loader.load_prompt_with_meta("trader")
        assert info1.prompt_version == "local"  # 兜底也进缓存
        time.sleep(0.06)
        healthy = _fake_client_returning("恢复内容", 7)
        with patch(loader.__name__ + "._get_client", return_value=healthy):
            info2 = loader.load_prompt_with_meta("trader")
        assert info2.template == "恢复内容"
        assert info2.prompt_version == 7

    def test_legacy_and_meta_share_cache(self, monkeypatch):
        """load_prompt 与 load_prompt_with_meta 共享同一 TTL 缓存(一次拉取,两接口一致)。"""
        from finance_agent.prompts import loader

        monkeypatch.setattr(loader, "_CACHE_TTL", 30.0)
        client = _fake_client_returning("共享内容", 5)
        with patch(loader.__name__ + "._get_client", return_value=client):
            text = loader.load_prompt("trader")
            info = loader.load_prompt_with_meta("trader")
        assert text == "共享内容" == info.template
        assert client.get_prompt.call_count == 1  # 只拉一次
