# 决策价位交叉校验门禁化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 决策文本价位交叉校验从「纯批注放行」升级为门禁——anomaly 打回重试一次，仍异常阻断交付（不进审批、不出报告、会话置 failed），报警只进 trace 不进报告。

**Architecture:** risk_judge 内新增第 4 个打回回路（复用既有三连打回模式），gate 结果落 `decision_price_gate`；`risk_judge → fund_manager` 无条件边改条件路由 `after_risk_judge`；报告侧删除 `_price_anomaly_notes` 渲染链；`_run_graph_streaming` 收尾对无报告结束置 failed + SSE error。

**Tech Stack:** Python 3.12 / LangGraph / pytest（unittest.mock.patch 桩 `finance_agent.nodes._llm_utils.call_llm_streaming`）

## Global Constraints

- 工作目录：worktree `D:\WorkSpace\finance_analysis_agent\.worktrees\decision-price-gate`（分支 `update-decision-price-gate`）
- spec：`openspec/changes/update-decision-price-gate/specs/`（price-level-tooling MODIFIED + pipeline-events ADDED），实现前先读
- 偏差阈值 2% 与两形态判定逻辑（`metrics/decision_price_check.py`）**不改**——本 delta 只改处置语义
- 打回重试**恰一次**，MUST NOT 死循环（与既有三回路同款）
- 不改 `src/finance_agent/prompts/*.md`（打回反馈在代码中构造，无需 deploy_prompts）
- 代码风格：snake_case + 中文注释（与周边一致）；commit 格式 `feat(scope): 中文描述`
- 红线：每任务先写失败测试（红）→ 最小实现（绿）→ 提交
- mypy/ruff 必须干净（仓库门禁）

---

### Task 1: state 声明 + risk_judge 价位交叉校验门禁回路

**Files:**
- Modify: `src/finance_agent/state.py:198-201`（`decision_price_anomalies` 注释修订 + 新增 `decision_price_gate`）
- Modify: `src/finance_agent/nodes/risk.py:225-248`（校验块替换为门禁回路）
- Modify: `src/finance_agent/metrics/decision_price_check.py:6,19-20,445-471`（docstring「纯观测」措辞改为门禁语义）
- Test: `tests/nodes/test_risk.py`（文件末尾新增 `TestDecisionPriceGate` 类）

**Interfaces:**
- Consumes: `check_decision_prices(decision, technical_indicators, price_levels, latest_close) -> list[dict]`（既有）；`_apply_payout_self_check`、`_recheck_price_note_after_retry`（既有）
- Produces: `risk_judge` 返回 dict 新增键 `decision_price_gate: dict`（`{"result": "pass"|"fail", "note": str}`，fail 时 note 含「已打回仍未通过」）；`decision_price_anomalies` 语义收窄为**最终终稿**残留 anomaly（修正后为 `[]`）

- [ ] **Step 1: Write the failing test**

在 `tests/nodes/test_risk.py` 文件末尾追加（import 区补 `from finance_agent.models import TradeDecision` 如缺失；`json`、`patch` 已有）：

