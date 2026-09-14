"""evals/run.py 汇总行构造（r1 复盘 #9：harness 跳过项的 skipped 原因被硬编码 None 丢弃，
汇总表把有意跳过的 3 条显示成「跑了但没分」，报告 JSON 也丢了原因）。"""

from __future__ import annotations

from types import SimpleNamespace

from evals.run import _rows_from_results


def _result(query: str, mode: str, output: dict | None, evaluations: list) -> SimpleNamespace:
    return SimpleNamespace(
        item=SimpleNamespace(input={"query": query, "mode": mode}),
        output=output,
        evaluations=evaluations,
    )


def test_skipped_reason_carried_from_task_output():
    ev = SimpleNamespace(name="report_relevance", value=5.0)
    rows = _rows_from_results(
        [
            _result("茅台现在能买吗", "quick", {"report": "r"}, [ev]),
            _result(
                "那它的风险呢",
                "follow_up",
                {"report": None, "skipped": "follow_up 需 session fixture"},
                [],
            ),
        ]
    )
    assert rows[0]["skipped"] is None and rows[0]["scores"] == {"report_relevance": 5.0}
    assert rows[1]["skipped"] == "follow_up 需 session fixture"
    assert rows[1]["scores"] == {}


def test_missing_output_does_not_crash():
    rows = _rows_from_results([_result("q", "deep", None, [])])
    assert rows[0]["skipped"] is None
