# require-watch-hold-rationale 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 watch/hold（非执行动作）决策结构化申报「不行动原因 + 再评估触发条件」，经两侧打回回路保证产出，报告结构化渲染，缺失时诚实标注。

**Architecture:** schema 保持宽松（`TradeDecision` 新增可选字段 + 噪声清洗），必填约束由规则节点承担——trader 侧走 `validate_trade_prices` 已有的一次打回回路（独立 attempts 计数），终稿侧走 `risk_judge` 的 `final_price_check` 同款一次重试回路；prompt 契约推动 LLM 产出，报告渲染结构化条目。与价位必填化（require-trade-price-declaration / extend-payout-self-check-coverage）完全同构。

**Tech Stack:** Python 3.14 / pydantic v2 / LangGraph / pytest / ruff / mypy

**Delta:** `openspec/changes/require-watch-hold-rationale/`（proposal / design / specs 已过 `--strict`）

## Global Constraints

- TDD 五步纪律：没有先写失败测试的代码 = 删除重写；每步「写测试→跑红→最小实现→跑绿→提交」
- schema 保持宽松：新字段可选、清洗 MUST NOT 抛异常中断管线（anchors 形态炸管线的教训）
- 回路语义固定：首次缺失 fail 打回一次 → 仍缺 pass + 如实标注，禁止死循环
- 字段名固定：`inaction_reason`（`str | None`）、`reeval_triggers`（`list[str]`）
- state 键固定：`inaction_rationale_check` / `inaction_rationale_feedback` / `inaction_rationale_attempts` / `final_inaction_check`
- 不动图结构（节点名 `validate_trade_prices`、所有边不变）、不动价检语义
- prompt 改动后必须 `uv run python scripts/deploy_prompts.py` 发布（否则 eval 门禁拒绝运行）
- 报告渲染用户可见行使用中文加粗标签；提交信息中文 + conventional 前缀（`feat:` / `test:` / `docs:`）
- 全量测试依赖 Docker/Langfuse 在线；卡 2% 先查环境再怀疑代码

---

### Task 1: TradeDecision 非执行动作字段与噪声清洗

**Files:**
- Modify: `src/finance_agent/models.py:191-224`（`TradeDecision`）
- Test: `tests/test_models.py`（文件末尾追加类；顶部已导入 `TradeDecision`）

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `TradeDecision.inaction_reason: str | None`（默认 None，纯空白归一为 None）、`TradeDecision.reeval_triggers: list[str]`（默认 []，str→单元素列表，None/非列表→[]，非 str 条目与纯空白条目丢弃）

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 末尾追加：

```python
class TestTradeDecisionInactionRationale:
    """require-watch-hold-rationale：非执行动作结构化理由字段与噪声清洗。"""

    def test_fields_default_none_and_empty(self):
        d = TradeDecision(action="watch", confidence=0.5, reasoning="r")
        assert d.inaction_reason is None
        assert d.reeval_triggers == []

    def test_reeval_triggers_single_string_to_list(self):
        d = TradeDecision(
            action="watch",
            confidence=0.5,
            reasoning="r",
            reeval_triggers="价格回落至 1500 以下",
        )
        assert d.reeval_triggers == ["价格回落至 1500 以下"]

    def test_reeval_triggers_none_and_other_types_to_empty(self):
        for raw in (None, 123, {"a": 1}):
            d = TradeDecision(
                action="hold", confidence=0.5, reasoning="r", reeval_triggers=raw
            )
            assert d.reeval_triggers == []

    def test_reeval_triggers_mixed_list_drops_non_str_and_blank(self):
        d = TradeDecision(
            action="watch",
            confidence=0.5,
            reasoning="r",
            reeval_triggers=["有效", 42, None, "  ", "第二条"],
        )
        assert d.reeval_triggers == ["有效", "第二条"]

    def test_blank_inaction_reason_normalized_to_none(self):
        d = TradeDecision(
            action="watch", confidence=0.5, reasoning="r", inaction_reason="   "
        )
        assert d.inaction_reason is None

    def test_buy_unaffected(self):
        d = TradeDecision(
            action="buy",
            confidence=0.8,
            reasoning="r",
            entry_price=1.0,
            stop_loss=0.9,
            target_price=1.2,
        )
        assert d.inaction_reason is None
        assert d.reeval_triggers == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_models.py::TestTradeDecisionInactionRationale -v`
Expected: FAIL —— `AttributeError: 'TradeDecision' object has no attribute 'reeval_triggers'`（pydantic v2 默认 ignore extra，未知 kwarg 被静默丢弃）

- [ ] **Step 3: 最小实现**

`src/finance_agent/models.py` 的 `TradeDecision` 类内，在 `evidence_refs` 字段后追加：

