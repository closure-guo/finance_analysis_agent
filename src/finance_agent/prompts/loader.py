"""Prompt / Template 加载器。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """加载 prompts/*.md 文件内容。"""
    p = _PROMPTS_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8")


@lru_cache(maxsize=32)
def load_template(name: str) -> str:
    """加载 templates/*.md 文件内容。"""
    p = _TEMPLATES_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8")


def render_template(template_name: str, **kwargs: str) -> str:
    """加载模板并做 {{key}} 替换。"""
    text = load_template(template_name)
    for k, v in kwargs.items():
        text = text.replace(f"{{{{{k}}}}}", v)
    return text
