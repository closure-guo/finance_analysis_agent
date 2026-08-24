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


def partial_json_progress(text: str, top_fields: list[str]) -> dict[str, str] | None:
    """尽力部分解析已生成正文，标注各顶层字段进度（llm-output-resume Task 1.3）。

    返回 {字段名: "done" | "in_progress" | "pending"}：
    - done：对应顶层字段的值已在文本中完整闭合（标量写完 / 容器闭合）；
    - in_progress：正在书写但未闭合（文本截断处所在顶层字段）；
    - pending：schema 顶层字段中尚未出现。
    文本不含 "{"（非 JSON/纯文本）或为空 → None（调用方降级仅尾部注入）。

    只报告「已闭合数量级」事实，不编造目标总数（"/5" 之类交付给续写指令）。
    纯函数：只做括号栈 + 引号扫描，不修改输入，也不做 JSON 完整校验。
    """
    start = text.find("{")
    if start < 0:
        return None

    stack: list[str] = []  # 括号栈（含根对象 {）
    seen: set[str] = set()  # 出现过的顶层 key
    done: set[str] = set()  # 值已完整闭合的顶层 key
    cur_key: str | None = None  # 当前值所属顶层 key
    expect_key = False  # 根层当前应读 key 而非值
    in_str = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
                # 根层字符串值闭合（非 key）→ 该字段 done
                if len(stack) == 1 and not expect_key and cur_key is not None:
                    done.add(cur_key)
                    expect_key = True
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
            if len(stack) == 1:
                expect_key = True  # 根对象内应读 key
        elif ch in "}]":
            # 根层标量在容器收口处补 done（如 {"a": 1} 的 }）
            if len(stack) == 1 and not expect_key and cur_key is not None:
                done.add(cur_key)
            if stack:
                stack.pop()
            if len(stack) == 0:
                break  # 根对象闭合，解析结束
            if len(stack) == 1:
                # 顶层容器值闭合 → done
                if cur_key is not None:
                    done.add(cur_key)
                expect_key = True
        elif ch == ":" and len(stack) == 1:
            key = _extract_key_around(text, i)
            if key:
                cur_key = key
                seen.add(key)
                expect_key = False
        elif ch == "," and len(stack) == 1:
            # 根层标量写完（逗号收口）
            if not expect_key and cur_key is not None:
                done.add(cur_key)
            expect_key = True

    # 截断时值未闭合 → 所在顶层字段 in_progress
    in_prog: str | None = None
    if cur_key is not None and cur_key not in done and not expect_key:
        in_prog = cur_key

    result: dict[str, str] = {}
    for f in top_fields:
        if f in done:
            result[f] = "done"
        elif f == in_prog or (in_prog is None and f in seen and f not in done):
            result[f] = "in_progress"
        else:
            result[f] = "pending"
    return result


def _extract_key_around(text: str, colon_idx: int) -> str | None:
    """在 colon 前找最近一个闭合引号包裹的 token（即 JSON key）。"""
    end = text.rfind('"', 0, colon_idx)
    if end < 0:
        return None
    start = text.rfind('"', 0, end)
    if start < 0:
        return None
    return text[start + 1 : end]


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


__all__ = ["extract_json", "parse_with_contract", "partial_json_progress", "OutputContractError"]
