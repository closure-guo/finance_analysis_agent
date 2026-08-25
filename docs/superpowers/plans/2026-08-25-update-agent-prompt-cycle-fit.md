# Update Agent Prompt Cycle Fit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使分析师提示词方法论与当前股市周期规律一致（阈值周期感知 + 技术钝化提示 + M1/M2 剪刀差），并给宏观数据管道加时效守卫（as_of_date + freshness）。

**Architecture:** 数据层在 `AKShareClient.fetch_macro_indicators`（akshare_client.py:483-518）为每指标追加 as_of_date/freshness 元数据（90 天界、各指标独立、解析失败 fail-safe 为 stale）；`nodes/analysts.py::_build_macro_context`（180-215 行）消费 freshness 并以确定性方式附加"数据滞后至 YYYY-MM"标注（不依赖 LLM 自觉）；3 个分析师 .md（fundamental/technical/macro）方法论改为周期感知表述。输出 JSON schema 与节点结构不变。

**Tech Stack:** Python 3.14、pytest、ruff、mypy、pandas DataFrames（akshare 返回）、Langfuse（prompt ver=3 发布）。

## Global Constraints

- 工作目录: `D:\WorkSpace\finance_analysis_agent`（执行时用 worktree），当前 main HEAD `7525aad`
- 测试命令: `uv run pytest <path> -v`；Lint: `uv run ruff check src tests`；类型: `uv run mypy src`
- **时效阈值 90 天**：freshness = (current_date - as_of_date).days ≤ 90 → fresh，否则 stale（spec/design 定稿，不得改）
- freshness 按**每指标独立计算**，不得统一标记（防"M2 新但 PMI 旧"被掩盖）
- as_of_date 从各指标首列（日期/月份字符串均可）解析；解析失败默认 stale + logger.warning（fail-safe 偏保守）
- **向后兼容**：fetch_macro_indicators 返回值只追加新键（as_of_date/freshness 挂结论层），records 列表结构不变；_build_macro_context 的 `records[:3]` 逻辑不变
- 提示词改动保留现有全部内容，只改「## 分析方法论」段的表述；中文、无 emoji
- 不改变 AnalystReport/TradeDecision JSON schema、state 字段、LangGraph 节点结构
- 提交信息遵循 `feat(prompts)/feat(data): ...` 风格，含 `(update-agent-prompt-cycle-fit)` 后缀

---

