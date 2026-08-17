# src/finance_agent/llm/adapters/litellm_adapter.py
"""litellm adapter：唯一允许 import/配置 litellm 的地方（delta Task 1.4）。

运行时防护收口（design 决策 4）：
- ``disable_streaming_logging``：incident 016 —— litellm 流式每个 chunk 向
  全局 100 线程池提交 logging，worker 内 asyncio.run 新建 ProactorEventLoop，
  Windows/Py3.14 ``_fallback_socketpair`` 并发竞态令线程永久卡在 accept()
  （100 worker 全灭、退出 join 挂死）。项目 Langfuse 走自研 SDK，零损失。
- ``drop_params``：历史行为保留（阶段二 Task 2.5 白名单化后收紧）。
- litellm-langfuse 兼容补丁：1.85.x 与 langfuse 4.x 深度不兼容
  （version 属性、sdk_integration 参数等多处不匹配），noop 其 logger。

业务模块（llm.py / harness/litellm_client.py）经 ``ensure_litellm_runtime``
触发初始化，不各自设置 —— 防止防护配置漂移。
"""

from __future__ import annotations

import threading

_INIT_LOCK = threading.Lock()
_initialized = False


def _apply_langfuse_compat_patch() -> None:
    """litellm-langfuse 兼容补丁（自 finance_agent/llm.py 迁入，行为不变）。"""
    try:
        import importlib.metadata

        import langfuse

        if not hasattr(langfuse, "version"):
            _lf_ver = importlib.metadata.version("langfuse")
            langfuse.version = type("version", (), {"__version__": _lf_ver})()  # type: ignore[attr-defined]
    except Exception:  # noqa: S110 -- 补丁失败不阻断初始化
        pass

    def _lf_noop(self, *a, **kw):  # noqa: ARG001
        pass

    def _lf_noop_init(self, *a, **kw):  # noqa: ARG001
        self.langfuse_sdk_version = "4.13.0"
        self.Langfuse = None
        self.langfuse_client = None

    for _cls_path in (
        "litellm.integrations.langfuse.langfuse.LangFuseLogger",
        "litellm.integrations.langfuse.langfuse_prompt_management.LangfusePromptManagement",
    ):
        try:
            _parts = _cls_path.rsplit(".", 1)
            _mod = __import__(_parts[0], fromlist=[_parts[1]])
            _cls = getattr(_mod, _parts[1])
            _cls.__init__ = _lf_noop_init
            for _method in ("log_event_on_langfuse", "_log_langfuse_v2", "_log_langfuse_v1"):
                if hasattr(_cls, _method):
                    setattr(_cls, _method, _lf_noop)
        except Exception:  # noqa: S110
            pass


def ensure_litellm_runtime() -> None:
    """幂等初始化 litellm 运行时防护（线程安全，可并发首次调用）。"""
    global _initialized
    if _initialized:
        return
    with _INIT_LOCK:
        if _initialized:
            return
        import litellm

        litellm.drop_params = True
        # incident 016 死锁防护（NOT RECOMMENDED 标记仅影响 litellm 自身
        # 用量回调——项目未注册任何 litellm callback，零功能损失）
        litellm.disable_streaming_logging = True
        _apply_langfuse_compat_patch()
        _initialized = True
