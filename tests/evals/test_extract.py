# tests/evals/test_extract.py
"""judge 变量提取:state → 9 个字符串变量,缺失容错,结论章节提取。"""

from evals.extract import extract_conclusion, extract_judge_vars

from finance_agent.citation import Claim
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

    def test_analyst_reports_prefers_plain_conclusion(self):
        """add-agent-readable-conclusion：analyst_reports 优先展示普通人可读结论。"""
        state = {
            "final_report": "报告",
            "analyst_reports": {
                "fundamental": {
                    "summary": "基本面黑话摘要：ROE 32%、负债率 41%",
                    "plain_conclusion": "基本面偏多：盈利质量优秀，负债率低",
                    "claims": [],
                }
            },
        }
        vars_ = extract_judge_vars(state, query="q")
        assert "基本面偏多：盈利质量优秀" in vars_["analyst_reports"]
        assert "ROE 32%" not in vars_["analyst_reports"]  # summary 不再默认展示

    def test_analyst_reports_fallbacks_without_plain_conclusion(self):
        """旧 trace 报告对象无 plain_conclusion 时回退 summary，不报错。"""
        state = {
            "final_report": "报告",
            "analyst_reports": {"fundamental": {"summary": "旧版本摘要", "claims": []}},
        }
        vars_ = extract_judge_vars(state, query="q")
        assert "旧版本摘要" in vars_["analyst_reports"]

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

    def test_fallback_starts_at_sentence_boundary(self):
        """回归（2026-09-09）：无结论性标题时不得从 report[-500:] 中间切开（半句话），
        须从最近断句边界（句号）之后开始。"""
        report = "前置句。" + "中" * 400 + "边界句。" + "尾" * 300
        conclusion = extract_conclusion(report)
        assert conclusion == "尾" * 300  # 从「边界句。」之后起，不以「中」开头

    def test_numbered_fund_manager_title(self):
        """真实报告结论标题为「## 六、基金经理决策」这类编号式，词表须匹配到。"""
        report = (
            "# 报告\n## 一、研究聚焦\n内容。\n"
            "## 六、基金经理决策\n批准买入，仓位 light，止损 1280。\n"
        )
        assert extract_conclusion(report) == "批准买入，仓位 light，止损 1280。"

    def test_last_conclusion_title_wins(self):
        """「多空辩论结论」等中间章节也含关键词时，取最后一个结论性标题。"""
        report = "## 三、多空辩论结论\n辩论内容\n## 六、基金经理决策\n最终决策内容\n"
        assert extract_conclusion(report) == "最终决策内容"

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

    def test_all_debate_rounds_kept_under_total_budget(self):
        """回归（2026-09-10 实测 2fd1ee6d）：多轮辩论总量超 _JUDGE_MAX_BYTES 时，
        整体 head/tail 截断把中间发言连【bear】标签一起挖掉——judge 评「逐条交锋」
        时看不到交锋过程。须按消息边界截断：每个角色标签都保留。"""
        messages = []
        for rnd, (role_a, role_b) in enumerate([("bull", "bear"), ("bull", "bear")], start=1):
            messages.append(
                {
                    "role": role_a,
                    "round": rnd,
                    "content": f"{role_a} 第{rnd}轮开场。" + "论据。" * 300,
                }
            )
            messages.append(
                {
                    "role": role_b,
                    "round": rnd,
                    "content": f"{role_b} 第{rnd}轮回应对方论点。" + "反驳。" * 300,
                }
            )
        state = {"debate_history": messages, "risk_debate_history": []}
        out = extract_judge_vars(state)["debate_history"]
        # 全部轮次的全部角色标签保留（中间发言不被整体截断挖掉）
        assert "【bull】" in out
        assert out.count("【bear】") == 2
        assert "第1轮回应对方论点" in out
        assert "第2轮回应对方论点" in out

    def test_key_arguments_prepended_to_debate_messages(self):
        """回归（2026-09-10）：DebateMessage.key_arguments 早已存在且被 LLM 填充，
        但 _summarize_debate 只拼 content 将其丢弃——judge 评「逐条交锋」时见不到
        每轮论点骨架。拼装 SHALL 把论点前置到每条发言开头（正文截断时骨架仍在）。"""
        state = {
            "debate_history": [
                {
                    "role": "bull",
                    "round": 1,
                    "key_arguments": ["估值下移空间未释放", "历史外推属归纳谬误"],
                    "content": "多头痛斥空头误读定价逻辑，展开论述。" * 50,
                },
                {
                    "role": "bear",
                    "round": 1,
                    "key_arguments": ["戴维斯双杀风险"],
                    "content": "空头反驳。",
                },
            ],
            "risk_debate_history": [],
        }
        out = extract_judge_vars(state)["debate_history"]
        # 论点骨架前置且完整（长正文被截断也不影响论点行）
        assert "论点: 估值下移空间未释放; 历史外推属归纳谬误" in out
        assert "论点: 戴维斯双杀风险" in out
        # pydantic DebateMessage 同样拼论点
        from finance_agent.models import DebateMessage

        state2 = {
            "debate_history": [
                DebateMessage(role="bull", round=1, content="看多", key_arguments=["净息差改善"])
            ]
        }
        out2 = extract_judge_vars(state2)["debate_history"]
        assert "论点: 净息差改善" in out2

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

    def test_all_agents_kept_under_total_budget(self):
        """回归（2026-09-09 实测）：4 个分析师结论+论据总量超 _JUDGE_MAX_BYTES(4096)
        时，整体 head/tail 截断会整段切掉中间 agent——fundamental 的 plain_conclusion
        在 judge 输入与标注材料里都不可见，consistency 评分无法核对各层结论。
        须按 agent 边界截断：每个 agent 的结论方向都保留。"""
        reports = {}
        for name, conclusion in (
            ("technical", "技术面偏多：均线多头排列，动能向上"),
            ("macro", "宏观中性：低通胀低利率，估值有支撑"),
            ("fundamental", "基本面优异但增速放缓：ROE 32.5%，营收转负"),
            ("sentiment", "舆情偏正面：渠道动作密集，资金回流"),
        ):
            reports[name] = {
                "agent_name": name,
                "plain_conclusion": conclusion,
                "claims": [
                    {
                        "claim_type": "numerical",
                        "source_type": "data",
                        "field_ref": "f",
                        "stated_value": float(i),
                        "interpretation": f"论据{name}{i}：数值核对" + "。" * 40,
                    }
                    for i in range(20)
                ],
            }
        state = {"final_trade_decision": {}, "analyst_reports": reports, "risk_debate_history": []}
        out = extract_judge_vars(state)["analyst_reports"]
        # 4 个 agent 全部保留（中间 agent 不被整体截断切掉）
        assert "【technical】" in out
        assert "【macro】" in out
        assert "【fundamental】" in out
        assert "【sentiment】" in out


class TestFormatClaims:
    """_format_claims 各分支（final review F3 加固）。"""

    def test_interpretation_and_value(self):
        from evals.extract import _format_claims

        out = _format_claims([{"interpretation": "ROE 提升", "stated_value": 3.4}])
        assert out == "ROE 提升(3.4)"

    def test_interpretation_only(self):
        from evals.extract import _format_claims

        out = _format_claims([{"interpretation": "盈利改善", "stated_value": ""}])
        assert out == "盈利改善"

    def test_value_only(self):
        from evals.extract import _format_claims

        out = _format_claims([{"interpretation": "", "stated_value": 0.05}])
        assert out == "0.05"

    def test_pydantic_claim_instance(self):
        from evals.extract import _format_claims

        c = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="x.y",
            stated_value=3.4,
            interpretation="ROE",
        )
        assert _format_claims([c]) == "ROE(3.4)"

    def test_empty_list(self):
        from evals.extract import _format_claims

        assert _format_claims([]) == ""
