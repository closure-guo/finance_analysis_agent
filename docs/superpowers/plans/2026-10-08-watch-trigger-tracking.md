# add-watch-trigger-tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** watch 决策的双向触发位从自由文本升级为结构化字段（`trigger_high`/`trigger_low`），四处消费：终稿申报门禁、价位方向校验、K线图参考线、预测池落库 + 报告渲染。

**Architecture:** schema 宽松 + 规则节点必填（同 `inaction_reason`/`final_reeval_check` 先例）；结构化触发位校验并入 `check_decision_prices`（自动共用既有打回预算）；K线扩展 `_DECISION_LEVEL_KEYS` 同型；predictions 表幂等 ALTER 迁移（同 `_migrate_*_columns` 先例）。

**Tech Stack:** Python 3.12 / pydantic v2 / pytest / matplotlib / SQLite / React 18 + ECharts + vitest。

**Spec:** `openspec/changes/add-watch-trigger-tracking/`（proposal/specs/design/tasks）

## Global Constraints

- 工作目录：`.worktrees/watch-trigger-tracking`（worktree，不动主检出）
- 清洗 MUST NOT 抛异常：非数值/负值/0/NaN/不可解析字符串 → `None`，与 `_scrub_evidence_refs` 同哲学
- 打回预算全局一次：结构化触发位 anomaly 与文本价位 anomaly 共用 `decision_price_gate` 的一次打回，MUST NOT 各自打回
- watch 触发位缺失的终稿处置 = 打回一次 → 仍缺放行 + note「已打回仍未申报」，MUST NOT 死循环、MUST NOT 虚构数值
- 报告渲染：触发位缺失标「未申报」，MUST NOT 从 `reeval_triggers` 文本解析回填
- 快照冻结：`session_id`/`trigger_high`/`trigger_low` 写入 predictions 后禁止修改；存量行 NULL 不追溯
- commit 格式：`feat: [模块] 描述 (add-watch-trigger-tracking)`；禁 merge commit（PR 收口）
- 每任务完成跑该任务测试 + `uv run ruff check src/finance_agent tests`；全任务完成后跑全量验证

---

### Task 1: TradeDecision 触发位字段 + 宽松清洗

**Files:**
- Modify: `src/finance_agent/models.py`（TradeDecision，`exit_schedule` 字段后、`price_level_corrected` 前，约 :202）
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `TradeDecision.trigger_high: float | None`、`TradeDecision.trigger_low: float | None`（pydantic 字段，清洗后保证 `None` 或正 float）。后续所有任务消费这两个字段名。

- [ ] **Step 1: Write the failing test**

在 `tests/test_models.py` 追加（文件已有 TradeDecision 测试类/区段，跟随既有 import 方式）：

```python
class TestTradeDecisionTriggerLevels:
    """add-watch-trigger-tracking：watch 双向触发位宽松清洗。"""

    def _make(self, **kwargs):
        base = dict(
            action="watch", confidence=0.55, reasoning="测试",
            inaction_reason="观望", reeval_triggers=["站上 24.6 重估"],
        )
        base.update(kwargs)
        return TradeDecision(**base)

    def test_valid_triggers_preserved(self):
        d = self._make(trigger_high=24.6, trigger_low=22.91)
        assert d.trigger_high == 24.6
        assert d.trigger_low == 22.91

    def test_numeric_string_coerced(self):
        d = self._make(trigger_high="24.6", trigger_low=" 22.91 ")
        assert d.trigger_high == 24.6
        assert d.trigger_low == 22.91

    def test_noise_normalized_to_none(self):
        d = self._make(trigger_high=None, trigger_low="abc")
        assert d.trigger_high is None
        assert d.trigger_low is None

    def test_invalid_values_normalized_to_none(self):
        d = self._make(trigger_high=-1, trigger_low=0)
        assert d.trigger_high is None  # 负值
        assert d.trigger_low is None   # 0

    def test_bool_and_nan_rejected(self):
        d = self._make(trigger_high=True, trigger_low=float("nan"))
        assert d.trigger_high is None
        assert d.trigger_low is None

    def test_absent_fields_default_none(self):
        d = self._make()
        assert d.trigger_high is None
        assert d.trigger_low is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::TestTradeDecisionTriggerLevels -v`
