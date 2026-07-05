"""5 层架构报告生成节点 — 汇总 Agent 输出为结构化 Markdown 报告。

从 state 读取 5 层 Agent 输出，组装为最终报告。
同时收集 chart_data 并生成 PNG 图表嵌入报告。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

from finance_agent.charts import collect_chart_data, generate_all_charts
from finance_agent.models import AnalystReport, DebateMessage, TradeDecision


def generate_report(state: dict) -> dict:
    """汇总 5 层 Agent 输出，生成最终 Markdown 报告 + 图表数据。"""
    stock_name = state.get("stock_name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    date = datetime.now().strftime("%Y-%m-%d")

    # ── 收集图表数据 ──
    chart_data = collect_chart_data(state)

    # ── 生成 PNG 图表 ──
    stock_code_safe = "".join(c for c in stock_code if c.isalnum()) or "unknown"
    charts_dir = os.path.join(tempfile.gettempdir(), "finance_charts", stock_code_safe)
    chart_paths = generate_all_charts(chart_data, charts_dir)

    sections: list[str] = [
        f"# {stock_name}({stock_code}) 投资分析报告",
        f"\n*报告日期: {date}*\n",
    ]

    # ── 一、核心财务指标图表 ──
    if chart_paths:
        sections.append("## 一、核心财务指标图表\n")
        chart_titles = [
            ("chart_revenue_profit", "营业收入与归母净利润"),
            ("chart_growth", "同比增速"),
            ("chart_margin", "毛利率与净利率"),
            ("chart_roe", "ROE 变化趋势"),
            ("chart_cashflow", "经营现金流净额"),
            ("chart_stock_price", "股价趋势"),
            ("chart_growth_vs_price", "财务增速 vs 股价涨幅"),
            ("chart_assets", "总资产与归母权益"),
            ("chart_contract_liab", "合同负债"),
            ("chart_debt_ratio", "资产负债率趋势"),
            ("chart_heatmap", "财报发布窗口期股价变化"),
            ("chart_dashboard", "财务指标综合仪表盘"),
            ("chart_market_share", "全球市场份额"),
        ]
        for chart_name, title in chart_titles:
            path = chart_paths.get(chart_name)
            if path:
                sections.append(f"### {title}\n")
                sections.append(f"![{title}]({path})\n")
        sections.append("---\n")

    # ── 二、分析师团队报告 ──
    reports = state.get("analyst_reports") or {}
    if reports:
        sections.append("## 二、分析师团队报告\n")
        for name, report in reports.items():
            sections.append(_format_analyst_report(name, report))

    # ── 三、多空辩论结论 ──
    conclusion = state.get("research_manager_conclusion")
    if conclusion:
        sections.append(f"## 三、多空辩论结论\n\n{conclusion}\n")

    # ── 四、交易决策 ──
    decision = state.get("final_trade_decision") or state.get("trader_plan")
    if decision:
        sections.append(f"## 四、交易决策\n\n{_format_trade_decision(decision)}\n")

    # ── 五、风控结论 ──
    risk_history = state.get("risk_debate_history") or []
    if risk_history:
        sections.append("## 五、风控辩论\n")
        for msg in risk_history:
            sections.append(_format_debate_message(msg))

    # ── 六、基金经理决策 ──
    fm_decision = state.get("fund_manager_decision")
    if fm_decision:
        sections.append(f"## 六、基金经理决策\n\n**{fm_decision}**\n")

    return {
        "final_report": "\n".join(sections),
        "chart_data": chart_data,
    }


def _format_analyst_report(name: str, report: AnalystReport | dict) -> str:
    """格式化单个分析师报告。"""
    if isinstance(report, AnalystReport):
        summary = report.summary
        findings = report.key_findings
    else:
        summary = report.get("summary", "")
        findings = report.get("key_findings", [])

    lines = [f"### {name}\n", f"{summary}\n"]
    if findings:
        lines.append("**关键发现：**\n")
        for f in findings:
            lines.append(f"- {f}")
        lines.append("")
    return "\n".join(lines)


def _format_trade_decision(decision: TradeDecision | dict) -> str:
    """格式化交易决策。"""
    if isinstance(decision, TradeDecision):
        action = decision.action
        confidence = decision.confidence
        reasoning = decision.reasoning
    else:
        action = decision.get("action", "N/A")
        confidence = decision.get("confidence", 0)
        reasoning = decision.get("reasoning", "")

    return f"- **方向**: {action}\n- **置信度**: {confidence:.0%}\n- **理由**: {reasoning}"


def _format_debate_message(msg: DebateMessage | dict) -> str:
    """格式化辩论消息。"""
    if isinstance(msg, DebateMessage):
        role = msg.role
        content = msg.content
    else:
        role = msg.get("role", "?")
        content = msg.get("content", "")

    return f"**{role}**: {content}\n"
