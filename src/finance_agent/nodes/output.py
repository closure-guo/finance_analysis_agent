"""generate_file: 生成 Word/PPT/PDF/Markdown 文件（统一追加免责声明）。"""

from __future__ import annotations

from finance_agent.export.service import append_disclaimer, export_report


def generate_file(state: dict) -> dict:
    final_report = state.get("final_report", "")
    if not final_report:
        return {"file_path": None, "file_paths": None}

    stock_code = state.get("stock_code", "unknown")
    stock_name = _get_stock_name(state)

    # 兼容旧行为：会话落库 / SSE 下发的 final_report（即 report_markdown）含免责声明；
    # 导出服务内 append_disclaimer 幂等，传已追加文本不会重复追加。
    final_report = append_disclaimer(final_report)

    # 导出服务统一处理免责声明、缺失图片容错、REPORTS_DIR 落盘与单格式失败容错
    file_paths = export_report(final_report, stock_code, stock_name)

    return {
        "file_path": file_paths.get("docx"),
        "file_paths": file_paths,
        "final_report": final_report,
    }


def _get_stock_name(state: dict) -> str:
    quote = state.get("stock_quote") or {}
    info = state.get("industry_info") or {}
    return str(quote.get("name") or info.get("name", ""))