Expected: FAIL（`TradeDecision` 无 `trigger_high` 字段 / extra field 忽略导致断言失败）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/models.py`：确认顶部有 `import math`（无则加）。在 `TradeDecision` 的 `exit_schedule: str | None = None` 之后加：

```python
    # add-watch-trigger-tracking：watch 双向触发位（上破/下破门槛）。宽松清洗同
    # _scrub_evidence_refs 哲学——噪声归 None 不炸管线；必填约束由 risk_judge
    # 终稿完整性检查承担（同 inaction_reason 先例），schema 保持宽松。
    trigger_high: float | None = None
    trigger_low: float | None = None

    @staticmethod
    def _coerce_trigger_level(value: object) -> float | None:
        """可解析数值字符串→float；None/bool/负值/0/非有限值/不可解析→None（未申报）。"""
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                return None
        if not isinstance(value, (int, float)):
            return None
        coerced = float(value)
        if not math.isfinite(coerced) or coerced <= 0:
            return None
        return coerced

    @field_validator("trigger_high", mode="before")
    @classmethod
    def _normalize_trigger_high(cls, value: object) -> object:
        return cls._coerce_trigger_level(value)

    @field_validator("trigger_low", mode="before")
    @classmethod
    def _normalize_trigger_low(cls, value: object) -> object:
        return cls._coerce_trigger_level(value)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS（含既有用例全绿）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/models.py tests/test_models.py
git commit -m "feat: [models] TradeDecision 新增 watch 双向触发位字段与宽松清洗 (add-watch-trigger-tracking)"
```

---

### Task 2: 结构化触发位方向校验（价位门禁）

**Files:**
- Modify: `src/finance_agent/metrics/decision_price_check.py`（`check_decision_prices` :541-590 内接入；新函数放 `empty_trigger` 检查 ：513-537 之后）
- Test: `tests/metrics/test_decision_price_check.py`

**Interfaces:**
- Consumes: Task 1 的 `TradeDecision.trigger_high/trigger_low`
- Produces: `check_decision_prices(decision, technical_indicators, price_levels, latest_close)` 返回列表**新增**结构化来源的 anomaly dict——字段键与既有 `empty_trigger` anomaly 完全同构（`kind`/`source_text`/`message` 等，实现前先读 ：513-537 的 dict 构造并镜像）。risk.py 门禁零改动即共用打回预算。

- [ ] **Step 1: Write the failing test**

在 `tests/metrics/test_decision_price_check.py` 追加（跟随该文件既有构造 decision/indicators 的辅助方式；若文件有 `make_decision` 类 fixture 则复用）：

```python
class TestStructuredTriggerLevels:
    """add-watch-trigger-tracking：结构化触发位空洞校验。"""

    def test_trigger_high_not_above_close_is_empty(self):
        decision = _make_decision(action="watch", trigger_high=22.61, trigger_low=22.0)
        anomalies = check_decision_prices(decision, {}, {}, latest_close=23.03)
        kinds = [a["source_text"] for a in anomalies]
        assert any("trigger_high" in s for s in kinds)

    def test_trigger_low_not_below_close_is_empty(self):
        decision = _make_decision(action="watch", trigger_high=25.0, trigger_low=24.6)
        anomalies = check_decision_prices(decision, {}, {}, latest_close=23.03)
        assert any("trigger_low" in a["source_text"] for a in anomalies)

    def test_valid_band_passes(self):
        decision = _make_decision(action="watch", trigger_high=24.6, trigger_low=22.91)
        assert check_decision_prices(decision, {}, {}, latest_close=23.03) == []

    def test_missing_triggers_pass(self):
        decision = _make_decision(action="watch", trigger_high=None, trigger_low=None)
        assert check_decision_prices(decision, {}, {}, latest_close=23.03) == []

    def test_no_latest_close_passes(self):
        decision = _make_decision(action="watch", trigger_high=24.6, trigger_low=22.91)
        assert check_decision_prices(decision, {}, {}, latest_close=None) == []
```

注意：`_make_decision` 换成该文件真实的 decision 构造辅助名（先读文件头 30 行确认；若直接构造则 `TradeDecision(action="watch", confidence=0.55, reasoning="x", inaction_reason="y", reeval_triggers=[], **kwargs)`）。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/metrics/test_decision_price_check.py::TestStructuredTriggerLevels -v`
Expected: FAIL（结构化字段无校验，返回 `[]`）

- [ ] **Step 3: Write minimal implementation**

`decision_price_check.py` 新函数（放在 empty_trigger 检查函数之后；anomaly dict 键 **必须镜像** ：513-537 既有 empty_trigger 的构造——先读该函数，把下面代码中的键名对齐成实际键名）：

