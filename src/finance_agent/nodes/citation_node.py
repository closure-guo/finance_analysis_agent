"""引用校验图节点 - 从 analyst_reports 提取 claims，批量校验。

在 Layer I 分析师产出后执行，校验所有 Claim 的数据引用。
citation_pass 驱动 after_citation 路由：PASS -> 渲染，FAIL -> 重试。
"""

from __future__ import annotations

import logging
import re

from finance_agent.citation import CitationReport, CitationResult, Claim, verify_claims
from finance_agent.citation_coverage import (
    CoverageReport,
    compute_coverage,
    extract_census_numbers,
)
from finance_agent.langfuse_tracing import get_langfuse, update_current_span
from finance_agent.models import AnalystReport
from finance_agent.routing import citation_retry_stagnated

logger = logging.getLogger("finance_agent.citation")

# refine-citation-coverage-v3 D2/D4：growth_rates 双条件补登记。
# 取整感知容差：整数百分比取整最大误差 0.5 个百分点
_ROUNDING_PP_TOL = 0.5


def _sentence_split(markdown: str) -> list[str]:
    return [s for s in re.split(r"[。\n！？!?；;]", markdown) if s.strip()]


def _event_values(state: dict) -> list[float]:
    """从 state 事件源（key_events/news_list）提取数值（D5，供 event_covered 标记）。

    事件数字（如新闻「出厂价由 969 元上调」）不建数值 claim 而按事件豁免，
    普查命中 event_covered 而非 unmatched。
    """
    items: list[dict | str] = []
    items.extend(state.get("key_events") or [])
    items.extend(state.get("news_list") or [])
    texts = []
    for it in items:
        if isinstance(it, dict):
            for k in ("title", "summary", "content", "text", "date"):
                v = it.get(k)
                if isinstance(v, str):
                    texts.append(v)
        elif isinstance(it, str):
            texts.append(it)
    values: list[float] = []
    for t in texts:
        for n in extract_census_numbers(t):
            if n.value not in values:
                values.append(n.value)
    return values


def supplement_anomaly_claims(
    markdown: str, state: dict, existing_claims: list[Claim | dict]
) -> list[Claim]:
    """state growth_rates 双条件共现自动补登记（D2 吸收 D4）。

    触发双条件：① 同一句中指标名与正文数值共现；② 数值与
    growth_rates.{dim}.{metric} 的整数百分比渲染按 0.5 个百分点容差匹配。
    field_ref 指向结构化真值 growth_rates.{dim}.{metric}（字符串只定位不验证，
    防循环验证）。与人工申报 claim 同 field_ref 的去重；state 无真值的不补
    （反洗白：编造数字不满足双条件）。

    来源为整个 growth_rates（而非仅 anomalies）——D4 吸收：可重算增速数字
    （如 FCF 同比 96.6%）即使未触发 anomaly（|growth|≤0.5）也能补登记；
    anomalies 是 growth_rates 的 |growth|>0.5 子集，天然覆盖。
    """
    growth_rates = state.get("growth_rates") or {}
    sentences = _sentence_split(markdown)
    existing_refs = {
        (c.field_ref if isinstance(c, Claim) else c.get("field_ref")) for c in existing_claims
    }
    out: list[Claim] = []
    for dim, metrics in growth_rates.items():
        for metric, growth in metrics.items():
            if not isinstance(growth, int | float) or growth is None:
                continue
            pct = int(round(growth * 100))  # 整数百分比渲染（compute.py:.0% 同源）
            for sent in sentences:
                if metric not in sent:
                    continue
                # 句中数值与 growth 整数百分比 0.5pp 容差匹配（percent 面值一致）
                hit = any(
                    abs(n.value - pct) <= _ROUNDING_PP_TOL
                    for n in extract_census_numbers(sent)
                    if n.kind == "percent"
                )
                if not hit:
                    continue
                ref = f"growth_rates.{dim}.{metric}"
                if ref in existing_refs:
                    continue
                out.append(
                    Claim(
                        claim_type="numerical",
                        source_type="data",
                        field_ref=ref,
                        stated_value=pct / 100,  # 分数制，与既有 growth claim 口径一致
                        interpretation=f"{metric} 变化率 {pct}%",
                        metric_name=metric,
                    )
                )
                existing_refs.add(ref)
                break
    return out