### Task 1: fetch_macro_indicators 时效守卫

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py:483-518`（`fetch_macro_indicators`）
- Test: `tests/test_macro_order_fix.py`（追加 `TestMacroFreshness` 类）

**Interfaces:**
- Consumes: 现有 `_call_ak`、`date`/`datetime` 已 import；`_safe_macro` 内部逻辑（只是扩充返回）
- Produces: `fetch_macro_indicators() -> dict[str, list[dict] | dict]` — 返回的每指标 dict 追加两项结论层键：`"as_of_date"`（该指标最新记录首列日期的 ISO 字符串）与 `"freshness"`（"fresh"|"stale"）。records 列表（键为指标名）结构与现有消费方（`_build_macro_context`、`test_macro_order_fix.py::TestFetchMacroIndicators`）保持兼容。

```python
# 返回结构（新）：
{
  "cpi": {
    "as_of_date": "2025-09-10", "freshness": "stale",
    "records": [ {原记录}, ... ]
  }
}
```

**设计细节（必须逐字遵守）**：
- 现结构 `result[key] = records`（list）；改为 `result[key] = {"as_of_date": ..., "freshness": ..., "records": records}`。**这改变了 records 的嵌套层级**——`nodes/analysts.py::_build_macro_context` 的 `for key, records in macro.items(): if isinstance(records, list)` 需要同步改为读 `records["records"]`（Task 2 处理）。tokens 修剪逻辑从 `records[:3]` 改为 `recs["records"][:3]`。
- as_of_date 解析：`records[0]` 的首列值（records 已按首列降序、index 0 最新）。值可能是 ISO date/datetime（已序列化为字符串）或月字符串如 `"2025年08月份"` / `"2025-08"`。用 `dateutil.parser.parse` 或正则提取 `\d{4}` 与 `\d{1,2}`；解析失败 → as_of_date=None、freshness="stale"、`logger.warning("macro %s as_of_date 解析失败，按 stale 处理", key)`。
- freshness 计算：`(datetime.now().date() - as_of_date).days > 90 → "stale"`，否则 `"fresh"`。
- 拉取失败（`_safe_macro` 返回空列表）→ 保持 `result[key] = []`（空列表），不套守卫壳——`_build_macro_context` 的 `if isinstance(records, list)` 分支正是为空列表兜底（Task 2 改后空列表仍走"数据暂不可用"分支）。

- [ ] **Step 1: Write the failing test**

在 `tests/test_macro_order_fix.py` 追加（文件已有 `_DESC_MONTHS`、`mock_ak` fixture）：

```python
class TestMacroFreshness:
    """fetch_macro_indicators 时效守卫：as_of_date + freshness。"""

    def _fresh_df(self):
        # 首列为"月份"字符串（akshare 真实格式：2026年07月份），第一条 = 本月
        cur = pd.Timestamp.now()
        m1 = f"{cur.year}年{cur.month:02d}月份"
        prev = (cur - pd.DateOffset(months=1))
        m2 = f"{prev.year}年{prev.month:02d}月份"
        return pd.DataFrame({"月份": [m1, m2], "制造业-指数": [50.2, 49.8]})

    def _stale_df(self):
        # 首列"月份"，最新一条距今 > 90 天
        old = pd.Timestamp.now() - pd.DateOffset(months=5)
        older = old - pd.DateOffset(months=1)
        return pd.DataFrame(
            {"月份": [f"{old.year}年{old.month:02d}月份",
                      f"{older.year}年{older.month:02d}月份"],
             "制造业-指数": [49.4, 49.1]}
        )

    def test_mark_fresh_and_stale_by_recency(self):
        import finance_agent.data.akshare_client as m
        orig = m._call_ak
        try:
            def fake_call(func, *a, **k):
                if func.__name__ == "macro_china_pmi":
                    return self._stale_df()
                return self._fresh_df()
            m._call_ak = fake_call
            client = AKShareClient()
            result = client.fetch_macro_indicators()
            assert result["pmi"]["freshness"] == "stale"
            assert result["m2"]["freshness"] == "fresh"
            assert result["cpi"]["freshness"] == "fresh"
            # as_of_date 解析出年份月份（stale 那条 = 5 个月前）
            assert result["pmi"]["as_of_date"].startswith(str((pd.Timestamp.now() - pd.DateOffset(months=5)).year))
        finally:
            m._call_ak = orig

    def test_failure_returns_empty_list(self):
        import finance_agent.data.akshare_client as m
        orig = m._call_ak
        try:
            m._call_ak = lambda func, *a, **k: None
            client = AKShareClient()
            result = client.fetch_macro_indicators()
            assert result["cpi"] == []
        finally:
            m._call_ak = orig
```

> 注意：`_call_ak` 是模块级函数（akshare_client.py:35），测试通过直接替换模块 attr 模拟真实调用链（不用 `@patch`，避免装饰器与模块级函数的绑定歧义）。测试意图：pmi 给 5 个月前的 df → stale；m2/cpi 给本月 df → fresh；`_call_ak` 返回 None → 空列表。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_macro_order_fix.py::TestMacroFreshness -v`
Expected: FAIL（`result["m2"]` 是 list 无 `["freshness"]` → TypeError/KeyError；失败原因符合"结构未变"）

- [ ] **Step 3: Write minimal implementation**

重写 `fetch_macro_indicators` 的 `_safe_macro` 内 records 组装代码（akshare_client.py:497-518 区域）：