```python
def _check_structured_trigger_levels(
    decision: TradeDecision, latest_close: float | None
) -> list[dict]:
    """结构化触发位方向校验（add-watch-trigger-tracking）。

    上破门槛须严格高于最新收盘、下破门槛须严格低于最新收盘；违反即空洞形态
    anomaly（与文本 empty_trigger 同构、同门禁）。不依赖文本解析；无收盘价直通。
    """
    if latest_close is None:
        return []
    anomalies: list[dict] = []
    for field, direction in (("trigger_high", "上破"), ("trigger_low", "下破")):
        value = getattr(decision, field, None)
        if value is None:
            continue
        violated = value <= latest_close if field == "trigger_high" else value >= latest_close
        if violated:
            anomalies.append(
                {
                    "kind": "empty_trigger",
                    "source_text": f"{field}={value}",
                    "message": (
                        f"结构化{direction}触发位 {value} 未{'高于' if field == 'trigger_high' else '低于'}"
                        f"最新收盘价 {latest_close}，触发条件在当前时点已满足，不构成有效门槛"
                    ),
                }
            )
    return anomalies
```

在 `check_decision_prices`（:541-590）内、文本 snippet 检查汇总处追加一行并入结果列表：

```python
    anomalies.extend(_check_structured_trigger_levels(decision, latest_close))
```

（`anomalies` 为该函数既有累计列表名，读实现后对齐变量名。）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/metrics/test_decision_price_check.py -v`
Expected: PASS（含既有用例全绿——若既有用例断言 `check_decision_prices` 精确返回值且 watch 决策带触发位，需核对无相互污染）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/metrics/decision_price_check.py tests/metrics/test_decision_price_check.py
git commit -m "feat: [metrics] 结构化触发位空洞校验并入价位门禁 (add-watch-trigger-tracking)"
```

---

### Task 3: 终稿完整性检查——watch 缺触发位打回一次

**Files:**
- Modify: `src/finance_agent/nodes/risk.py`（`final_reeval_check` 块 ：387-415 之后插入同款块；state 聚合点 grep `final_reeval_check` 的落 state 处）
- Test: `tests/nodes/test_risk.py`

**Interfaces:**
- Consumes: Task 1 字段；`call_llm_for_json`/`TradeDecision.model_validate`（既有重试机制）
- Produces: state 检查注记 `final_trigger_check: {"result": "pass"|"pass_with_note", "note": str}`（聚合方式镜像 `final_reeval_check` 的落 state 处）

- [ ] **Step 1: Write the failing test**

在 `tests/nodes/test_risk.py` 找到 `final_reeval_check` 的既有测试（`grep -n "final_reeval_check" tests/nodes/test_risk.py`），镜像其 mock 结构（stub `call_llm_for_json`）追加：

```python
def test_watch_missing_triggers_bounces_once_then_passes_with_note():
    """watch 终稿缺触发位：打回一次，补齐后放行（note=打回后已申报）。"""
    # 镜像 final_reeval_check 既有测试的 arrange：第一次返回缺触发位的 watch 决策，
    # 打回后返回带 trigger_high/trigger_low 的决策
    ...

def test_watch_missing_triggers_still_missing_after_retry_annotated():
    """打回后仍缺：放行 + note「已打回仍未申报触发位」，不虚构。"""
    ...

def test_buy_decision_unaffected_by_trigger_check():
    """buy/sell 终稿无触发位：final_trigger_check 不打回不标注。"""
    ...
```

