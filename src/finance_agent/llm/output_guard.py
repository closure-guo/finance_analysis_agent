# src/finance_agent/llm/output_guard.py
"""纯文本交付物输出合同校验器（delta add-output-contract-guard）。

凡 LLM 文本直接进入用户可见交付物（报告章节、研究聚焦摘要等）的路径，
嵌入前 MUST 经本校验：泄露检测（任务独白标记、非目标语言占比）、
截断检测（finish_reason=length 或句中悬空收尾）。
判定违约由调用方定向重试，重试仍违约回退结构化兜底（spec «纯文本交付物输出合同»）。
规则以 incident 036 实测泄露样本为基准、中远海能 2026-10-04 14:49 干净样本
为反例双向校准（误伤干净输出视为校验器缺陷）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 任务独白泄露模式（incident 036 实测；锚定行首/固定短语，降低误伤）
_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("leak:the_user_wants", re.compile(r"The user wants", re.IGNORECASE)),
    ("leak:draft_marker", re.compile(r"^\s*Draft\s*:", re.MULTILINE)),
    ("leak:key_points_marker", re.compile(r"Key points to weave in", re.IGNORECASE)),
    ("leak:important_constraint", re.compile(r"Important constraint\s*:", re.IGNORECASE)),
    ("leak:let_me", re.compile(r"^\s*(?:Let me|I'll|I will|I need to)\b", re.MULTILINE)),
)

# 句中悬空收尾（截断启发式；finish_reason 缺失时的兜底信号）
_TRUNCATED_TAIL = re.compile(r"(?:[0-9]+\.$|[,，、；;：:（(]$)")

# 中文交付物最低中文字符占比（对 CJK+拉丁字母总数；容忍 PE_ttm/MACD 等术语）。
# 校准依据：本规则定位是「英文独白主导」检测（incident 036 泄露样本占比约 0.17），
# 阈值须容忍数字密集的合法中文（含术语与数字 token）——CJK/拉丁分母不含数字，
# 数字密集中文摘要的字母占比天然偏低，0.6 会误伤研究聚焦等数字密集文体；
# 误伤干净输出视为校验器缺陷（spec 明文）。
_ZH_RATIO_MIN = 0.35

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass
class GuardVerdict:
    """校验判定（进 trace metadata，spec «判定结果可观测»）。"""

    ok: bool
    reason: str | None = None
    hits: list[str] = field(default_factory=list)


def validate_deliverable_text(
    text: str | None,
    *,
    target_lang: str = "zh",
    finish_reason: str | None = None,
) -> GuardVerdict:
    """校验 LLM 文本能否直接嵌入交付物。不抛错，返回判定由调用方处置。"""
    if not text or not text.strip():
        return GuardVerdict(ok=False, reason="empty", hits=["empty"])

    hits: list[str] = []
    if finish_reason == "length":
        hits.append("truncated:length")

    for name, pat in _LEAK_PATTERNS:
        if pat.search(text):
            hits.append(name)

    if target_lang == "zh":
        cjk = len(_CJK.findall(text))
        latin = len(_LATIN.findall(text))
        if cjk + latin > 0 and cjk / (cjk + latin) < _ZH_RATIO_MIN:
            hits.append("leak:lang_ratio")

    if "truncated:length" not in hits and _TRUNCATED_TAIL.search(text.rstrip()):
        hits.append("truncated:tail")

    if not hits:
        return GuardVerdict(ok=True)
    return GuardVerdict(ok=False, reason=hits[0], hits=hits)
