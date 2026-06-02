"""export/pptx_exporter.py 单元测试。"""

from pathlib import Path

from finance_agent.export.pptx_exporter import markdown_to_pptx


def test_pptx_generation(tmp_path):
    markdown = "## Chapter 1\n\nContent here.\n\n## Chapter 2\n\nMore content.\n"
    output = tmp_path / "test.pptx"
    result = markdown_to_pptx(markdown, str(output), "Test Stock")

    assert Path(result).exists()


def test_pptx_contains_disclaimer(tmp_path):
    markdown = "## Chapter 1\n\nHello world."
    output = tmp_path / "test.pptx"
    markdown_to_pptx(markdown, str(output))

    assert Path(output).exists()
