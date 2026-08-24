"""output.py 单元测试 — 验证 generate_file 返回正确路径。"""

from unittest.mock import patch


@patch("finance_agent.export.service.markdown_to_docx")
@patch("finance_agent.export.service.markdown_to_pptx")
def test_generate_file_returns_paths(mock_pptx, mock_docx, tmp_path, monkeypatch):
    from finance_agent.nodes.output import generate_file

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))

    state = {
        "final_report": "# Report",
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台"},
        "industry_info": {},
    }
    result = generate_file(state)

    assert result["file_path"] is not None
    assert result["file_paths"] is not None
    assert result["file_paths"]["docx"] is not None
    assert result["file_paths"]["pptx"] is not None


def test_generate_file_empty_report():
    from finance_agent.nodes.output import generate_file

    result = generate_file({"final_report": ""})

    assert result["file_path"] is None
    assert result["file_paths"] is None


@patch("finance_agent.export.service.markdown_to_docx")
@patch("finance_agent.export.service.markdown_to_pptx")
def test_generate_file_creates_nested_reports_dir(mock_pptx, mock_docx, monkeypatch, tmp_path):
    """REPORTS_DIR 的父目录不存在时，generate_file 应递归创建而非崩溃（issue #46）。

    根因：mkdir(exist_ok=True) 缺少 parents=True，当 REPORTS_DIR 为嵌套路径
    （如 E2E 的 tmp/e2e-reports-8002）且父目录不存在时抛 FileNotFoundError，
    导致管线末端节点崩溃、report_ready 事件丢失。
    """
    # 设置一个父目录不存在的嵌套路径
    nestedDir = tmp_path / "a" / "b" / "c"
    monkeypatch.setenv("REPORTS_DIR", str(nestedDir))

    from finance_agent.nodes.output import generate_file

    state = {
        "final_report": "# Report",
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台"},
        "industry_info": {},
    }
    # 不应抛 FileNotFoundError
    result = generate_file(state)
    assert result["file_path"] is not None
