"""TDD tests for ReAct 慢路径阻断终态可见化（update-decision-price-gate Fix 轮）。

agent_factory.run_deep_analysis 的 _background_consume 正常结束分支此前对
final_report 为空（价位门禁 fail / 勾稽 FAIL 阻断）的运行也无条件置
completed + 下发 report_ready + 落库决策，违反 delta spec pipeline-events
ADDED requirement「管线阻断终态可见化」（SHALL 路径无关）。

本文件锁定慢路径同语义收口：会话置 failed + failure_reason，TOOL_RESULT
带 pipeline_blocked 阻断标记、不带 report_ready；未经审批的决策不落战绩。
fast path（api._run_graph_streaming）同语义回归见 tests/test_api_blocked_terminal.py。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from finance_agent import session_store
from finance_agent.agent_factory import _make_run_deep_analysis
from finance_agent.api import _ALL_NODES


def test_fake_chunk_nodes_are_tracked():
    """守卫：fake 图 chunk 的节点必须在 _ALL_NODES 内，否则 updates 被静默跳过。

    兼作模块级预导入 finance_agent.api——run_deep_analysis 工具内会懒导入
    api（_ALL_NODES 等），若首次导入发生在 build_5layer_graph 被 patch 期间，
    api.py 模块级 graph = build_5layer_graph() 会拿到 fake 实例而 TypeError。
    """
    assert "risk_judge" in _ALL_NODES
    assert "generate_report" in _ALL_NODES


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """隔离的 session DB（指向 tmp_path，避免测试污染开发库）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


class _FakeGraph:
    """单节点 scripted 图：yield 给定 chunks 后耗尽（模拟门禁阻断 → END）。

    镜像 tests/test_deep_trace_root.py 对 agent_factory 的 fake-graph 模式：
    patch 构造函数 finance_agent.graph.build_5layer_graph（_stream_graph 调用期
    才 from finance_agent.graph import build_5layer_graph，故 patch 生效）；
    api 侧则是 patch 模块属性 finance_agent.api.graph，勿混淆。
    """

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def stream(self, state, config=None, stream_mode=None):  # noqa: ARG002
        yield from self._chunks


def _gate_fail_chunks() -> list[Any]:
    """risk_judge 产出决策 + 价位门禁 fail 后图流耗尽（无 generate_report 节点）。"""
    return [
        (
            "updates",
            {
                "risk_judge": {
                    "final_trade_decision": {"action": "sell", "confidence": 0.65},
                    "decision_price_gate": {"result": "fail", "note": "已打回仍未通过：1 条残留"},
                    "decision_price_anomalies": [
                        {
                            "kind": "deviation",
                            "message": "文本价位 95 与 近期低点 已验证值 570 偏差 83.33%",
                        }
                    ],
                }
            },
        )
    ]


def _report_chunks() -> list[Any]:
    """有报告的正常完成（generate_report 产出 final_report，门禁放行）。"""
    return [
        ("updates", {"generate_report": {"final_report": "# 报告\n\n正文", "chart_data": {}}}),
    ]


async def _run_tool(
    isolated_db, monkeypatch, chunks: list[Any], persist_spy: MagicMock
) -> tuple[str, list[Any]]:
    """隔离 DB + 关闭 Langfuse + fake graph 下跑完 run_deep_analysis 工具。

    返回 (session_id, 全部 StreamEvent)。消费到自然耗尽（None 哨兵）时，
    后台 _background_consume 的收尾分支已执行完毕，无竞态。
    """
    # 清掉可能压小全局预算的环境变量，避免误触发超时分支语义
    # （monkeypatch 保证测试结束后还原，不污染开发者本机环境）
    monkeypatch.delenv("PIPELINE_TIMEOUT_SECONDS", raising=False)
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")
    tool = _make_run_deep_analysis(api_key="fake", session_id=sid)
    events: list[Any] = []
    with (
        patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
        patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
        # build_5layer_graph 是构造函数：patch 为返回 fake 图的可调用工厂
        # （镜像 test_deep_trace_root.py 的 _fake_graph 模式，勿传实例本身）
        patch("finance_agent.graph.build_5layer_graph", lambda: _FakeGraph(chunks)),
        patch("finance_agent.agent_factory._persist_decision_from_tool", persist_spy),
    ):
        async for ev in tool("600519", "贵州茅台"):
            events.append(ev)
    return sid, events


@pytest.mark.asyncio
async def test_gate_fail_exhaust_marks_session_failed(isolated_db, monkeypatch):
    """门禁 fail 后图流正常耗尽 → 会话 failed + 阻断 TOOL_RESULT，非 completed 空报告。"""
    persist_spy = MagicMock()
    sid, events = await _run_tool(isolated_db, monkeypatch, _gate_fail_chunks(), persist_spy)

    # 1) 会话终态：failed + 阻断归因（不得停留 completed 空报告）
    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "failed", (
        f"门禁阻断的运行应置 failed，实际 {row['status']}（慢路径缺口未收口）"
    )
    assert row["failure_reason"] is not None
    assert "决策价位交叉校验" in row["failure_reason"]

    # 2) 报告数据 MUST NOT 落库（无报告可落）
    assert not (row.get("report_markdown") or "")

    # 3) 未经审批的决策 MUST NOT 落战绩
    persist_spy.assert_not_called()

    # 4) Agent 侧：TOOL_RESULT 如实转述阻断，带 pipeline_blocked 标记，
    #    不带 report_ready / sse_type: report_ready（阻断运行不得伪装报告就绪）
    tool_results = [e for e in events if e.event_type.value == "tool_result"]
    assert tool_results, (
        f"阻断运行必须下发 TOOL_RESULT 使 Agent 能转述失败，实际事件: "
        f"{[e.event_type.value for e in events]}"
    )
    last = tool_results[-1]
    tr = last.tool_result
    assert tr is not None
    meta = tr.metadata or {}
    assert meta.get("pipeline_blocked") is True
    assert "决策价位交叉校验" in (meta.get("failure_reason") or "")
    assert "决策价位交叉校验" in (tr.output or "")
    assert "report_ready" not in meta
    assert meta.get("sse_type") != "report_ready"


@pytest.mark.asyncio
async def test_normal_completion_not_affected(isolated_db, monkeypatch):
    """有报告的正常完成 → 照常 completed + report_ready + 决策落库（回归保护）。"""
    persist_spy = MagicMock()
    sid, events = await _run_tool(isolated_db, monkeypatch, _report_chunks(), persist_spy)

    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "completed", "有报告的正常完成 MUST NOT 误标 failed"
    assert (row.get("report_markdown") or "").startswith("# 报告")

    # 正常完成仍落战绩（现状行为不回归）
    persist_spy.assert_called_once()

    tool_results = [e for e in events if e.event_type.value == "tool_result"]
    assert tool_results
    meta = tool_results[-1].tool_result.metadata or {}
    assert meta.get("sse_type") == "report_ready"
    assert "pipeline_blocked" not in meta