```python
def _sell_decision_json(triggers: list[str]) -> str:
    """sell 终稿 JSON：结构化价位齐全（不触发既有三回路），变盘点在 triggers。"""
    return json.dumps(
        {
            "action": "sell",
            "confidence": 0.65,
            "position_size": "light",
            "entry_price": 640.0,
            "stop_loss": 700.0,
            "target_price": 571.0,
            "reasoning": "趋势走弱，减仓规避回撤",
            "reeval_triggers": triggers,
        },
        ensure_ascii=False,
    )


# 95 元为正式批实证形态（丢位幻觉）；570 为已验证近期低点（偏差 83.33% > 2% 阈值）
_BAD_TRIGGER = ["股价回落至 95 元附近再评估"]
_GOOD_TRIGGER = ["股价跌破 570 一线再评估"]
# price_levels 只给 entry_ref（兜底最新收盘 653.8）与近期低点/高点，不给参考带 → 无豁免
_PRICE_GATE_STATE = {
    "trader_plan": {"action": "sell", "confidence": 0.7},
    "risk_debate_history": [],
    "price_levels": {
        "available": True,
        "entry_ref": 653.8,
        "recent_low": 570.0,
        "recent_high": 940.0,
    },
}


class TestDecisionPriceGate:
    """update-decision-price-gate：价位交叉校验 anomaly → 打回重试一次 → 仍异常 gate fail。"""

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_anomaly_retry_fixed_passes(self, mock_llm):
        """偏差 anomaly（95 vs 570）→ 打回一次 → 修正后 gate pass、残留清空。"""
        mock_llm.side_effect = [
            _sell_decision_json(_BAD_TRIGGER),
            _sell_decision_json(_GOOD_TRIGGER),
        ]
        result = risk_judge(dict(_PRICE_GATE_STATE))
        assert mock_llm.call_count == 2
        gate = result["decision_price_gate"]
        assert gate["result"] == "pass"
        assert gate["note"] == "打回后已修正"
        assert result["decision_price_anomalies"] == []
        assert "570" in result["final_trade_decision"].reeval_triggers[0]

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_anomaly_persists_after_retry_fails_gate(self, mock_llm):
        """打回后仍输出 95 → gate fail（路由据此阻断），残留 anomaly 落 state。"""
        mock_llm.side_effect = [
            _sell_decision_json(_BAD_TRIGGER),
            _sell_decision_json(_BAD_TRIGGER),
        ]
        result = risk_judge(dict(_PRICE_GATE_STATE))
        assert mock_llm.call_count == 2
        gate = result["decision_price_gate"]
        assert gate["result"] == "fail"
        assert "已打回仍未通过" in gate["note"]
        assert len(result["decision_price_anomalies"]) == 1
        assert result["decision_price_anomalies"][0]["kind"] == "deviation"

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_no_anomaly_direct_pass(self, mock_llm):
        """触发价与已验证低点一致 → 不打回（LLM 恰调用 1 次），gate 直通。"""
        mock_llm.return_value = _sell_decision_json(_GOOD_TRIGGER)
        result = risk_judge(dict(_PRICE_GATE_STATE))
        mock_llm.assert_called_once()
        assert result["decision_price_gate"] == {"result": "pass", "note": ""}

    @patch("finance_agent.nodes.risk.check_decision_prices", side_effect=RuntimeError("boom"))
    def test_validator_crash_fails_open(self, _mock_check):
        """校验器自身异常 → fail-open 放行，gate pass，MUST NOT 阻断。"""
        with patch(
            "finance_agent.nodes._llm_utils.call_llm_streaming",
            return_value=_sell_decision_json(_BAD_TRIGGER),
        ):
            result = risk_judge(dict(_PRICE_GATE_STATE))
        assert result["decision_price_gate"]["result"] == "pass"
        assert "final_trade_decision" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_risk.py::TestDecisionPriceGate -v`
Expected: FAIL——`KeyError: 'decision_price_gate'`（直通用例）/ call_count 断言失败（打回用例）

- [ ] **Step 3: Write minimal implementation**

3a. `src/finance_agent/state.py` —— 将 198-201 行的注释与字段替换为：

```python
    # 决策文本价位交叉校验残留 anomaly（update-decision-integrity-gates Task 1 →
    # update-decision-price-gate 收窄）：保存 risk_judge **最终终稿**的残留 anomaly
    # （打回修正后为空列表），仅经 state/Langfuse trace 可观测，MUST NOT 渲染进报告
    decision_price_anomalies: list[dict]
    # 价位交叉校验门禁（update-decision-price-gate）：{result: pass|fail, note}——
    # anomaly 打回重试后修正放行（note「打回后已修正」）；仍异常 fail，
    # after_risk_judge 据此阻断（不进 FM 审批、不产出报告）
    decision_price_gate: dict
```

3b. `src/finance_agent/nodes/risk.py` —— 将 225-248 行（`# 决策文本价位交叉校验…` 注释起至 return 结束）替换为：

