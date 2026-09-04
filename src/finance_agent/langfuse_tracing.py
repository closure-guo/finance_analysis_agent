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
from typing import Any

_langfuse_client = None
_langfuse_checked = False


def _silence_benign_detach_errors() -> None:
    """静音 OTel detach 的已知无害错误日志（add-user-feedback 排查引入）。

    背景：langfuse 的 start_as_current_observation / propagate_attributes 在
    async/executor 线程边界下，detach 的 contextvars token 可能已因内层
    attach/detach 失配而失效——langfuse 自身的 _detach_context_token_safely
    文档明确「observation 已完成，mismatch 可安全忽略」并为此内置了安全助手；
    但 OTel 公开 detach 路径仍会 logger.exception("Failed to detach context")
    刷出完整堆栈，污染运行日志。
    处理：按消息内容过滤该已知无害记录（opentelemetry.context logger 下的
    其他错误照常暴露），不改变任何行为——仅去日志噪音。
    """

    class _BenignDetachFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "Failed to detach context" not in (record.getMessage() or "")

    # 注意:logger 级 filter 只作用于经该 logger 发出的记录(传播记录不经过
    # 父 logger 的 filter),而本记录恰由 opentelemetry.context logger 发出
    logging.getLogger("opentelemetry.context").addFilter(_BenignDetachFilter())


def get_langfuse():
    """返回 Langfuse 客户端单例；未配置或初始化失败返回 None。

    初始化失败时不缓存结果，允许下次调用重试（Langfuse 可能短暂不可用后恢复）。
    成功后缓存客户端单例，并静音 OTel detach 的已知无害错误日志（见
    _silence_benign_detach_errors）。
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
        _silence_benign_detach_errors()
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

    langchain 为可选依赖（仅 langchain-core 时 graph 可跑，但 langfuse
    的 CallbackHandler 强依赖完整 langchain）——缺失时静默降级返回 None，
    只留 DEBUG 记录（WARNING 级 exc_info 刷屏会在每次 graph 调用污染日志）。
    """
    client = get_langfuse()
    if client is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except ModuleNotFoundError:
        logging.getLogger("finance_agent.langfuse").debug(
            "Langfuse CallbackHandler 不可用（缺 langchain 可选依赖），静默降级为 None"
        )
        return None
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


def update_current_span(metadata: dict | None = None, level: str | None = None) -> None:
    """更新当前 OTel span 的 metadata/level，带优雅降级。

    未配置 Langfuse 或 client 抛异常时不影响业务（对应 spec 降级契约）。
    用于节点内部子状态上 trace（解析降级 / 重试计数等），不新建 span。
    """
    client = get_langfuse()
    if client is None:
        return
    try:
        kwargs: dict[str, Any] = {}
        if metadata is not None:
            kwargs["metadata"] = metadata
        if level is not None:
            kwargs["level"] = level
        if kwargs:
            client.update_current_span(**kwargs)
    except Exception:
        _span_logger.warning("update_current_span 失败", exc_info=True)


def truncate_for_trace(text: str, max_bytes: int = 8192) -> str:
    """超长文本裁剪，保留首尾 + 中部省略标记，避免撑爆 Langfuse span。"""
    if not text:
        return text
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # 首尾各保留约 1/4，中部用省略标记；max_bytes<4 时强制至少 1 字节，避免 [-0:] 退化成全串
    _quarter = max(1, max_bytes // 4)
    head = encoded[:_quarter].decode("utf-8", errors="ignore")
    tail = encoded[-_quarter:].decode("utf-8", errors="ignore")
    omitted = len(encoded) - len(head.encode("utf-8")) - len(tail.encode("utf-8"))
    return f"{head}\n...[truncated {omitted} bytes]...\n{tail}"
