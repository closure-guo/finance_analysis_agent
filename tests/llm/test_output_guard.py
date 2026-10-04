# tests/llm/test_output_guard.py
"""纯文本交付物输出合同校验器（delta add-output-contract-guard / incident 036）。"""

from __future__ import annotations

from finance_agent.llm.output_guard import validate_deliverable_text

# incident 036 实测泄露样本（拓荆 171013 报告研究聚焦段，节选）
_LEAKED_036 = (
    "The user wants a 150-200 character (Chinese characters) research focus summary "
    "for 拓荆科技 (Piotech), synthesizing the analysis outputs. Key points to weave in:\n\n"
    "- Rating: 中性 (0.50 confidence), watch decision\n\n"
    "Important constraint: cite financial data with latest disclosed period.\n\n"
    "Draft:\n\n"
    "“综合裁决为中性（置信度0.50），交易决策维持watch观望。多空优势错位于时间维度……PE_ttm 85."
)

# 干净反例（中远海能 2026-10-04 14:49 报告研究聚焦段，节选）
_CLEAN_ZH = (
    "中远海能多空证据大体均衡，给予中性评级（置信度0.55-0.6），维持观望。核心支撑在于："
    "油运高景气推动2026H1归母净利同比+143%，中期技术趋势完好（MA20较MA60高15%），"
    "PE_ttm约16.76倍估值不算贵。业绩利好已兑现后进入催化真空期，建议等待数据确认后再择向。"
)


def test_leaked_036_sample_rejected():
    v = validate_deliverable_text(_LEAKED_036)
    assert v.ok is False
    assert "leak:the_user_wants" in v.hits
    assert "leak:draft_marker" in v.hits
    assert "truncated:tail" in v.hits  # 「PE_ttm 85.」句中悬空


def test_clean_zh_sample_passes():
    v = validate_deliverable_text(_CLEAN_ZH)
    assert v.ok is True, f"干净样本被误伤: hits={v.hits}"
    assert v.hits == []


def test_finish_reason_length_forces_truncated():
    v = validate_deliverable_text(_CLEAN_ZH, finish_reason="length")
    assert v.ok is False
    assert "truncated:length" in v.hits


def test_tail_heuristic_catches_mid_sentence_cut():
    v = validate_deliverable_text("拓荆科技维持观望，现价对应PE_ttm 85.")
    assert v.ok is False
    assert "truncated:tail" in v.hits


def test_english_only_rejected_by_lang_ratio():
    v = validate_deliverable_text(
        "Piotech is a semiconductor equipment company with strong growth."
    )
    assert v.ok is False
    assert "leak:lang_ratio" in v.hits


def test_digit_dense_zh_fragment_passes():
    # 数字密集合法中文（研究聚焦文体典型句）：CJK/拉丁分母不含数字，
    # 数字密集中文的字母占比天然偏低，lang_ratio 阈值不得误伤（审查回归）
    v = validate_deliverable_text("2026H1归母净利同比+143%，PE_ttm约16.76倍，MA20较MA60高15%。")
    assert v.ok is True, f"数字密集干净片段被误伤: hits={v.hits}"
    assert v.hits == []


def test_empty_text_rejected():
    v = validate_deliverable_text("")
    assert v.ok is False
    assert v.reason == "empty"
