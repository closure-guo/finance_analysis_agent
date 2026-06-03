"""merge_reports: 拼接 FA + IA 报告，comprehensive 模式下 LLM 写综合摘要 + 代码硬拼对比表格。

免责声明统一由 output.py 的 generate_file 节点追加，避免重复。
"""

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

    # ── Comprehensive 模式：LLM 综合摘要 + 对比表格 ──
    fa_report = state.get("financial_report", "")
    ia_report = state.get("investment_report", "")

    # 防御：如果某一方报告缺失，先透传已有的
    if not fa_report:
        return {"final_report": ia_report or ""}
    if not ia_report:
        return {"final_report": fa_report or ""}

    # 提取分析正文（比完整报告更紧凑，更适合作为 LLM 上下文）
    fa_analysis = state.get("financial_analysis", "")
    ia_analysis = state.get("investment_analysis", "")

    # 代码硬拼对比表格
    comparison_table = _build_comparison_table(state)

    # 综合结论
    synthesis = _generate_synthesis(fa_analysis, ia_analysis, comparison_table)

    final = (
        f"# 综合分析报告\n\n"
        f"## 综合结论\n\n{synthesis}\n\n"
        f"## 核心数据对比\n\n{comparison_table}\n\n"
        f"---\n\n"
        f"{fa_report}\n\n"
        f"---\n\n"
        f"{ia_report}"
    )

    return {"final_report": final}


def _build_comparison_table(state: dict) -> str:
    """从 state 提取结构化数据，硬拼 Markdown 对比表格。"""
    rows: list[str] = []
    rows.append("| 评估维度 | 财务分析 (FA) | 投资分析 (IA) |")
    rows.append("|---------|--------------|--------------|")

    # 健康度评分
    health = state.get("health_score") or {}
    total = health.get("total")
    rating = health.get("rating", "N/A")
    dims = health.get("dimensions") or {}
    if total is not None:
        rows.append(f"| 综合健康度 | **{total} 分**（{rating}） | — |")

    # 四维度分数
    dim_names = {
        "solvency": "偿债能力",
        "profitability": "盈利能力",
        "efficiency": "运营效率",
        "cashflow": "现金流健康",
    }
    for key, label in dim_names.items():
        val = dims.get(key)
        if val is not None:
            rows.append(f"| {label} | {val:.1f} 分 | — |")

    # 估值水平（来自 stock_quote）
    quote = state.get("stock_quote") or {}
    pe = quote.get("PE") or quote.get("PE_ttm")
    pb = quote.get("PB")
    if pe is not None or pb is not None:
        pe_str = f"{pe:.2f}x" if pe is not None else "N/A"
        pb_str = f"{pb:.2f}x" if pb is not None else "N/A"
        rows.append(f"| 估值水平 | — | PE {pe_str} / PB {pb_str} |")

    # GARP 筛选
    garp = state.get("garp_result")
    if garp:
        passed = "✅ 通过" if garp.get("pass") else "❌ 未通过"
        failures = garp.get("failures", [])
        detail = f"（{', '.join(failures)}）" if failures else ""
        rows.append(f"| GARP 筛选 | — | {passed}{detail} |")

    return "\n".join(rows) if len(rows) > 2 else "*暂无对比数据*"


def _generate_synthesis(fa_analysis: str, ia_analysis: str, comparison_table: str) -> str:
    """调用 LLM 生成 300-500 字综合摘要。"""
    if not fa_analysis and not ia_analysis:
        return "暂无分析数据。"

    prompt = load_prompt("synthesis").replace("{{fa_analysis}}", fa_analysis or "无")
    prompt = prompt.replace("{{ia_analysis}}", ia_analysis or "无")

    # 把对比表格也传给 LLM，帮助它发现分歧点
    prompt += f"\n\n## 核心数据对比\n\n{comparison_table}\n\n请在综合结论中引用上述数据，并明确指出 FA 与 IA 的一致性与分歧点。"

    return call_llm(
        prompt,
        system="你是资深投资顾问，擅长整合财务分析与投资分析观点，撰写简明扼要的综合结论。",
        temperature=0.3,
        max_tokens=1024,
    )