```python
        def _safe_macro(key: str, func):
            df = _call_ak(func)
            if df is not None and not df.empty:
                df = df.sort_values(df.columns[0], ascending=False).reset_index(drop=True)
                records = df.head(6).to_dict(orient="records")
                for r in records:
                    for k, v in r.items():
                        if isinstance(v, (date, datetime)):
                            r[k] = v.isoformat()
                # ── 时效守卫：as_of_date + freshness（90 天界，各指标独立）──
                result[key] = _with_freshness(key, records)
            else:
                result[key] = []

        result = {}
        _safe_macro("cpi", ak.macro_china_cpi)
        _safe_macro("pmi", ak.macro_china_pmi)
        _safe_macro("m2", ak.macro_china_money_supply)
        _safe_macro("lpr", ak.macro_china_lpr)
        return result
```

并在类内新增 helper（放在 `fetch_macro_indicators` 方法前）：

```python
    @staticmethod
    def _with_freshness(key: str, records: list[dict]) -> dict:
        """为指标 records 附加 as_of_date + freshness。

        最新日期取自 records[0] 首列（已降序）；解析失败按 stale 处理（fail-safe）。
        """
        raw = records[0].get(next(iter(records[0])))  # 首列的键值
        as_of = None
        if isinstance(raw, str):
            import re
            m = re.search(r"(\d{4})[-年/.]?(\d{1,2})", raw)
            if m:
                try:
                    as_of = date(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    as_of = None
            else:
                as_of = None
        elif isinstance(raw, (date, datetime)):
            as_of = raw.date() if isinstance(raw, datetime) else raw
        if as_of is None:
            logger.warning("macro %s as_of_date 解析失败，按 stale 处理", key)
        days = (datetime.now().date() - as_of).days if as_of else 10**9
        return {
            "as_of_date": as_of.isoformat() if as_of else None,
            "freshness": "fresh" if days <= 90 else "stale",
            "records": records,
        }
```

> 确保 `next(iter(records[0]))` 取到首列（降序排序列）。若首列可能是非日期列（如"商品"），以实际 akshare 输出为准——CPI/PMI/M2/LPR 首列均为日期/月份列（实测确认）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_macro_order_fix.py -v`
Expected: PASS（TestMacroFreshness + 既有 TestFetchMacroIndicators/TestFetchIndicators 全过）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/data/akshare_client.py tests/test_macro_order_fix.py
git commit -m "feat(data): 宏观数据时效守卫 as_of_date+freshness (update-agent-prompt-cycle-fit)"
```

---

### Task 2: _build_macro_context 消费 freshness + 确定性滞后标注

**Files:**
- Modify: `src/finance_agent/nodes/analysts.py:180-215`（`_build_macro_context`）
- Test: `tests/test_macro_order_fix.py::TestBuildMacroContext`（更新既有用例 + 追加滞后标注用例）

**Interfaces:**
- Consumes: Task 1 的返回结构 `{"as_of_date", "freshness", "records"}`（空列表时不套壳）
- Produces: context 文本——每个指标追加一行时效标注（stale 时确定性附加，fresh 不打扰）；`json.dumps` 时用 trimmed 的 records 子集

- [ ] **Step 1: Write the failing test**

更新 `TestBuildMacroContext::test_macro_context_shows_newest_first` 适配新结构，并追加：

```python
    def test_macro_context_shows_newest_first(self):
        records = [
            {"月份": m, "全国-当月-同比增长": 10.0 + i * 0.1}
            for i, m in enumerate(_DESC_MONTHS[:6])
        ]
        state = {"macro_indicators": {"cpi": {
            "as_of_date": "2026-07-01", "freshness": "fresh", "records": records}}}
        context = _build_macro_context(state)
        payload = context.split("宏观经济指标（近3期）:\n", 1)[1]
        trimmed = json.loads(payload)
        assert [r["月份"] for r in trimmed["cpi"]] == _DESC_MONTHS[:3]

    def test_macro_context_marks_stale_indicators(self):
        """stale 指标须确定性附加"数据滞后"标注（不依赖 LLM 自觉）。"""
        records = [{"月份": "2025年08月份", "今值": 49.4}]
        state = {"macro_indicators": {"pmi": {
            "as_of_date": "2025-08-01", "freshness": "stale", "records": records}}}
        context = _build_macro_context(state)
        assert "pmi 数据滞后" in context
        assert "2025-08" in context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_macro_order_fix.py::TestBuildMacroContext -v`
