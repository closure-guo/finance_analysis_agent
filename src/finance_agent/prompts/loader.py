"""Prompt / Template 加载器。

ADR-0016：prompt 权威源为 Langfuse（配置启用时），本地 prompts/*.md 作兜底基线。
load_prompt 先查 Langfuse production label，失败/未配置时回退本地并打 WARN。
渲染仍由调用方用 .replace("{{key}}", ...) 完成（与 Langfuse {{var}} 语法一致），
故此处返回未 compile 的原始模板文本。lru_cache 使版本在进程内固定，
换版本靠改 production label + 重启进程。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("finance_agent.prompts")

_PROMPTS_DIR = Path(__file__).parent


def _langfuse_prompt_text(name: str) -> str | None:
    """从 Langfuse 拉取 production label 的原始模板文本；不可用返回 None。"""
    try:
        from finance_agent.langfuse_tracing import get_langfuse

        client = get_langfuse()
        if client is None:
            return None
        prompt = client.get_prompt(name)
        if prompt is None:
            return None
        return getattr(prompt, "prompt", None)
    except Exception as e:
        logger.debug("Langfuse prompt %s 拉取失败，将回退本地: %s", name, e)
        return None


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """加载 prompt：Langfuse production 优先，失败回退本地 prompts/*.md。

    回退时打 WARN 提示可能版本漂移（本地文件可能滞后于 Langfuse）。
    返回未 compile 的原始模板文本，调用方自行 .replace("{{key}}", ...)。
    """
    text = _langfuse_prompt_text(name)
    if text is not None:
        return text
    logger.warning("prompt %s 回退本地，可能版本漂移", name)
    p = _PROMPTS_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8")
