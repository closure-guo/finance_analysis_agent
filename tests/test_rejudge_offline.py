"""fix-citation-contract-diseases 离线重判回归测试。

两层：
1. 归一化纯函数（词表/索引语义/行键展开/单位后缀还原）单元级钉子；
2. 全量 fixture 重判验收：FAIL == 5 且残量恰好为 5 条已证实的真幻觉
   （stated 值在来源序列中不存在）——契约疾病归零的回归网。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from rejudge_citation_offline import (  # noqa: E402
    FIXTURE_PATH,
    normalize_field_ref,
    rebuild_state,
    rejudge,
)

_HALLUCINATION_REFS = {
    "technical_indicators.MA.5.-6",
    "technical_indicators.MACD.histogram.-7",
    "technical_indicators.MACD.histogram.-39",
    "technical_indicators.RSI.14.-6",
    "technical_indicators.BOLL.upper.-1",
}


def _state() -> dict:
    return {
        "income_statement": pd.DataFrame(
            {"报告日": ["20251231", "20241231"], "营业总收入": [1.0, 0.9]}
        ),
        "financial_indicators": pd.DataFrame(
            {
                "日期": ["2025-12-31T00:00:00.000", "2024-12-31T00:00:00.000"],
                "每股净资产_调整前(元)": [4.7316, 4.1],
            }
        ),
        "quarterly_trend": {"quarters": ["2026Q2", "2026Q1"], "net_profit": [0.68, 0.38]},
    }


class TestNormalizeFieldRef:
    def test_chinese_root_mapped(self):
        assert (
            normalize_field_ref("利润表.20251231.营业总收入", _state())
            == "income_statement.20251231.营业总收入"
        )

    def test_events_root_mapped(self):
        assert normalize_field_ref("events[0].title", _state()) == "key_events[0].title"

    def test_technical_window_index_to_negative(self):
        assert (
            normalize_field_ref("technical_indicators.MA.5.59", _state())
            == "technical_indicators.MA.5.-1"
        )
        assert (
            normalize_field_ref("technical_indicators.MACD.DIF.54", _state())
            == "technical_indicators.MACD.DIF.-6"
        )

    def test_technical_out_of_window_unchanged(self):
        # 超出窗口语义的正索引（不可能来自 60 期窗口）不转换
        assert (
            normalize_field_ref("technical_indicators.MA.5.200", _state())
            == "technical_indicators.MA.5.200"
        )

    def test_year_rowkey_expanded_by_dataframe(self):
        out = normalize_field_ref("income_statement.2025.营业总收入", _state())
        assert out == "income_statement.20251231.营业总收入"
        # Timestamp ISO 串日期列 → date-only（无小数点，field_ref 语法安全）
        out2 = normalize_field_ref("financial_indicators.2025.每股净资产_调整前", _state())
        assert out2 == "financial_indicators.2025-12-31.每股净资产_调整前(元)"

    def test_year_not_in_dataframe_unchanged(self):
        assert normalize_field_ref("杜邦分析.L1.2025.ROE", _state()) == "dupont_tree.L1.2025.ROE"

    def test_unit_elided_column_restored(self):
        out = normalize_field_ref("financial_indicators.2025-12-31.每股净资产_调整前", _state())
        assert out.endswith("每股净资产_调整前(元)")

    def test_quarterly_label_to_index(self):
        assert (
            normalize_field_ref("quarterly_trend.net_profit.2026Q2", _state())
            == "quarterly_trend.net_profit.0"
        )
        assert (
            normalize_field_ref("quarterly_trend.yoy.2026Q1", _state()) == "quarterly_trend.yoy.1"
        )


class TestRebuildState:
    def test_date_columns_date_only(self):
        fixture = {
            "state": {
                "json": {},
                "dataframes": {
                    "financial_indicators": {
                        "日期": {"0": "2025-12-31T00:00:00.000"},
                        "x": {"0": 1.0},
                    }
                },
            }
        }
        state = rebuild_state(fixture)
        assert state["financial_indicators"]["日期"].iloc[0] == "2025-12-31"


class TestFullRejudge:
    """全量 fixture 重判验收（回归网：契约疾病归零，残量为已证实的真幻觉）。"""

    @pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="fixture 未生成")
    def test_contract_diseases_zero_residual_hallucinations_pinned(self):
        import json

        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        results, residual = rejudge(fixture)
        counts = {"PASS": 0, "FAIL": 0, "UNVERIFIABLE": 0}
        for r in results:
            counts[r.status] += 1
        # 契约疾病归零：FAIL 恰为 5 条真幻觉，引用集合逐一钉死
        assert counts["FAIL"] == 5, f"残量漂移: {[c['field_ref'] for c in residual]}"
        assert {c["field_ref"] for c in residual} == _HALLUCINATION_REFS
        assert counts["PASS"] + counts["FAIL"] + counts["UNVERIFIABLE"] == len(fixture["claims"])