Expected: FAIL（trimmed 结构变化导致 payload 解析失败 + stale 标注缺失）

- [ ] **Step 3: Write minimal implementation**

`_build_macro_context` 的 macro 段改为：

```python
    macro = state.get("macro_indicators") or {}
    if macro:
        # 只取最近 3 个月数据，减少 token 消耗；records 现挂在 "records" 键下（fetch 守卫结构）。
        trimmed = {}
        for key, value in macro.items():
            if isinstance(value, dict):
                recs = value.get("records") or []
                freshness = value.get("freshness")
                as_of = value.get("as_of_date")
                trimmed[key] = recs[:3]
                if freshness == "stale":
                    trimmed[f"{key} 数据滞后"] = f"最新至 {as_of or '未知日期'}，请按滞后数据处理并降级结论"
            else:
                trimmed[key] = value
        sections.append(
            f"宏观经济指标（近3期）:\n{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("宏观经济指标: 数据暂不可用")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_macro_order_fix.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/analysts.py tests/test_macro_order_fix.py
git commit -m "feat(prompts): macro context 消费 freshness 并确定性标注滞后 (update-agent-prompt-cycle-fit)"
```

---

### Task 3: 分析师提示词周期感知表述

**Files:**
- Modify: `src/finance_agent/prompts/fundamental_analyst.md`（「## 分析方法论」段）
- Modify: `src/finance_agent/prompts/technical_analyst.md`（「## 分析方法论」段）
- Modify: `src/finance_agent/prompts/macro_analyst.md`（「## 分析方法论」段）
- Modify: `tests/test_prompt_contracts.py`（追加断言）

**Interfaces:**
- Consumes: tests/test_prompt_contracts.py 已有 `_load`、`_PROMPTS_DIR`
- Produces: 三个 .md 的方法论语段更新为周期感知表述；契约测试追加新断言

- [ ] **Step 1: Write the failing test**

`tests/test_prompt_contracts.py` 追加（文件末尾，`TestReportSummaryGrounding` 之后或类内追加方法）：

```python
class TestCycleFitMethodology:
    """周期适配方法论契约（update-agent-prompt-cycle-fit）。"""

    def test_fundamental_relative_and_cycle_aware(self):
        text = _load("fundamental_analyst.md")
        assert "同业" in text
        assert "周期" in text or "环境" in text

    def test_technical_mandates_rsa_blunting_in_strong_trend(self):
        text = _load("technical_analyst.md")
        assert "钝化" in text
        assert "趋势" in text

    def test_macro_mandates_m1_m2_scissors(self):
        text = _load("macro_analyst.md")
        assert "剪刀差" in text

    def test_macro_mandates_stale_downweight(self):
        text = _load("macro_analyst.md")
        assert "滞后" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py::TestCycleFitMethodology -v`
Expected: FAIL（4 断言全失败）

- [ ] **Step 3: Write minimal implementation**

**fundamental_analyst.md「## 分析方法论」** 整段替换为：