```python
    # require-watch-hold-rationale：非执行动作（watch/hold）结构化理由与再评估触发条件。
    # 必填约束由规则节点承担（同价位必填化先例），schema 保持宽松、清洗不抛异常。
    inaction_reason: str | None = None
    reeval_triggers: list[str] = Field(default_factory=list)

    @field_validator("inaction_reason", mode="before")
    @classmethod
    def _blank_inaction_reason_to_none(cls, value: object) -> object:
        """纯空白等同缺失（与 plain_conclusion 空值口径一致，但不抛异常）。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("reeval_triggers", mode="before")
    @classmethod
    def _normalize_reeval_triggers(cls, value: object) -> object:
        """LLM 形态噪声归一（同 anchors 先例）：str→单元素列表；
        None/非列表→[]；非 str 条目与纯空白条目丢弃（不字符串化，不抛异常）。"""
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [v for v in value if isinstance(v, str) and v.strip()]
        return []
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS（新类 6 例全绿 + 既有模型测试无回归）

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/models.py tests/test_models.py
git commit -m "feat(models): TradeDecision 增加非执行动作结构化理由字段与噪声清洗（require-watch-hold-rationale）"
```

---

### Task 2: 理由检查助手 + trader 侧回路 + 路由 + state 键

**Files:**
- Modify: `src/finance_agent/nodes/validate.py:151-279`（`validate_trade_prices` 拆包装 + 新助手）
- Modify: `src/finance_agent/routing.py:160-165`（`after_validate_trade_prices`）
- Modify: `src/finance_agent/state.py:113` 后（价位回路键区追加）
- Test: `tests/nodes/test_validate_trade_prices.py`（末尾追加两个类）

**Interfaces:**
- Consumes: Task 1 的 `TradeDecision.inaction_reason` / `.reeval_triggers`
- Produces: `inaction_rationale_missing(decision: object) -> list[str]`（接受 pydantic 对象或 dict；buy/sell 返回 []）；`validate_trade_prices(state) -> dict` 额外返回 `inaction_rationale_check`（`{result, reason?, note?}`）、fail 时含 `inaction_rationale_feedback: str` 与 `inaction_rationale_attempts: int`；`after_validate_trade_prices` 对 `inaction_rationale_check.result == "fail"` 返回 `"trader"`

- [ ] **Step 1: 写失败测试**

在 `tests/nodes/test_validate_trade_prices.py` 末尾追加：

```python
class TestInactionRationaleCheck:
    """require-watch-hold-rationale：watch/hold 结构化理由回路（trader 侧）。"""

    def test_watch_with_rationale_passes(self):
        plan = TradeDecision(
            action="watch",
            confidence=0.5,
            reasoning="r",
            inaction_reason="估值分位偏高且缺催化剂",
            reeval_triggers=["价格回落至 1500 以下", "季报毛利率低于 60%"],
        )
        out = validate_trade_prices(_state(plan))
        assert out["inaction_rationale_check"]["result"] == "pass"

    def test_watch_missing_rationale_fails_first_attempt(self):
        plan = TradeDecision(action="watch", confidence=0.5, reasoning="r")
        out = validate_trade_prices(_state(plan))
        assert out["inaction_rationale_check"]["result"] == "fail"
        assert out["inaction_rationale_attempts"] == 1
        fb = out["inaction_rationale_feedback"]
        assert "inaction_reason" in fb
        assert "reeval_triggers" in fb

    def test_hold_partial_missing_lists_only_missing(self):
        plan = TradeDecision(
            action="hold",
            confidence=0.5,
            reasoning="r",
            inaction_reason="维持仓位等待趋势确认",
        )
        out = validate_trade_prices(_state(plan))
        assert out["inaction_rationale_check"]["result"] == "fail"
        assert "reeval_triggers" in out["inaction_rationale_check"]["reason"]
        assert "inaction_reason" not in out["inaction_rationale_check"]["reason"]

    def test_second_attempt_still_missing_released_with_note(self):
        plan = TradeDecision(action="watch", confidence=0.5, reasoning="r")
        state = _state(plan)
        state["inaction_rationale_attempts"] = 1
        out = validate_trade_prices(state)
        assert out["inaction_rationale_check"]["result"] == "pass"
        assert "未申报" in out["inaction_rationale_check"]["note"]
        assert out["inaction_rationale_attempts"] == 1  # 不再递增

    def test_buy_gets_pass_and_price_unchanged(self):
        out = validate_trade_prices(_state(_plan()))
        assert out["price_check"]["result"] == "pass"
        assert out["inaction_rationale_check"]["result"] == "pass"

    def test_stale_fail_key_overwritten_for_buy(self):
        """上一轮 watch fail 后重出 buy：理由键必须被覆盖为 pass，防路由回跳。"""
        state = _state(_plan())
        state["inaction_rationale_check"] = {"result": "fail"}
        out = validate_trade_prices(state)
        assert out["inaction_rationale_check"]["result"] == "pass"

    def test_helper_accepts_dict_and_pydantic(self):
        from finance_agent.nodes.validate import inaction_rationale_missing

        as_dict = {"action": "watch", "confidence": 0.5, "reasoning": "r"}
        as_obj = TradeDecision(action="watch", confidence=0.5, reasoning="r")
        assert inaction_rationale_missing(as_dict) == ["inaction_reason", "reeval_triggers"]
        assert inaction_rationale_missing(as_obj) == ["inaction_reason", "reeval_triggers"]
        # dict 形态字符串 triggers 视为已申报（报告/历史对象兼容）
        partial = {"action": "hold", "inaction_reason": "等待", "reeval_triggers": "价格跌破 10"}
        assert inaction_rationale_missing(partial) == []


class TestInactionRationaleRouting:
    def test_rationale_fail_routes_back_to_trader(self):
        state = {
            "price_check": {"result": "pass"},
            "inaction_rationale_check": {"result": "fail"},
        }
        assert after_validate_trade_prices(state) == "trader"

    def test_both_pass_goes_forward(self):
        state = {
            "price_check": {"result": "pass"},
            "inaction_rationale_check": {"result": "pass"},
        }
        assert after_validate_trade_prices(state) == "risk_r1_entry"

    def test_price_fail_still_routes_back(self):
        state = {"price_check": {"result": "fail"}}
        assert after_validate_trade_prices(state) == "trader"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/nodes/test_validate_trade_prices.py -k "Inaction" -v`
