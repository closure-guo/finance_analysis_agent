# 校验器误报修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复决策价位校验器两个误报缺陷（VaR95 语境误读 + 复合回踩触发误判空洞），解除对正常决策的门禁误拦。

**Architecture:** 全部在 `metrics/decision_price_check.py` 纯函数层：词表两处追加 + `_check_snippet` 内同数值方向集合预扫与复合豁免。门禁回路/路由/报告链零改动。

**Tech Stack:** Python 3.12 / pytest

## Global Constraints

- 工作目录：worktree `D:\WorkSpace\finance_analysis_agent\.worktrees\fix-price-check-fp`（分支 `fix-decision-price-check-false-positives`）
- spec：`openspec/changes/fix-decision-price-check-false-positives/`（MODIFIED price-level-tooling）
- 偏差阈值 2%、门禁回路、路由、报告渲染**一律不动**
- 模块保持纯函数；中文注释、snake_case；TDD 先红后绿
- mypy 零新增 error（基线 81）

---

### Task 1: 校验器误报修复（词表 + 复合豁免）+ 688072 回归

**Files:**
- Modify: `src/finance_agent/metrics/decision_price_check.py`（`_NON_PRICE_KEYWORDS`、`_BREAKDOWN_WORDS`、`_check_snippet`）
- Test: `tests/metrics/test_decision_price_check.py`（文件末尾新增 `TestFalsePositiveFix688072` 类）

**Interfaces:**
- Consumes: 无（纯函数层自包含）
- Produces: `check_decision_prices` 行为变更——VaR 语境数值不进校验；同条目同数值 down+up 共现时不判 empty_trigger（deviation 不受影响）

- [ ] **Step 1: Write the failing test**

在 `tests/metrics/test_decision_price_check.py` 文件末尾追加（import 区确认已有 `check_decision_prices`、`TradeDecision`，缺则补）：

```python
class TestFalsePositiveFix688072:
    """fix-decision-price-check-false-positives：688072 重跑实证的两个误报回归。

    案例背景（incident 034 / trace 7f43b9c9…）：reasoning 的「VaR95单日6.6%」
    曾被误读为股价 95 vs 近期低点 570 偏差 83.33%；触发条件「回撤至610以下…
    站稳610」的回踩确认结构曾被句法命中上破模式判空洞，导致门禁误拦。
    """

    STATE = {
        "available": True,
        "entry_ref": 640.0,
        "recent_low": 570.0,
        "recent_high": 945.0,
        "stop_band_long": {"low": 570.0, "high": 605.0},
        "target_band_long": {"low": 500.0, "high": 560.0},
    }

    GEN1_TRIGGER = "价格回撤至610以下且连续5日收盘站稳610并缩量企稳（量化原610企稳条件）"
    GEN2_TRIGGER = (
        "价格有效回撤至近期低点570-605止损带区域（需实际跌破610后连续5日收盘"
        "站稳610之上且成交量萎缩，形成回踩确认的企稳结构，而非当前640价位下直接满足）"
    )
    VAR_REASONING = (
        "(1)以PEG口径论证86倍PE便宜依赖+1324%单期增速可外推，属'线性外推'；"
        "(2)VaR95单日6.6%不能证明'高波动来自上行弹性'，最大回撤30.37%是已实现极值。"
    )

    def _decision(self, trigger: str, reasoning: str) -> TradeDecision:
        return TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.6,
                "reasoning": reasoning,
                "inaction_reason": trigger,
                "reeval_triggers": [trigger],
            }
        )

    def test_var95_not_misread_as_price(self):
        """缺陷 A：VaR95 语境的 95 不再被当股价报偏差。"""
        anoms = check_decision_prices(
            self._decision(" MACD柱线重新翻正且MA5收复MA10 ".strip(), self.VAR_REASONING),
            {},
            self.STATE,
            640.0,
        )
        assert not [a for a in anoms if "95" in str(a.get("verified_value")) or "95" in a["message"]]

    def test_var_percent_and_chinese_forms_not_misread(self):
        """VaR(95% / 在险价值95 变体形态同样不误报。"""
        for reasoning in ("VaR(95%置信)下单日6.6%", "在险价值95口径下回撤可控"):
            anoms = check_decision_prices(
                self._decision("跌破近期低点570重估", reasoning), {}, self.STATE, 640.0
            )
            assert not [a for a in anoms if "95" in a["message"]], reasoning

    def test_compound_retest_trigger_gen1_not_empty(self):
        """缺陷 B：gen1 复合回踩（回撤至610…站稳610）不判空洞。"""
        anoms = check_decision_prices(
            self._decision(self.GEN1_TRIGGER, "观望等待回踩确认"), {}, self.STATE, 640.0
        )
        assert not [a for a in anoms if a["kind"] == "empty_trigger"]

    def test_compound_retest_trigger_gen2_not_empty(self):
        """缺陷 B：gen2 复合回踩（跌破610后站稳610之上）不判空洞。"""
        anoms = check_decision_prices(
            self._decision(self.GEN2_TRIGGER, "观望等待回踩确认"), {}, self.STATE, 640.0
        )
        assert not [a for a in anoms if a["kind"] == "empty_trigger"]

    def test_simple_breakout_still_empty(self):
        """护栏：单上破无下破语境（spec 场景）照常判空洞——豁免不得扩大化。"""
        anoms = check_decision_prices(
            self._decision("价格放量站上止损参考带上沿605", "等待企稳"), {}, self.STATE, 640.0
        )
        assert [a for a in anoms if a["kind"] == "empty_trigger"]

    def test_real_hallucinated_price_still_reported(self):
        """护栏：真幻觉价位（无 var 语境的裸 95）照常报偏差——修复只豁免风险度量语境。"""
        anoms = check_decision_prices(
            self._decision("目标价看到 95 元附近减仓", "技术形态走弱"), {}, self.STATE, 640.0
        )
        assert [a for a in anoms if a["kind"] == "deviation" and "95" in a["message"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/metrics/test_decision_price_check.py::TestFalsePositiveFix688072 -v`
