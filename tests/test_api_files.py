"""add-download-center：文件列表/删除接口测试。"""

from fastapi.testclient import TestClient

from finance_agent.api import app


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr("finance_agent.api.REPORTS_DIR", tmp_path)
    return TestClient(app)


def test_list_files_empty_dir(monkeypatch, tmp_path):
    resp = _client(monkeypatch, tmp_path).get("/api/files")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_files_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("finance_agent.api.REPORTS_DIR", tmp_path / "nope")
    resp = TestClient(app).get("/api/files")
    assert resp.status_code == 200 and resp.json() == []


def test_list_files_sorted_and_meta(monkeypatch, tmp_path):
    import time

    # Windows 的 st_ctime 是真实创建时间（os.utime 改不动），故用先后创建保证时序
    (tmp_path / "a.docx").write_bytes(b"x" * 204800)
    time.sleep(0.2)
    (tmp_path / "b.pptx").write_bytes(b"y")
    (tmp_path / "chart.png").write_bytes(b"png")
    (tmp_path / "tmp.tmp").write_bytes(b"t")
    resp = _client(monkeypatch, tmp_path).get("/api/files")
    items = resp.json()
    assert [i["file_name"] for i in items] == ["b.pptx", "a.docx"]
    assert items[0] == {
        "file_name": "b.pptx",
        "file_type": "pptx",
        "size_bytes": 1,
        "created_at": items[0]["created_at"],
    }
    assert isinstance(items[0]["created_at"], int) and items[0]["created_at"] > 0
    assert items[1]["size_bytes"] == 204800


def test_delete_existing_file(monkeypatch, tmp_path):
    (tmp_path / "a.docx").write_bytes(b"x")
    c = _client(monkeypatch, tmp_path)
    assert c.delete("/api/files/a.docx").status_code == 200
    assert c.get("/api/files").json() == []


def test_delete_missing_file_404(monkeypatch, tmp_path):
    assert _client(monkeypatch, tmp_path).delete("/api/files/nonexistent.docx").status_code == 404


def test_path_traversal_rejected(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    for url in ("/api/files/..%2F..%2F.env", "/api/files/%2e%2e%2fsecret.md"):
        assert c.delete(url).status_code in (400, 404)
        assert c.get(url).status_code in (400, 404)


def test_reports_dir_honors_env_override(tmp_path, monkeypatch):
    """api 模块的 REPORTS_DIR 应尊重环境变量（与 export/service.py 一致）。

    E2E 门禁（playwright.config.ts webServer）注入 REPORTS_DIR=<tmp 目录> 实现
    测试隔离；此前 api.py 硬编码 Path("reports") 导致 /api/files 扫描生产目录。
    """
    import importlib

    import finance_agent.api as api_module

    env_dir = tmp_path / "env-reports"
    monkeypatch.setenv("REPORTS_DIR", str(env_dir))
    importlib.reload(api_module)
    try:
        assert env_dir == api_module.REPORTS_DIR
        client = TestClient(api_module.app)
        assert client.get("/api/files").json() == []
    finally:
        monkeypatch.undo()
        importlib.reload(api_module)