Expected: FAIL —— `KeyError: 'inaction_rationale_check'` / `ImportError: cannot import name 'inaction_rationale_missing'`

- [ ] **Step 3: 最小实现**

3a. `src/finance_agent/nodes/validate.py`：把现有 `validate_trade_prices`（151 行起）**函数体原样**改名为 `_validate_price_levels`（docstring 原文保留，签名不变），在其上方新增：

```python
def inaction_rationale_missing(decision: object) -> list[str]:
    """非执行动作（watch/hold）缺失理由清单（require-watch-hold-rationale）。

    只查缺失、不做形态清洗（模型层负责）：inaction_reason 纯空白视为缺失；
    reeval_triggers 无有效条目视为缺失（str 形态视为已申报，兼容 dict 历史对象）。
    buy/sell 无要求（返回 []）。接受 pydantic 对象与 dict 两种形态。
    """
    if isinstance(decision, dict):
        action = str(decision.get("action") or "")
        reason = decision.get("inaction_reason")
        triggers = decision.get("reeval_triggers")
    else:
        action = str(getattr(decision, "action", "") or "")
        reason = getattr(decision, "inaction_reason", None)
        triggers = getattr(decision, "reeval_triggers", None)
    if action not in ("watch", "hold"):
        return []
    missing: list[str] = []
    if not (isinstance(reason, str) and reason.strip()):
        missing.append("inaction_reason")
    if isinstance(triggers, str):
        triggers = [triggers] if triggers.strip() else []
    if not (
        isinstance(triggers, list)
        and any(isinstance(t, str) and t.strip() for t in triggers)
    ):
        missing.append("reeval_triggers")
    return missing


def _inaction_rationale_check(plan: object, state: dict) -> dict:
    """非执行动作理由完整性检查（trader 侧）：缺一次打回，仍缺放行+如实标注。

    与价位检查同款一次重试语义（require-trade-price-declaration 先例），
    独立 attempts 计数，避免与价位回路互相消耗。
    """
    missing = inaction_rationale_missing(plan)
    if not missing:
        return {"inaction_rationale_check": {"result": "pass"}}
    attempts = int(state.get("inaction_rationale_attempts") or 0)
    if attempts < 1:
        reason = (
            "watch/hold 决策必须结构化申报不行动理由与再评估触发条件，"
            f"缺失：{'、'.join(missing)}"
        )
        return {
            "inaction_rationale_check": {"result": "fail", "reason": reason},
            "inaction_rationale_feedback": (
                f"非执行动作理由检查未通过：{reason}。"
                "请补全 inaction_reason（一句话，具体到当前不满足执行条件的点）与 "
                "reeval_triggers（1-3 条可观察、可判定的再评估触发条件）。"
            ),
            "inaction_rationale_attempts": attempts + 1,
        }
    return {
        "inaction_rationale_check": {
            "result": "pass",
            "note": (
                "已打回仍未申报非执行动作理由（watch/hold 必填），放行——"
                "报告按「未申报」渲染，不虚构内容"
            ),
        },
        "inaction_rationale_attempts": attempts,
    }


def validate_trade_prices(state: dict) -> dict:
    """校验 trader 方案：价位 sanity（原语义）+ 非执行动作理由完整性。

    require-watch-hold-rationale：watch/hold 的结构化理由缺失同样打回一次。
    两类检查动作互斥（buy/sell vs watch/hold），但理由键在所有路径统一补齐——
    防止上一轮 fail 状态滞留导致路由回跳。
    """
    updates = _validate_price_levels(state)
    plan = state.get("trader_plan") or {}
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump()
    updates.update(_inaction_rationale_check(plan, state))
    return updates
```

