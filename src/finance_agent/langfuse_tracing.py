"""Langfuse tracing 辅助（ADR-0015）。

集中管理 Langfuse 客户端的可用性判断与单例，供 llm.py 与
litellm_client.py 共用。配置了 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
时启用，否则跳过（本地开发与离线场景不受影响）。

litellm 内置 langfuse 集成因 1.85.x / 4.x 不兼容已禁用（见 llm.py 顶部补丁），
LLM 调用细节改由 start_as_current_observation 在 call_llm 三入口包裹，
图节点骨架由 CallbackHandler 在图调用边界注入。
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

_langfuse_client = None
_langfuse_checked = False


def get_langfuse():
    """返回 Langfuse 客户端单例；未配置或初始化失败返回 None。

    初始化失败时不缓存结果，允许下次调用重试（Langfuse 可能短暂不可用后恢复）。
    成功后缓存客户端单例。
    """
    global _langfuse_client, _langfuse_checked
    if _langfuse_checked:
        return _langfuse_client

    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        _langfuse_checked = True
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
        )
        _langfuse_checked = True
    except Exception:
        logging.getLogger("finance_agent.langfuse").warning(
            "Langfuse 初始化失败，将在下次调用重试", exc_info=True
        )
    return _langfuse_client


def get_callback_handler():
    """返回 LangChain/LangGraph CallbackHandler；未配置返回 None。

    供图调用边界使用：Send() 扇出会自动把 callback 传播到并行节点，
    使 5 层管线拓扑在 Langfuse 里显示为 span 树（节点骨架）。
    """
    client = get_langfuse()
    if client is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logging.getLogger("finance_agent.langfuse").warning(
            "Langfuse CallbackHandler 创建失败", exc_info=True
        )
        return None


_span_logger = logging.getLogger("finance_agent.langfuse")


@contextmanager
def open_span(name: str, input: dict | None = None):
    """创建 Langfuse span 上下文管理器；未配置或异常时优雅降级。

    用于工具调用、网络搜索等非 LLM 操作的可观测性追踪。复用
    get_langfuse() 单例，已配置时调用 start_as_current_observation
    建立 span（as_type=span），未配置或异常时降级为 yield None（零开销，
    业务无感知）。调用方可用 obs.update(output=...) 记录 output。

    Args:
        name: span 名称（如 "tool:web_search"、"search_api_call"）
        input: span 的 input 字段（dict）

    Yields:
        observation 对象（已配置时）或 None（降级时）
    """
    client = get_langfuse()
    if client is None:
        yield None
        return
    try:
        cm = client.start_as_current_observation(name=name, as_type="span", input=input or {})
    except Exception:
        _span_logger.warning("Langfuse span 创建失败: %s", name, exc_info=True)
        yield None
        return
    obs = cm.__enter__()
    try:
        yield obs
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            _span_logger.warning("Langfuse span 退出失败: %s", name, exc_info=True)
