"""引用校验图节点 - 从 analyst_reports 提取 claims，批量校验。

在 Layer I 分析师产出后执行，校验所有 Claim 的数据引用。
citation_pass 驱动 after_citation 路由：PASS -> 渲染，FAIL -> 重试。
"""

from __future__ import annotations

import logging

from finance_agent.citation import CitationReport, Claim, verify_claims
from finance_agent.langfuse_tracing import get_langfuse, update_current_span
from finance_agent.models import AnalystReport
from finance_agent.routing import citation_retry_stagnated

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

    # citation-retry-policy delta：记录各轮失败率，供 after_citation 做重试
    # 降级（失败率停滞时提前放行渲染，不再全量重跑分析师）。
    fail_count = sum(1 for r in results if r.status == "FAIL")
    fail_rate = fail_count / len(results) if results else 0.0
    fail_rates = list(state.get("citation_fail_rates") or []) + [fail_rate]

    minor_fail = (not report.all_passed) and fail_count <= 1 and fail_rate <= 0.05
    if minor_fail:
        # skip-citation-retry-on-minor-failures：单点/近零失败直接放行渲染，
        # 不重跑分析师（校验器确定性，同 claim 重跑必复现——incident 022 实测
        # 汉森/茅台 1/46=2.2% FAIL 仍全量重跑 1-2 轮空转）。
        update_current_span(
            metadata={
                "citation_minor_fail_deescalated": True,
                "fail_rates": fail_rates,
            },
            level="WARNING",
        )

    if not report.all_passed and iteration_count + 1 < 3 and citation_retry_stagnated(fail_rates):
        # 降级决策须可观测：路由将因失败率停滞跳过下一轮重试
        update_current_span(
            metadata={
                "citation_retry_deescalated": True,
                "fail_rates": fail_rates,
            },
            level="WARNING",
        )

    return {
        "citation_report": report.model_dump(),
        "citation_pass": report.all_passed,
        "iteration_count": iteration_count + 1,
        "citation_fail_rates": fail_rates,
        "citation_minor_fail": minor_fail,
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