3b. `src/finance_agent/routing.py` 的 `after_validate_trade_prices` 整体替换为：

```python
def after_validate_trade_prices(state: dict) -> str:
    """价位/非执行动作理由 sanity 路由：pass/corrected 前行，任一 fail 打回 trader。"""
    check = state.get("price_check") or {}
    if check.get("result") == "fail":
        return "trader"
    rationale = state.get("inaction_rationale_check") or {}
    if rationale.get("result") == "fail":
        return "trader"
    return "risk_r1_entry"
```

3c. `src/finance_agent/state.py` 的 `price_check_attempts` 声明行（113 行）后追加：

```python
    # 非执行动作理由回路（require-watch-hold-rationale）：watch/hold 结构化理由缺失
    # 同款一次打回（独立计数，不与价位回路互相消耗）
    inaction_rationale_check: dict  # {result: pass|fail, reason?, note?}
    inaction_rationale_feedback: str  # fail 时打回 trader 的重出反馈
    inaction_rationale_attempts: int  # 理由检查已打回次数（<1 fail 打回；>=1 放行+标注）
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/nodes/test_validate_trade_prices.py tests/test_graph_5layer.py -v`
Expected: PASS（新增 10 例全绿；既有价位测试与图通道门禁无回归）

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/nodes/validate.py src/finance_agent/routing.py src/finance_agent/state.py tests/nodes/test_validate_trade_prices.py
git commit -m "feat(validate): 非执行动作理由检查回路与路由（watch/hold 缺理由打回一次）（require-watch-hold-rationale）"
```

---

### Task 3: trader 消费打回反馈

**Files:**
- Modify: `src/finance_agent/nodes/trader.py:88-90`（`price_check_feedback` 注入块之后）
- Test: `tests/nodes/test_trader.py`

**Interfaces:**
- Consumes: Task 2 的 `inaction_rationale_feedback` state 键
- Produces: trader context 新增段「非执行动作理由打回意见: …」（仅在键非空时注入）

- [ ] **Step 1: 写失败测试**

先查 `tests/nodes/test_trader.py` 既有 mock 模式（`call_llm_streaming` patch + `_build_trader_context` 直调），追加：

```python
class TestInactionFeedbackInjection:
    """require-watch-hold-rationale：理由打回意见注入 trader context。"""

    def test_feedback_injected_into_context(self):
        from finance_agent.nodes.trader import _build_trader_context

        ctx = _build_trader_context(
            {
                "analyst_reports": {},
                "inaction_rationale_feedback": (
                    "非执行动作理由检查未通过：缺失 inaction_reason、reeval_triggers"
                ),
            }
        )
        assert "非执行动作理由打回意见" in ctx
        assert "reeval_triggers" in ctx

    def test_absent_feedback_not_injected(self):
        from finance_agent.nodes.trader import _build_trader_context

        ctx = _build_trader_context({"analyst_reports": {}})
        assert "非执行动作理由打回意见" not in ctx
```

（若 `_build_trader_context` 名称不同，以 `trader.py` 中实际构建函数名为准——现为 `_build_trader_context`，见 88 行 `price_feedback = state.get("price_check_feedback")` 所在函数。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/nodes/test_trader.py -k "InactionFeedback" -v`
Expected: FAIL —— context 不含「非执行动作理由打回意见」

- [ ] **Step 3: 最小实现**

`src/finance_agent/nodes/trader.py`，在 `price_check_feedback` 注入块之后追加：

```python
    # 非执行动作理由打回意见（require-watch-hold-rationale：watch/hold 缺理由
    # fail 后重出时携带；非 fail 路径无此键，不注入）
    inaction_feedback = state.get("inaction_rationale_feedback")
    if inaction_feedback:
        sections.append(f"非执行动作理由打回意见: {inaction_feedback}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/nodes/test_trader.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/nodes/trader.py tests/nodes/test_trader.py
git commit -m "feat(trader): 消费非执行动作理由打回意见（require-watch-hold-rationale）"
```

---

### Task 4: 终稿侧回路（risk_judge）

**Files:**
- Modify: `src/finance_agent/nodes/risk.py:85-112`（`risk_judge` 内，价位完整性块之后）
- Modify: `src/finance_agent/state.py:178-180`（`final_price_check` 声明后）
- Test: `tests/nodes/test_risk.py`（新增类 + 更新既有 `test_watch_no_price_requirement`）

