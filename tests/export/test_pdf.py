"""export/pdf_exporter.py 单元测试。"""

import pytest

weasyprint = pytest.importorskip("weasyprint", exc_type=OSError)

from finance_agent.export.pdf_exporter import markdown_to_pdf  # noqa: E402


def test_pdf_generation_with_chinese_and_table(tmp_path):
    markdown = (
        "# 测试报告\n\n"
        "## 第一章\n\n"
        "这是**中文**段落。\n\n"
        "| 指标 | 数值 |\n"
        "|------|------|\n"
        "| 营收 | 100亿 |\n"
    )
    output = tmp_path / "test.pdf"
    result = markdown_to_pdf(markdown, str(output), "测试股票")

    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0
    with output.open("rb") as f:
        assert f.read(5) == b"%PDF-"


def test_pdf_embeds_existing_image(tmp_path):
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    markdown = f"# 报告\n\n![盈利图]({img})\n\n正文。\n"
    output = tmp_path / "with_img.pdf"

    markdown_to_pdf(markdown, str(output))

    assert output.exists()
    assert output.stat().st_size > 0


def test_pdf_skips_missing_image(tmp_path):
    markdown = "# 报告\n\n![图表](C:/不存在/图表.png)\n\n正文仍要渲染。\n"
    output = tmp_path / "no_img.pdf"

    result = markdown_to_pdf(markdown, str(output))

    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0
