# tests/evals/test_eval_live.py
"""@live 用例:真实 DeepSeek 裁判 + 真实 quick task,nightly 跑防漂移。"""

import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="需 DEEPSEEK_API_KEY"),
]


def test_live_judge_returns_score_in_range():
    """真实裁判调用:report_relevance 返回 1-5 整数(明显切题的输入应得高分)。"""
    from evals.judges import run_judge

    result = run_judge(
        "report_relevance",
        {
            "query": "贵州茅台盈利能力如何",
            "report": "贵州茅台盈利能力极强,ROE 长期维持 30% 以上,毛利率 91%。",
        },
    )
    assert result["score"] is not None, f"裁判解析失败: {result}"
    assert 1 <= result["score"] <= 5
    assert result["reason"]


def test_live_quick_task_produces_report():
    """真实 quick task:run_task 产出非空 report(防 ReAct/stub 漂移)。"""
    from evals.task import run_task

    out = run_task(item={"input": {"query": "茅台现在能买吗", "mode": "quick", "ticker": "600519"}})
    assert out["skipped"] is None
    assert out["report"]
    assert out["judge_vars"]["query"] == "茅台现在能买吗"