```python
    # 决策文本价位交叉校验门禁（update-decision-integrity-gates Task 1 →
    # update-decision-price-gate）：reeval_triggers/inaction_reason/reasoning 的
    # 自由文本价位 vs state 已验证技术指标。anomaly 非空 → 携明细定向打回重试一次 →
    # 重放 payout self-check → 复检；修正放行（note「打回后已修正」），仍异常 gate fail
    # （after_risk_judge 据此阻断，不进 FM 审批）。校验器自身异常 fail-open（放行 + 告警）。
    def _run_price_check(dec: TradeDecision) -> list[dict]:
        try:
            return check_decision_prices(
                dec,
                state.get("technical_indicators") or {},
                state.get("price_levels") or {},
                _latest_close_for_price_check(state),
            )
        except Exception:  # noqa: BLE001 -- fail-open：校验器自身异常不得阻断决策放行
            logger.warning("decision_price_check 执行失败（fail-open 放行）", exc_info=True)
            return []

    decision_price_anomalies = _run_price_check(decision)
    decision_price_gate: dict = {"result": "pass", "note": ""}
    if decision_price_anomalies:
        feedback = "；".join(
            str(a.get("message") or "") for a in decision_price_anomalies if isinstance(a, dict)
        )
        retry_context = (
            f"{context}\n\n【决策价位交叉校验打回】终稿自由文本价位与已验证技术指标冲突：{feedback}。"
            "请核对相关价位（以已验证指标值为准），修正后重新输出完整决策 JSON。"
        )
        data = call_llm_for_json(
            retry_context,
            system=system,
            api_key=api_key,
            node_name="risk_judge",
            llm_config=state.get("llm_config"),
            stock_code=state.get("stock_code"),
            prompt_name=_pinfo.prompt_name,
            prompt_version=_pinfo.prompt_version,
        )
        decision = TradeDecision.model_validate(data)
        decision_price_gate["note"] = "打回后已修正"
        # 重试换代重放 payout self-check（重试可能再引入自算赔率），计数合并不清零
        _reasoning2, _payout_fixed2, _payout_skipped2 = _apply_payout_self_check(
            decision.reasoning,
            decision.action,
            decision.entry_price,
            decision.stop_loss,
            decision.target_price,
        )
        if _payout_fixed2:
            decision = decision.model_copy(update={"reasoning": _reasoning2})
        _payout_fixed = _payout_fixed or _payout_fixed2
        _payout_skipped += _payout_skipped2
        # 重试换代复核价位完整性结论（I-1 模式：如实改注，不再打回，MUST NOT 死循环）
        _recheck_price_note_after_retry(decision, final_price_check, "价位交叉校验重试")
        decision_price_anomalies = _run_price_check(decision)
        if decision_price_anomalies:
            decision_price_gate["result"] = "fail"
            decision_price_gate["note"] = f"已打回仍未通过：{len(decision_price_anomalies)} 条残留"

    return {
        "final_trade_decision": decision,
        "payout_ratio_corrected": _payout_fixed,
        "payout_ratio_conflict_skipped": _payout_skipped,
        "final_price_check": final_price_check,
        "final_inaction_check": final_inaction_check,
        "final_reeval_check": final_reeval_check,
        "decision_price_anomalies": decision_price_anomalies,
        "decision_price_gate": decision_price_gate,
    }
```

3c. `src/finance_agent/metrics/decision_price_check.py` docstring 修订——第 6 行 `（纯观测，不参与路由）：` 改为 `（update-decision-price-gate 门禁化：调用方据 anomaly 打回重试/阻断）：`；19-20 行 `管线不中断由调用方保证（risk_judge 观测旁路 try/except），本模块保持纯函数、不改写决策。` 改为 `处置语义由调用方（risk_judge 门禁回路）保证：anomaly 非空 → 打回重试一次 → 仍异常阻断；校验器自身异常由调用方 fail-open。本模块保持纯函数、不改写决策。`；471 行 docstring 尾 `纯观测，调用方不得据此\n        中断管线。` 改为 `门禁语义：调用方据非空 anomaly 打回重试，\n        仍异常阻断交付（见 update-decision-price-gate spec）。`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_risk.py -v`
Expected: PASS（含既有 TestRiskJudge 全绿——既有用例无 price_levels → `_run_price_check` 返回 `[]` 直通）

再跑通道门禁：`uv run pytest tests/test_graph_5layer.py -v`（新增 state 键已声明，节点产出 ⊆ 声明）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/state.py src/finance_agent/nodes/risk.py src/finance_agent/metrics/decision_price_check.py tests/nodes/test_risk.py
git commit -m "feat(pipeline): 决策价位交叉校验门禁化——risk_judge 打回回路 + gate 落 state (update-decision-price-gate T1)"
```

