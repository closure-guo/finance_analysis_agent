"""generate_file: 生成 Word/PPT 文件。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from finance_agent.export.docx_exporter import markdown_to_docx
from finance_agent.export.pptx_exporter import markdown_to_pptx


def generate_file(state: dict) -> dict:
    final_report = state.get("final_report", "")
    if not final_report:
        return {"file_path": None, "file_paths": None}

    stock_code = state.get("stock_code", "unknown")
    stock_name = _get_stock_name(state)

    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d")
    base_name = f"{stock_code}_{date_str}"

    docx_path = str(reports_dir / f"{base_name}_report.docx")
    pptx_path = str(reports_dir / f"{base_name}_report.pptx")

    try:
        markdown_to_docx(final_report, docx_path, stock_name)
    except Exception:
        docx_path = None  # noqa: S110

    try:
        markdown_to_pptx(final_report, pptx_path, stock_name)
    except Exception:
        pptx_path = None  # noqa: S110

    file_paths: dict[str, str | None] = {
        "docx": docx_path,
        "pptx": pptx_path,
    }

    return {
        "file_path": docx_path,
        "file_paths": file_paths,
    }


def _get_stock_name(state: dict) -> str:
    quote = state.get("stock_quote") or {}
    info = state.get("industry_info") or {}
    return quote.get("name") or info.get("name", "")
