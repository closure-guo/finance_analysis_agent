# tests/evals/test_judges.py
"""LLM-as-Judge:rubric 完整性、JSON 解析容错、环境标记、降级。"""

import os
from unittest.mock import MagicMock, patch

from evals.judges import JUDGE_ENV, JUDGE_MODEL, RUBRICS, run_judge


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
            assert "不以" in rubric and "长度" in rubric, f"{dim} rubric 缺「不以长度论优劣」"

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
    @patch("evals.judges._judge_client", None)  # 重置 lru_cache 用 patch 见实施说明
    @patch("litellm.completion")
    def test_score_parsed(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 4, "reason": "基本切题"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result == {"name": "report_relevance", "score": 4, "reason": "基本切题"}
        # 裁判模型与温度
        _, kwargs = mock_llm.call_args
        assert kwargs["model"] == JUDGE_MODEL
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