（三个测试体在阅读既有 final_reeval_check 测试后按同一 mock 模式写实——mock 首次/重试两次 `call_llm_for_json` 返回值，断言 `final_trigger_check["result"]`/`["note"]` 与打回次数。）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_risk.py -k trigger -v`
Expected: FAIL（无 `final_trigger_check`）

- [ ] **Step 3: Write minimal implementation**

`risk.py` 在 `final_reeval_check` 块结束后（`_missing_inaction_after` 复核之后、`_apply_payout_self_check` 之前）插入：

```python
    # add-watch-trigger-tracking：watch 终稿双向触发位申报检查（同 final_reeval_check
    # 一次打回语义）。触发位是 watch 唯一的可执行承诺，必须结构化可追踪；缺失打回
    # 一次，仍缺放行 + 如实标注（MUST NOT 死循环/虚构）。buy/sell/hold 不约束。
    final_trigger_check: dict = {"result": "pass", "note": ""}
    if str(getattr(decision, "action", "")) == "watch" and (
        getattr(decision, "trigger_high", None) is None
        and getattr(decision, "trigger_low", None) is None
    ):
        retry_context = (
            f"{context}\n\n【触发位申报打回】watch 终稿必须结构化申报双向触发位"
            "（trigger_high=上破触发价，须严格高于最新收盘价；trigger_low=下破触发价，"
            "须严格低于最新收盘价），当前两者均缺失。"
            "可从风险辩论与再评估触发条件中的价位线索申报（如「站上 X 重估」→ trigger_high=X）。"
            "请重新输出补全 trigger_high/trigger_low 的完整决策 JSON。"
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
        if (
            getattr(decision, "trigger_high", None) is None
            and getattr(decision, "trigger_low", None) is None
        ):
            final_trigger_check["note"] = "已打回仍未申报触发位"
        else:
            final_trigger_check["note"] = "打回后已申报"
        # 重试使终稿换代，复核前序结论（不再触发新一轮打回，MUST NOT 死循环）
        _recheck_price_note_after_retry(decision, final_price_check, "触发位重试")
        if not decision.reeval_triggers:
            final_reeval_check["note"] = (
                final_reeval_check["note"] or "触发位重试后 reeval_triggers 为空（未再次打回，如实标注）"
            )
```

并把 `final_trigger_check` 加入 `final_reeval_check` 的 state 聚合点（grep 该文件中 `final_reeval_check` 写入 state/返回 dict 的位置，同型加一行）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_risk.py -v`
Expected: PASS（含既有用例全绿）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/risk.py tests/nodes/test_risk.py
git commit -m "feat: [risk] watch 终稿触发位申报检查——打回一次+如实标注 (add-watch-trigger-tracking)"
```

---

### Task 4: K线采集携带触发位 + PNG 参考线

**Files:**
- Modify: `src/finance_agent/charts.py`（:120 `_DECISION_LEVEL_KEYS`、:496-499 specs、:600 画线循环）
- Test: `tests/test_charts_kline_data.py`

**Interfaces:**
- Consumes: Task 1 字段（`_extract_decision_levels` 的 getattr 路径自动覆盖）
- Produces: `chart_data["price"]["decision_levels"]` dict 可能含 `trigger_high`/`trigger_low` 键（Task 8 前端消费）

- [ ] **Step 1: Write the failing test**

`tests/test_charts_kline_data.py` 找到决策位采集的既有用例（`grep -n "decision_levels" tests/test_charts_kline_data.py`）镜像追加：

```python
def test_collect_chart_data_carries_trigger_levels():
    """watch 决策 trigger_high/trigger_low 进 decision_levels（仅在场字段携带）。"""
    state = _make_state_with_decision(action="watch", trigger_high=24.6, trigger_low=22.91)
    data = collect_chart_data(state)
    assert data["price"]["decision_levels"]["trigger_high"] == 24.6
    assert data["price"]["decision_levels"]["trigger_low"] == 22.91

def test_collect_chart_data_without_triggers_omits_keys():
    state = _make_state_with_decision(action="buy", entry_price=10, stop_loss=9, target_price=12)
    data = collect_chart_data(state)
    assert "trigger_high" not in data["price"]["decision_levels"]
    assert "trigger_low" not in data["price"]["decision_levels"]
```

（`_make_state_with_decision` 换成该文件既有的 state 构造辅助；PNG 画线部分用 matplotlib 后端聚合断言或既有图像测试模式——若该文件只测数据不测渲染，画线逻辑由 Task 8 的前端 option 测试与人工验证覆盖，此处至少断言采集。）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_charts_kline_data.py -k trigger -v`
Expected: FAIL（`trigger_high` 不在采集键中）

- [ ] **Step 3: Write minimal implementation**

`charts.py`：

```python
# :120 扩展（_extract_decision_levels 自动覆盖新键）
_DECISION_LEVEL_KEYS = ("entry_price", "stop_loss", "target_price", "trigger_high", "trigger_low")

# :496-499 既有 _DECISION_LEVEL_SPECS 旁新增（虚线点型 + 独立配色，与入场/止损/目标可区分）
_TRIGGER_LEVEL_SPECS = (
    ("trigger_high", "上破触发", "#E67E22"),
    ("trigger_low", "下破触发", "#8E44AD"),
)
```

K线画线循环（:600 附近的 `for key, label, color in _DECISION_LEVEL_SPECS:` 之后）加第二循环：

```python
    for key, label, color in _TRIGGER_LEVEL_SPECS:
        if key in levels:
            ax.axhline(y=levels[key], color=color, linewidth=1.0, linestyle=":", alpha=0.9)
            ax.annotate(
                label,
                xy=(1.0, levels[key]),
                xycoords=("axes fraction", "data"),
                xytext=(3, 0),
                textcoords="offset points",
                fontsize=8,
                color=color,
                va="center",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_charts_kline_data.py tests/test_charts_none_series.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/charts.py tests/test_charts_kline_data.py
git commit -m "feat: [charts] K线采集与渲染 watch 双向触发位参考线 (add-watch-trigger-tracking)"
```

---

### Task 5: 报告渲染——触发位行 + 入池声明 + 数据真空提示

**Files:**
- Modify: `src/finance_agent/nodes/report.py`（`_format_trade_decision` :751 起、调用点 :561、cutoff 计算 :464）
- Test: `tests/nodes/test_report_decision_render.py`（决策渲染既有测试所在）

**Interfaces:**
- Consumes: Task 1 字段；`DEFAULT_HORIZON_DAYS`（`src/finance_agent/outcome/track_record/judgment.py:19`）
- Produces: `_format_trade_decision(decision, data_cutoff=None, fund_approved=False)` 新签名（默认参数保持旧调用兼容）

- [ ] **Step 1: Write the failing test**

`tests/nodes/test_report_decision_render.py` 追加（镜像该文件既有 decision 构造方式）：

```python
class TestWatchTriggerRendering:
    """add-watch-trigger-tracking：watch 触发位行/入池声明/数据真空提示。"""

    def _watch(self, **kw):
        base = dict(action="watch", confidence=0.55, reasoning="r",
                    inaction_reason="观望", reeval_triggers=["站上 24.6 重估"])
        base.update(kw)
        return TradeDecision(**base)

    def test_watch_renders_trigger_rows(self):
        md = _format_trade_decision(self._watch(trigger_high=24.6, trigger_low=22.91))
        assert "上破触发位: 24.6" in md
        assert "下破触发位: 22.91" in md

    def test_watch_missing_triggers_annotated_not_parsed(self):
        md = _format_trade_decision(self._watch())
        assert "上破触发位: 未申报" in md
        assert "下破触发位: 未申报" in md
        # MUST NOT 从 reeval_triggers 文本解析回填
        assert "24.6" not in md.split("上破触发位")[1].split("下破触发位")[0]

    def test_buy_does_not_render_trigger_rows(self):
        d = TradeDecision(action="buy", confidence=0.6, reasoning="r",
                          entry_price=10.0, stop_loss=9.0, target_price=12.0)
        md = _format_trade_decision(d)
        assert "上破触发位" not in md

    def test_pool_declaration_rendered_when_approved(self):
        md = _format_trade_decision(self._watch(trigger_high=24.6), fund_approved=True)
        assert "已入池跟踪" in md and "交易日窗口结算" in md

    def test_pool_declaration_absent_when_not_approved(self):
        md = _format_trade_decision(self._watch(trigger_high=24.6), fund_approved=False)
        assert "已入池跟踪" not in md

    def test_data_vacuum_notice_rendered(self):
        md = _format_trade_decision(
            self._watch(trigger_high=24.6),
            data_cutoff=date(2026, 9, 30),
            report_date=date(2026, 10, 8),
        )
        assert "数据真空" in md or "跳空缺口" in md
        assert "2026-09-30" in md

    def test_no_vacuum_notice_when_fresh(self):
        md = _format_trade_decision(
            self._watch(trigger_high=24.6),
            data_cutoff=date(2026, 10, 8),
            report_date=date(2026, 10, 8),
        )
        assert "跳空缺口" not in md
```

（`_format_trade_decision`/`TradeDecision`/`date` 的 import 跟随该文件既有方式；`report_date` 作为新可选参数注入便于测试，生产路径传 `date.today()`。）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_report_decision_render.py::TestWatchTriggerRendering -v`
Expected: FAIL（TypeError：未知参数 / 断言失败）

- [ ] **Step 3: Write minimal implementation**

`report.py`：

1. `_format_trade_decision` 签名改为：

```python
def _format_trade_decision(
    decision: TradeDecision | dict,
    data_cutoff: date | None = None,
    fund_approved: bool = False,
    report_date: date | None = None,
) -> str:
```

2. watch 分支（`inaction_reason` 行之后、`_fmt_reeval_triggers` 行 ：818 之前）插入触发位行——字段读取镜像该函数既有 dict/对象双形态模式（:771 getattr 与 ：785 dict.get）：

```python
    trigger_high = (
        getattr(decision, "trigger_high", None)
        if not isinstance(decision, dict)
        else decision.get("trigger_high")
    )
    trigger_low = (
        getattr(decision, "trigger_low", None)
        if not isinstance(decision, dict)
        else decision.get("trigger_low")
    )
    if action in ("watch", "hold"):
        lines.append(f"- **上破触发位**: {trigger_high if trigger_high is not None else '未申报'}")
        lines.append(f"- **下破触发位**: {trigger_low if trigger_low is not None else '未申报'}")
```

3. 入池声明（`fund_approved=True` 时）与真空提示（所有 action）：

```python
    if fund_approved:
        lines.append(
            f"- **跟踪**: 本决策已入池跟踪，按 {DEFAULT_HORIZON_DAYS} 交易日窗口结算，"
            "结算结果见战绩页"
        )
    if data_cutoff is not None and report_date is not None:
        vacuum_days = (report_date - data_cutoff).days
        if vacuum_days > _DATA_VACUUM_THRESHOLD_DAYS:
            lines.append(
                f"- ⚠ 数据真空提示：触发价位锚定 {data_cutoff.isoformat()} 收盘价，"
                f"期间 {vacuum_days} 个自然日无行情，跳空缺口可能使触发条件失真"
            )
```

模块级常量与 import：

```python
_DATA_VACUUM_THRESHOLD_DAYS = 3  # 行情截止与报告日最大可接受间隔（自然日）
from finance_agent.outcome.track_record.judgment import DEFAULT_HORIZON_DAYS
from datetime import date
```

4. 调用点 ：561 改为（cutoff 的字符串转 date——:464 的 `cutoff` 是 `render_date` 产物字符串 `YYYY-MM-DD`）：

```python
        sections.append(
            f"{next_title('交易决策')}\n{_format_trade_decision(
                decision,
                data_cutoff=_parse_cutoff_date(cutoff) if kline_df is not None else None,
                fund_approved=state.get("fund_manager_decision") == "approve",
                report_date=date.today(),
            )}\n"
        )
