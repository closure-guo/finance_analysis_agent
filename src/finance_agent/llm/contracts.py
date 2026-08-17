# src/finance_agent/llm/contracts.py
"""结构化输出合同（delta Task 3.1，设计档案 §9）。

所有「LLM 文本 → json/Pydantic/进管线/进评估」的路径统一走：
    extract_json → Pydantic validate → repair（1-2 次）→ OutputContractError

- ``extract_json``：自 nodes/_llm_utils.parse_json_response 迁入并升级，
  含 markdown fence、首尾噪声、尾逗号清理（incident 017 实战炸点）。
- ``parse_with_contract``：validate + repair 编排。repair 函数由调用方
  注入（真实场景包 LLM 重发带 schema/错误/原输出的强化 prompt），
  本模块不依赖具体 LLM 调用，保持可测。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import cast

from pydantic import BaseModel, ValidationError

from finance_agent.llm.errors import OutputContractError

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
# 尾逗号：`,]` / `,}`（含空白/换行）→ 删逗号
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def extract_json(text: str) -> dict:
    """从 LLM 响应提取 JSON：fence/噪声/尾逗号全兼容。

    失败抛 JSONDecodeError（调用方决定是否 repair——见 parse_with_contract）。
    """
    match = _JSON_FENCE_RE.search(text)
    if match:
        text = match.group(1)
    text = text.strip()
    try:
        return cast(dict, json.loads(text))
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx = text.find("{")
    if idx >= 0:
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            return cast(dict, obj)
        except json.JSONDecodeError:
            pass
        cleaned = _TRAILING_COMMA_RE.sub(r"\1", text[idx:])
        try:
            obj, _ = decoder.raw_decode(cleaned)
            return cast(dict, obj)
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No JSON object found", text, 0)


def parse_with_contract[T: BaseModel](
    text: str,
    *,
    schema: type[T],
    repair: Callable[[str, str], str] | None,
    max_repairs: int = 2,
) -> T:
    """extract → validate → repair → OutputContractError 编排。

    repair 签名 (raw_excerpt, error) -> 修正文本；None 表示不重试。
    重试耗尽后抛 OutputContractError（带 raw_excerpt 供 trace 审计），
    调用方按节点语义处理——不静默降级关键决策（如 fund_manager）。
    """
    excerpt = text[:500]
    try:
        data = extract_json(text)
        return schema.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        error_detail = str(exc)
        if repair is None:
            raise OutputContractError(
                f"结构化输出解析失败且未配置 repair：{error_detail}",
                raw_excerpt=excerpt,
            ) from exc
        for _ in range(max_repairs):
            try:
                fixed = repair(excerpt, error_detail)
                return schema.model_validate(extract_json(fixed))
            except (json.JSONDecodeError, ValidationError) as exc2:
                error_detail = str(exc2)
                continue
        raise OutputContractError(
            f"repair {max_repairs} 次后仍失败：{error_detail}", raw_excerpt=excerpt
        ) from exc


__all__ = ["extract_json", "parse_with_contract", "OutputContractError"]
