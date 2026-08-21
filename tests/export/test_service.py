"""export/service.py 单元测试。"""

from pathlib import Path

from finance_agent.export.service import append_disclaimer, export_report, sanitize_missing_images

_SAMPLE = "# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"


def test_sanitize_missing_images_drops_broken_lines():
    text = "# 标题\n\n![好图](C:/存在/图.png)\n\n![坏图](C:/不存在/图.png)\n正文\n"
    result = sanitize_missing_images(text)

    assert "![好图]" in result
    assert "![坏图]" not in result
    assert "正文" in result


def test_append_disclaimer_idempotent():
    once = append_disclaimer("正文")
    twice = append_disclaimer(once)

    assert "免责声明" in once
    assert twice == once


def test_export_report_all_formats(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "贵州茅台")

    assert set(result.keys()) == {"docx", "pptx", "pdf", "md"}
    for fmt, path in result.items():
        assert path is not None, f"{fmt} 应生成成功"
        assert Path(path).exists()


def test_export_report_single_format(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "贵州茅台", formats=("md",))

    assert list(result.keys()) == ["md"]
    assert result["md"] is not None
    content = Path(result["md"]).read_text(encoding="utf-8")
    assert "免责声明" in content
