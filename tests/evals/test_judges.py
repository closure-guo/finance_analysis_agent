# tests/evals/test_judges.py
"""LLM-as-Judge:rubric 完整性、JSON 解析容错、环境标记、降级。

judge 调用已迁移至 gateway 统一入口（purpose="judge"），mock 目标为
``finance_agent.llm.gateway.complete_text``（返回 (text, metadata) 元组）。
"""

import os
from unittest.mock import patch

from evals.judges import JUDGE_ENV, RUBRICS, _judge_model, run_judge

_GATEWAY = "finance_agent.llm.gateway.complete_text"


def _mock_completion(score_json: str):
    """complete_text mock 返回值:(text, metadata)。"""
    return (score_json, {})


class TestRubricContract:
    def test_four_dimensions(self):
        assert set(RUBRICS.keys()) == {
            "report_relevance",
            "debate_quality",
            "decision_grounding",
            "consistency",
        }

    def test_rubrics_have_json_constraint_and_no_length_bias(self):
        for dim, rubric in RUBRICS.items():
            assert '{"score"' in rubric, f"{dim} rubric 缺 JSON 输出约束"
            assert "不以篇幅长短论优劣" in rubric, f"{dim} rubric 缺「不以篇幅长短论优劣」"

    def test_consistency_rubric_checks_fund_vs_risk(self):
        # spec consistency Scenario「特别检查 Fund Manager 与 Risk Judge 一致性」
        assert "Fund Manager" in RUBRICS["consistency"]
        assert "Risk Judge" in RUBRICS["consistency"]