Expected: FAIL——VaR 用例红于「95 偏差」anomaly 存在；gen1/gen2 红于 empty_trigger 存在（护栏用例 pass）

- [ ] **Step 3: Write minimal implementation**

3a. `_BREAKDOWN_WORDS` 替换为（追加两个回踩语境词，注释同步）：

```python
# 空洞形态方向词（spec：上破类「站上/突破/收复 X」/ 下破类「跌破/回落至 X」；
# 「放量突破」被「突破」覆盖；「站稳」为同族上破语义扩展；
# 「回撤至/回调至」为回踩语境同族下破词（fix-decision-price-check-false-positives，
# 688072 实证：缺失导致复合回踩触发的前半句无方向、后半句被误判空洞）
_BREAKDOWN_WORDS: tuple[str, ...] = ("跌破", "回落至", "失守", "回撤至", "回调至")
```

3b. `_NON_PRICE_KEYWORDS` 元组内 `"var"` 之前合适位置（保持字母序可读性不强制）追加两词，并在注释行同步说明：

```python
    "var",  # VaR95/VaR(95% 风险度量语境（fix-decision-price-check-false-positives：
    # 688072 实证 95 曾被误读为股价）
    "在险价值",
```

3c. `_check_snippet` —— 在 `for match in _NUM_RE.finditer(text):` 循环**之前**插入方向集合预扫，并在 empty_trigger 判定处加豁免：

```python
    # 复合回踩豁免（fix-decision-price-check-false-positives）：同一文本内同一数值
    # 同时出现下破语境与上破语境（「先跌破/回撤至 X，再站稳 X」）时，该数值的
    # 空洞判定跳过——两个子条件串联，整体是前瞻有效门槛，非当前时点已满足
    _value_dirs: dict[float, set[str]] = {}
    for m in _NUM_RE.finditer(text):
        s = (m.start(), m.end())
        if _overlaps(s, exclusions):
            continue
        v = float(m.group())
        if 0 < v < 1 or _non_price_context(text, s):
            continue
        d = _break_direction(text, s[0])
        if d is not None:
            _value_dirs.setdefault(v, set()).add(d)
```

empty_trigger 块改为（在 `if latest_close is not None:` 内、direction 计算后）：

```python
        if latest_close is not None:
            direction = _break_direction(text, span[0])
            is_empty = (direction == "up" and value <= latest_close) or (
                direction == "down" and value >= latest_close
            )
            dirs_of_value = _value_dirs.get(value, set())
            if is_empty and "up" in dirs_of_value and "down" in dirs_of_value:
                is_empty = False  # 复合回踩结构：down+up 共现，见函数头注释
```

（其余 anomaly 构造逻辑不变；docstring 补一句复合豁免说明。）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/metrics/test_decision_price_check.py -v`
Expected: PASS 全绿（新 6 用例 + 既有全部）

再跑受影响面：`uv run pytest tests/metrics/ tests/nodes/test_risk.py tests/test_after_risk_judge_routing.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/metrics/decision_price_check.py tests/metrics/test_decision_price_check.py
git commit -m "fix(metrics): 价位校验器两误报修复——VaR95 语境不读价 + 复合回踩触发豁免空洞 (fix-decision-price-check-false-positives T1)"
```

---

### Task 2: incident 034 文档 + 全量验证 + 工件入库

**Files:**
- Create: `docs/incidents/034-decision-price-check-false-positives-20261002.md`
- Modify: `docs/incidents/README.md`（索引追加一行）
- Create: `tests/validation/2026-10-02-fix-decision-price-check-false-positives-validation.md`
- Modify: `openspec/changes/fix-decision-price-check-false-positives/tasks.md`（回填）

- [ ] **Step 1: incident 034 文档**（内容要点：现象→取证链（trace id、两次 generation 时间戳、本地确定性复现）→根因（A/B 两缺陷）→**对回归评审原始诊断的更正**（「95 元幻觉」实为误报）→修复与回归→遗留（门禁自动阻断策略 owner 终裁挂起））。README 索引追加。

- [ ] **Step 2: 全量验证** `uv run ruff check`（干净）、`uv run mypy src/finance_agent`（=81 基线零新增）、`uv run pytest` 全量（唯一可接受失败：@live 环境项）；验证报告落 tests/validation/。

- [ ] **Step 3: 回填 tasks.md 勾选 + 提交全部工件**（含 delta 四工件与本计划）：

```bash
git add -A
git commit -m "docs(incident): 034 价位校验器误报归档 + 全量验证证据 + delta 工件 (fix-decision-price-check-false-positives T2)"
```
