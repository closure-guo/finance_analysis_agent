# tests/evals/test_extract.py
"""judge 变量提取:state → 9 个字符串变量,缺失容错,结论章节提取。"""

from evals.extract import extract_conclusion, extract_judge_vars


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
