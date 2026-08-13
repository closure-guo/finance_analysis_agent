"""Prompt / Template 加载器。

ADR-0016：prompt 权威源为 Langfuse（配置启用时），本地 prompts/*.md 作兜底基线。
load_prompt 先查 Langfuse production label，失败/未配置时回退本地并打 WARN。
渲染仍由调用方用 .replace("{{key}}", ...) 完成（与 Langfuse {{var}} 语法一致），
故此处返回未 compile 的原始模板文本。lru_cache 使版本在进程内固定，
换版本靠改 production label + 重启进程。

ADR-0015（agent-trace-content-fidelity Task 4）：load_prompt_with_meta 额外返回
prompt_name + prompt_version，供 Langfuse generation metadata 挂载，兑现
「Prompt 元数据可追溯」承诺。version 来自 Langfuse BasePrompt.version（int），
本地兜底为 "local"。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("finance_agent.prompts")

_PROMPTS_DIR = Path(__file__).parent


@dataclass
class PromptInfo:
    """prompt 模板 + 元数据，供 generation metadata 挂载。

    Attributes:
        template: 未 compile 的原始模板文本，调用方自行 .replace/.format 渲染。
        prompt_name: prompt 名称（Langfuse prompt name 或本地文件名 stem）。
        prompt_version: Langfuse BasePrompt.version（int）或本地兜底 "local"。
    """

    template: str
    prompt_name: str
    prompt_version: str | int


def _get_client():
    """获取 Langfuse 客户端；未配置/初始化失败时返回 None。

    薄封装 langfuse_tracing.get_langfuse，集中供 loader 内部复用，
    便于在单测中 patch（finance_agent.prompts.loader._get_client）。
    """
    from finance_agent.langfuse_tracing import get_langfuse

    return get_langfuse()


def _langfuse_prompt_text(name: str) -> str | None:
    """从 Langfuse 拉取 production label 的原始模板文本；不可用返回 None。"""
    try:
        client = _get_client()
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

    向后兼容入口（11+ caller + @lru_cache）。需要 prompt 元数据时改用
    load_prompt_with_meta。
    """
    text = _langfuse_prompt_text(name)
    if text is not None:
        return text
    logger.warning("prompt %s 回退本地，可能版本漂移", name)
    p = _PROMPTS_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8")


def load_prompt_with_meta(name: str) -> PromptInfo:
    """加载 prompt 并附带元数据（name + version），供 Langfuse generation metadata 使用。

    Langfuse production label 优先（含 version）；失败/未配置时回退本地
    （version="local"）。返回 PromptInfo，调用方用 .template 渲染、用
    .prompt_name/.prompt_version 透传给 call_llm* / chat_stream 的 metadata。

    不使用 @lru_cache：与 load_prompt 共享缓存会破坏「PromptInfo 与 version
    绑定」的语义边界（旧 str 接口的调用方不期望拿到 PromptInfo）；另开缓存
    又易与 load_prompt 的缓存出现版本漂移。每次直接读取（已读的本地文件
    IO 成本可忽略，Langfuse client 内部也有缓存）。
    """
    client = _get_client()
    if client is not None:
        try:
            prompt = client.get_prompt(name)
            if prompt is not None:
                text = getattr(prompt, "prompt", None)
                if text is not None:
                    return PromptInfo(
                        template=text,
                        prompt_name=name,
                        prompt_version=getattr(prompt, "version", "local"),
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("Langfuse prompt %s 拉取失败，回退本地: %s", name, e)
    # 本地兜底
    logger.warning("prompt %s 回退本地，可能版本漂移", name)
    p = _PROMPTS_DIR / f"{name}.md"
    return PromptInfo(
        template=p.read_text(encoding="utf-8"),
        prompt_name=name,
        prompt_version="local",
    )
