"""可复用报告导出服务：Markdown → docx/pptx/pdf/md 四格式。

generate_file（管线结束自动生成）与 POST /api/export（按需导出）共用本模块，
统一负责免责声明追加、缺失图片图片容错与 REPORTS_DIR 落盘。
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from finance_agent.export.docx_exporter import markdown_to_docx
from finance_agent.export.pdf_exporter import markdown_to_pdf
from finance_agent.export.pptx_exporter import markdown_to_pptx

EXPORT_FORMATS: tuple[str, ...] = ("docx", "pptx", "pdf", "md")

_DISCLAIMER = (
    "\n\n---\n\n**免责声明**：本报告由 AI 系统基于公开财务数据自动生成，仅供参考，不构成任何投资建议。"
    "报告中的分析和结论基于历史数据和公开市场信息，不保证未来表现。"
    "投资者应结合自身情况独立判断，并咨询专业投资顾问。"
)

_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")


def sanitize_missing_images(markdown_text: str) -> str:
    """删除引用不存在文件的图片行（![alt](path)），其余原样保留。"""
    out_lines = []
    for line in markdown_text.splitlines():
        m = _IMAGE_LINE_RE.match(line.strip())
        if m and not Path(m.group(2)).exists():
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def append_disclaimer(markdown_text: str) -> str:
    """追加统一免责声明（已含「免责声明」则不重复）。"""
    if "免责声明" in markdown_text:
        return markdown_text
    return markdown_text + _DISCLAIMER


def export_report(
    markdown_text: str,
    stock_code: str,
    stock_name: str = "",
    formats: Sequence[str] = EXPORT_FORMATS,
) -> dict[str, str | None]:
    """将报告 Markdown 生成指定格式文件到 REPORTS_DIR。

    Returns
    -------
    dict[str, str | None]
        {fmt: 完整文件路径 | None}，单格式失败置 None（不抛异常，不阻断其余格式）。
    """
    if not markdown_text:
        return dict.fromkeys(formats)

    markdown_text = append_disclaimer(sanitize_missing_images(markdown_text))

    reports_dir = Path(os.environ.get("REPORTS_DIR", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    name_part = (stock_name or "").strip()
    stem = f"{name_part}_{stock_code}" if name_part and name_part != stock_code else stock_code
    base_name = str(reports_dir / f"{stem}_{date_str}_report")

    converters = {
        "docx": (markdown_to_docx, ".docx"),
        "pptx": (markdown_to_pptx, ".pptx"),
        "pdf": (markdown_to_pdf, ".pdf"),
        "md": (None, ".md"),
    }

    result: dict[str, str | None] = {}
    for fmt in formats:
        if fmt not in converters:
            result[fmt] = None
            continue
        converter, ext = converters[fmt]
        target = base_name + ext
        try:
            if converter is None:  # md：直接写文本
                Path(target).write_text(markdown_text, encoding="utf-8")
            else:
                converter(markdown_text, target, stock_name)
            result[fmt] = target
        except Exception:
            result[fmt] = None  # noqa: S110 — 单格式失败容错
    return result
