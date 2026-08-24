"""TDD tests for models.py — Agent 间通信的结构化输出模型。

参考 ADR-0011 和 TradingAgents (arXiv:2412.20138)。
结构化输出解决"电话效应"：agent 间传递 Pydantic 对象而非自由 Markdown。
"""

from finance_agent.citation import Claim, verify_claims
from finance_agent.models import (
    AnalystReport,
    DebateMessage,
    FundManagerDecision,
    TradeDecision,
)


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


class TestModelFieldConstraints:
    """枚举与范围约束（harden-llm-output-validation）。

    加固前 role 是裸 str、confidence 无 ge/le、round 无范围——
    LLM 串角色或返回百分数置信度不会被发现，只会污染报告渲染。
    """

    def test_debate_message_invalid_role_rejected(self):
        """非法角色值被拒绝（加固前为裸 str，静默透传）。"""
        import pytest

        with pytest.raises(ValueError):
            DebateMessage(
                role="随便",
                round=1,
                content="内容",
                key_arguments=["论据"],
            )

    def test_debate_message_all_legal_roles_accepted(self):
        """7 个合法角色值全部通过校验。"""
        for role in (
            "bull",
            "bear",
            "aggressive",
            "conservative",
            "neutral",
            "research_manager",
            "risk_judge",
        ):
            msg = DebateMessage(role=role, round=1, content="内容", key_arguments=["论据"])
            assert msg.role == role

    def test_debate_message_invalid_round_rejected(self):
        """round 小于 1 被拒绝。"""
        import pytest

        for badRound in (0, -1):
            with pytest.raises(ValueError):
                DebateMessage(
                    role="bull",
                    round=badRound,
                    content="内容",
                    key_arguments=["论据"],
                )

    def test_trade_decision_confidence_out_of_range_rejected(self):
        """置信度超出 0-1 被拒绝（如 LLM 按百分数返回 95）。"""
        import pytest

        for badConfidence in (95, -0.5, 1.5):
            with pytest.raises(ValueError):
                TradeDecision(
                    action="buy",
                    confidence=badConfidence,
                    reasoning="理由",
                )

    def test_trade_decision_confidence_boundaries_accepted(self):
        """置信度边界值 0 与 1 合法。"""
        for okConfidence in (0.0, 1.0):
            decision = TradeDecision(action="hold", confidence=okConfidence, reasoning="理由")
            assert decision.confidence == okConfidence


class TestFundManagerDecision:
    """Layer V 基金经理审批决策模型（harden-llm-output-validation）。"""

    def test_legal_decisions_accepted(self):
        for decision in ("approve", "reject", "return"):
            model = FundManagerDecision(decision=decision, reasoning="理由")
            assert model.decision == decision

    def test_normalizes_case_and_whitespace(self):
        """大小写与首尾空白归一化。"""
        assert FundManagerDecision(decision=" Approve ").decision == "approve"
        assert FundManagerDecision(decision="REJECT").decision == "reject"

    def test_invalid_decision_rejected(self):
        """非法值被拒绝，不做同义词映射。"""
        import pytest

        for illegal in ("revise", "拒绝", "maybe", ""):
            with pytest.raises(ValueError):
                FundManagerDecision(decision=illegal)

    def test_reasoning_optional(self):
        """reasoning 缺省为空串，不阻塞校验。"""
        assert FundManagerDecision(decision="approve").reasoning == ""


class TestTradeDecisionEvidenceRefs:
    """TradeDecision.evidence_refs 结构化论据引用（improve-decision-grounding）。"""

    def test_evidence_refs_parsed(self):
        decision = TradeDecision.model_validate(
            {
                "action": "buy",
                "confidence": 0.75,
                "reasoning": "理由",
                "evidence_refs": [
                    {"claim": "ROE 3.4% 高于行业均值", "source": "fundamental"},
                    {"claim": "股价站上 60 日均线", "source": "technical"},
                ],
            }
        )
        assert len(decision.evidence_refs) == 2
        assert decision.evidence_refs[0].source == "fundamental"
        assert decision.evidence_refs[0].claim == "ROE 3.4% 高于行业均值"

    def test_evidence_refs_default_empty(self):
        decision = TradeDecision.model_validate(
            {"action": "hold", "confidence": 0.5, "reasoning": "理由"}
        )
        assert decision.evidence_refs == []

    def test_source_aliases_normalized(self):
        decision = TradeDecision.model_validate(
            {
                "action": "buy",
                "confidence": 0.6,
                "reasoning": "理由",
                "evidence_refs": [
                    {"claim": "a", "source": "Technical_Analyst"},
                    {"claim": "b", "source": "BULL"},
                    {"claim": "c", "source": "research_manager_conclusion"},
                    {"claim": "d", "source": " sentiment "},
                ],
            }
        )
        sources = [r.source for r in decision.evidence_refs]
        assert sources == ["technical", "debate_bull", "research_manager", "sentiment"]

    def test_unknown_source_lenient(self):
        decision = TradeDecision.model_validate(
            {
                "action": "buy",
                "confidence": 0.6,
                "reasoning": "理由",
                "evidence_refs": [{"claim": "a", "source": "risk_debater"}],
            }
        )
        assert decision.evidence_refs[0].source == "risk_debater"

    def test_evidence_refs_none_scrubbed_to_empty(self):
        decision = TradeDecision.model_validate(
            {"action": "hold", "confidence": 0.5, "reasoning": "理由", "evidence_refs": None}
        )
        assert decision.evidence_refs == []

    def test_malformed_evidence_refs_items_dropped(self):
        decision = TradeDecision.model_validate(
            {
                "action": "hold",
                "confidence": 0.5,
                "reasoning": "理由",
                "evidence_refs": [
                    None,
                    {"claim": "缺 source"},
                    {"source": "缺 claim"},
                    {"claim": "正常", "source": "fundamental"},
                    "not-a-dict",
                ],
            }
        )
        assert [r.claim for r in decision.evidence_refs] == ["正常"]
        assert decision.evidence_refs[0].source == "fundamental"
