"""add-citation-display Task 1.1/1.2 契约测试：引用结构化下发。

- _citations_payload：CitationReport（model_dump 后 dict）→ 前端五字段引用数组，
  verdict 三级映射 PASS→verified / FAIL→failed / UNVERIFIABLE→unchecked
- inject_citation_marks：报告 Markdown 唯一匹配的 claim 处注入 [[cite-<id>]] 标记
- 持久化往返：citations 随 update_session_report 落库、get_session 读回；
  旧数据无该字段 → citations 为 None（缺省不报错，向后兼容）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from finance_agent import session_store
from finance_agent.api import _citations_payload, _report_ready_event, inject_citation_marks


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    """独立临时库，避免污染开发数据。"""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "sessions.db"
        monkeypatch.setattr(session_store, "_DB_PATH", db)
        session_store.init_db()
        yield db


def _sample_report() -> dict:
    return {
        "results": [
            {
                "status": "PASS",
                "claim": {
                    "claim_type": "computational",
                    "source_type": "data",
                    "field_ref": "solvency_metrics.资产负债率.2024",
                    "stated_value": 62.5,
                    "interpretation": "2024 年末资产负债率为 62.5%",
                },
                "ground_truth": 62.5,
                "delta": 0.0,
                "coverage_gap": False,
            },
            {
                "status": "FAIL",
                "claim": {
                    "claim_type": "comparative",
                    "source_type": "mixed",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "field_ref_b": "profitability_metrics.毛利率.2023",
                    "stated_value": "同比提升",
                    "interpretation": "毛利率同比提升",
                },
                "ground_truth": 31.2,
                "delta": -0.8,
                "coverage_gap": False,
            },
            {
                "status": "UNVERIFIABLE",
                "claim": {
                    "claim_type": "llm_inference",
                    "source_type": "llm_inference",
                    "field_ref": "unknown.metric",
                    "stated_value": 0,
                    "interpretation": "行业景气度处于上行区间",
                },
                "ground_truth": None,
                "delta": None,
                "coverage_gap": True,
            },
        ],
    }


class TestCitationsPayload:
    def test_verdict_mapping_and_fields(self) -> None:
        citations = _citations_payload(_sample_report())
        assert len(citations) == 3
        assert [c["verdict"] for c in citations] == ["verified", "failed", "unchecked"]
        for i, c in enumerate(citations, start=1):
            assert c["id"] == f"cite-{i}"
            assert set(c) == {"id", "claim", "source", "verdict", "detail"}
        assert citations[0]["claim"] == "2024 年末资产负债率为 62.5%"
        assert "solvency_metrics.资产负债率.2024" in citations[0]["source"]
        assert "重算" in citations[0]["detail"]

    def test_empty_and_missing_report(self) -> None:
        assert _citations_payload(None) == []
        assert _citations_payload({}) == []
        assert _citations_payload({"results": []}) == []


class TestInjectCitationMarks:
    def test_unique_match_injected(self) -> None:
        citations = _citations_payload(_sample_report())
        md = "报告中提到，2024 年末资产负债率为 62.5%，风险可控。"
        out = inject_citation_marks(md, citations)
        assert "[[cite-1]]" in out
        assert "风险可控" in out  # 其余内容不动

    def test_no_match_untouched(self) -> None:
        citations = _citations_payload(_sample_report())
        md = "完全无关的报告正文。"
        assert inject_citation_marks(md, citations) == md

    def test_ambiguous_match_skipped(self) -> None:
        citations = _citations_payload(_sample_report())
        md = "毛利率同比提升；另一种说法：毛利率同比提升。"
        out = inject_citation_marks(md, citations)
        assert "[[cite-2]]" not in out  # 多处出现不注入，避免锚点漂移


class TestReportReadyPayload:
    def test_event_carries_citations(self) -> None:
        ev = _report_ready_event(
            analysis_id="a1",
            session_id="s1",
            report_markdown="# 报告",
            chart_data={},
            file_paths={},
            stock_code="600449",
            stock_name="宁夏建材",
            duration_ms=1000,
            citations=_citations_payload(_sample_report()),
        )
        assert ev["type"] == "report_ready"
        assert len(ev["citations"]) == 3
        assert ev["citations"][0]["verdict"] == "verified"

    def test_event_without_citations_omits_key(self) -> None:
        # 旧调用路径（无引用）：负载省略 citations 键，前端按缺省处理
        ev = _report_ready_event(
            analysis_id="a1",
            session_id="s1",
            report_markdown="",
            chart_data={},
            file_paths={},
            stock_code="",
            stock_name="",
            duration_ms=0,
        )
        assert "citations" not in ev


class TestPersistenceRoundTrip:
    def test_citations_roundtrip(self, temp_db: Path) -> None:
        session_id = session_store.create_session(
            stock_code="600449", stock_name="宁夏建材", status="running"
        )
        citations = _citations_payload(_sample_report())
        assert session_store.update_session_report(
            session_id,
            report_markdown="# 报告",
            status="completed",
            citations=citations,
        )
        detail = session_store.get_session(session_id)
        assert detail is not None
        assert detail["citations"] == citations

    def test_legacy_session_without_citations(self, temp_db: Path) -> None:
        session_id = session_store.create_session(
            stock_code="600519", stock_name="贵州茅台", status="completed"
        )
        session_store.update_session_report(
            session_id, report_markdown="# 旧报告", status="completed"
        )
        detail = session_store.get_session(session_id)
        assert detail is not None
        assert detail["citations"] is None  # 旧数据缺省，不报错