```markdown
## 分析方法论

- 盈利能力：ROE 与毛利率优先与同业中位数对比判断相对强弱；绝对阈值（如 ROE 15%、毛利率 30%）仅作参考，须结合当前利率与通胀环境调整判定（低利率周期企业盈利中枢整体下移，阈值应相应放宽）
- 偿债能力：负债率 60% 以下、流动比率大于 1.5、利息保障倍数大于 3 为健康参考，但需结合行业属性（重资产/金融业天然高负债）与利率环境判断
- 现金流：经营现金流/净利润 大于 1 说明利润含金量高，长期低于 0.8 需警惕
- 估值：PE/PB 与同业及自身历史分位对比，判断贵贱；用历史分位而非绝对倍数，天然适配牛熊周期位置
- GARP 关注 PEG 是否合理，但成长股在流动性宽松周期 PEG 容忍度更高
- 趋势：单季数据波动大，结论优先基于多期趋势与同业对比，不基于单点值
```

**technical_analyst.md「## 分析方法论」** 追加一条（末尾）：

```markdown
- 周期提示：强趋势行情中（单边上涨/下跌）RSI、KDJ 等摆动指标可能长期钝化（持续超买/超卖），此时以 MA 趋势与 MACD 方向为主，超买超卖信号降权，避免逆势误判反转
```

**macro_analyst.md「## 分析方法论」** 整段替换为：

```markdown
## 分析方法论

- CPI：同比上升 3% 以上为通胀压力参考线，负值需警惕通缩；区分食品/核心项影响
- PMI：以 50 为荣枯线——50 上方制造业扩张，下方收缩；关注连续 3 期方向
- M2：增速高于 GDP 增速+CPI 时流动性偏宽松，反之偏紧
- M1/M2 剪刀差：M1 增速持续低于 M2（剪刀差走阔）代表资金空转、活化不足，即便 M2 增速高也应下调"流动性宽松"结论强度；剪刀差收窄（M1 回升）才代表资金活化、宽松传导到实体
- LPR：利率下行利好高负债行业，上行利好银行股；结合行业属性判断
- 数据时效：若某指标最新数据明显滞后于当前日期（如 stale 标记），须在报告中标注该指标数据滞后、不得将旧值表述为当前最新状态，并相应降低相关结论置信度
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: PASS（既有契约 + 新增 4 断言）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/prompts/fundamental_analyst.md src/finance_agent/prompts/technical_analyst.md src/finance_agent/prompts/macro_analyst.md tests/test_prompt_contracts.py
git commit -m "feat(prompts): 分析师方法论周期感知（同业相对/钝化/剪刀差/时效降级) (update-agent-prompt-cycle-fit)"
```

---

### Task 4: 全量验证

**Files:**
- 无新文件；运行验证命令

**Interfaces:**
- Consumes: Task 1-3 全部改动
- Produces: 通过证据（测试输出、ruff/mypy 输出）

- [ ] **Step 1: Run full test suite（非 live）**

Run: `uv run pytest -m "not live"`
Expected: 0 failures（全量回测确认无回归；宏观 fetch/context/契约测试全绿）

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src tests`
Expected: All checks passed

- [ ] **Step 3: Run type check**

Run: `uv run mypy src`
Expected: 无新增错误（基线 69 个既有错误不变，不得**新增**）

- [ ] **Step 4: 人工抽查**

触发一次深度分析（真实数据），抽查宏观分析输出：
- PMI/CPI 若为 stale，报告中出现"数据滞后至 YYYY-MM"标注且未把旧值当最新
- M2/M1 剪刀差表述出现
- 技术面在强趋势股票上未因 RSI 超买直接判反转

记录到 `tests/validation/2026-08-25-update-agent-prompt-cycle-fit-validation.md`。

- [ ] **Step 5: Commit validation record**

```bash
git add tests/validation/2026-08-25-update-agent-prompt-cycle-fit-validation.md
git commit -m "docs(validation): update-agent-prompt-cycle-fit 验证报告"
```

---

（可选，Langfuse 启用时）**Task 5: Langfuse prompt 版本发布**

用 `tests/scripts/import_prompts_to_langfuse.py` 把 3 个改动的 prompt 发布为 ver=3 production label（fundamental/technical/macro_analyst），确认与本地一致后记录到验证报告。