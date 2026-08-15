"""run_experiment:evaluator 装配、quick 模式 judge 跳过、本地降级、结果表。"""

from unittest.mock import patch

from evals.run import _mean_rows, all_evaluators, run_local


class TestEvaluatorAssembly:
    def test_six_evaluators(self):
        evals = all_evaluators()
        assert len(evals) == 6  # 2 确定性 + 4 judge

    def test_deterministic_evaluator_shape(self):
        evals = {e.__name__: e for e in all_evaluators()}
        result = evals["eval_section_coverage"](
            input={"query": "q", "mode": "deep"},
            output={
                "report": "偿债能力 盈利能力",
                "ticker": "600519",
                "judge_vars": {},
                "mode": "deep",
            },
            expected_output={"must_cover": ["偿债能力", "盈利能力"]},
            metadata={},
        )
        assert result is not None
        # langfuse Evaluation 或本地 dict 两种形态都可能,统一经 _as_dict
        assert (
            getattr(result, "name", None) == "section_coverage"
            or result["name"] == "section_coverage"
        )

    @patch("evals.run.run_judge")
    def test_judge_skipped_for_quick_mode(self, mock_judge):
        mock_judge.return_value = {"name": "debate_quality", "score": 4, "reason": "x"}
        evals = {e.__name__: e for e in all_evaluators()}
        result = evals["eval_debate_quality"](
            input={"query": "q", "mode": "quick"},
            output={"report": "r", "ticker": None, "judge_vars": {}, "mode": "quick"},
            expected_output={},
            metadata={},
        )
        # quick 无辩论 → 返回空(list)或 None,不调 judge
        mock_judge.assert_not_called()
        assert result in (None, [])

    @patch("evals.run.run_judge")
    def test_judge_uses_output_judge_vars(self, mock_judge):
        mock_judge.return_value = {"name": "report_relevance", "score": 5, "reason": "切题"}
        evals = {e.__name__: e for e in all_evaluators()}
        evals["eval_report_relevance"](
            input={"query": "茅台", "mode": "quick"},
            output={
                "report": "r",
                "ticker": None,
                "judge_vars": {"query": "茅台", "report": "茅台好"},
                "mode": "quick",
            },
            expected_output={},
            metadata={},
        )
        mock_judge.assert_called_once_with(
            "report_relevance", {"query": "茅台", "report": "茅台好"}
        )


class TestLocalRun:
    @patch("evals.run.run_task")
    @patch("evals.run.run_judge")
    def test_local_run_produces_rows(self, mock_judge, mock_task):
        mock_task.return_value = {
            "report": "偿债能力 盈利能力",
            "ticker": "600519",
            "judge_vars": {"query": "q", "report": "r"},
            "mode": "deep",
            "skipped": None,
        }
        mock_judge.return_value = {"name": "report_relevance", "score": 4, "reason": "x"}
        items = [
            {
                "input": {"query": "q", "mode": "deep", "stock_code": "600519"},
                "expected_output": {"ticker": "600519", "must_cover": ["偿债能力"]},
                "metadata": {"category": "deep_typical", "source": "test"},
            }
        ]
        rows = run_local(items, "test-exp")
        assert len(rows) == 1
        row = rows[0]
        assert row["scores"]["ticker_match"] == 1.0
        assert row["scores"]["section_coverage"] == 1.0
        assert row["scores"]["report_relevance"] == 4

    def test_mean_rows(self):
        rows = [
            {"scores": {"a": 1.0, "b": 4}, "judge_failures": 0},
            {"scores": {"a": 0.0, "b": None}, "judge_failures": 1},
        ]
        means = _mean_rows(rows)
        assert means["a"] == 0.5
        assert means["b"] == 4.0  # None 不计入均值
        assert means["judge_failures"] == 1