```

`_parse_cutoff_date` 小助手（字符串解析失败返回 None，不炸渲染）。变量作用域（kline_df/cutoff 是否在该作用域可见）以 :464 实际所在函数为准，实现时对齐。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_report_decision_render.py tests/nodes/test_report.py -v`
Expected: PASS（既有用例若因新行快照断言需更新，逐条核对——新增行属预期行为变更，MUST NOT 删弱既有断言）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/report.py tests/nodes/test_report_decision_render.py
git commit -m "feat: [report] watch 触发位行/入池声明/数据真空提示渲染 (add-watch-trigger-tracking)"
```

---

### Task 6: predictions 表迁移 + ingest 落库

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`（DDL :26-55、迁移注册 ：204-215、`insert_prediction` :739 起）
- Modify: `src/finance_agent/outcome/track_record/ingest.py`（:24-105）
- Test: `tests/outcome/`（该目录既有 model/ingest 测试文件）

**Interfaces:**
- Consumes: Task 1 字段
- Produces: predictions 行新增可空列 `session_id TEXT`/`trigger_high REAL`/`trigger_low REAL`；`persist_prediction_from_accumulated` 写入三者

- [ ] **Step 1: Write the failing test**

`tests/outcome/` 找 predictions 建表/插入既有测试文件（`grep -rln "insert_prediction\|_migrate" tests/outcome/`），镜像追加：

