"""TradeDecision 相关 prompt 的内容契约（improve-decision-grounding）。

prompt 是行为契约的一部分：trader/risk_judge 必须要求模型输出
evidence_refs，否则 judge 无结构化引用可核对。
"""

from pathlib import Path

import pytest

from finance_agent.models import TRADE_EVIDENCE_SOURCES

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "src/finance_agent/prompts"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


class TestTraderPromptEvidenceRefs:
    def test_example_contains_evidence_refs(self):
        assert '"evidence_refs"' in _load("trader.md")

    def test_mandates_ref_for_each_reasoning_claim(self):
        text = _load("trader.md")
        assert "evidence_ref" in text
        assert "source" in text

    def test_source_enum_listed(self):
        text = _load("trader.md")
        assert "technical" in text
        assert "debate_bull" in text
        assert "research_manager" in text


class TestRiskJudgePromptEvidenceRefs:
    def test_example_contains_evidence_refs(self):
        assert '"evidence_refs"' in _load("risk_judge.md")

    def test_mandates_passthrough_without_fabrication(self):
        text = _load("risk_judge.md")
        assert "evidence_ref" in text
        # 不虚构来源 + 允许空数组（无可对应来源时）
        assert "不得" in text
        assert "[]" in text


class TestPromptSourceEnumDriftGuard:
    """prompt 的 source 枚举必须与 models.TRADE_EVIDENCE_SOURCES 一致（final review F5）。"""

    @pytest.mark.parametrize("name", ["trader.md", "risk_judge.md"])
    def test_all_canonical_sources_listed(self, name):
        text = _load(name)
        for src in TRADE_EVIDENCE_SOURCES:
            assert src in text, f"{name} 缺 source: {src}"
