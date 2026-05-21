"""merge_reports: 拼接 FA + IA 报告，LLM 写综合摘要"""


def merge_reports(state: dict) -> dict:
    fa = state.get("financial_report", "")
    ia = state.get("investment_report", "")
    return {"final_report": f"# 综合分析报告\n\n{fa}\n\n{ia}"}
