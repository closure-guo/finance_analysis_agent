"""验证 ReAct 管线在专用 executor 运行，不占事件循环默认池。

根因（复现）：run_deep_analysis 的 _run_graph 用 run_in_executor(None,...)
共享事件循环默认 executor。管线的 matplotlib 图表生成（generate_all_charts
的 findfont 全盘字体扫描）是长任务，占满默认池（max_workers=cpu+4=20）后，
事件循环上 asyncio.to_thread 的 SQLite 等快速 IO（/api/sessions、/api/health）
排队拿不到线程 -> 超时，前端刷新表现为「会话列表为空」。

修复标准：_run_graph 跑在独立 _pipeline_executor（thread_name_prefix="pipeline"），
不占默认池，快速 IO 的默认池线程不被管线长任务饿死。
"""

from __future__ import annotations

import threading

import pytest

from finance_agent import session_store
from finance_agent.agent_factory import _make_run_deep_analysis


def _mock_stream_events():
    yield ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000})
    yield ("updates", {"check_cache": {"cached": True}})
    yield ("custom", {"type": "node_end", "node": "check_cache", "ts": 1001, "duration_ms": 1})
    yield ("updates", {"generate_report": {"final_report": "# 报告\n内容"}})


@pytest.mark.asyncio
async def test_react_pipeline_runs_in_dedicated_executor(tmp_path, monkeypatch):
    """ReAct 管线的 _run_graph SHALL 在专用 pipeline 线程运行，而非默认池线程。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600449", stock_name="宁夏建材", status="running")

    thread_names: list[str] = []

    def _spy_stream_graph(initial_state, config=None, session_id=None):
        # 记录 _run_graph 实际运行的线程名
        thread_names.append(threading.current_thread().name)
        return _mock_stream_events()

    monkeypatch.setattr("finance_agent.agent_factory._stream_graph", _spy_stream_graph)

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)
    async for _ in run_deep_analysis("600449", "宁夏建材"):
        pass

    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    assert thread_names, "_run_graph 未执行"
    # 修复前：默认池线程名形如 "ThreadPoolExecutor-0_1"（asyncio 默认 executor）
    # 修复后：专用池线程名形如 "pipeline_0"
    assert any(name.startswith("pipeline") for name in thread_names), (
        f"_run_graph 未在专用 pipeline executor 运行，实际线程: {thread_names}"
    )