def verify_citations(state: dict) -> dict:
    """从 analyst_reports 提取所有 Claim，批量校验（按分析师归属聚合）。

    harden-citation-semantic-coverage：FAIL 分桶；值级 FAIL 产出定向重试目标
    与失败明细（供 after_citation 分流与重试上下文注入）；正文 markdown 数字
    普查产出 citation_coverage（监控告警，不进路由）。
    """
    reports = state.get("analyst_reports") or {}

    per_agent: dict[str, list[CitationResult]] = {}
    claims_by_agent: dict[str, list[Claim]] = {}
    for agent, report in reports.items():
        claims = _extract_claims(report)
        claims_by_agent[agent] = claims
        per_agent[agent] = verify_claims(claims, state)

    # D2（refine-citation-coverage-v3）：state anomalies 自动补登记——正文数字 +
    # 指标名同句共现且 state 有结构化真值 → 补 claim，走与人工申报完全相同的校验路径。
    # 编造数字（state 无对应）不满足双条件，保持 unmatched（反洗白）。
    markdown = "\n\n".join(_markdown_of(r) for r in reports.values())
    supplement = supplement_anomaly_claims(
        markdown,
        state,
        [c for claims in claims_by_agent.values() for c in claims],
    )
    if supplement:
        claims_by_agent["anomaly_supplement"] = supplement
        per_agent["anomaly_supplement"] = verify_claims(supplement, state)

    results = [r for rs in per_agent.values() for r in rs]
    report = CitationReport.from_results(results)

    # 分桶聚合：仅 value_mismatch 触发定向重试（D3）；格式类 FAIL 直判不重试
    retry_targets: list[str] = []
    retry_feedback: dict[str, list[dict]] = {}
    fail_buckets: dict[str, int] = {}
    for agent, rs in per_agent.items():
        for r in rs:
            if r.status != "FAIL" or r.bucket is None:
                continue
            fail_buckets[r.bucket] = fail_buckets.get(r.bucket, 0) + 1
            if r.bucket != "value_mismatch":
                continue
            if agent not in retry_targets:
                retry_targets.append(agent)
            retry_feedback.setdefault(agent, []).append(
                {
                    "field_ref": r.claim.field_ref,
                    "stated_value": r.claim.stated_value,
                    "ground_truth": r.ground_truth,
                    "delta": r.delta,
                    "interpretation": r.claim.interpretation,
                }
            )
    retry_targets.sort()

    # 正文覆盖率：合并四分析师 markdown 普查，claim stated_value 全集为认领池
    # （含 anomaly_supplement 补登记 claim，认领池同步扩充）
    all_stated = [
        float(c.stated_value)
        for claims in claims_by_agent.values()
        for c in claims
        if _is_float(c.stated_value)
    ]
    coverage = compute_coverage(markdown, all_stated, event_values=_event_values(state))

    _report_to_langfuse(report, coverage)

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
            metadata={"citation_minor_fail_deescalated": True, "fail_rates": fail_rates},
            level="WARNING",
        )

    # 格式类 FAIL 直判放行（D3）：有 FAIL 但无值级重试目标 → incident 候选可观测
    if not report.all_passed and not retry_targets:
        update_current_span(
            metadata={
                "citation_format_fail_incident_candidate": True,
                "fail_buckets": fail_buckets,
            },
            level="WARNING",
        )

    if not report.all_passed and iteration_count + 1 < 3 and citation_retry_stagnated(fail_rates):
        # 降级决策须可观测：路由将因失败率停滞跳过下一轮重试
        update_current_span(
            metadata={"citation_retry_deescalated": True, "fail_rates": fail_rates},
            level="WARNING",
        )

    return {
        "citation_report": report.model_dump(),
        "citation_pass": report.all_passed,
        "iteration_count": iteration_count + 1,
        "citation_fail_rates": fail_rates,
        "citation_minor_fail": minor_fail,
        "citation_retry_targets": retry_targets,
        "citation_retry_feedback": retry_feedback,
        "citation_fail_buckets": fail_buckets,
        "citation_coverage": coverage.coverage,
    }


def _is_float(v: object) -> bool:
    try:
        float(v)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False


def _markdown_of(report: AnalystReport | dict) -> str:
    if isinstance(report, AnalystReport):
        return report.markdown
    if isinstance(report, dict):
        return str(report.get("markdown") or "")
    return ""


def _report_to_langfuse(report: CitationReport, coverage: CoverageReport) -> None:
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
        # citation_coverage（harden-citation-semantic-coverage）：NUMERIC 0-1，
        # 只监控不进路由；< 0.8 告警（span WARNING + 日志）
        client.score_current_trace(
            name="citation_coverage",
            value=round(coverage.coverage, 4),
            data_type="NUMERIC",
            comment=f"{coverage.matched}/{coverage.total} numbers claimed",
            metadata={"unmatched": coverage.unmatched[:20]},
        )
        if coverage.coverage < 0.8:
            logger.warning(
                "citation_coverage %.4f < 0.8：%d/%d 未认领 %s",
                coverage.coverage,
                len(coverage.unmatched),
                coverage.total,
                coverage.unmatched[:10],
            )
            client.update_current_span(
                metadata={
                    "citation_coverage_alert": True,
                    "citation_coverage": coverage.coverage,
                    "unmatched": coverage.unmatched[:20],
                },
                level="WARNING",
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