---

### Task 2: after_risk_judge 条件路由 + 图接线

**Files:**
- Modify: `src/finance_agent/routing.py`（文件末尾追加 `after_risk_judge`）
- Modify: `src/finance_agent/graph.py:31-35`（import 区补 `after_risk_judge`）与 `:151`（无条件边改条件边）
- Test: Create `tests/test_after_risk_judge_routing.py`

**Interfaces:**
- Consumes: Task 1 的 `state["decision_price_gate"]`（`{"result": "pass"|"fail", "note": str}`，缺失/形态噪声视为放行）
- Produces: `after_risk_judge(state) -> str`（返回 `"__end__"` 或 `"fund_manager"`，LangGraph 条件路由函数）

- [ ] **Step 1: Write the failing test**

创建 `tests/test_after_risk_judge_routing.py`：

```python
"""TDD tests for after_risk_judge 门禁路由（update-decision-price-gate Task 2）。

gate fail → "__end__"（阻断：不进 FM 审批、不产出报告）；其余（pass/缺失/形态噪声）
→ "fund_manager"（fail-open 与管线既有容错风格一致）。
"""

from finance_agent.graph import build_5layer_graph
from finance_agent.routing import after_risk_judge


class TestAfterRiskJudgeRouting:
    def test_gate_fail_blocks_to_end(self):
        state = {"decision_price_gate": {"result": "fail", "note": "已打回仍未通过：1 条残留"}}
        assert after_risk_judge(state) == "__end__"

    def test_gate_pass_proceeds_to_fund_manager(self):
        state = {"decision_price_gate": {"result": "pass", "note": "打回后已修正"}}
        assert after_risk_judge(state) == "fund_manager"

    def test_gate_missing_or_malformed_defaults_to_fund_manager(self):
        assert after_risk_judge({}) == "fund_manager"
        assert after_risk_judge({"decision_price_gate": "garbage"}) == "fund_manager"
        assert after_risk_judge({"decision_price_gate": None}) == "fund_manager"

    def test_graph_wiring_replaces_unconditional_edge(self):
        """risk_judge → fund_manager 必须经条件路由（无条件边已移除）。"""
        graph = build_5layer_graph()
        edges = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("risk_judge", "fund_manager") in edges
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_after_risk_judge_routing.py -v`
Expected: FAIL with `ImportError: cannot import name 'after_risk_judge'`

- [ ] **Step 3: Write minimal implementation**

3a. `src/finance_agent/routing.py` 文件末尾追加：

```python
def after_risk_judge(state: dict) -> str:
    """决策价位交叉校验门禁路由（update-decision-price-gate）：gate fail 阻断交付——
    不进 FM 审批、不产出报告（会话终态由 API 收尾置 failed）；其余放行审批。
    gate 缺失/形态噪声视为放行（fail-open，与管线既有容错风格一致）。"""
    gate = state.get("decision_price_gate")
    if isinstance(gate, dict) and gate.get("result") == "fail":
        return "__end__"
    return "fund_manager"
```

3b. `src/finance_agent/graph.py:31-35` 的 routing import 列表补 `after_risk_judge`（保持字母序）；`:151` 的 `graph.add_edge("risk_judge", "fund_manager")` 替换为：

```python
    graph.add_conditional_edges("risk_judge", after_risk_judge)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_after_risk_judge_routing.py tests/test_graph_5layer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/routing.py src/finance_agent/graph.py tests/test_after_risk_judge_routing.py
git commit -m "feat(pipeline): after_risk_judge 条件路由——gate fail 阻断不进审批 (update-decision-price-gate T2)"
```

---

### Task 3: 报警退出交付物（report 渲染链移除 + FM 复核标注接入）

**Files:**
- Modify: `src/finance_agent/nodes/report.py:491,663-686,689-705,708-769`（删 `_price_anomaly_notes`，签名收窄，调用点同步）
- Modify: `src/finance_agent/nodes/fund_manager.py:16-22`（`FINAL_CHECK_LABELS` 追加 gate）
- Test: Modify `tests/nodes/test_report_decision_render.py:186-301`（`TestPriceAnomalyAnnotation` 整类替换为 `TestPriceAlarmNeverRendered`）；Modify `tests/nodes/test_fund_manager.py`（新增 gate 标注用例）

