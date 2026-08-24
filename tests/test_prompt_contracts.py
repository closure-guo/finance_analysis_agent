"""提示词行为契约（enhance-agent-prompt-quality）。

prompt 是行为契约的一部分：分析师必须含反幻觉硬规则与分析方法论，
辩论者必须含对抗性指令，决策层必须含语义契约，research_manager 必须
含评级表态，deep_mode 必须含输出约束。
"""

from pathlib import Path

import pytest

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "src/finance_agent/prompts"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


ANALYSTS = ["fundamental_analyst", "macro_analyst", "technical_analyst", "sentiment_analyst"]


@pytest.mark.parametrize("name", ANALYSTS)
class TestAnalystAntiHallucination:
    def test_has_methodology_section(self, name):
        assert "## 分析方法论" in _load(f"{name}.md")

    def test_has_hard_rules_section(self, name):
        assert "## 反幻觉硬规则" in _load(f"{name}.md")

    def test_mandates_data_sufficiency_declaration(self, name):
        assert "数据不足" in _load(f"{name}.md")


DEBATERS = ["bull_debater", "bear_debater", "risk_debater"]


@pytest.mark.parametrize("name", DEBATERS)
class TestDebaterAdversarialInstruction:
    def test_has_debate_discipline_section(self, name):
        assert "## 辩论纪律" in _load(f"{name}.md")

    def test_mandates_refute_opponent(self, name):
        text = _load(f"{name}.md")
        assert "反驳" in text
        assert "论点" in text


DECISION_PROMPTS = ["trader", "risk_judge", "fund_manager"]


@pytest.mark.parametrize("name", DECISION_PROMPTS)
class TestDecisionSemantics:
    def test_has_semantics_section(self, name):
        assert "## 决策语义" in _load(f"{name}.md")


class TestTraderSemantics:
    def test_position_size_defined(self):
        text = _load("trader.md")
        assert "light" in text
        assert "moderate" in text
        assert "heavy" in text

    def test_confidence_anchored(self):
        assert "0.7" in _load("trader.md")


class TestRiskJudgeSemantics:
    def test_balanced_evidence_guidance(self):
        assert "均衡" in _load("risk_judge.md")


class TestFundManagerSemantics:
    def test_decision_options_defined(self):
        text = _load("fund_manager.md")
        assert "approve" in text
        assert "reject" in text
        assert "return" in text
