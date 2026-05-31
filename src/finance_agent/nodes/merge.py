"""merge_reports: 拼接 FA + IA 报告，comprehensive 模式下 LLM 写综合摘要。"""

from __future__ import annotations

from finance_agent.llm import call_llm
from finance_agent.prompts.loader import load_prompt


def merge_reports(state: dict) -> dict:
    analysis_type = state.get("analysis_type", "financial")

    # ── 单 Agent 模式：直接透传 ──
    if analysis_type != "comprehensive":
        fa = state.get("financial_report", "")
        ia = state.get("investment_report", "")
        return {"final_report": fa or ia or ""}

    # ── Comprehensive 模式：LLM 综合摘要 ──
    fa_report = state.get("financial_report", "")
    ia_report = state.get("investment_report", "")

    # 防御：如果某一方报告缺失，先透传已有的
    if not fa_report:
        return {"final_report": ia_report}
    if not ia_report:
        return {"final_report": fa_report}

    # 提取分析正文（比完整报告更紧凑，更适合作为 LLM 上下文）
    fa_analysis = state.get("financial_analysis", "")
    ia_analysis = state.get("investment_analysis", "")

    synthesis = _generate_synthesis(fa_analysis, ia_analysis)

    final = (
        "# 综合分析报告\n\n"
        "## 综合结论\n\n"
        f"{synthesis}\n\n"
        "---\n\n"
        f"{fa_report}\n\n"
        "---\n\n"
        f"{ia_report}"
    )

    return {"final_report": final}


def _generate_synthesis(fa_analysis: str, ia_analysis: str) -> str:
    """调用 LLM 生成 300-500 字综合摘要。"""
    if not fa_analysis and not ia_analysis:
        return "暂无分析数据。"

    prompt = load_prompt("synthesis").replace("{{fa_analysis}}", fa_analysis or "无")
    prompt = prompt.replace("{{ia_analysis}}", ia_analysis or "无")

    return call_llm(
        prompt,
        system="你是资深投资顾问，擅长整合财务分析与投资分析观点，撰写简明扼要的综合结论。",
        temperature=0.3,
        max_tokens=1024,
    )
