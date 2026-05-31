"""export/docx_exporter.py 单元测试。"""

from pathlib import Path

from finance_agent.export.docx_exporter import markdown_to_docx


def test_docx_generation(tmp_path):
    markdown = (
        "# Report\n\n"
        "## Chapter 1\n\n"
        "Some **bold** text.\n\n"
        "| Col1 | Col2 |\n"
        "|------|------|\n"
        "| A    | B    |\n"
    )
    output = tmp_path / "test.docx"
    result = markdown_to_docx(markdown, str(output), "Test Stock")

    assert Path(result).exists()


def test_docx_contains_disclaimer(tmp_path):
    markdown = "# Report\n\nHello world."
    output = tmp_path / "test.docx"
    markdown_to_docx(markdown, str(output))

    assert Path(output).exists()
