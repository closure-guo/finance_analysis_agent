"""output.py 单元测试 — 验证 generate_file 返回正确路径。"""

from unittest.mock import patch


@patch("finance_agent.nodes.output.markdown_to_docx")
@patch("finance_agent.nodes.output.markdown_to_pptx")
def test_generate_file_returns_paths(mock_pptx, mock_docx, tmp_path):
    from finance_agent.nodes.output import generate_file

    mock_docx.return_value = str(tmp_path / "test.docx")
    mock_pptx.return_value = str(tmp_path / "test.pptx")

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
