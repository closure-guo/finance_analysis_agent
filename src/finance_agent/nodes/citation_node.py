"""引用校验图节点 - 从 analyst_reports 提取 claims，批量校验。

在 Layer I 分析师产出后执行，校验所有 Claim 的数据引用。
citation_pass 驱动 after_citation 路由：PASS -> 渲染，FAIL -> 重试。
"""

from __future__ import annotations

import logging

from finance_agent.citation import CitationReport, Claim, verify_claims
from finance_agent.langfuse_tracing import get_langfuse
from finance_agent.models import AnalystReport

logger = logging.getLogger("finance_agent.citation")


def verify_citations(state: dict) -> dict:
    """从 analyst_reports 提取所有 Claim，批量校验。"""
    reports = state.get("analyst_reports") or {}

    all_claims: list[Claim] = []
    for report in reports.values():
        claims = _extract_claims(report)
        all_claims.extend(claims)

    results = verify_claims(all_claims, state)
    report = CitationReport.from_results(results)

    # L0（ADR-0010 第 124 行兑现）：citation_pass 上报为 trace 级 boolean score，
    # 明细附在 verify_citations span 的 metadata 上供下钻。
    _report_to_langfuse(report)

    # 递增 iteration_count，使 after_citation 的重试上限（< 3）真正生效。
    # 否则 citation_pass=False 时会无限重试，图永远无法推进到辩论/报告阶段。
    iteration_count = state.get("iteration_count", 0)

    return {
        "citation_report": report.model_dump(),
        "citation_pass": report.all_passed,
        "iteration_count": iteration_count + 1,
    }


def _report_to_langfuse(report: CitationReport) -> None:
    """上报 citation 校验结果到 Langfuse（trace 级 boolean score + span 明细）。

    citation_unverifiable_ratio（spec「UNVERIFIABLE 占比监控」）是数据层退化的
    先行指标；上报失败记 WARN（spec：Langfuse 不可用 SHALL 记 WARN 且不阻断）。
    """
    try:
        client = get_langfuse()
        if client is None:
            logger.warning("Langfuse 未配置, citation score 未上报")
            return
        fail_count = sum(1 for r in report.results if r.status == "FAIL")
        total = len(report.results)
        client.score_current_trace(
            name="citation_pass",
            value=1.0 if report.all_passed else 0.0,
            data_type="BOOLEAN",
            comment=f"{'PASS' if report.all_passed else 'FAIL'}: {fail_count}/{total} claims failed",
            metadata={"all_passed": report.all_passed, "fail_count": fail_count, "total": total},
        )
        ratio = (report.unverifiable / total) if total else 0.0
        client.score_current_trace(
            name="citation_unverifiable_ratio",
            value=round(ratio, 4),
            data_type="NUMERIC",
            comment=f"UNVERIFIABLE {report.unverifiable}/{total}; coverage_gaps={report.coverage_gaps}",
        )
        client.update_current_span(
            metadata={"citation_report": report.model_dump()},
        )
    except Exception as e:
        logger.warning("Langfuse citation score 上报失败: %s", e)


def _extract_claims(report: AnalystReport | dict) -> list[Claim]:
    """从 AnalystReport（Pydantic 或 dict）中提取 Claim 列表。"""
    if isinstance(report, AnalystReport):
        return list(report.claims)

    if isinstance(report, dict):
        raw_claims = report.get("claims", [])
        return [Claim.model_validate(c) if isinstance(c, dict) else c for c in raw_claims]

    return []
