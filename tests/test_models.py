"""TDD tests for models.py — Agent 间通信的结构化输出模型。

参考 ADR-0011 和 TradingAgents (arXiv:2412.20138)。
结构化输出解决"电话效应"：agent 间传递 Pydantic 对象而非自由 Markdown。
"""

from finance_agent.citation import Claim, verify_claims
from finance_agent.models import AnalystReport, DebateMessage, TradeDecision


class TestAnalystReport:
    """Layer I 分析师输出模型。"""

    def test_report_contains_claims_for_verification(self):
        """AnalystReport 包含 Claim 列表，可提取用于引用校验。"""
        report = AnalystReport(
            agent_name="fundamental",
            summary="基本面分析",
            key_findings=["ROE 28.33%", "资产负债率 40%"],
            claims=[
                Claim(
                    claim_type="numerical",
                    source_type="data",
                    field_ref="solvency_metrics.资产负债率.2024",
                    stated_value=40.0,
                    interpretation="资产负债率 40%",
                ),
            ],
            markdown="## 基本面分析\n...",
        )
        assert len(report.claims) == 1
        # 可以直接传给 verify_claims
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}
        results = verify_claims(report.claims, state)
        assert results[0].status == "PASS"


class TestDebateMessage:
    """Layer II/IV 辩论消息模型。"""

    def test_bull_bear_debate_message(self):
        """Bull/Bear 辩论消息包含角色、轮次、论点。"""
        msg = DebateMessage(
            role="bull",
            round=1,
            content="基于强劲的 ROE 增长和低负债率，建议买入",
            key_arguments=["ROE 28.33% 高于行业平均", "资产负债率仅 40%"],
        )
        assert msg.role == "bull"
        assert msg.round == 1
        assert len(msg.key_arguments) == 2

    def test_risk_debate_message(self):
        """风险管理辩论消息。"""
        msg = DebateMessage(
            role="conservative",
            round=1,
            content="虽然基本面稳健，但需关注估值过高风险",
            key_arguments=["PE 处于历史 90 分位"],
        )
        assert msg.role == "conservative"


class TestTradeDecision:
    """Layer III/IV 交易决策模型。"""

    def test_buy_decision(self):
        """买入决策包含方向、置信度、理由。"""
        decision = TradeDecision(
            action="buy",
            confidence=0.75,
            reasoning="ROE 持续高于 15%，负债率健康，估值合理",
        )
        assert decision.action == "buy"
        assert decision.confidence > 0.5

    def test_invalid_action_rejected(self):
        """无效的交易方向被拒绝。"""
        import pytest

        with pytest.raises(ValueError):
            TradeDecision(
                action="strong_buy",
                confidence=0.8,
                reasoning="",
            )
