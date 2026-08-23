"""run_experiment:evaluator 装配、quick 模式 judge 跳过、langfuse 必达、结果表。"""

import sys
from unittest.mock import MagicMock, patch

import evals.run
import pytest
from evals.dataset_seed import DATASET_NAME
from evals.run import _mean_rows, all_evaluators


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


class TestMeanRows:
    def test_mean_rows(self):
        rows = [
            {"scores": {"a": 1.0, "b": 4}, "judge_failures": 0},
            {"scores": {"a": 0.0, "b": None}, "judge_failures": 1},
        ]
        means = _mean_rows(rows)
        assert means["a"] == 0.5
        assert means["b"] == 4.0  # None 不计入均值
        assert means["judge_failures"] == 1


class TestLangfuseRequired:
    def test_no_langfuse_exits_nonzero_without_scores(self, monkeypatch):
        """无 langfuse → main() 必须显式报错退出,绝不本地循环产出分数。"""
        monkeypatch.setattr(sys, "argv", ["evals/run.py", "test-exp"])
        with (
            patch("evals.run.get_langfuse", return_value=None),
            patch("evals.run.run_task") as mock_task,
            pytest.raises(SystemExit) as exc_info,
        ):
            evals.run.main()
        assert exc_info.value.code  # 非零退出码(字符串/1 皆为真)
        mock_task.assert_not_called()  # 不走 run_task,不产出分数

    def test_with_langfuse_runs_run_experiment(self, monkeypatch):
        """有 langfuse → 走 run_experiment 路径,不抛、不降级。"""
        monkeypatch.setattr(sys, "argv", ["evals/run.py", "test-exp"])
        fake = MagicMock()
        fake_result = MagicMock()
        fake_result.item_results = []
        fake.get_dataset.return_value.run_experiment.return_value = fake_result
        with patch("evals.run.get_langfuse", return_value=fake), patch("evals.run._write_report"):
            evals.run.main()
        fake.get_dataset.assert_called_once_with(DATASET_NAME)
        fake.get_dataset.return_value.run_experiment.assert_called_once()
        fake.flush.assert_called_once()