**Interfaces:**
- Consumes: Task 1 的 `decision_price_gate`（FM 经 `final_integrity_notes` 消费 note）
- Produces: `_format_trade_decision(decision)` / `_fmt_reeval_triggers(triggers)` 新签名（无 anomalies 参数）；`final_integrity_notes` 返回项含 `("决策价位校验", note)`

- [ ] **Step 1: Write the failing test**

1a. `tests/nodes/test_report_decision_render.py` —— 用以下类**整体替换** `TestPriceAnomalyAnnotation` 类（文件头 docstring 中 Task 3「同源标注」描述同步改为「update-decision-price-gate：报警仅进 trace，渲染链不接收 anomalies」）：

```python
class TestPriceAlarmNeverRendered:
    """update-decision-price-gate：报警信息属于内部 trace——报告 MUST NOT 渲染
    「价位待核实」类标注；渲染链签名不再接收 anomalies（阻断语义下报告只可能
    由无残留 anomaly 的终稿产出）。"""

    ANOMALY = {
        "kind": "deviation",
        "source_text": "价格回落至 1500 以下",
        "indicator": "近期低点",
        "verified_value": 1450.0,
        "deviation_pct": 3.45,
        "message": "文本价位 1500 与近期低点已验证值 1450 偏差 3.45%，价位待核实",
    }

    def test_rendering_chain_no_longer_accepts_anomalies(self):
        import inspect

        from finance_agent.nodes.report import _fmt_reeval_triggers, _format_trade_decision

        assert "anomalies" not in inspect.signature(_format_trade_decision).parameters
        assert "anomalies" not in inspect.signature(_fmt_reeval_triggers).parameters
        import pytest

        with pytest.raises(TypeError):
            _format_trade_decision(_watch_decision(), [self.ANOMALY])  # type: ignore[call-arg]

    def test_trigger_entry_rendered_without_annotation(self):
        decision = TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "r",
                "inaction_reason": "等待回落确认",
                "reeval_triggers": ["价格回落至 1500 以下", "跌破 1400 元离场"],
            }
        )
        md = _format_trade_decision(decision)
        assert "① 价格回落至 1500 以下" in md
        assert "价位待核实" not in md
        assert "② 跌破 1400 元离场" in md

    def test_sell_reasoning_rendered_without_annotation(self):
        decision = TradeDecision.model_validate(
            {
                "action": "sell",
                "confidence": 0.55,
                "reasoning": "股价跌破近期低点 26.28 支撑，趋势走弱",
                "entry_price": 26.0,
                "stop_loss": 27.5,
                "target_price": 24.0,
                "reeval_triggers": ["反弹至 27.5 元减仓"],
            }
        )
        md = _format_trade_decision(decision)
        assert "- **理由**: 股价跌破近期低点 26.28 支撑，趋势走弱" in md
        assert "价位待核实" not in md
```

> 注意：若 `_watch_decision()` 辅助工厂在该测试文件不存在，则按文件内既有用例的 dict 形态内联构造 watch 决策（字段同上第一个用例）。替换后删除文件顶部已无消费方的 anomaly 夹具 import。

1b. `tests/nodes/test_fund_manager.py` 新增（import 区补 `from finance_agent.nodes.fund_manager import final_integrity_notes` 如缺失）：

```python
def test_final_integrity_notes_includes_price_gate_note():
    """update-decision-price-gate：gate「打回后已修正」复核标注进 FM 上下文。"""
    state = {
        "final_price_check": {"result": "pass", "note": ""},
        "final_inaction_check": {"result": "pass", "note": ""},
        "final_reeval_check": {"result": "pass", "note": ""},
        "decision_price_gate": {"result": "pass", "note": "打回后已修正"},
    }
    notes = final_integrity_notes(state)
    assert ("决策价位校验", "打回后已修正") in notes


def test_final_integrity_notes_empty_gate_note_skipped():
    state = {
        "final_price_check": {"result": "pass", "note": ""},
        "final_inaction_check": {"result": "pass", "note": ""},
        "final_reeval_check": {"result": "pass", "note": ""},
        "decision_price_gate": {"result": "pass", "note": ""},
    }
    assert final_integrity_notes(state) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_report_decision_render.py tests/nodes/test_fund_manager.py -v`
