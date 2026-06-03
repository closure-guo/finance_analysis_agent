"""generate_file: 生成 Word/PPT 文件（统一追加免责声明）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from finance_agent.export.docx_exporter import markdown_to_docx
from finance_agent.export.pptx_exporter import markdown_to_pptx

_DISCLAIMER = (
    "\n\n---\n\n**免责声明**：本报告由 AI 系统基于公开财务数据自动生成，仅供参考，不构成任何投资建议。"
    "报告中的分析和结论基于历史数据和公开市场信息，不保证未来表现。"
    "投资者应结合自身情况独立判断，并咨询专业投资顾问。"
)


def generate_file(state: dict) -> dict:
    final_report = state.get("final_report", "")
    if not final_report:
        # Single-agent mode fallback (investment/financial without merge)
        final_report = state.get("investment_report", "") or state.get("financial_report", "")
    if not final_report:
        return {"file_path": None, "file_paths": None}

    # 统一追加免责声明（避免重复）
    if "免责声明" not in final_report:
        final_report += _DISCLAIMER

    stock_code = state.get("stock_code", "unknown")
    stock_name = _get_stock_name(state)

    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d")
    base_name = f"{stock_code}_{date_str}"

    docx_target = str(reports_dir / f"{base_name}_report.docx")
    pptx_target = str(reports_dir / f"{base_name}_report.pptx")

    docx_path: str | None = docx_target
    pptx_path: str | None = pptx_target

    try:
        markdown_to_docx(final_report, docx_target, stock_name)
    except Exception:
        docx_path = None  # noqa: S110

    try:
        markdown_to_pptx(final_report, pptx_target, stock_name)
    except Exception:
        pptx_path = None  # noqa: S110

    file_paths: dict[str, str | None] = {
        "docx": docx_path,
        "pptx": pptx_path,
    }

    return {
        "file_path": docx_path,
        "file_paths": file_paths,
        "final_report": final_report,
    }


def _get_stock_name(state: dict) -> str:
    quote = state.get("stock_quote") or {}
    info = state.get("industry_info") or {}
    return str(quote.get("name") or info.get("name", ""))
