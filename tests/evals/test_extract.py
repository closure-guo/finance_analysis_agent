# tests/evals/test_extract.py
"""judge 变量提取:state → 9 个字符串变量,缺失容错,结论章节提取。"""

from evals.extract import extract_conclusion, extract_judge_vars

from finance_agent.models import TradeDecision


def _state() -> dict:
    return {
        "final_report": "# 报告\n## 财务分析\n很好。\n## 结论\n建议买入,目标价 2000。\n## 风险提示\n波动。",
        "analyst_reports": {
            "fundamental": {"summary": "基本面强劲", "claims": []},
            "technical": {"conclusion": "均线上扬"},
            "macro": {},
            "sentiment": {"summary": "情绪偏热"},
        },
        "debate_history": [
            {"role": "bull", "content": "看多理由"},
            {"role": "bear", "content": "看空理由"},
        ],
        "research_manager_conclusion": "综合看多方占优",
        "final_trade_decision": {"action": "buy", "confidence": 0.8, "reasoning": "论据充分"},
        "risk_debate_history": [{"role": "risky", "content": "激进看法"}],
        "fund_manager_decision": "approve",
    }


class TestExtractJudgeVars:
    def test_nine_keys_all_str(self):
        vars_ = extract_judge_vars(_state(), query="分析茅台")
        expected_keys = {
            "query",
            "report",
            "report_conclusion",
            "analyst_reports",
            "debate_history",
            "research_manager_decision",
            "trade_decision",
            "risk_judgment",
            "fund_manager_decision",
        }
        assert set(vars_.keys()) == expected_keys
        assert all(isinstance(v, str) for v in vars_.values())

    def test_values_mapped_from_state(self):
        vars_ = extract_judge_vars(_state(), query="分析茅台")
        assert "基本面强劲" in vars_["analyst_reports"]
        assert "看多理由" in vars_["debate_history"]
        assert vars_["research_manager_decision"] == "综合看多方占优"
        assert "buy" in vars_["trade_decision"]
        assert vars_["fund_manager_decision"] == "approve"
        assert "建议买入" in vars_["report_conclusion"]
        # review 加固:risk_judgment 拼接契约 + query/report echo
        assert "buy" in vars_["risk_judgment"], "risk_judgment 应含决策 JSON"
        assert "激进看法" in vars_["risk_judgment"], "risk_judgment 应含 risk_debate 末条"
        assert vars_["query"] == "分析茅台", "query 应原样 echo"
        assert "财务分析" in vars_["report"], "report 应含 final_report 原文"

    def test_missing_keys_give_empty_string(self):
        vars_ = extract_judge_vars({})
        assert vars_["report"] == ""
        assert vars_["analyst_reports"] == ""
        assert vars_["fund_manager_decision"] == ""

    def test_long_values_truncated(self):
        state = _state()
        state["research_manager_conclusion"] = "长" * 10000
        vars_ = extract_judge_vars(state)
        assert len(vars_["research_manager_decision"]) < 5000
        assert "truncated" in vars_["research_manager_decision"]


class TestExtractConclusion:
    def test_section_hit(self):
        report = "## 财务分析\nA\n## 结论\n买入。\n## 风险提示\nB"
        assert extract_conclusion(report) == "买入。"

    def test_fallback_to_tail(self):
        report = "没有任何章节标题。" + "尾" * 600
        conclusion = extract_conclusion(report)
        assert conclusion == "尾" * 500

    def test_empty_report(self):
        assert extract_conclusion("") == ""


class TestPydanticStateCompat:
    """管线 state 中 debate/analyst 为 pydantic 对象时须正常提取。

    跑批实测：graph.invoke 返回的 state 里 DebateMessage 是 pydantic 实例，
    _summarize_debate 的 isinstance(dict) 静默跳过 → judge 拿到空辩论打 1 分
    （debate_quality 全 1.0 的根因，混在真实分数中不可察觉）。
    """

    def test_pydantic_debate_messages_extracted(self):
        from finance_agent.models import DebateMessage

        state = {
            "debate_history": [
                DebateMessage(
                    role="bull", round=1, content="看多：净息差改善", key_arguments=["a"]
                ),
                DebateMessage(role="bear", round=1, content="看空：不良抬头", key_arguments=["b"]),
            ],
        }
        vars_ = extract_judge_vars(state, query="q")
        assert "看多：净息差改善" in vars_["debate_history"]
        assert "看空：不良抬头" in vars_["debate_history"]

    def test_pydantic_risk_debate_extracted(self):
        from finance_agent.models import DebateMessage

        state = {
            "risk_debate_history": [
                DebateMessage(role="aggressive", round=1, content="加仓", key_arguments=[])
            ]
        }
        vars_ = extract_judge_vars(state, query="q")
        assert "加仓" in vars_["risk_judgment"]


class TestSerializeDecisionEvidenceRefs:
    """_serialize_decision / trade_decision 变量含 evidence_refs。"""

    def test_judge_var_trade_decision_contains_evidence_refs(self):
        state = {
            "final_trade_decision": TradeDecision.model_validate(
                {
                    "action": "buy",
                    "confidence": 0.75,
                    "reasoning": "理由",
                    "evidence_refs": [{"claim": "ROE 3.4%", "source": "fundamental"}],
                }
            ),
            "analyst_reports": {},
            "risk_debate_history": [],
        }
        vars_ = extract_judge_vars(state)
        assert "evidence_refs" in vars_["trade_decision"]
        assert "fundamental" in vars_["trade_decision"]


class TestSummarizeAnalystReportsKeepsNumbers:
    """_summarize_analyst_reports 必须保留可核对的数值（claims 附注）。"""

    def test_claim_numbers_preserved(self):
        reports = {
            "fundamental": {
                "agent_name": "fundamental",
                "summary": "盈利能力稳健",
                "key_findings": ["ROE 提升"],
                "claims": [
                    {
                        "claim_type": "numerical",
                        "source_type": "data",
                        "field_ref": "profitability_metrics.roe.2024",
                        "stated_value": 3.4,
                        "interpretation": "ROE 处于行业中等水平",
                    }
                ],
                "markdown": "# fundamental\n正文",
            }
        }
        state = {
            "final_trade_decision": {},
            "analyst_reports": reports,
            "risk_debate_history": [],
        }
        vars_ = extract_judge_vars(state)
        assert "3.4" in vars_["analyst_reports"]
        assert "ROE 处于行业中等水平" in vars_["analyst_reports"]