Expected: FAIL——渲染链用例 `TypeError`/`价位待核实` 断言失败；FM 用例 `("决策价位校验", …) not in notes`

- [ ] **Step 3: Write minimal implementation**

3a. `src/finance_agent/nodes/report.py`：
- 删除 `_price_anomaly_notes` 函数整体（663-686 行）
- `:491` 改为 `f"{_format_trade_decision(decision)}\n"`
- `_fmt_reeval_triggers` 签名改 `def _fmt_reeval_triggers(triggers: object) -> str:`，`:704` 改 `parts.append(f"{mark} {t}")`，docstring 删 Task 3 标注描述
- `_format_trade_decision` 签名改 `def _format_trade_decision(decision: TradeDecision | dict) -> str:`，`:761` 改 `f"- **不行动原因**: {inaction}"`，`:767` 改 `lines.append(f"- **再评估触发条件**: {_fmt_reeval_triggers(triggers)}")`，`:769` 改 `lines.append(f"- **理由**: {reasoning}")`，docstring 删 `price_anomalies` 段

3b. `src/finance_agent/nodes/fund_manager.py` `FINAL_CHECK_LABELS` 追加一行：

```python
    ("decision_price_gate", "决策价位校验"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/ -v`
Expected: PASS 全绿

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/report.py src/finance_agent/nodes/fund_manager.py tests/nodes/test_report_decision_render.py tests/nodes/test_fund_manager.py
git commit -m "feat(report): 价位报警退出交付物——渲染链移除 + FM 复核标注接入 (update-decision-price-gate T3)"
```

---

### Task 4: 阻断终态可见化（API 收尾置 failed + SSE error）

**Files:**
- Modify: `src/finance_agent/api.py`（`_run_graph_streaming` 上方新增 `_blocked_failure_reason` 纯函数；图流 for 循环之后、`except` 之前插入收尾块）
- Test: Create `tests/test_api_blocked_terminal.py`

**Interfaces:**
- Consumes: Task 1/2 的 `decision_price_gate` / `decision_price_anomalies`（经 `accumulated`）
- Produces: `_blocked_failure_reason(accumulated: dict) -> tuple[str, str]`（返回 `(failure_reason, node_id)`，恒非 None——调用方仅在 `not report_sent` 时调用）

- [ ] **Step 1: Write the failing test**

创建 `tests/test_api_blocked_terminal.py`（DB 隔离夹具与 fake graph 形态镜像 `tests/test_api_failure_reason.py` 与 `tests/test_deep_trace_root.py` 既有模式）：

```python
"""TDD tests for 管线阻断终态可见化（update-decision-price-gate Task 4）。

管线正常结束但未产出报告（门禁阻断/勾稽 FAIL）→ 会话置 failed + failure_reason
+ SSE error 终态事件，MUST NOT 停留 running 等超时兜底。
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import _blocked_failure_reason, app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


class TestBlockedFailureReason:
    def test_price_gate_fail_maps_to_risk_judge(self):
        accumulated = {
            "decision_price_gate": {"result": "fail", "note": "已打回仍未通过：1 条残留"},
            "decision_price_anomalies": [
                {"kind": "deviation", "message": "文本价位 95 与 近期低点 已验证值 570 偏差 83.33%"}
            ],
        }
        reason, node_id = _blocked_failure_reason(accumulated)
        assert "决策价位交叉校验未通过" in reason
        assert "95" in reason
        assert node_id == "risk_judge"

    def test_validation_fail_maps_to_validate_node(self):
        reason, node_id = _blocked_failure_reason({"validation_result": "FAIL"})
        assert "勾稽校验失败" in reason
        assert node_id == "validate_financials"

    def test_unknown_absence_maps_to_unknown(self):
        reason, node_id = _blocked_failure_reason({})
        assert reason == "管线结束但未产出报告"
        assert node_id == "unknown"


class _FakeGraph:
    """单节点 scripted 图：yield 给定 chunks 后耗尽（模拟门禁阻断 → END）。"""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def stream(self, state, config=None, stream_mode=None):  # noqa: ARG002
        yield from self._chunks


def _gate_fail_chunks() -> list[Any]:
    return [
        (
            "updates",
            {
                "risk_judge": {
                    "final_trade_decision": {"action": "sell", "confidence": 0.65},
                    "decision_price_gate": {"result": "fail", "note": "已打回仍未通过：1 条残留"},
                    "decision_price_anomalies": [
                        {"kind": "deviation", "message": "文本价位 95 与 近期低点 已验证值 570 偏差 83.33%"}
                    ],
                }
            },
        )
    ]


def test_blocked_stream_marks_session_failed(isolated_db):
    """故障注入回归（评审建议固化）：stub 固定输出错误价位 → 运行 FAIL，不出报告。"""
    req_payload = {"stock_code": "600519", "query": "分析贵州茅台"}
    from finance_agent.api import AnalyzeRequest

    req = AnalyzeRequest(**req_payload)
    with TestClient(app):
        with patch("finance_agent.graph.build_5layer_graph", return_value=_FakeGraph(_gate_fail_chunks())):
            from finance_agent.api import _run_graph_streaming

            events = list(
                _run_graph_streaming(
                    stock_code="600519",
                    stock_name="贵州茅台",
                    req=req,
                    analysis_id="a1",
                    start_time=time.time(),
                )
            )
        payloads = [__import__("json").loads(e.removeprefix("data: ")) for e in events if e.startswith("data: ")]
        types = [p.get("type") for p in payloads]
        assert "report_ready" not in types
        errors = [p for p in payloads if p.get("type") == "error"]
        assert errors and "决策价位交叉校验未通过" in errors[-1]["message"]
        # 会话终态 failed 且可归因
        sid = payloads[0]["session_id"]
        detail = TestClient(app).get(f"/api/sessions/{sid}").json()
        assert detail["status"] == "failed"
        assert "决策价位交叉校验" in detail["failure_reason"]


def test_normal_completion_not_affected(isolated_db):
    """有报告的正常完成 → 照常 report_ready，MUST NOT 误标 failed。"""
    from finance_agent.api import AnalyzeRequest

    req = AnalyzeRequest(stock_code="600519", query="分析贵州茅台")
    report_md = "# 报告\n\n正文"
    chunks = [("updates", {"generate_report": {"final_report": report_md, "chart_data": {}}})]
    with TestClient(app):
        with patch("finance_agent.graph.build_5layer_graph", return_value=_FakeGraph(chunks)):
            from finance_agent.api import _run_graph_streaming

            events = list(
                _run_graph_streaming(
                    stock_code="600519",
                    stock_name="贵州茅台",
                    req=req,
                    analysis_id="a2",
                    start_time=time.time(),
                )
            )
        payloads = [__import__("json").loads(e.removeprefix("data: ")) for e in events if e.startswith("data: ")]
        types = [p.get("type") for p in payloads]
        assert "report_ready" in types
        assert "error" not in types
```

> 实施备注：`AnalyzeRequest` 的实际导入路径与必填字段以 `tests/test_deep_trace_root.py` 的既有构造为准镜像调整；`_sse` 前缀格式（`data: `）同该文件断言方式。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_blocked_terminal.py -v`
Expected: FAIL with `ImportError: cannot import name '_blocked_failure_reason'`

- [ ] **Step 3: Write minimal implementation**

3a. `src/finance_agent/api.py` —— 在 `_run_graph_streaming` 定义之前新增：

```python
def _blocked_failure_reason(accumulated: dict) -> tuple[str, str]:
    """无报告收尾的阻断归因（update-decision-price-gate）：返回 (failure_reason, node_id)。

    归因优先级：决策价位交叉校验门禁 fail > 勾稽校验 FAIL > 未产出报告兜底。
    调用方仅在图流正常耗尽且 report_sent 为 False 时调用。
    """
    gate = accumulated.get("decision_price_gate")
    if isinstance(gate, dict) and gate.get("result") == "fail":
        anomalies = accumulated.get("decision_price_anomalies") or []
        first = ""
        if anomalies and isinstance(anomalies[0], dict):
            first = str(anomalies[0].get("message") or "")
        return f"决策价位交叉校验未通过（打回重试后仍异常），报告阻断交付：{first}", "risk_judge"
    if accumulated.get("validation_result") == "FAIL":
        return "勾稽校验失败（硬等式不通过），管线阻断", "validate_financials"
    return "管线结束但未产出报告", "unknown"
```

3b. `_run_graph_streaming` 内，图流 `for mode, chunk in graph.stream(...)` 循环体结束后（8 空格缩进、仍在 `try:` 内、`except` 之前）插入：

```python
        # 管线阻断终态可见化（update-decision-price-gate）：图流正常耗尽但未产出报告
        # （决策价位门禁 fail / 勾稽 FAIL / 其他前置阻断）→ 置 failed + error 终态事件，
        # MUST NOT 停留 running 等超时兜底
        if not report_sent:
            reason, node_id = _blocked_failure_reason(accumulated)
            update_session_status(session_id, "failed", failure_reason=reason)
            yield _sse(
                {
                    "type": "error",
                    "node_id": node_id,
                    "session_id": session_id,
                    "message": reason,
                    "timestamp": _now(),
                }
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_blocked_terminal.py tests/test_api_failure_reason.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_blocked_terminal.py
git commit -m "feat(api): 管线阻断终态可见化——无报告收尾置 failed + SSE error (update-decision-price-gate T4)"
```

---

### Task 5: 全量验证 + validation 报告 + tasks 勾选

**Files:**
- Create: `tests/validation/2026-10-02-update-decision-price-gate-validation.md`
- Modify: `openspec/changes/update-decision-price-gate/tasks.md`（回填勾选）

**Interfaces:**
- Consumes: Task 1-4 全部产物
- Produces: 验证证据（命令输出摘要）+ validation 报告

- [ ] **Step 1: 全量门禁验证**

```bash
uv run ruff check
uv run mypy
uv run pytest
```

Expected: 三者全绿（0 failures / 0 errors）。注意：全量 pytest 需要 Langfuse 在线（Docker 栈）——若环境阻塞，如实记录受阻范围并至少跑齐 `uv run pytest tests/nodes tests/metrics tests/test_api_blocked_terminal.py tests/test_after_risk_judge_routing.py tests/test_graph_5layer.py tests/test_api_failure_reason.py tests/test_report_decision_render.py -v` 级别的全绿证据。

- [ ] **Step 2: 验证报告落 tests/validation/**

`tests/validation/2026-10-02-update-decision-price-gate-validation.md`：

```markdown
# 验证报告: update-decision-price-gate

**日期**: 2026-10-02
**关联 delta**: openspec/changes/update-decision-price-gate/
**变更类型**: 非交互类（纯后端逻辑 + 会话终态）→ 不适用 E2E 门禁

## 验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 故障注入：打回后修正放行 | tests/nodes/test_risk.py::TestDecisionPriceGate | ✅ |
| 故障注入：打回后仍异常 gate fail + 路由阻断 | 同上 + tests/test_after_risk_judge_routing.py | ✅ |
| 校验器 fail-open | tests/nodes/test_risk.py::TestDecisionPriceGate::test_validator_crash_fails_open | ✅ |
| 报警不渲染进报告 | tests/nodes/test_report_decision_render.py::TestPriceAlarmNeverRendered | ✅ |
| 阻断终态：会话 failed + failure_reason + SSE error | tests/test_api_blocked_terminal.py | ✅ |
| 正常完成路径不受影响 | tests/test_api_blocked_terminal.py::test_normal_completion_not_affected | ✅ |
| lint / 类型 / 全量回归 | ruff / mypy / pytest | （回填实际输出摘要） |

## 结论
[x] 全部通过
```

- [ ] **Step 3: 勾选 tasks.md 并提交**

勾选 `openspec/changes/update-decision-price-gate/tasks.md` 全部 6 项后：

```bash
git add tests/validation/2026-10-02-update-decision-price-gate-validation.md openspec/changes/update-decision-price-gate/tasks.md
git commit -m "docs(validation): 决策价位门禁化验证报告入库 + tasks 回填 (update-decision-price-gate T5)"
```
