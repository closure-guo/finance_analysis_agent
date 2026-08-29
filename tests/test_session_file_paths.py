"""sessions 表持久化报告文件产物（update-file-export-entry Task 3）。"""

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


def test_update_session_report_persists_and_returns_file_paths(isolated_db):
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")
    session_store.update_session_report(
        sid,
        report_markdown="# 报告",
        file_paths={
            "md": "/tmp/贵州茅台_600519_20260825_report.md",  # noqa: S108  fixture 值非真实临时文件
            "docx": "/tmp/贵州茅台_600519_20260825_report.docx",  # noqa: S108  fixture 值非真实临时文件
        },
        duration_ms=1234,
    )
    row = session_store.get_session(sid)
    assert row["file_paths"] == {
        "md": "/tmp/贵州茅台_600519_20260825_report.md",  # noqa: S108  fixture 值非真实临时文件
        "docx": "/tmp/贵州茅台_600519_20260825_report.docx",  # noqa: S108  fixture 值非真实临时文件
    }
    detail = TestClient(app).get(f"/api/sessions/{sid}").json()
    assert detail["file_paths"]["md"].endswith("_report.md")


def test_legacy_session_without_file_paths_returns_empty(isolated_db):
    sid = session_store.create_session(stock_code="600519", status="completed")
    row = session_store.get_session(sid)
    assert row["file_paths"] == {}
