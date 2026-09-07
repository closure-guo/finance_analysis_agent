"""surgical-citation-repair：单点修复模块单元测试（TDD）。

纯函数三件套（locate_sentence / build_repair_prompt / apply_repair）+
repair_claims LLM 封装（mock call_llm_for_json）。
"""

from finance_agent.citation import Claim
from finance_agent.nodes import citation_repair as cr

MD = (
    "## 基本面分析\n\n"
    "公司营收稳健增长。2023 年资产负债率为 99.0%，杠杆水平异常偏高。\n\n"
    "2024 年资产负债率为 40.0%，杠杆回落至合理区间。现金流状况良好。"
)


def _claim(stated=99.0, ref="solvency_metrics.资产负债率.2023", gt=38.0):
    return Claim(
        claim_type="numerical",
        source_type="data",
        field_ref=ref,
        stated_value=stated,
        interpretation="2023 年资产负债率为 99.0%",
    )


class TestLocateSentence:
    def test_finds_sentence_containing_wrong_number(self):
        s = cr.locate_sentence(MD, _claim())
        assert s is not None
        assert "99.0%" in s and "杠杆水平异常偏高" in s

    def test_multiple_hits_take_first(self):
        md = MD + "\n另注：99.0% 的口径为申报口径。"
        s = cr.locate_sentence(md, _claim())
        assert "杠杆水平异常偏高" in s

    def test_no_hit_returns_none(self):
        assert cr.locate_sentence("全文无相关数字。", _claim()) is None

    def test_prefers_interpretation_number_over_other_claims_number(self):
        # interpretation 说 99.0，正文 40.0 不该被误定位
        s = cr.locate_sentence(MD, _claim())
        assert "40.0%" not in s


class TestBuildRepairPrompt:
    def test_contains_sentence_truth_and_discipline(self):
        p = cr.build_repair_prompt(
            "2023 年资产负债率为 99.0%，杠杆偏高。", "前文。", "后文。", _claim(), 38.0
        )
        assert "99.0%" in p
        assert "38.0" in p
        assert "只改必要处" in p
        assert "repaired_sentence" in p  # JSON 输出契约

    def test_contains_direction_example_when_direction_delta_landed(self):
        p = cr.build_repair_prompt("句。", "", "", _claim(), 38.0)
        assert "direction=negative" in p


class TestApplyRepair:
    def test_replaces_first_occurrence(self):
        out = cr.apply_repair(MD, "杠杆水平异常偏高", "杠杆水平偏高但可控")
        assert out is not None and "杠杆水平偏高但可控" in out
        assert out.count("杠杆水平偏高但可控") == 1

    def test_missing_original_returns_none(self):
        assert cr.apply_repair(MD, "不存在的句子", "新句") is None

    def test_identical_replacement_returns_none(self):
        assert cr.apply_repair(MD, "杠杆水平异常偏高", "杠杆水平异常偏高") is None


class TestRepairClaims:
    def test_repairs_and_updates_markdown(self, monkeypatch):
        new_sentence = "2023 年资产负债率为 38.0%，杠杆水平异常偏高。"
        calls = []

        def fake_llm(*args, **kwargs):
            calls.append(kwargs)
            return {"repaired_sentence": new_sentence, "stated_value": 38.0}

        monkeypatch.setattr(cr, "call_llm_for_json", fake_llm)
        failures = [{"agent": "fundamental", "claim": _claim(), "ground_truth": 38.0}]
        md2, records = cr.repair_claims(MD, failures, llm_config=None)
        assert "38.0%，杠杆水平异常偏高" in md2 and "99.0%" not in md2
        assert len(calls) == 1
        assert calls[0]["node_name"] == "citation_repair"
        assert records and records[0]["repaired"] is True
        assert records[0]["ground_truth"] == 38.0
        assert records[0]["updated_claim"].stated_value == 38.0

    def test_llm_failure_skips_claim_without_crash(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("llm down")

        monkeypatch.setattr(cr, "call_llm_for_json", boom)
        failures = [{"agent": "fundamental", "claim": _claim(), "ground_truth": 38.0}]
        md2, records = cr.repair_claims(MD, failures, llm_config=None)
        assert md2 == MD
        assert records and records[0]["repaired"] is False

    def test_repair_output_without_sentence_contract_fails_gracefully(self, monkeypatch):
        monkeypatch.setattr(cr, "call_llm_for_json", lambda *a, **k: {"foo": "bar"})
        failures = [{"agent": "fundamental", "claim": _claim(), "ground_truth": 38.0}]
        md2, records = cr.repair_claims(MD, failures, llm_config=None)
        assert md2 == MD
        assert records and records[0]["repaired"] is False


class TestRepairBudget:
    """surgical-citation-repair 3.2：修复调用与分析师同口径（gateway usage 记账）。"""

    def test_llm_config_passthrough(self, monkeypatch):
        cfg = {"model": "test-model"}
        seen = {}

        def fake_llm(*args, llm_config=None, node_name=None, **kw):
            seen["llm_config"] = llm_config
            seen["node_name"] = node_name
            return {"repaired_sentence": "x", "stated_value": 1.0}

        monkeypatch.setattr(cr, "call_llm_for_json", fake_llm)
        cr.repair_claims(
            MD, [{"agent": "f", "claim": _claim(), "ground_truth": 38.0}], llm_config=cfg
        )
        assert seen["llm_config"] == cfg
        assert seen["node_name"] == "citation_repair"
