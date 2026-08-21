"""POST /api/export 按需导出接口测试。

覆盖 delta: 按需导出（pdf/word/markdown 单文件）。
- 200：生成文件 + 可下载 URL
- 404：会话不存在 / 无报告内容
- 400：非法格式
- 500：转换失败（converter 抛异常 → export_report 置 None → 500）
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """隔离的 session DB（指向 tmp_path，避免测试污染开发库）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "export.db")
    session_store.init_db()


def _make_session(report_md: str) -> str:
    """创建带报告内容的会话，返回 create_session 生成的真实 session_id。"""
    return session_store.create_session(
        stock_code="600519",
        stock_name="贵州茅台",
        report_markdown=report_md,
    )


def test_export_pdf_returns_url(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    sid = _make_session("# 测试报告\n\n正文。\n")

    with TestClient(app) as client:
        resp = client.post("/api/export", json={"session_id": sid, "fmt": "pdf"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["file_name"].endswith(".pdf")
    assert data["url"].startswith("/api/files/")


def test_export_word_and_markdown(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    sid = _make_session("# R\n\n正文。\n")

    with TestClient(app) as client:
        resp_word = client.post("/api/export", json={"session_id": sid, "fmt": "word"})
        resp_md = client.post("/api/export", json={"session_id": sid, "fmt": "markdown"})

    assert resp_word.status_code == 200
    assert resp_word.json()["file_name"].endswith(".docx")
    assert resp_md.status_code == 200
    assert resp_md.json()["file_name"].endswith(".md")


def test_export_unknown_session_404(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.post("/api/export", json={"session_id": "no-such-session", "fmt": "pdf"})

    assert resp.status_code == 404


def test_export_invalid_format_400(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    sid = _make_session("# R\n")

    with TestClient(app) as client:
        resp = client.post("/api/export", json={"session_id": sid, "fmt": "exe"})

    assert resp.status_code == 400


def test_export_conversion_failure_500(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    sid = _make_session("# R\n正文。\n")

    with (
        patch("finance_agent.export.service.markdown_to_pdf", side_effect=RuntimeError("boom")),
        TestClient(app) as client,
    ):
        resp = client.post("/api/export", json={"session_id": sid, "fmt": "pdf"})

    assert resp.status_code == 500
