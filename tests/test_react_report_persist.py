"""复现测试：ReAct 路径（run_deep_analysis 工具）报告数据未落库 sessions 表。

根因：fast path（_run_graph_streaming）在管线完成后调 update_session_report
写入 report_markdown / chart_data / duration_ms；而 ReAct 路径（agent_factory
run_deep_analysis 工具）正常结束时只 update_session_status(completed)，
从不调 update_session_report——报告数据仅经 SSE metadata 下发，不落库。

后果：刷新页面重建会话时，GET /api/sessions/{id} 返回的 duration_ms=0、
report_markdown 为空，前端报告卡片显示「耗时未知」且报告正文/图表丢失。

修复标准：ReAct 路径管线正常结束后，报告数据 SHALL 落库 sessions 表
（report_markdown / chart_data / analyst_reports / duration_ms）。
"""

from __future__ import annotations

import pytest

from finance_agent import session_store
from finance_agent.agent_factory import _make_run_deep_analysis


def _mock_stream_events():
    """模拟完整管线事件序列：节点完成 + 最终报告 + 图表数据。"""
    yield ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000})
    yield ("updates", {"check_cache": {"cached": True}})
    yield ("custom", {"type": "node_end", "node": "check_cache", "ts": 1001, "duration_ms": 1})
    yield (
        "updates",
        {
            "generate_report": {
                "final_report": "# 宁夏建材深度分析报告\n正文内容",
                "chart_data": {"annual": [{"year": 2024}]},
                "analyst_reports": {"fundamental": "基本面分析"},
            }
        },
    )


@pytest.mark.asyncio
async def test_react_pipeline_persists_report_to_sessions(tmp_path, monkeypatch):
    """ReAct 路径管线正常结束后，报告数据 SHALL 落库 sessions 表。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600449", stock_name="宁夏建材", status="running")

    monkeypatch.setattr(
        "finance_agent.agent_factory._stream_graph",
        lambda initial_state, config=None, session_id=None: _mock_stream_events(),
    )

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    # 完整消费事件流直到结束
    async for _ in run_deep_analysis("600449", "宁夏建材"):
        pass

    # 等待后台 Task 完成
    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    # 关键断言：报告数据落库（修复前 report_markdown/duration_ms 均为空/0）
    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "completed"
    assert row["report_markdown"], "ReAct 路径报告正文未落库（刷新后丢失）"
    assert "宁夏建材深度分析报告" in row["report_markdown"]
    assert row["duration_ms"] and row["duration_ms"] > 0, "耗时未落库（前端显示耗时未知）"
