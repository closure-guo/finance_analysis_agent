"""TDD tests for 管线阻断终态可见化（update-decision-price-gate Task 4）。

管线正常结束但未产出报告（门禁阻断/勾稽 FAIL）→ 会话置 failed + failure_reason
+ SSE error 终态事件，MUST NOT 停留 running 等超时兜底。
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import _blocked_failure_reason, app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """隔离的 session DB（指向 tmp_path，避免测试污染开发库）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


class TestBlockedFailureReason:
    def test_price_gate_fail_maps_to_risk_judge(self):
        accumulated = {
            "decision_price_gate": {"result": "fail", "note": "已打回仍未通过：1 条残留"},
            "decision_price_anomalies": [
                {"kind": "deviation", "message": "文本价位 95 与 近期低点 已验证值 570 偏差 83.33%"}
            ],
        }
        reason, node_id = _blocked_failure_reason(accumulated)
        assert "决策价位交叉校验未通过" in reason
        assert "95" in reason
        assert node_id == "risk_judge"

    def test_validation_fail_maps_to_validate_node(self):
        reason, node_id = _blocked_failure_reason({"validation_result": "FAIL"})
        assert "勾稽校验失败" in reason
        assert node_id == "validate_financials"

    def test_unknown_absence_maps_to_unknown(self):
        reason, node_id = _blocked_failure_reason({})
        assert reason == "管线结束但未产出报告"
        assert node_id == "unknown"


class _FakeGraph:
    """单节点 scripted 图：yield 给定 chunks 后耗尽（模拟门禁阻断 → END）。"""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def stream(self, state, config=None, stream_mode=None):  # noqa: ARG002
        yield from self._chunks


def _gate_fail_chunks() -> list[Any]:
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


def _run_stream(isolated_db, fake_graph: Any) -> list[str]:
    """在隔离 DB + Langfuse 关闭 + fake graph 下跑完 _run_graph_streaming。

    patch 目标为 finance_agent.api.graph（api.py 模块导入期已绑定 graph 实例，
    patch build_5layer_graph 不生效——同 tests/test_deep_trace_root.py 既有方式）。
    """
    from finance_agent.api import AnalyzeRequest, _run_graph_streaming

    req = AnalyzeRequest(stock_code="600519", query="分析贵州茅台")
    with (
        patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
        patch("finance_agent.langfuse_tracing.get_callback_handler", return_value=None),
        patch("finance_agent.api.graph", fake_graph),
    ):
        return list(
            _run_graph_streaming(
                stock_code="600519",
                stock_name="贵州茅台",
                req=req,
                analysis_id="a1",
                start_time=time.time(),
            )
        )


def test_blocked_stream_marks_session_failed(isolated_db):
    """故障注入回归（评审建议固化）：stub 固定输出错误价位 → 运行 FAIL，不出报告。"""
    with TestClient(app):
        events = _run_stream(isolated_db, _FakeGraph(_gate_fail_chunks()))
    payloads = [json.loads(e.removeprefix("data: ")) for e in events if e.startswith("data: ")]
    types = [p.get("type") for p in payloads]
    assert "report_ready" not in types
    errors = [p for p in payloads if p.get("type") == "error"]
    assert errors and "决策价位交叉校验未通过" in errors[-1]["message"]
    # 会话终态 failed 且可归因
    sid = payloads[0]["session_id"]
    detail = TestClient(app).get(f"/api/sessions/{sid}").json()
    assert detail["status"] == "failed"
    assert "决策价位交叉校验" in detail["failure_reason"]


def test_normal_completion_not_affected(isolated_db):
    """有报告的正常完成 → 照常 report_ready，MUST NOT 误标 failed。"""
    report_md = "# 报告\n\n正文"
    chunks = [("updates", {"generate_report": {"final_report": report_md, "chart_data": {}}})]
    with TestClient(app):
        events = _run_stream(isolated_db, _FakeGraph(chunks))
    payloads = [json.loads(e.removeprefix("data: ")) for e in events if e.startswith("data: ")]
    types = [p.get("type") for p in payloads]
    assert "report_ready" in types
    assert "error" not in types
