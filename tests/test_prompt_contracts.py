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