**Interfaces:**
- Consumes: Task 2 的 `inaction_rationale_missing`
- Produces: `risk_judge` 返回值新增 `final_inaction_check: dict`（`{result: "pass", note: ""}` / note="打回后已申报" / note="已打回仍未申报：…"）

- [ ] **Step 1: 写失败测试**

在 `tests/nodes/test_risk.py` 追加（沿用文件既有 `@patch("finance_agent.nodes._llm_utils.call_llm_streaming")` 与 `self._resp(...)` 模式）：

```python
class TestFinalInactionRationale:
    """require-watch-hold-rationale：终稿 watch/hold 理由完整性回路。"""

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_watch_with_rationale_no_extra_call(self, mock_llm):
        mock_llm.return_value = self._resp(
            action="watch",
            inaction_reason="估值分位偏高且缺催化剂",
            reeval_triggers=["价格回落至 1500 以下"],
        )
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 1
        assert result["final_inaction_check"] == {"result": "pass", "note": ""}

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_watch_missing_rationale_retries_then_completes(self, mock_llm):
        mock_llm.side_effect = [
            self._resp(action="watch"),
            self._resp(
                action="watch",
                inaction_reason="等待趋势确认",
                reeval_triggers=["价格站稳 60 日均线"],
            ),
        ]
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        assert result["final_inaction_check"] == {"result": "pass", "note": "打回后已申报"}

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_retry_exhausted_passes_with_note(self, mock_llm):
        mock_llm.return_value = self._resp(action="watch")
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        assert result["final_inaction_check"]["result"] == "pass"
        assert "已打回仍未申报" in result["final_inaction_check"]["note"]
        assert "inaction_reason" in result["final_inaction_check"]["note"]

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_buy_unaffected(self, mock_llm):
        mock_llm.return_value = self._resp(
            entry_price=26.35, stop_loss=25.3, target_price=28.0
        )
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 1
        assert result["final_inaction_check"] == {"result": "pass", "note": ""}
```

同时**更新既有测试** `TestFinalPriceIntegrity::test_watch_no_price_requirement`（227 行附近）：该用例的 watch mock 无理由字段，新回路会触发一次重试 → 改为携带理由字段、并断言 `final_inaction_check` 为 pass：

```python
    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_watch_no_price_requirement(self, mock_llm):
        mock_llm.return_value = self._resp(
            action="watch",
            inaction_reason="多因素均衡，等待信号",
            reeval_triggers=["关键指标显著变化"],
        )
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 1
        assert result["final_price_check"] == {"result": "pass", "note": ""}
```

