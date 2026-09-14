"""D5：辩论层与风险层 context 的 focus 注入（harden-decision-report-semantics）。"""

from finance_agent.nodes.debate import _build_debate_context
from finance_agent.nodes.risk import _build_risk_context


class TestFocusInjection:
    def test_debate_context_contains_focus(self):
        state = {
            "focus": "长期持有",
            "analyst_reports": {},
            "debate_history": [
                {"role": "bull", "round": 1, "content": "看多", "key_arguments": []},
            ],
        }
        assert "用户关注点: 长期持有" in _build_debate_context(state)

    def test_risk_context_contains_focus(self):
        state = {
            "focus": "长期持有",
            "trader_plan": {"action": "watch"},
            "risk_metrics": {},
            "risk_debate_history": [],
        }
        assert "用户关注点: 长期持有" in _build_risk_context(state)

    def test_empty_focus_no_injection(self):
        state = {
            "analyst_reports": {},
            "debate_history": [],
            "trader_plan": {},
            "risk_metrics": {},
            "risk_debate_history": [],
        }
        assert "用户关注点" not in _build_debate_context(state)
        assert "用户关注点" not in _build_risk_context(state)
