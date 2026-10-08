"""TDD tests for update-decision-integrity-gates Task 4 — FM 审批可见性 + 置信度语义。

Task 4.1：FM 上下文注入终稿完整性标注——final_price_check / final_inaction_check /
final_reeval_check / final_trigger_check（add-watch-trigger-tracking 追加）的 note
非空时进上下文（spec agent-node-contracts「FM 审批对象
完整性可见性」Scenario「FM 上下文携带完整性标注」；仲裁权保留：标注不禁止 approve）。
Task 4.2：报告「基金经理决策」节——先渲染「审批对象结构不完整标注」再渲染 FM 审批
意见（Scenario「报告并排渲染不完整标注与 FM 论断」；完整方案零增量，无空标注行）；
置信度漂移披露（spec「Fund Manager 操作性结论字段」MODIFIED Scenario「置信度漂移
披露」：FM approve 且与终稿 confidence 偏差 >0.15 → 标注含两值；reject/return 不产
漂移标注；≤0.15 无标注）。
"""

import json
from unittest.mock import patch

import pytest

from finance_agent.models import TradeDecision
from finance_agent.nodes.fund_manager import _build_fund_manager_context, fund_manager

# ── fixtures / helpers ──


def _decision(**overrides: object) -> dict:
    """终稿决策 dict（watch 完整申报形态）。"""
    base: dict = {
        "action": "watch",
        "confidence": 0.55,
        "reasoning": "终稿理由",
        "inaction_reason": "等待右侧信号",
        "reeval_triggers": ["放量站上 20 日线"],
    }
    base.update(overrides)
    return base


def _checks(
    price: str = "",
    inaction: str = "",
    reeval: str = "",
    trigger: str = "",
) -> dict:
    """终稿完整性检查 state 片段（note 默认空 = 全部通过无标注）。"""
    return {
        "final_price_check": {"result": "pass", "note": price},
        "final_inaction_check": {"result": "pass", "note": inaction},
        "final_reeval_check": {"result": "pass", "note": reeval},
        "final_trigger_check": {"result": "pass", "note": trigger},
    }


def _fm_report_state(
    decision: dict | TradeDecision,
    *,
    fm_decision: str = "approve",
    fm_action: str | None = "watch",
    fm_confidence: float | None = 0.8,
    reasoning: str = "FM 审批理由全文。",
    checks: dict | None = None,
) -> dict:
    """报告渲染用 state（FM 节相关字段齐备，600515 形态锚点）。"""
    state: dict = {
        "stock_code": "600515",
        "final_trade_decision": decision,
        "fund_manager_decision": fm_decision,
        "fund_manager_decision_reasoning": reasoning,
    }
    if fm_action is not None:
        state["fund_manager_action"] = fm_action
    if fm_confidence is not None:
        state["fund_manager_confidence"] = fm_confidence
    if checks:
        state.update(checks)
    return state


@pytest.fixture(autouse=True)
def _stub_focus_summary(monkeypatch):
    """研究聚焦摘要打桩（同 test_report_decision_render 手法：渲染测试不烧 LLM）。"""
    from finance_agent.nodes import report as report_mod

    monkeypatch.setattr(report_mod, "complete_text", lambda *a, **k: ("聚焦摘要（测试数据）", {}))


def _mock_fm_response(decision: str) -> str:
    payload: dict = {"decision": decision, "reasoning": "测试理由"}
    if decision.strip().lower() == "approve":
        payload["action"] = "watch"
        payload["confidence"] = 0.55
    return json.dumps(payload, ensure_ascii=False)


# ── Task 4.1：FM 上下文携带完整性标注 ──