```python
def test_trigger_tracking_columns_migrated_and_written(tmp_path):
    """加列迁移幂等；ingest 写入 session_id 与触发位；存量语义 NULL 不回填。"""
    db = tmp_path / "pred.db"
    # 1) 用旧 schema 建表（或直接建新表）→ 跑迁移 → PRAGMA 断言三列存在
    conn = _connect(db)
    _migrate_trigger_tracking_columns(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    assert {"session_id", "trigger_high", "trigger_low"} <= cols
    # 2) 幂等：再跑一次不抛异常
    _migrate_trigger_tracking_columns(conn)

def test_ingest_persists_session_id_and_triggers(tmp_path, monkeypatch):
    # 镜像既有 ingest 测试的 accumulated fixture，decision 带 trigger_high=24.6/trigger_low=22.91
    pred = persist_prediction_from_accumulated(accumulated, session_id="sess_test", stock_code="600000", stock_name="浦发银行")
    row = _fetch_prediction(pred["prediction_id"], db_path=...)
    assert row["session_id"] == "sess_test"
    assert row["trigger_high"] == 24.6
    assert row["trigger_low"] == 22.91
```

（辅助函数名以该目录既有测试为准；`accumulated` fixture 里 `final_trade_decision` 换成带触发位的 watch 决策 dict。）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome -k "trigger or migrate" -v`
Expected: FAIL（无 `_migrate_trigger_tracking_columns`）

- [ ] **Step 3: Write minimal implementation**

`model.py`：

```python
# :204-209 迁移注册处追加一行 _migrate_trigger_tracking_columns(conn)
# :212 附近新增（完全镜像 _migrate_stage_c_columns 的幂等模式）：
_TRIGGER_TRACKING_COLUMNS = (
    ("session_id", "ALTER TABLE predictions ADD COLUMN session_id TEXT"),
    ("trigger_high", "ALTER TABLE predictions ADD COLUMN trigger_high REAL"),
    ("trigger_low", "ALTER TABLE predictions ADD COLUMN trigger_low REAL"),
)


