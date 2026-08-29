"""实验对比测试：配对 bootstrap + 结论措辞约束（CI 含 0 → 只能写无显著差异）。"""

import json

from evals.compare import compare_reports


def _write(tmp_path, name: str, scores: list[float]) -> object:
    path = tmp_path / f"{name}.json"
    rows = [
        {"item": f"q{i}", "mode": "deep", "scores": {"report_relevance": s}}
        for i, s in enumerate(scores)
    ]
    path.write_text(json.dumps({"experiment": name, "rows": rows}), encoding="utf-8")
    return path


class TestCompareReports:
    def test_significant_improvement(self, tmp_path):
        a = _write(tmp_path, "a", [0.9, 0.91, 0.89, 0.92, 0.9, 0.91])
        b = _write(tmp_path, "b", [0.5, 0.48, 0.52, 0.5, 0.49, 0.51])
        report = compare_reports(a, b, B=2_000, seed=7)
        m = report.metrics["report_relevance"]
        assert m.conclusion == "显著改进"
        assert m.ci[0] > 0

    def test_no_significant_difference(self, tmp_path):
        a = _write(tmp_path, "a", [0.6, 0.5, 0.55, 0.52])
        b = _write(tmp_path, "b", [0.51, 0.49, 0.5, 0.53])
        report = compare_reports(a, b, B=2_000, seed=7)
        m = report.metrics["report_relevance"]
        assert m.conclusion == "无显著差异"

    def test_unpaired_items_rejected(self, tmp_path):
        a = _write(tmp_path, "a", [0.6, 0.5])
        b = _write(tmp_path, "b", [0.5])  # 缺 q1
        import pytest

        with pytest.raises(ValueError, match="item 不对齐"):
            compare_reports(a, b)