class TestFMContextIntegrityNotes:
    """终稿三个 *_check 的 note 非空时进 FM 上下文（含标注原文）。"""

    def test_context_includes_inaction_check_note(self):
        """spec 锚点形态：watch 终稿 reeval_triggers 经打回后仍缺失——标注原文进上下文。"""
        state = {
            "final_trade_decision": _decision(),
            "return_count": 0,
            **_checks(inaction="已打回仍未申报：reeval_triggers"),
        }
        ctx = _build_fund_manager_context(state)
        assert "终稿完整性标注" in ctx
        assert "已打回仍未申报：reeval_triggers" in ctx

    def test_context_includes_trigger_check_note(self):
        """add-watch-trigger-tracking：watch 终稿触发位打回后仍缺——标注进 FM 上下文。"""
        state = {
            "final_trade_decision": _decision(),
            "return_count": 0,
            **_checks(trigger="已打回仍未申报触发位"),
        }
        ctx = _build_fund_manager_context(state)
        assert "终稿完整性标注" in ctx
        assert "触发位申报——已打回仍未申报触发位" in ctx

    def test_context_lists_all_three_labels(self):
        """三个检查都有标注时逐项列出（标签 + note 原文）。"""
        state = {
            "final_trade_decision": _decision(),
            "return_count": 0,
            **_checks(
                price="已打回仍未申报：entry_price",
                inaction="已打回仍未申报：inaction_reason",
                reeval="已打回仍未申报再评估触发条件",
            ),
        }
        ctx = _build_fund_manager_context(state)
        assert "价位——已打回仍未申报：entry_price" in ctx
        assert "非执行动作理由——已打回仍未申报：inaction_reason" in ctx
        assert "再评估触发条件——已打回仍未申报再评估触发条件" in ctx

    def test_no_notes_no_section(self):
        """全部检查通过（note 空）→ 不出现标注段（零增量，无空标注行）。"""
        state = {
            "final_trade_decision": _decision(),
            "return_count": 0,
            **_checks(),
        }
        ctx = _build_fund_manager_context(state)
        assert "终稿完整性标注" not in ctx

    def test_missing_check_keys_tolerated(self):
        """历史 state 无任何 *_check 键 → 不出标注段、不抛异常。"""
        ctx = _build_fund_manager_context({"final_trade_decision": _decision(), "return_count": 0})
        assert "终稿完整性标注" not in ctx

    @pytest.mark.parametrize(
        "checks",
        [
            {"final_price_check": "not-a-dict"},
            {"final_price_check": {"result": "pass", "note": 123}},
            {"final_price_check": {"result": "pass", "note": "   "}},
        ],
    )
    def test_note_shape_noise_tolerated(self, checks):
        """噪声形态（非 dict / note 非字符串 / 纯空白）静默跳过，不炸上下文构建。"""
        ctx = _build_fund_manager_context(
            {"final_trade_decision": _decision(), "return_count": 0, **checks}
        )
        assert "价位——" not in ctx

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_llm_prompt_carries_annotation(self, mock_llm):
        """端到端：发给 LLM 的 prompt 正文含标注原文。"""
        mock_llm.return_value = _mock_fm_response("approve")
        state = {
            "final_trade_decision": _decision(),
            "return_count": 0,
            **_checks(reeval="已打回仍未申报再评估触发条件"),
        }
        fund_manager(state)
        sent_prompt = mock_llm.call_args.args[0]
        assert "终稿完整性标注" in sent_prompt
        assert "已打回仍未申报再评估触发条件" in sent_prompt

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_approve_not_blocked_by_annotation(self, mock_llm):
        """spec AND 子句：上下文含标注不禁止 approve（仲裁权保留，可见性义务优先）。"""
        mock_llm.return_value = _mock_fm_response("approve")
        state = {
            "final_trade_decision": _decision(),
            "return_count": 0,
            **_checks(inaction="已打回仍未申报：reeval_triggers"),
        }
        result = fund_manager(state)
        assert result["fund_manager_decision"] == "approve"


class TestRulingFullFieldsInContext:
    """spec「审批对象进 FM 上下文」：完整字段（含仓位/价位/结构化理由）可见。

    对象/dict 两种形态的「含 action/confidence 的交易决策段」已由
    test_fund_manager.py::TestTradeDecisionVisibleToFM 锁定；此处补锁完整字段集。
    """

    def _decision_obj(self) -> TradeDecision:
        return TradeDecision.model_validate(
            {
                "action": "buy",
                "confidence": 0.55,
                "position_size": "light",
                "entry_price": 6.12,
                "stop_loss": 5.8,
                "target_price": 6.8,
                "reasoning": "r",
                "reeval_triggers": ["跌破 5.8 元止损离场"],
            }
        )

    def test_object_full_fields_in_context(self):
        ctx = _build_fund_manager_context(
            {"final_trade_decision": self._decision_obj(), "return_count": 0}
        )
        for fragment in (
            '"action": "buy"',
            '"confidence": 0.55',
            '"position_size": "light"',
            '"entry_price": 6.12',
            '"stop_loss": 5.8',
            '"target_price": 6.8',
            "跌破 5.8 元止损离场",
        ):
            assert fragment in ctx

    def test_dict_full_fields_in_context(self):
        ctx = _build_fund_manager_context(
            {
                "final_trade_decision": json.loads(self._decision_obj().model_dump_json()),
                "return_count": 0,
            }
        )
        assert '"entry_price": 6.12' in ctx
        assert "跌破 5.8 元止损离场" in ctx


# ── Task 4.2：报告「基金经理决策」节渲染 ──