def _migrate_trigger_tracking_columns(conn: sqlite3.Connection) -> None:
    """add-watch-trigger-tracking：补 session_id 关联列与 watch 触发位列（幂等）。"""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    for name, ddl in _TRIGGER_TRACKING_COLUMNS:
        if name not in existing:
            conn.execute(ddl)
```

同时把三列加进 ：26-55 的 CREATE TABLE DDL（新库直建）。`insert_prediction` 的 INSERT 列与参数绑定追加三字段（从 `record.get("session_id")`/`record.get("trigger_high")`/`record.get("trigger_low")`）。

`ingest.py` 的 record 构造（:74 附近）追加：

```python
        "session_id": session_id,
        "trigger_high": _decision_field(decision, "trigger_high"),
        "trigger_low": _decision_field(decision, "trigger_low"),
```

`_decision_field` 镜像该文件既有序列化/字段提取辅助（decision 可能是 dict 或 pydantic 对象——跟随 ：91-95 申报价位冻结处的既有取值模式，不新造机制）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome -v`
Expected: PASS（全目录绿）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py src/finance_agent/outcome/track_record/ingest.py tests/outcome/
git commit -m "feat: [track-record] predictions 补 session_id/触发位列并落库 (add-watch-trigger-tracking)"
```

---

### Task 7: trader.md 申报纪律 + prompt 发布

**Files:**
- Modify: `src/finance_agent/prompts/trader.md`（JSON 示例 ：13-15 区、watch 分型说明 ：49-68 区）
- Modify: `src/finance_agent/prompts/risk_judge.md`（若其中有决策 JSON 契约描述，同步字段——先 grep `reeval_triggers` 确认）

**Interfaces:**
- Consumes: Task 1-3 的行为语义（打回/空洞校验），prompt 只写纪律与方向语义

- [ ] **Step 1: Edit prompt（prompt 无单测，验证走 prompt-contract 测试与发布指纹）**

`trader.md` JSON 示例（:13-15 的 entry/stop/target 旁）追加：

```json
  "trigger_high": 24.6,
  "trigger_low": 22.91,
```

watch 分型说明（:49 附近「无需 entry_price/stop_loss/target_price」段）追加：

```markdown
  watch/hold 必须申报 trigger_high（上破触发价，MUST 严格高于最新收盘价）与
  trigger_low（下破触发价，MUST 严格低于最新收盘价）至少其一——双向触发位是
  watch 决策唯一的可执行承诺，系统会做方向交叉校验：上破价不高于现价或下破价
  不低于现价会被判空洞打回。reeval_triggers 文本继续承载完整语义（含非价位
  条件），trigger_high/trigger_low 是其机器可消费的价位子集，两者必须一致
  （文本写「站上 24.6 重估」→ trigger_high=24.6）。
