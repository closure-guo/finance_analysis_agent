"""TDD tests for after_risk_judge 门禁路由（update-decision-price-gate Task 2）。

gate fail → "__end__"（阻断：不进 FM 审批、不产出报告）；其余（pass/缺失/形态噪声）
→ "fund_manager"（fail-open 与管线既有容错风格一致）。
"""

from finance_agent.graph import build_5layer_graph
from finance_agent.routing import after_risk_judge


class TestAfterRiskJudgeRouting:
    def test_gate_fail_blocks_to_end(self):
        state = {"decision_price_gate": {"result": "fail", "note": "已打回仍未通过：1 条残留"}}
        assert after_risk_judge(state) == "__end__"

    def test_gate_pass_proceeds_to_fund_manager(self):
        state = {"decision_price_gate": {"result": "pass", "note": "打回后已修正"}}
        assert after_risk_judge(state) == "fund_manager"

    def test_gate_missing_or_malformed_defaults_to_fund_manager(self):
        assert after_risk_judge({}) == "fund_manager"
        assert after_risk_judge({"decision_price_gate": "garbage"}) == "fund_manager"
        assert after_risk_judge({"decision_price_gate": None}) == "fund_manager"

    def test_graph_wiring_replaces_unconditional_edge(self):
        """risk_judge → fund_manager 必须经条件路由（无条件边已移除）。

        langgraph 1.2 的 get_graph() draw 遇不可静态推断的分支即塌缩（本图首个
        无 map 条件边 check_cache 处即断），故检查 draw 所消费的同一结构源：
        builder.edges（无条件边）与 builder.branches（条件路由 branch ends）。
        """
        graph = build_5layer_graph()
        builder = graph.builder
        assert ("risk_judge", "fund_manager") not in builder.edges
        branch_ends = {
            end
            for branch in builder.branches.get("risk_judge", {}).values()
            for end in (getattr(branch, "ends", None) or {}).values()
        }
        assert "fund_manager" in branch_ends
        assert "__end__" in branch_ends
