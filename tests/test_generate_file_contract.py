"""nodes/output.generate_file 契约测试：file_paths 含四键，单格式失败置 None。"""

from unittest.mock import patch

from finance_agent.nodes.output import generate_file


def test_generate_file_returns_four_format_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    state = {
        "final_report": "# 测试\n\n正文。\n",
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台"},
    }

    result = generate_file(state)

    assert set(result["file_paths"].keys()) == {"docx", "pptx", "pdf", "md"}
    assert result["final_report"].count("免责声明") >= 1


def test_generate_file_single_failure_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    state = {
        "final_report": "# 测试\n\n正文。\n",
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台"},
    }

    with patch(
        "finance_agent.export.service.markdown_to_pdf",
        side_effect=RuntimeError("render failed"),
    ):
        result = generate_file(state)

    assert result["file_paths"]["pdf"] is None
    assert result["file_paths"]["docx"] is not None
    assert result["file_paths"]["md"] is not None
