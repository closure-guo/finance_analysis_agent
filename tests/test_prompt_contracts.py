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
        assert "对方" in text


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
        assert "≥0.7" in _load("trader.md")


class TestRiskJudgeSemantics:
    def test_balanced_evidence_guidance(self):
        assert "均衡" in _load("risk_judge.md")


class TestFundManagerSemantics:
    def test_decision_options_defined(self):
        text = _load("fund_manager.md")
        assert "approve" in text
        assert "reject" in text
        assert "return" in text


class TestResearchManagerStance:
    def test_has_stance_section(self):
        assert "## 评级表态" in _load("research_manager.md")

    def test_mandates_direction(self):
        text = _load("research_manager.md")
        assert "看多" in text
        assert "看空" in text
        assert "中性" in text


class TestDeepModeOutputConstraint:
    def test_has_output_constraint_section(self):
        assert "## 输出约束" in _load("deep_mode.md")

    def test_bounded_to_tool_output(self):
        assert "工具输出" in _load("deep_mode.md")


class TestReportSummaryGrounding:
    def test_mandates_material_only(self):
        src = Path(__file__).resolve().parents[1] / "src/finance_agent/nodes/report.py"
        text = src.read_text(encoding="utf-8")
        assert "仅基于" in text
        assert "不得引入" in text


SRC_DIR = Path(__file__).resolve().parents[1] / "src/finance_agent"


class TestStockParsingConvergence:
    def test_stock_parsing_prompt_lives_only_in_react_agent(self):
        # nlp.py 必须不存在；股票解析提示词文本必须只出现在 react_agent.py 一处
        assert not (SRC_DIR / "nlp.py").exists()
        hits = []
        for py in SRC_DIR.rglob("*.py"):
            if "你是A股股票代码解析助手" in py.read_text(encoding="utf-8"):
                hits.append(str(py.relative_to(SRC_DIR)))
        assert hits == ["react_agent.py"], hits

    def test_react_system_prompt_removed(self):
        ra = (SRC_DIR / "react_agent.py").read_text(encoding="utf-8")
        assert "REACT_SYSTEM_PROMPT" not in ra


class TestCycleFitMethodology:
    """周期适配方法论契约（update-agent-prompt-cycle-fit）。"""

    def test_fundamental_relative_and_cycle_aware(self):
        text = _load("fundamental_analyst.md")
        assert "同业" in text
        assert "周期" in text or "环境" in text

    def test_technical_mandates_rsa_blunting_in_strong_trend(self):
        text = _load("technical_analyst.md")
        assert "钝化" in text
        assert "趋势" in text

    def test_macro_mandates_m1_m2_scissors(self):
        text = _load("macro_analyst.md")
        assert "剪刀差" in text

    def test_macro_mandates_stale_downweight(self):
        text = _load("macro_analyst.md")
        assert "滞后" in text


class TestTechnicalArrayOrderContract:
    """incident 022：引用 -1 前须核对序列尾部（正序，末尾=最新）。"""

    def test_technical_prompt_mandates_tail_verification(self):
        text = _load("technical_analyst.md")
        assert "序列尾部" in text or "末尾" in text
        assert "正序" in text
