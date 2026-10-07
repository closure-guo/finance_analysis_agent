"""TDD tests: 分析师输出批注剥离 + 估值缺失文案数值格式化（add-output-lint）。

背景（2026-10-05 八份报告二轮质检，issue #244）：
- 深南电路(002916) 技术分析师把自我修正批注「（低于MA20约1.9%需修正）」
  泄漏进报告终稿关键发现；
- 南方航空(600029) 口径披露节原样输出未舍入浮点
  「TTM 归母净利润(-13.060000000000002)非正」。

「需修正」在辩论 prose 中是合法用语（赛轮「需修正其『多空证据实质均衡』
的定性」、光大「无需修正」），剥离规则 MUST 限定括号收尾形态避免误伤。
"""

from __future__ import annotations

import json

from finance_agent.models import AnalystReport
from finance_agent.nodes.analysts import _strip_editor_notes
from finance_agent.nodes.compute import _derive_pe_ttm


def _report(**overrides) -> AnalystReport:
    base: dict = {
        "agent_name": "technical",
        "summary": "技术面短线回调压力较大",
        "plain_conclusion": "技术面偏弱",
        "key_findings": ["中期多头结构未破"],
        "claims": [],
        "markdown": "## 技术面\n短线回调压力较大",
    }
    base.update(overrides)
    return AnalystReport.model_validate(base)


class TestStripEditorNotes:
    def test_shennan_note_stripped_from_key_finding(self):
        """深南实例：括号内自我修正批注整体移除，其余文字保留。"""
        rep = _report(
            key_findings=[
                "收盘价高于MA20约1.9%的偏离反向（低于MA20约1.9%需修正），MA20(380.25) > MA60(365.6)"
            ]
        )
        out = _strip_editor_notes(rep)
        assert out.key_findings[0] == "收盘价高于MA20约1.9%的偏离反向，MA20(380.25) > MA60(365.6)"

    def test_note_stripped_across_all_text_fields(self):
        note = "（EMA口径待核实需修正）"
        rep = _report(
            summary=f"结论正确{note}。",
            plain_conclusion=f"偏空{note}",
            markdown=f"## 技术面\n正文{note}结尾",
        )
        out = _strip_editor_notes(rep)
        assert note not in out.summary
        assert note not in out.plain_conclusion
        assert note not in out.markdown
        assert "结论正确。" in out.summary

    def test_negative_form_preserved(self):
        """「无需修正」否定形态是合法语义，MUST NOT 误伤。"""
        text = "口径核对完成（中报累计值无需修正）"
        rep = _report(key_findings=[text])
        out = _strip_editor_notes(rep)
        assert out.key_findings[0] == text

    def test_debate_prose_without_parens_preserved(self):
        """赛轮实例：无括号包裹的「需修正其…定性」是正常辩论用语。"""
        text = "支持其对观望合理性的论证，但需修正其『多空证据实质均衡』的定性"
        rep = _report(key_findings=[text])
        out = _strip_editor_notes(rep)
        assert out.key_findings[0] == text

    def test_non_tail_form_preserved(self):
        """「需修正」不在括号收尾位置（后仍有内容）→ 不命中。"""
        text = "（该结论需修正后才成立）"
        rep = _report(key_findings=[text])
        out = _strip_editor_notes(rep)
        assert out.key_findings[0] == text

    def test_overlong_content_not_matched(self):
        """括号内容超长（>48 字符）→ 不命中，避免吞掉正常长注释。"""
        long_content = "注" * 49 + "需修正"
        text = f"（{long_content}）"
        rep = _report(key_findings=[text])
        out = _strip_editor_notes(rep)
        assert out.key_findings[0] == text


class TestParsePathAppliesStrip:
    def test_parse_strips_note_in_key_findings(self):
        from finance_agent.nodes.analysts import _parse_analyst_report

        payload = {
            "agent_name": "technical",
            "summary": "短期回调压力较大",
            "plain_conclusion": "技术面偏弱",
            "key_findings": [
                "收盘价高于MA20约1.9%的偏离反向（低于MA20约1.9%需修正）",
                "MACD高位死叉",
            ],
            "claims": [],
            "markdown": "## 技术面\n关键发现含批注（低于MA20约1.9%需修正）",
        }
        rep = _parse_analyst_report(
            f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```", "technical"
        )
        assert "需修正）" not in rep.key_findings[0]
        assert "偏离反向" in rep.key_findings[0]
        assert "需修正）" not in rep.markdown
        assert rep.parse_degraded is False


class TestPeTtmReasonFormatting:
    def test_negative_ttm_reason_has_no_float_tail(self):
        """南航同型：8.10 − 0.94 + (-20.22) = -13.060000000000002 → 文案 -13.06。"""
        snap = {
            "报告日": "2026-06-30",
            "期类型": "中报",
            "归母净利润(累计)": -20.22,
            "上年同期归母净利润": 0.94,
        }
        pe, reason = _derive_pe_ttm(100.0, 8.1, snap)
        assert pe is None
        assert "-13.06" in reason
        assert "13.060000000000002" not in reason
