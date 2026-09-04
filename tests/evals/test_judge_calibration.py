"""add-judge-human-calibration：标注导出 + 一致性指标 测试（fixtures 离线）。"""

import json

from evals.judge_calibration.measure import (
    consistency,
    export_row,
    export_rows,
    load_labeled_rows,
)


def _trace(tid="t1", scores=None, judge_output=None):
    return {
        "id": tid,
        "scores": scores or {},
        "observations": ([{"name": "judge", "output": judge_output}] if judge_output else []),
    }


class TestExport:
    def test_judge_score_from_trace_scores(self):
        t = _trace(scores={"report_relevance": 4.0, "evidence_grounding": 3.0})
        row = export_row(t, "report_relevance")
        assert row.judge_score == 4.0
        assert row.human_score is None

    def test_fallback_to_judge_observation(self):
        t = _trace(judge_output={"multi_perspective": 5.0})
        row = export_row(t, "multi_perspective")
        assert row.judge_score == 5.0

    def test_no_score_stays_none(self):
        assert export_row(_trace(), "report_relevance").judge_score is None

    def test_export_rows_per_dimension(self):
        rows = export_rows([_trace(scores={"report_relevance": 4.0})])
        assert len(rows) == 4  # 每个维度一行
        assert all(r.human_score is None for r in rows)


class TestConsistency:
    def _labeled(self):
        # 10 对：judge 与 human 单调一致（spearman 高、MAE 小）
        import evals.judge_calibration.measure as m

        js = [1, 2, 3, 4, 5, 2, 3, 4, 3, 5]
        hs = [1.5, 2, 3.5, 4, 5, 2.5, 3, 4, 3.5, 5]
        return [
            m.LabeledRow(
                trace_id=f"t{i}", dimension="report_relevance", judge_score=j, human_score=h
            )
            for i, (j, h) in enumerate(zip(js, hs, strict=False))
        ]

    def test_best_agreement_no_calibrate(self):
        result = consistency(self._labeled())
        o = result["overall"]
        assert o["n"] == 10
        assert o["spearman"] >= 0.9
        assert o["mae"] <= 0.5
        assert o["direction_rate"] >= 0.7
        assert o["need_calibrate"] is False

    def test_divergence_flags_calibrate(self):
        import evals.judge_calibration.measure as m

        rows = [
            m.LabeledRow(
                trace_id=f"t{i}", dimension="report_relevance", judge_score=5.0, human_score=1.0
            )
            for i in range(6)
        ]
        result = consistency(rows)
        assert result["overall"]["need_calibrate"] is True
        assert result["by_dimension"]["report_relevance"]["need_calibrate"] is True

    def test_empty_labeled(self):
        import evals.judge_calibration.measure as m

        result = consistency([m.LabeledRow(trace_id="t1", dimension="x", judge_score=4.0)])
        assert result["labeled_count"] == 0
        assert result["overall"] == {"n": 0}


class TestLoadRows:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "labeled.jsonl"
        rows = [
            {
                "trace_id": "t1",
                "dimension": "report_relevance",
                "judge_score": 4.0,
                "human_score": 3.0,
            },
            {
                "trace_id": "t2",
                "dimension": "evidence_grounding",
                "judge_score": 2.0,
                "human_score": 5.0,
            },
        ]
        p.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
        loaded = load_labeled_rows(p)
        assert len(loaded) == 2
        assert loaded[1].human_score == 5.0
