"""add-user-feedback:POST /api/feedback 端点测试（mock Langfuse 与 session trace 解析）。"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from finance_agent.api import app


def _client():
    return TestClient(app)


def test_like_reports_score_value_1():
    lf = MagicMock()
    with (
        patch("finance_agent.api.get_session_trace_id", return_value="trace-1"),
        patch("finance_agent.api.get_langfuse", return_value=lf),
    ):
        resp = _client().post("/api/feedback", json={"session_id": "s1", "value": "like"})
    assert resp.status_code == 200 and resp.json()["submitted"] is True
    kwargs = lf.create_score.call_args.kwargs
    assert kwargs["name"] == "user_feedback" and kwargs["value"] == 1
    assert kwargs["trace_id"] == "trace-1"


def test_dislike_reports_score_value_0():
    lf = MagicMock()
    with (
        patch("finance_agent.api.get_session_trace_id", return_value="trace-2"),
        patch("finance_agent.api.get_langfuse", return_value=lf),
    ):
        resp = _client().post("/api/feedback", json={"session_id": "s1", "value": "dislike"})
    assert resp.status_code == 200
    assert lf.create_score.call_args.kwargs["value"] == 0


def test_invalid_value_422():
    resp = _client().post("/api/feedback", json={"session_id": "s1", "value": "meh"})
    assert resp.status_code == 422


def test_missing_session_422():
    resp = _client().post("/api/feedback", json={"value": "like"})
    assert resp.status_code == 422


def test_session_without_trace_noop():
    """session 无关联 trace → 不调 create_score,响应仍成功（前端不报错）。"""
    lf = MagicMock()
    with (
        patch("finance_agent.api.get_session_trace_id", return_value=None),
        patch("finance_agent.api.get_langfuse", return_value=lf),
    ):
        resp = _client().post("/api/feedback", json={"session_id": "s1", "value": "like"})
    assert resp.status_code == 200 and resp.json()["submitted"] is False
    lf.create_score.assert_not_called()


def test_langfuse_unconfigured_noop():
    """Langfuse 未配置 → 跳过上报,响应成功。"""
    with (
        patch("finance_agent.api.get_session_trace_id", return_value="trace-1"),
        patch("finance_agent.api.get_langfuse", return_value=None),
    ):
        resp = _client().post("/api/feedback", json={"session_id": "s1", "value": "like"})
    assert resp.status_code == 200 and resp.json()["submitted"] is False


def test_langfuse_error_bypass():
    """create_score 抛异常（trace 不可查）→ 不传播,响应成功。"""
    lf = MagicMock()
    lf.create_score.side_effect = RuntimeError("trace gone")
    with (
        patch("finance_agent.api.get_session_trace_id", return_value="trace-1"),
        patch("finance_agent.api.get_langfuse", return_value=lf),
    ):
        resp = _client().post("/api/feedback", json={"session_id": "s1", "value": "like"})
    assert resp.status_code == 200 and resp.json()["submitted"] is False
