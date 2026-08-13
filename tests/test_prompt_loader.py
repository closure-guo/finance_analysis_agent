"""prompt loader 单元测试（agent-trace-content-fidelity Task 4）。

覆盖：
- `load_prompt_with_meta` 从 Langfuse 拉取时携带 version
- 本地兜底分支 version="local"
- `load_prompt`（旧接口）行为不变（向后兼容回归）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


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