class TestRunJudge:
    @patch(_GATEWAY)
    def test_score_parsed(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 4, "reason": "基本切题"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result == {"name": "report_relevance", "score": 4, "reason": "基本切题"}
        # 统一入口:purpose=judge + temperature=0
        _, kwargs = mock_llm.call_args
        assert kwargs["purpose"] == "judge"
        assert kwargs["temperature"] == 0.0
        # llm_config 三件套由 JUDGE_*(→LLM_*) helpers 调用时读环境拼出
        assert kwargs["llm_config"]["model"] == _judge_model()
        assert kwargs["llm_config"]["baseUrl"] == (
            os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL", "") or ""
        )
        assert mock_llm.call_args.args[0][0]["role"] == "user"

    @patch(_GATEWAY)
    def test_parse_failure_retries_once_then_null(self, mock_llm):
        # 两次都返回非 JSON → score=None,不抛异常(spec「重试一次,仍失败记 null」)
        mock_llm.return_value = _mock_completion("这不是 JSON")
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None
        assert result["reason"] == "judge_parse_failed"
        assert mock_llm.call_count == 2

    @patch(_GATEWAY)
    def test_llm_exception_retries_then_null(self, mock_llm):
        """gateway 抛异常(API/网络/配置错误)同样重试一次后 score=None。

        run_judge 的 try/except 覆盖 _call_judge_llm 抛出的异常,与解析失败同路径,
        不向调用方泄露异常(spec「不阻塞实验」)。
        """
        mock_llm.side_effect = RuntimeError("boom")
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None
        assert result["reason"] == "judge_parse_failed"
        assert mock_llm.call_count == 2


class TestLazyEnvRead:
    """judge 配置必须调用时读环境（python -m evals.run 时序 bug 回归防护）。

    实况：模块 import（judges.py 固化常量）先于 main() 的 load_dotenv 执行，
    import 时 JUDGE_* 为空 → 跑批 judge 28 项全败而单测（先 dotenv 后 import）
    全通。修复：常量改函数，每次调用读环境。
    """

    @patch.dict(
        os.environ,
        {
            "JUDGE_BASE_URL": "https://judge-lazy.test/v1",
            "JUDGE_API_KEY": "sk-lazy-test",
        },
    )
    @patch(_GATEWAY)
    def test_env_set_after_import_is_effective(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 3, "reason": "x"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] == 3
        _, kwargs = mock_llm.call_args
        cfg = kwargs["llm_config"]
        assert cfg["baseUrl"] == "https://judge-lazy.test/v1"
        assert cfg["apiKey"] == "sk-lazy-test"

    @patch(_GATEWAY)
    def test_score_out_of_range_treated_as_failure(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 9, "reason": "x"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None

    @patch(_GATEWAY)
    def test_variables_substituted_into_prompt(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 5, "reason": "ok"}')
        run_judge("report_relevance", {"query": "茅台怎么样", "report": "茅台是好公司"})
        prompt = mock_llm.call_args.args[0][0]["content"]
        assert "茅台怎么样" in prompt and "茅台是好公司" in prompt
        assert "{{query}}" not in prompt

    @patch(_GATEWAY)
    def test_render_no_double_substitution(self, mock_llm):
        """变量值含 {{another_key}} 字面时不被后续迭代二次替换(单次扫描)。"""
        mock_llm.return_value = _mock_completion('{"score": 5, "reason": "x"}')
        run_judge("report_relevance", {"query": "见 {{report}}", "report": "机密"})
        prompt = mock_llm.call_args.args[0][0]["content"]
        # query 值原样保留(含字面 {{report}})或被自身键正确替换,二选一
        assert "见 {{report}}" in prompt or "见 机密" in prompt
        # report 槽位只替换一次:无论何种情况「机密」最多出现一次
        assert prompt.count("机密") == 1

    def test_render_missing_var_becomes_empty(self):
        """未提供的变量替换为空串,不残留 {{key}} 占位符（直接测 _render）。"""
        from evals.judges import _render

        prompt = _render("report_relevance", {"query": "q"})  # 缺 report
        assert "{{report}}" not in prompt

    @patch(_GATEWAY)
    def test_judge_generation_marked_with_env(self, mock_llm):
        """spec「裁判成本独立核算」:judge generation 观测带 environment 标记。

        迁移后 observation 由 gateway 统一开启，environment 审计经
        trace.metadata 传递（name="judge" + environment=JUDGE_ENV）。
        """
        mock_llm.return_value = _mock_completion('{"score": 3, "reason": "x"}')
        run_judge("report_relevance", {"query": "q", "report": "r"})
        _, kwargs = mock_llm.call_args
        trace = kwargs["trace"]
        assert trace["name"] == "judge"
        assert trace["metadata"]["environment"] == JUDGE_ENV


class TestInputMissingGuard:
    """评估链路输入合同（delta 3.4）：关键维度变量为空 → input_missing 跳过。

    实战教训（baseline r5 校准）：空辩论静默打 1 分混入真实分数，
    「自信但失真」。空输入不得出具看似正常的数字分数。
    """

    @patch(_GATEWAY)
    def test_debate_empty_marks_input_missing(self, mock_llm):
        from evals.judges import run_judge

        mock_llm.return_value = _mock_completion('{"score": 1, "reason": "x"}')
        result = run_judge("debate_quality", {"query": "q", "debate_history": "", "report": "r"})
        assert result["score"] is None
        assert result["reason"] == "input_missing:debate_history"
        mock_llm.assert_not_called()  # 关键：空输入根本不打分

    @patch(_GATEWAY)
    def test_report_empty_marks_input_missing(self, mock_llm):
        from evals.judges import run_judge

        result = run_judge("report_relevance", {"query": "q", "report": ""})
        assert result["score"] is None
        assert result["reason"] == "input_missing:report"
        mock_llm.assert_not_called()

    @patch(_GATEWAY)
    def test_non_empty_inputs_normal_scoring(self, mock_llm):
        from evals.judges import run_judge

        mock_llm.return_value = _mock_completion('{"score": 4, "reason": "ok"}')
        result = run_judge(
            "debate_quality",
            {"query": "q", "debate_history": "【bull】看多\n【bear】看空", "report": "r"},
        )
        assert result["score"] == 4
        mock_llm.assert_called_once()