class TestReportIntegrityAnnotation:
    """审批对象结构不完整标注：先渲染标注，再渲染 FM 审批意见（并排可见）。"""

    def test_annotation_rendered_before_fm_opinion(self):
        state = _fm_report_state(
            _decision(),
            reasoning="FM 认为执行安排完备。",
            checks=_checks(inaction="已打回仍未申报：reeval_triggers"),
        )
        md = _report_md(state)
        assert "审批对象结构不完整标注" in md
        assert "已打回仍未申报：reeval_triggers" in md
        # 顺序：标注在前，FM 审批意见在后；FM 论断不因标注被隐去
        assert md.index("审批对象结构不完整标注") < md.index("**审批通过**")
        assert "FM 认为执行安排完备。" in md

    def test_all_three_notes_rendered_with_labels(self):
        state = _fm_report_state(
            _decision(),
            checks=_checks(
                price="已打回仍未申报：entry_price",
                reeval="已打回仍未申报再评估触发条件",
            ),
        )
        md = _report_md(state)
        assert "价位——已打回仍未申报：entry_price" in md
        assert "再评估触发条件——已打回仍未申报再评估触发条件" in md

    def test_trigger_note_rendered_with_label(self):
        """add-watch-trigger-tracking：触发位不完整标注进报告（标签 + note 原文）。"""
        state = _fm_report_state(
            _decision(),
            checks=_checks(trigger="已打回仍未申报触发位"),
        )
        md = _report_md(state)
        assert "审批对象结构不完整标注" in md
        assert "触发位申报——已打回仍未申报触发位" in md

    def test_complete_plan_zero_increment(self):
        """方案完整（无标注）→ 维持现状形态，无标注块、无空标注行。"""
        md = _report_md(_fm_report_state(_decision()))
        assert "审批对象结构不完整标注" not in md
        assert "终稿完整性标注" not in md

    def test_resolved_notes_not_rendered_as_incomplete(self):
        """「打回后已申报」等复核性标注属完整方案——不渲染为「结构不完整」。"""
        state = _fm_report_state(
            _decision(),
            checks=_checks(price="打回后已申报", reeval="打回后已申报", trigger="打回后已申报"),
        )
        md = _report_md(state)
        assert "审批对象结构不完整标注" not in md

    def test_missing_check_keys_zero_increment(self):
        """历史 state 无 *_check 键 → 零增量，不抛异常。"""
        md = _report_md(_fm_report_state(_decision()))
        assert "审批对象结构不完整标注" not in md


class TestReportConfidenceDrift:
    """置信度漂移披露：approve 且偏差 >0.15 → 操作定性旁标注两值；其余不产标注。"""

    def test_600515_anchor_drift_annotated(self):
        """锚点形态：FM 0.8 vs 终稿 0.55（偏差 0.25）→ 标注含两个置信度值。"""
        md = _report_md(_fm_report_state(_decision(confidence=0.55), fm_confidence=0.8))
        assert "置信度漂移：FM 0.8 / 终稿 0.55" in md
        # FM reasoning 全文并排（供标注人判读差异是否合理）
        assert "FM 审批理由全文。" in md

    def test_drift_beside_qualifier_same_line(self):
        """漂移标注渲染在操作定性旁（同一行），不另起孤立段落。"""
        md = _report_md(_fm_report_state(_decision(confidence=0.55), fm_confidence=0.8))
        line = next(ln for ln in md.splitlines() if "置信度漂移" in ln)
        assert "操作定性" in line and "审批通过" in line

    def test_gap_within_threshold_no_annotation(self):
        """偏差 ≤0.15（0.6 vs 0.55）→ 无漂移标注。"""
        md = _report_md(_fm_report_state(_decision(confidence=0.55), fm_confidence=0.6))
        assert "置信度漂移" not in md

    def test_boundary_float_noise_no_annotation(self):
        """边界 0.15（0.7 vs 0.55）：浮点噪声（0.15000...2）不触发标注。"""
        md = _report_md(_fm_report_state(_decision(confidence=0.55), fm_confidence=0.7))
        assert "置信度漂移" not in md

    @pytest.mark.parametrize("fm_decision", ["reject", "return"])
    def test_non_approve_no_drift(self, fm_decision):
        """reject/return 不产漂移标注（无操作定性可比）。"""
        md = _report_md(
            _fm_report_state(
                _decision(confidence=0.55),
                fm_decision=fm_decision,
                fm_action=None,
                fm_confidence=None,
            )
        )
        assert "置信度漂移" not in md

    @pytest.mark.parametrize("fm_decision", ["reject", "return"])
    def test_non_approve_with_confidence_no_drift(self, fm_decision):
        """reject/return 即便带置信度（历史 state 兼容）也不产漂移标注。"""
        md = _report_md(
            _fm_report_state(
                _decision(confidence=0.55),
                fm_decision=fm_decision,
                fm_action=None,
                fm_confidence=0.9,
            )
        )
        assert "置信度漂移" not in md

    def test_missing_ruling_confidence_no_crash(self):
        """终稿无 confidence（历史 dict）→ 无标注、不抛异常。"""
        decision = {"action": "watch", "reasoning": "r"}
        md = _report_md(_fm_report_state(decision, fm_confidence=0.8))
        assert "置信度漂移" not in md


def _report_md(state: dict) -> str:
    from finance_agent.nodes.report import generate_report

    return generate_report(state)["final_report"]