注意：`self._resp(...)` 是 `TestFinalPriceIntegrity` 类内辅助方法——新类需自带 `_resp`（复制该辅助并支持 `inaction_reason`/`reeval_triggers` 透传），或把新测试放进同类。**本计划选择：新测试类内自带一个 `_resp` 副本**（与原类解耦）。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/nodes/test_risk.py -k "InactionRationale or watch_no_price" -v`
Expected: FAIL —— 返回值无 `final_inaction_check`；watch 无理由时 call_count 仍为 1

- [ ] **Step 3: 最小实现**

3a. `src/finance_agent/nodes/risk.py` 顶部 import 追加：

```python
from finance_agent.nodes.validate import final_price_missing, inaction_rationale_missing
```

3b. `risk_judge` 内，价位完整性块（`if _missing: ... retry ...` 结束）之后、赔率自检之前插入：

```python
    # 终稿非执行动作理由完整性（require-watch-hold-rationale）：watch/hold 缺理由
    # 首次打回重试一次；仍缺放行 + 如实标注（与 final_price_check 同款一次重试语义）
    final_inaction_check: dict = {"result": "pass", "note": ""}
    _missing_inaction = inaction_rationale_missing(decision)
    if _missing_inaction:
        retry_context = (
            f"{context}\n\n【非执行动作理由打回】watch/hold 终稿必须结构化申报不行动理由"
            f"与再评估触发条件，缺失：{'、'.join(_missing_inaction)}。"
            "请重新输出补全 inaction_reason（一句话，具体到当前不满足执行条件的点）与 "
            "reeval_triggers（1-3 条可观察、可判定的再评估触发条件）的完整决策 JSON。"
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
        _missing_inaction = inaction_rationale_missing(decision)
        if _missing_inaction:
            final_inaction_check["note"] = f"已打回仍未申报：{'、'.join(_missing_inaction)}"
        else:
            final_inaction_check["note"] = "打回后已申报"
```

3c. `risk_judge` 返回 dict 追加：

```python
        "final_inaction_check": final_inaction_check,
```

3d. `src/finance_agent/state.py` 的 `final_price_check` 声明后追加：

```python
    final_inaction_check: (
        dict  # 终稿非执行动作理由完整性（require-watch-hold-rationale）：{result, note}
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/nodes/test_risk.py tests/test_graph_5layer.py -v`
Expected: PASS（新类 4 例 + 既有全部无回归）

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/nodes/risk.py src/finance_agent/state.py tests/nodes/test_risk.py
git commit -m "feat(risk): 终稿非执行动作理由完整性打回回路（require-watch-hold-rationale）"
```

---

### Task 5: 报告渲染结构化条目

**Files:**
- Modify: `src/finance_agent/nodes/report.py:499-542`（`_format_trade_decision` + 新助手 `_fmt_reeval_triggers`）
- Test: `tests/nodes/test_report.py`（改写 `test_watch_no_price_rows_and_trigger_hint` + 新增两例）

**Interfaces:**
- Consumes: Task 1 的字段（pydantic 与 dict 两形态）
- Produces: 报告「交易决策」节 watch/hold 渲染 `- **不行动原因**: <值|未申报>` 与 `- **再评估触发条件**: ① …；② …`（无有效条目时 `未申报`）；替换旧占位行 `- **再评估触发条件**: 见理由`

- [ ] **Step 1: 写失败测试**

`tests/nodes/test_report.py`：把 `test_watch_no_price_rows_and_trigger_hint` 整体替换为：

```python
    def test_watch_missing_rationale_marked_unprovided(self):
        state = {
            "stock_code": "600519",
            "final_trade_decision": {
                "action": "watch",
                "confidence": 0.5,
                "position_size": "light",
                "entry_price": None,
                "stop_loss": None,
                "target_price": None,
                "reasoning": "等待站稳均线",
            },
        }
        md = generate_report(state)["final_report"]
        assert "watch" in md
        assert "- **不行动原因**: 未申报" in md
        assert "- **再评估触发条件**: 未申报" in md
        # 锚定渲染器特有的加粗标签行断言：watch/hold 不渲染硬价格行
        param_lines = [
            ln.strip()
            for ln in md.split("\n")
            if any(
                k in ln for k in ("**入场价**", "**止损价**", "**目标价**")
            )
        ]
        assert param_lines == []

    def test_watch_renders_structured_rationale(self):
        state = {
            "stock_code": "600519",
            "final_trade_decision": {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "等待站稳均线",
                "inaction_reason": "估值分位偏高且缺乏催化剂",
                "reeval_triggers": ["价格回落至 1500 以下", "季报毛利率低于 60%"],
            },
        }
        md = generate_report(state)["final_report"]
        assert "- **不行动原因**: 估值分位偏高且缺乏催化剂" in md
        assert "- **再评估触发条件**: ① 价格回落至 1500 以下；② 季报毛利率低于 60%" in md

    def test_watch_pydantic_decision_renders_structured_rationale(self):
        from finance_agent.models import TradeDecision

        state = {
            "stock_code": "600519",
            "final_trade_decision": TradeDecision(
                action="hold",
                confidence=0.6,
                reasoning="r",
                inaction_reason="维持仓位等待趋势确认",
                reeval_triggers=["价格跌破 1450"],
            ),
        }
        md = generate_report(state)["final_report"]
        assert "- **不行动原因**: 维持仓位等待趋势确认" in md
        assert "- **再评估触发条件**: ① 价格跌破 1450" in md
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/nodes/test_report.py -k "rationale or unprovided" -v`
Expected: FAIL —— 渲染仍是 `- **再评估触发条件**: 见理由`

- [ ] **Step 3: 最小实现**

3a. `src/finance_agent/nodes/report.py`，在 `_format_trade_decision` 上方新增：

```python
_TRIGGER_MARKS = "①②③④⑤⑥⑦⑧⑨⑩"


def _fmt_reeval_triggers(triggers: object) -> str:
    """再评估触发条件渲染：编号条目；无有效条目 → 未申报（require-watch-hold-rationale）。"""
    items: list[str] = []
    if isinstance(triggers, str):
        items = [triggers.strip()] if triggers.strip() else []
    elif isinstance(triggers, (list, tuple)):
        items = [t.strip() for t in triggers if isinstance(t, str) and t.strip()]
    if not items:
        return "未申报"
    parts = []
    for i, t in enumerate(items):
        mark = _TRIGGER_MARKS[i] if i < len(_TRIGGER_MARKS) else f"({i + 1})"
        parts.append(f"{mark} {t}")
    return "；".join(parts)
```

3b. `_format_trade_decision` 内：

- docstring 更新为：「buy/sell 渲染仓位+入场/止损/目标价（0/缺失「未提供」）；watch/hold 语义上无建仓参数，不渲染硬价格行，渲染结构化「不行动原因」与「再评估触发条件」（缺失如实标注「未申报」，require-watch-hold-rationale）。」
- pydantic 分支提取：

```python
        inaction = getattr(decision, "inaction_reason", None)
        triggers = getattr(decision, "reeval_triggers", []) or []
```

- dict 分支提取：

```python
        inaction = decision.get("inaction_reason")
        triggers = decision.get("reeval_triggers") or []
```

- `else` 分支（watch/hold）替换为：

```python
    else:
        lines.append(f"- **不行动原因**: {inaction if isinstance(inaction, str) and inaction.strip() else '未申报'}")
        lines.append(f"- **再评估触发条件**: {_fmt_reeval_triggers(triggers)}")
```

（旧行 `lines.append("- **再评估触发条件**: 见理由")` 删除。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/nodes/test_report.py -v`
Expected: PASS（3 例新/改写全绿 + 既有报告测试无回归）

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/nodes/report.py tests/nodes/test_report.py
git commit -m "feat(report): watch/hold 决策节渲染结构化不行动理由与再评估条件（require-watch-hold-rationale）"
```

---

### Task 6: prompt 契约 + 发布 + stub 同步

**Files:**
- Modify: `src/finance_agent/prompts/trader.md`（价位申报段之后 + JSON 示例区）
- Modify: `src/finance_agent/prompts/risk_judge.md`（「## 决策语义」价位继承行之后）
- Modify: `src/finance_agent/nodes/_llm_utils.py:58-63`（`_STUB_TRADE_DECISION`）
- Test: `tests/test_trade_decision_prompts.py`（追加类）、`tests/nodes/test_stub_contract_sync.py`（追加测试）

**Interfaces:**
- Consumes: Task 1 的字段名（prompt 为文本契约，无类型面）
- Produces: 两个 prompt 均含 `inaction_reason` / `reeval_triggers` 契约文本；stub hold 载荷携带两字段；Langfuse 已发布

- [ ] **Step 1: 写失败测试**

`tests/test_trade_decision_prompts.py` 末尾追加：

```python
class TestInactionRationalePromptContract:
    """require-watch-hold-rationale：prompt 必须声明非执行动作理由字段与必填义务。"""

    def test_trader_prompt_declares_fields_and_mandate(self):
        text = _load("trader.md")
        assert "inaction_reason" in text
        assert "reeval_triggers" in text
        assert "hold 或 watch" in text or ("hold" in text and "watch" in text)

    def test_risk_judge_prompt_inherits_mandate(self):
        text = _load("risk_judge.md")
        assert "inaction_reason" in text
        assert "reeval_triggers" in text
```

`tests/nodes/test_stub_contract_sync.py` 末尾追加：

```python
def test_stub_hold_carries_inaction_rationale():
    """require-watch-hold-rationale：stub hold 载荷须带结构化理由（E2E 报告结构化渲染）。"""
    payload = json.loads(_stub_pipeline_answer("trader"))
    assert payload.get("inaction_reason")
    assert payload.get("reeval_triggers")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_trade_decision_prompts.py::TestInactionRationalePromptContract tests/nodes/test_stub_contract_sync.py::test_stub_hold_carries_inaction_rationale -v`
Expected: FAIL —— prompt 文本与 stub 载荷均不含新字段

- [ ] **Step 3: 最小实现**

3a. `src/finance_agent/prompts/trader.md`：在价位申报段（「action 为 hold 或 watch 时无需价位（可省略或置 null）。」）之后追加：

```markdown
非执行动作结构化理由（watch/hold 必填）：action 为 watch 或 hold 时 MUST 结构化申报
inaction_reason（一句话，具体到当前不满足执行条件的点，如「估值分位偏高且缺乏催化剂」
「关键财务数据待季报验证」）与 reeval_triggers（1-3 条可观察、可判定的再评估触发条件，
如「价格回落至 1500 以下」「季报毛利率低于 60%」）；禁止空泛表述（如「等待好转」
「观察后续走势」）。系统会校验并打回缺失申报的方案。action 为 buy/sell 时两个字段无要求。
```

并在 JSON 示例区（buy 示例代码块之后）追加 watch 形态示例：

```markdown
watch/hold 形态示例（无价位，带结构化理由）：

```json
{
  "action": "watch",
  "confidence": 0.5,
  "reasoning": "决策理由",
  "inaction_reason": "估值分位偏高且缺乏催化剂",
  "reeval_triggers": ["价格回落至 1500 以下", "季报毛利率低于 60%"],
  "evidence_refs": [{"claim": "论据原文", "source": "fundamental"}]
}
```
```

3b. `src/finance_agent/prompts/risk_judge.md`：「## 决策语义」列表中，价位继承行之后追加：

```markdown
- 非执行动作理由继承：裁决为 hold/watch 时 MUST 结构化申报 inaction_reason（不行动依据）
  与 reeval_triggers（1-3 条可观察、可判定的再评估触发条件）——可基于风险辩论改写内容，
  但 MUST NOT 置空或省略；方向为 buy/sell 时两个字段无要求
```

3c. `src/finance_agent/nodes/_llm_utils.py` 的 `_STUB_TRADE_DECISION` 追加两键：

```python
_STUB_TRADE_DECISION: dict = {
    "action": "hold",
    "confidence": 0.6,
    "reasoning": "STUB 交易决策：多因素均衡，建议持有观察（测试数据）",
    # require-watch-hold-rationale：非执行动作结构化理由（同契约，E2E 报告结构化渲染）
    "inaction_reason": "STUB 不行动原因：多因素均衡（测试数据）",
    "reeval_triggers": ["STUB 触发条件：关键指标显著变化（测试数据）"],
    "evidence_refs": [],
}
```

3d. 发布 prompt（必须，eval 门禁依赖）：

Run: `uv run python scripts/deploy_prompts.py`
Expected: 两个 prompt 发布成功（Langfuse 在线；离线则记录待发布并在 eval 前补发）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_trade_decision_prompts.py tests/nodes/test_stub_contract_sync.py tests/test_pipeline_stub.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/prompts/trader.md src/finance_agent/prompts/risk_judge.md src/finance_agent/nodes/_llm_utils.py tests/test_trade_decision_prompts.py tests/nodes/test_stub_contract_sync.py
git commit -m "feat(prompts): trader/risk_judge 非执行动作结构化理由契约 + stub 同步 + 发布（require-watch-hold-rationale）"
```

---

### Task 7: 全量验证与收口

**Files:**
- 无代码改动（验证与文档收口）

**Interfaces:**
- Consumes: Task 1-6 全部产物
- Produces: 验证证据（全量测试输出 / ruff / mypy / openspec validate）+ tasks.md 勾选

- [ ] **Step 1: 全量测试（先确认 Docker/Langfuse 在线）**

Run: `docker compose ps`（确认 langfuse/db 在跑，离线先 `docker compose up -d`）
Run: `uv run pytest -q`
Expected: 0 failed（基线为改动前全绿数 + 新增用例数；若卡 2% 先查 Langfuse 连通再怀疑代码）

- [ ] **Step 2: lint / 类型**

Run: `uv run ruff check src/finance_agent/nodes/validate.py src/finance_agent/nodes/risk.py src/finance_agent/nodes/report.py src/finance_agent/nodes/trader.py src/finance_agent/models.py src/finance_agent/state.py src/finance_agent/routing.py`
Run: `uv run mypy src/finance_agent/nodes/validate.py src/finance_agent/nodes/risk.py src/finance_agent/nodes/report.py`
Expected: 触碰文件 0 新增问题（全仓既有 mypy 债务不属本任务）

- [ ] **Step 3: delta 校验与任务勾选**

Run: `openspec validate require-watch-hold-rationale --strict`
Expected: valid；随后回填 `openspec/changes/require-watch-hold-rationale/tasks.md` 勾选（真实链路验证 5.3 若环境不可用则如实标注待补）

- [ ] **Step 4: 真实链路验证（环境可用时）**

用真实后端跑一次 watch/hold 标的（或复用 P1 材料快照），确认：① 报告决策节出现结构化「不行动原因 / 再评估触发条件」；② 缺失场景渲染「未申报」；③ 打回回路日志（如有）。证据落 `tests/validation/2026-09-21-require-watch-hold-rationale-validation.md`。

- [ ] **Step 5: 提交收口**

```bash
git add openspec/changes/require-watch-hold-rationale/tasks.md tests/validation/2026-09-21-require-watch-hold-rationale-validation.md
git commit -m "docs(openspec): require-watch-hold-rationale 验证收口与 tasks 勾选"
```

---

## Self-Review 记录

- **Spec 覆盖**：agent-node-contracts 4 个 scenario → 噪声清洗（Task 1）、trader 侧打回/放行（Task 2）、终稿侧打回/放行（Task 4）、buy/sell 不受约束（Task 2/4 的 buy 用例）；report-decision-rendering 2 个 scenario → 结构化渲染（Task 5）+ 旧对象兼容（Task 5 第三例）。prompt 契约与发布（Task 6）覆盖 proposal 的 What Changes 第 4 条。
- **占位符扫描**：无 TBD/TODO；每个改动步骤含完整代码。
- **类型一致性**：`inaction_rationale_missing` 在 Task 2 定义、Task 4 消费（risk.py import 同行）；`final_inaction_check` 键在 Task 4 定义、state 声明同步；字段名 `inaction_reason` / `reeval_triggers` 在全部任务一致；报告助手 `_fmt_reeval_triggers` 仅在 Task 5 定义与使用。
- **已知测试改动点**：`tests/nodes/test_risk.py::TestFinalPriceIntegrity::test_watch_no_price_requirement`（Task 4 更新）、`tests/nodes/test_report.py::test_watch_no_price_rows_and_trigger_hint`（Task 5 改写）。