```

- [ ] **Step 2: Run prompt contract tests**

Run: `uv run pytest tests/test_prompt_contracts.py tests/test_prompt_anchor_contract.py tests/test_trade_decision_prompts.py -v`
Expected: PASS（若合同测试枚举 JSON 字段集，需同步更新期望字段列表——属预期变更，如实更新）

- [ ] **Step 3: 发布 prompt 到 Langfuse**

```bash
uv run python scripts/deploy_prompts.py
```

Expected: 发布成功输出。若本机无 Langfuse env（凭证在 backend 容器 env），从容器取 env 后重试（`docker exec` 导出），仍不可行则**如实记录为待办 op 步骤**，不得假装已发布。

- [ ] **Step 4: Commit**

```bash
git add src/finance_agent/prompts/trader.md src/finance_agent/prompts/risk_judge.md
git commit -m "feat: [prompts] trader watch 触发位申报纪律 (add-watch-trigger-tracking)"
```

---

### Task 8: 前端 K线触发位参考线

**Files:**
- Modify: `frontend/src/types.ts`（`ChartData['price']['decision_levels']` 类型，grep `decision_levels`）
- Modify: `frontend/src/Charts.tsx`（`StockPriceChart` 的 markLine 构建，grep `decision_levels`/`markLine`）
- Test: `frontend/src/test/stockPriceKline.test.tsx`

**Interfaces:**
- Consumes: Task 4 的 `decision_levels` 新键 `trigger_high`/`trigger_low`
- Produces: 前端 K线渲染「上破触发」「下破触发」虚线（点线，与入场/止损/目标实虚可区分）

- [ ] **Step 1: Write the failing test**

`frontend/src/test/stockPriceKline.test.tsx` 追加（镜像该文件既有的 captured option 断言模式与 markLine 用例写法——先读既有「决策价位 markLine」用例）：

```tsx
it('renders trigger level markLines for watch decisions', () => {
  render(<StockPriceChart data={makeData({ trigger_high: 24.6, trigger_low: 22.91 })} />)
  const option = captured.at(-1) as any
  const markLineData = /* 镜像既有决策位用例的提取路径 */
  const triggers = markLineData.filter((d: any) =>
    ['上破触发', '下破触发'].includes(d?.label?.formatter ?? d?.name),
  )
  expect(triggers).toHaveLength(2)
  // 与入场/止损/目标参考线可区分：点线
  for (const t of triggers) expect(t.lineStyle?.type).toBe('dotted')
})
```

（`makeData` 换成该文件真实 fixture 名；提取路径镜像既有决策位 markLine 断言。）

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- stockPriceKline`
Expected: FAIL（无触发位 markLine）

- [ ] **Step 3: Write minimal implementation**

`types.ts`：`decision_levels` 类型若为显式键联合则加 `trigger_high?: number; trigger_low?: number`（`Record<string, number>` 则无需改）。
`Charts.tsx`：在决策位 markLine 映射处（entry/stop/target → 入场/止损/目标）加：

```ts
trigger_high: { label: '上破触发', color: '#E67E22', type: 'dotted' as const },
trigger_low: { label: '下破触发', color: '#8E44AD', type: 'dotted' as const },
```

（跟随该组件既有的 key→markLine 映射结构，不新造机制。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS（全量前端测试绿）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/Charts.tsx frontend/src/test/stockPriceKline.test.tsx
git commit -m "feat: [frontend] K线触发位参考线渲染 (add-watch-trigger-tracking)"
```

---

### Task 9: 全量验证 + 收口

**Files:**
- Modify: `openspec/changes/add-watch-trigger-tracking/tasks.md`（回填勾选）

- [ ] **Step 1: 后端全量**

```bash
uv run pytest -x -q          # 全绿（faulthandler 若卡 2% 先查 Docker/Langfuse 是否在跑）
uv run ruff check
uv run mypy
```

- [ ] **Step 2: 前端全量**

```bash
cd frontend && npm test && npm run build
```

- [ ] **Step 3: E2E 门禁处置（如实）**

本仓 §5.6 Playwright e2e/ 项目尚未建设（无 e2e/ 目录，P1-P4 未落地）。处置：前端交互契约已由 Task 8 vitest 覆盖；浏览器级验证归入人工验证（复跑 watch 标的看三处一致）。在 delta `tasks.md` 的 E2E 项下注明「E2E 基建未建（P1-P4 pending），以 vitest 契约 + 人工验证替代」，不得静默勾选。

- [ ] **Step 4: 端到端复跑（需后端在跑，操作前查 `GET /api/sessions` 无 running 会话）**

复跑一只 watch 标的（如 601066），核对：报告触发位行 / K线虚线 / predictions 行三处一致。容器环境不满足时如实记录为人工验证待办。

- [ ] **Step 5: 派发 final code-reviewer（全分支 diff）→ 修复循环 → PR**

```bash
gh pr create --title "feat: watch 触发位结构化——门禁/K线/报告/预测池四处消费 (add-watch-trigger-tracking)" --body "..."
```
