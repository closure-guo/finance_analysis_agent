"""单点修复模块（surgical-citation-repair）：value_mismatch 稀疏失败的有据改写。

与全量定向重试（分析师整份重跑）相对：只把出错句 + 真值 + 局部上下文交给一次
轻量 LLM 调用做叙事一致性改写，回填正文后由 citation 节点强制整体重校验。
分流转额阈值（≥3 处回退全量）与「同处不二次修复」由 citation_node 把关，本模块
只做无状态修复：定位 → 提示词 → 一次 LLM → 整句回填，任何单点失败跳过不中断。
"""

from __future__ import annotations

import logging
import re

from finance_agent.citation import Claim
from finance_agent.nodes._llm_utils import call_llm_for_json

logger = logging.getLogger(__name__)

# system 固化模板，受 prompt 契约测试锁定（tests/nodes/test_citation_repair.py）
REPAIR_SYSTEM_PROMPT = (
    "你是财经报告单点修复器。输入一段出错的报告句子、它前后的上下文、"
    "以及校验器解析出的 ground_truth。只改必要处：修正错误数字及其直接联动"
    "的方向词/结论措辞，保持 markdown 格式与原句式，禁止改写其他内容、"
    '禁止引入新数字。输出 JSON：{"repaired_sentence": "修复后的整句", "stated_value": 修复后的数值}。'
    "direction 申报示例：正文写「下滑 X%」而真值为负 → stated_value=X、"
    "direction=negative；正文直接写 signed 值 → direction=positive。"
)

_NUM_RE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_SENT_SPLIT_RE = re.compile(r"(?<=[。；！？\n])")


def _numbers(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.finditer(text):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:  # pragma: no cover - 正则保证可解析
            continue
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.01, abs(b) * 0.001)


def locate_sentence(markdown: str, claim: Claim) -> str | None:
    """定位 claim 对应的出错句：句内数值 ≈ stated_value；多命中取首个。"""
    try:
        stated = float(claim.stated_value)
    except (TypeError, ValueError):
        return None
    for part in _SENT_SPLIT_RE.split(markdown):
        s = part.strip()
        if not s:
            continue
        if any(_close(n, stated) for n in _numbers(s)):
            return s
    return None


def build_repair_prompt(
    sentence: str,
    context_before: str,
    context_after: str,
    claim: Claim,
    ground_truth: object,
) -> str:
    """构造单点改写提示词（出错句 + 前后各段上下文 + 真值 + 输出契约）。"""
    return (
        f"出错句：{sentence}\n\n"
        f"前文上下文：{context_before or '（无）'}\n"
        f"后文上下文：{context_after or '（无）'}\n\n"
        f"校验器解析的 ground_truth：{ground_truth}\n"
        f"claim 申报：field_ref={claim.field_ref}, stated_value={claim.stated_value}, "
        f"interpretation={claim.interpretation}\n\n"
        "direction 申报示例：正文写「下滑 X%」而真值为负 → stated_value=X、"
        "direction=negative；正文直接写 signed 值 → direction=positive。\n\n"
        '要求：只改必要处，输出 {"repaired_sentence": "修复后的整句", "stated_value": 修复后的数值}。'
    )


def apply_repair(markdown: str, old_sentence: str, new_sentence: str) -> str | None:
    """整句替换（首处）；原句不在正文、新句为空或新旧相同 → None（不盲写）。"""
    if not old_sentence or not new_sentence or new_sentence == old_sentence:
        return None
    if old_sentence not in markdown:
        return None
    return markdown.replace(old_sentence, new_sentence, 1)


def repair_claims(
    markdown: str,
    failures: list[dict],
    llm_config=None,
) -> tuple[str, list[dict]]:
    """批量单点修复。failures: [{agent, claim, ground_truth}]。

    返回 (新 markdown, 修复记录)。单点失败（定位失败/LLM 异常/输出无契约）
    跳过该处不中断；记录含 before/after/ground_truth/repaired 供遥测。
    修复成功的记录携带 updated_claim（stated_value 取 LLM 申报的新值、
    interpretation 取修复后整句）——重校验仍是仲裁：LLM 改错照常 FAIL。
    """
    current = markdown
    records: list[dict] = []
    for f in failures:
        claim: Claim = f["claim"]
        gt = f.get("ground_truth")
        record = {
            "agent": f.get("agent"),
            "field_ref": claim.field_ref,
            "ground_truth": gt,
            "repaired": False,
        }
        try:
            old = locate_sentence(current, claim)
            if old is None:
                records.append(record)
                continue
            record["before"] = old
            idx = current.find(old)
            before = _last_paragraph(current[:idx])
            after = _next_paragraph(current[idx + len(old) :])
            resp = call_llm_for_json(
                build_repair_prompt(old, before, after, claim, gt),
                system=REPAIR_SYSTEM_PROMPT,
                node_name="citation_repair",
                llm_config=llm_config,
            )
            new = str((resp or {}).get("repaired_sentence") or "").strip()
            new_stated = (resp or {}).get("stated_value")
            updated = apply_repair(current, old, new)
            if updated is None or new_stated is None:
                records.append(record)
                continue
            record["after"] = new
            record["repaired"] = True
            record["stated_value"] = new_stated
            record["updated_claim"] = claim.model_copy(
                update={"stated_value": new_stated, "interpretation": new}
            )
            current = updated
        except Exception as e:  # noqa: BLE001 - 单点失败隔离（spec：跳过不中断）
            logger.warning("citation 单点修复失败 %s: %s", claim.field_ref, e)
        records.append(record)
    return current, records


def _last_paragraph(text: str) -> str:
    """取光标前最近一段非空文本（段落以空行/标题分隔）。"""
    parts = re.split(r"\n\s*\n|^#+ .*$", text, flags=re.MULTILINE)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts[-1] if parts else ""


def _next_paragraph(text: str) -> str:
    parts = re.split(r"\n\s*\n", text, flags=re.MULTILINE)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts[0] if parts else ""
