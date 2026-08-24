"""export/service.py 单元测试。"""

from pathlib import Path

import pytest

from finance_agent.export.service import append_disclaimer, export_report, sanitize_missing_images

_SAMPLE = "# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"


def test_sanitize_missing_images_drops_broken_lines(tmp_path):
    good_img = tmp_path / "good.png"
    good_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    text = f"# 标题\n\n![好图]({good_img})\n\n![坏图](C:/不存在/图.png)\n正文\n"
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
    # 探测 weasyprint 可用性：Windows 本地缺 GTK 系统库时 import 抛 OSError，
    # CI/Linux 已配系统库。可用 → 断言四格式全部生成；不可用 → 不整个跳过本用例
    # （docx/pptx/md 生成仍须验证），把降级行为固化为断言：pdf 为 None。
    pdf_available = True
    try:
        pytest.importorskip("weasyprint", exc_type=(ImportError, OSError))
    except pytest.skip.Exception:
        pdf_available = False

    result = export_report(_SAMPLE, "600519", "贵州茅台")

    assert set(result.keys()) == {"docx", "pptx", "pdf", "md"}
    assert bool(pdf_available) == (result["pdf"] is not None)
    for fmt, path in result.items():
        if fmt == "pdf" and not pdf_available:
            continue
        assert path is not None, f"{fmt} 应生成成功"
        assert Path(path).exists()


def test_export_report_single_format(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "贵州茅台", formats=("md",))

    assert list(result.keys()) == ["md"]
    assert result["md"] is not None
    content = Path(result["md"]).read_text(encoding="utf-8")
    assert "免责声明" in content
