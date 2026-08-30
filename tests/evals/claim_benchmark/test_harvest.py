"""收割脚本测试：mock Langfuse 客户端 → 断言 claims_raw 记录写入与版本/复判字段。"""

from datetime import UTC, datetime

from evals.claim_benchmark._langfuse import LangfuseClient

from evals.claim_benchmark import harvest


def _trace(trace_id: str, ts: str, stock: str, results: list[dict]) -> dict:
    return {
        "id": trace_id,
        "name": f"deep_analysis:{stock}",
        "timestamp": ts,
        "input": {"stock_code": stock},
        "metadata": {"citation_report": {"results": results, "total": len(results)}},
    }


def _result(status: str, field_ref: str, stated, gt, delta, coverage_gap=False) -> dict:
    return {
        "status": status,
        "claim": {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": field_ref,
            "stated_value": stated,
            "interpretation": "",
        },
        "ground_truth": gt,
        "delta": delta,
        "coverage_gap": coverage_gap,
    }


class FakeClient:
    def __init__(self, traces: list[dict]) -> None:
        self._traces = traces

    def iter_deep_traces(self, from_date, to_date=None) -> list[dict]:
        return self._traces


class TestHarvestRecords:
    def _run(self, traces: list[dict]) -> list[dict]:
        cutoff = datetime(2026, 8, 29, 4, 5, tzinfo=UTC)
        from_date = datetime(2026, 7, 1, tzinfo=UTC)
        return harvest.harvest_records(FakeClient(traces), from_date, None, cutoff)  # type: ignore[arg-type]

    def test_emits_claim_records_with_version_split(self):
        traces = [
            _trace(
                "t-pre",
                "2026-08-26T10:00:00+00:00",
                "某股",
                [
                    _result("FAIL", "盈利能力.毛利率.2025", 77.0, None, None),
                    _result("PASS", "profitability_metrics.毛利率.2025", 77.36, 77.363, 0.003),
                ],
            ),
            _trace(
                "t-post",
                "2026-08-30T09:00:00+00:00",
                "汉森制药",
                [_result("PASS", "technical_indicators.MA.5.-1", 12.7, 12.7, 0.0)],
            ),
        ]
        recs = self._run(traces)
        assert len(recs) == 3
        assert [r["trace_version"] for r in recs] == ["pre_fix", "pre_fix", "post_fix"]
        # rejudged_status 按当前契约填充：词表疾病样本 gt=None → UNVERIFIABLE（离线不可复判）
        assert recs[0]["rejudged_status"] == "UNVERIFIABLE"
        # 容差内 PASS
        assert recs[1]["rejudged_status"] == "PASS"
        assert recs[2]["rejudged_status"] == "PASS"
        # stock_code 从 input 取
        assert recs[2]["stock_code"] == "汉森制药"

    def test_llm_inference_status_preserved(self):
        res = {
            "status": "UNVERIFIABLE",
            "claim": {
                "claim_type": "numerical",
                "source_type": "llm_inference",
                "field_ref": "x",
                "stated_value": "",
                "interpretation": "",
            },
            "ground_truth": None,
            "delta": None,
            "coverage_gap": False,
        }
        recs = self._run([_trace("t1", "2026-08-30T09:00:00+00:00", "某股", [res])])
        assert recs[0]["verifier_status"] == "UNVERIFIABLE"
        assert recs[0]["rejudged_status"] == "UNVERIFIABLE"


class TestLangfuseClient:
    def test_secret_required(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        try:
            LangfuseClient()
        except RuntimeError as e:
            assert "LANGFUSE_PUBLIC_KEY" in str(e)
        else:  # pragma: no cover
            raise AssertionError("缺少凭据时应抛 RuntimeError")
