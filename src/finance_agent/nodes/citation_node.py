"""引用校验图节点 — 从 analyst_reports 提取 claims，批量校验。

在 Layer I 分析师产出后执行，校验所有 Claim 的数据引用。
citation_pass 驱动 after_citation 路由：PASS → 渲染，FAIL → 重试。
"""

from __future__ import annotations

from finance_agent.citation import CitationReport, Claim, verify_claims
from finance_agent.models import AnalystReport


def verify_citations(state: dict) -> dict:
    """从 analyst_reports 提取所有 Claim，批量校验。"""
    reports = state.get("analyst_reports") or {}

    all_claims: list[Claim] = []
    for report in reports.values():
        claims = _extract_claims(report)
        all_claims.extend(claims)

    results = verify_claims(all_claims, state)
    report = CitationReport.from_results(results)

    return {
        "citation_report": report.model_dump(),
        "citation_pass": report.all_passed,
    }


def _extract_claims(report: AnalystReport | dict) -> list[Claim]:
    """从 AnalystReport（Pydantic 或 dict）中提取 Claim 列表。"""
    if isinstance(report, AnalystReport):
        return list(report.claims)

    if isinstance(report, dict):
        raw_claims = report.get("claims", [])
        return [Claim.model_validate(c) if isinstance(c, dict) else c for c in raw_claims]

    return []
