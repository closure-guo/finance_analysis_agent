"""TDD tests for nodes/research_manager.py — Layer II Research Manager。"""

from unittest.mock import patch

from finance_agent.nodes.research_manager import research_manager


class TestResearchManager:
    """Layer II Research Manager — 总结 Bull/Bear 辩论。"""

    @patch("finance_agent.nodes.research_manager.call_llm_streaming")
    def test_produces_conclusion(self, mock_llm):
        mock_llm.return_value = "综合多空双方观点，基本面强劲但需关注估值风险。"
        state = {
            "analyst_reports": {},
            "debate_history": [],
        }
        result = research_manager(state)
        assert "research_manager_conclusion" in result
        assert "基本面" in result["research_manager_conclusion"]
