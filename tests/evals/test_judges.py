# tests/evals/test_judges.py
"""LLM-as-Judge:rubric 完整性、JSON 解析容错、环境标记、降级。"""

import os
from unittest.mock import MagicMock, patch

import evals.judges as judges_module
import pytest
from evals.judges import JUDGE_ENV, RUBRICS, _judge_model, run_judge


@pytest.fixture(autouse=True)
def _reset_judge_singleton():
    """每个用例前后重置模块级 _judge_client 单例,防止跨用例泄露。

    必要性:test_judge_generation_marked_with_env 用 `with patch("_create_judge_client")`
    包裹工厂;退出 with 只恢复工厂,但 get_judge_langfuse() 已把返回的 mock_client 赋给
    _judge_client。残留 mock 会让后续用例命中 stale 单例。autouse fixture 兜底清零。
    """
    judges_module._judge_client = None
    yield
    judges_module._judge_client = None


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


def _mock_completion(score_json: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = score_json
    return resp


class TestRunJudge:
    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_score_parsed(self, mock_llm):
        # _judge_client 单例由 autouse fixture _reset_judge_singleton 兜底重置
        mock_llm.return_value = _mock_completion('{"score": 4, "reason": "基本切题"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result == {"name": "report_relevance", "score": 4, "reason": "基本切题"}
        # 裁判模型与温度
        _, kwargs = mock_llm.call_args
        assert kwargs["model"] == _judge_model()
        assert kwargs["temperature"] == 0.0

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_parse_failure_retries_once_then_null(self, mock_llm):
        # 两次都返回非 JSON → score=None,不抛异常(spec「重试一次,仍失败记 null」)
        mock_llm.return_value = _mock_completion("这不是 JSON")
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None
        assert result["reason"] == "judge_parse_failed"
        assert mock_llm.call_count == 2

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_llm_exception_retries_then_null(self, mock_llm):
        """litellm 抛异常(API/网络错误)同样重试一次后 score=None。

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
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
            "JUDGE_BASE_URL": "https://judge-lazy.test/v1",
            "JUDGE_API_KEY": "sk-lazy-test",
        },
    )
    @patch("litellm.completion")
    def test_env_set_after_import_is_effective(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 3, "reason": "x"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] == 3
        _, kwargs = mock_llm.call_args
        assert kwargs["api_base"] == "https://judge-lazy.test/v1"
        assert kwargs["api_key"] == "sk-lazy-test"

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_score_out_of_range_treated_as_failure(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 9, "reason": "x"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_variables_substituted_into_prompt(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 5, "reason": "ok"}')
        run_judge("report_relevance", {"query": "茅台怎么样", "report": "茅台是好公司"})
        prompt = mock_llm.call_args.kwargs["messages"][0]["content"]
        assert "茅台怎么样" in prompt and "茅台是好公司" in prompt
        assert "{{query}}" not in prompt

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_render_no_double_substitution(self, mock_llm):
        """变量值含 {{another_key}} 字面时不被后续迭代二次替换(单次扫描)。"""
        mock_llm.return_value = _mock_completion('{"score": 5, "reason": "x"}')
        run_judge("report_relevance", {"query": "见 {{report}}", "report": "机密"})
        prompt = mock_llm.call_args.kwargs["messages"][0]["content"]
        # query 值原样保留(含字面 {{report}})或被自身键正确替换,二选一
        assert "见 {{report}}" in prompt or "见 机密" in prompt
        # report 槽位只替换一次:无论何种情况「机密」最多出现一次
        assert prompt.count("机密") == 1

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    def test_render_missing_var_becomes_empty(self):
        """未提供的变量替换为空串,不残留 {{key}} 占位符（直接测 _render）。"""
        from evals.judges import _render

        prompt = _render("report_relevance", {"query": "q"})  # 缺 report
        assert "{{report}}" not in prompt

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})
    @patch("litellm.completion")
    def test_judge_generation_marked_with_env(self, mock_llm):
        """spec「裁判成本独立核算」:有凭据时 generation 经 environment=judge client 包裹。"""
        mock_llm.return_value = _mock_completion('{"score": 3, "reason": "x"}')
        mock_client = MagicMock()
        with patch("evals.judges._create_judge_client", return_value=mock_client) as factory:
            run_judge("report_relevance", {"query": "q", "report": "r"})
        factory.assert_called_once_with(JUDGE_ENV)
        mock_client.start_as_current_observation.assert_called_once()
        _, kwargs = mock_client.start_as_current_observation.call_args
        assert kwargs.get("as_type") == "generation"


class TestInputMissingGuard:
    """评估链路输入合同（delta 3.4）：关键维度变量为空 → input_missing 跳过。

    实战教训（baseline r5 校准）：空辩论静默打 1 分混入真实分数，
    「自信但失真」。空输入不得出具看似正常的数字分数。
    """

    @patch("litellm.completion")
    def test_debate_empty_marks_input_missing(self, mock_llm):
        from evals.judges import run_judge

        mock_llm.return_value = _mock_completion('{"score": 1, "reason": "x"}')
        result = run_judge("debate_quality", {"query": "q", "debate_history": "", "report": "r"})
        assert result["score"] is None
        assert result["reason"] == "input_missing:debate_history"
        mock_llm.assert_not_called()  # 关键：空输入根本不打分

    @patch("litellm.completion")
    def test_report_empty_marks_input_missing(self, mock_llm):
        from evals.judges import run_judge

        result = run_judge("report_relevance", {"query": "q", "report": ""})
        assert result["score"] is None
        assert result["reason"] == "input_missing:report"
        mock_llm.assert_not_called()

    @patch("litellm.completion")
    def test_non_empty_inputs_normal_scoring(self, mock_llm):
        from evals.judges import run_judge

        mock_llm.return_value = _mock_completion('{"score": 4, "reason": "ok"}')
        result = run_judge(
            "debate_quality",
            {"query": "q", "debate_history": "【bull】看多\n【bear】看空", "report": "r"},
        )
        assert result["score"] == 4
        mock_llm.assert_called_once()
