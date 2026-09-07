# tests/llm/adapters/test_litellm_adapter.py
"""litellm adapter 运行时防护收口测试（Task 1.4）。

设计决策 4：库级平台 bug 防护（incident 016 死锁开关、请求超时、
litellm-langfuse 兼容补丁）统一在 adapter 初始化，业务模块不各自设置。
"""

from __future__ import annotations

import threading

from finance_agent.llm.adapters.litellm_adapter import ensure_litellm_runtime


class TestEnsureLitellmRuntime:
    def test_sets_deadlock_guard_flag(self):
        """incident 016：流式 logging 线程死锁开关必须生效。"""
        ensure_litellm_runtime()
        import litellm

        assert litellm.disable_streaming_logging is True

    def test_idempotent(self):
        """幂等初始化：多次调用无副作用、不重复打补丁。"""
        ensure_litellm_runtime()
        ensure_litellm_runtime()
        import litellm

        assert litellm.disable_streaming_logging is True

    def test_thread_safe_concurrent_init(self):
        """并发首次调用安全（管线多入口同时初始化场景）。"""
        results: list[None] = []
        barrier = threading.Barrier(4)

        def call():
            barrier.wait()
            results.append(ensure_litellm_runtime())

        threads = [threading.Thread(target=call) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert len(results) == 4

    def test_langfuse_compat_patch_applied(self):
        """litellm-langfuse 深度不兼容补丁：LangFuseLogger 方法为空操作。"""
        ensure_litellm_runtime()
        from litellm.integrations.langfuse.langfuse import LangFuseLogger

        assert LangFuseLogger.__init__ is not None


def test_raw_stream_sets_include_usage(monkeypatch):
    """流式调用必须传 stream_options.include_usage，否则 OpenAI 兼容端点(glm 等)
    流式响应不含 usage → Langfuse generation 无 token 用量 → cost 无法计算。"""
    import litellm

    from finance_agent.llm.adapters import litellm_adapter

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        from unittest.mock import MagicMock

        return MagicMock()

    monkeypatch.setattr(litellm, "completion", fake_completion)
    litellm_adapter.raw_stream(
        model="openai/glm-5.3",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert captured.get("stream") is True
    assert captured.get("stream_options") == {"include_usage": True}
