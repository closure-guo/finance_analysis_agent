"""claim 基准集 schema 与加载测试。"""

from evals.claim_benchmark.fixtures import build_state
from evals.claim_benchmark.schema import (
    BenchmarkEntry,
    BenchmarkMeta,
    compute_kappa,
    load_entries,
    load_meta,
)


class TestSchema:
    def test_entry_roundtrip(self):
        entry = BenchmarkEntry(
            entry_id="e1",
            state_key="state_v1",
            claim={
                "claim_type": "numerical",
                "source_type": "data",
                "field_ref": "solvency_metrics.资产负债率.2024",
                "stated_value": 40.0,
                "interpretation": "",
            },
            label_final="PASS",
            label_a="PASS",
            label_b="PASS",
            annotator_a="a",
            annotator_b="b",
            subsets=[],
        )
        dumped = entry.model_dump()
        assert BenchmarkEntry.model_validate(dumped) == entry

    def test_meta_requires_version(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BenchmarkMeta(n_reports=1, n_claims=1, notes="")


class TestFixture:
    def test_state_v1_deterministic(self):
        s1, s2 = build_state("state_v1"), build_state("state_v1")
        assert list(s1.keys()) == list(s2.keys())
        assert s1["balance_sheet"].equals(s2["balance_sheet"])
        # 各注册表根键的原始输入齐备
        for key in (
            "balance_sheet",
            "income_statement",
            "cash_flow_statement",
            "financial_indicators",
            "kline",
            "benchmark_kline",
        ):
            assert key in s1


class TestSeed:
    def test_seed_loads_and_wellformed(self):
        entries = load_entries()
        assert 30 <= len(entries) <= 60  # 种子集规模（30 份报告起点，随 bad case 扩充）
        meta = load_meta()
        assert meta.version
        assert meta.n_claims == len(entries)
        for e in entries:
            assert e.label_final in {"PASS", "FAIL", "UNVERIFIABLE"}
            assert build_state(e.state_key) is not None

    def test_seed_contains_adversarial_subsets(self):
        entries = load_entries()
        assert any("borderline" in e.subsets for e in entries)
        assert any("hedged" in e.subsets for e in entries)

    def test_compute_kappa_dual_labels(self):
        entries = load_entries()
        kappa = compute_kappa(entries)
        # 种子集 label_a/label_b 同源（synthetic-seed）→ kappa=1.0；人工双标后为真实值
        assert kappa is None or 0.0 <= kappa <= 1.0
