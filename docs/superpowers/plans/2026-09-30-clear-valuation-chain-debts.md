# clear-valuation-chain-debts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清偿 update-financial-freshness-and-valuation 终审后的全部挂账——GARP 诚实分桶推广到全部输入、实现 fetch_peer_data 同业抓取、fetch 层 NaN 归一、报告披露节编号化、api 健康度死代码、图通道门禁扩展 fetch 产出。

**Architecture:** 两个 spec 级变更（valuation-signal-integrity MODIFIED、analyst-data-sources ADDED）+ 四个实现级修复。全部在工作分支 feat/fin-freshness-valuation 上继续（前 delta 已 sync+archive，commit 634813d6）。

**Tech Stack:** Python 3.12 / pandas / pytest / akshare。

## Global Constraints

- **工作目录**: `.worktrees/fin-freshness-valuation`（分支 feat/fin-freshness-valuation），下文路径相对 worktree 根。
- **TDD 铁律**: 先红后绿再提交。
- **不产出伪值**: 缺失/NaN → None + 标注，无 0/无穷/NaN 占位。
- **诚实文案**: 缺失与比较失败分桶；既有真实比较失败文案（「净利润增长率 <= 15%」等）对有值输入保持不变。
- **Lint/类型**: ruff check 全绿；mypy src/ 基线 81 持平（入口 `uv run mypy src/`）。
- **market_cap 单位契约**: quote 层统一元（东财透传/百度×1e8），compute 层亿元——同业抓取复用 fetch_stock_quote 即自动继承，不得另立口径。
- **Commit**: 中文描述、引用 delta 名与任务号；不 push。

---

### Task 1: D1 GARP 诚实分桶推广到 growth/ROE/负债率

**Files:**
- Modify: `src/finance_agent/metrics/garp.py`（growth/ROE/负债率三分支 + `_clean_num` 应用到三输入）
- Test: `tests/metrics/test_garp.py`

**Interfaces:**
- Consumes: 既有 `_clean_num`（NaN→None）
- Produces: 缺失文案 `"<指标> 数据缺失（未参与比较）"` + `details["<指标>_missing"]=True`；真实比较失败文案不变；GARP 其余行为（PE 三桶、PE_caliber）不变

- [ ] **Step 1: 写失败测试**（追加到 tests/metrics/test_garp.py）

```python
class TestGarpHonestBucketAllInputs:
    """delta clear-valuation-chain-debts D1：诚实分桶从 PE 推广到全部输入。"""

    def _data(self, **overrides):
        base = {
            "PE": 20.0,
            "industry_avg_PE": 25.0,
            "net_profit_growth": 0.25,
            "ROE": 0.20,
            "debt_ratio": 0.45,
        }
        base.update(overrides)
        return base

    def test_roe_missing_honest(self):
        result = calc_garp(self._data(ROE=None))
        assert "ROE 数据缺失（未参与比较）" in result["failures"]
        assert "ROE <= 15%" not in result["failures"]
        assert result["details"]["ROE_missing"] is True

    def test_debt_nan_treated_as_missing_not_pass(self):
        result = calc_garp(self._data(debt_ratio=float("nan")))
        assert "负债率 数据缺失（未参与比较）" in result["failures"]
        assert "负债率 >= 60%" not in result["failures"]
        assert result["details"]["负债率_missing"] is True

    def test_growth_missing_honest(self):
        result = calc_garp(self._data(net_profit_growth=None))
        assert "净利润增长率 数据缺失（未参与比较）" in result["failures"]
        assert "净利润增长率 <= 15%" not in result["failures"]
        assert result["details"]["净利润增长率_missing"] is True

    def test_real_comparison_failures_unchanged(self):
        result = calc_garp(
            self._data(net_profit_growth=0.10, ROE=0.10, debt_ratio=0.70)
        )
        assert "净利润增长率 <= 15%" in result["failures"]
        assert "ROE <= 15%" in result["failures"]
        assert "负债率 >= 60%" in result["failures"]
        for key in ("净利润增长率_missing", "ROE_missing", "负债率_missing"):
            assert key not in result["details"]
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/metrics/test_garp.py::TestGarpHonestBucketAllInputs -v` → 3 failed（NaN 用例可能也红：当前 NaN `<=`/`>=` 恒 False 走通过分支，断言失败）
- [ ] **Step 3: 实现**（garp.py：三输入 `_clean_num` + 三分支缺失桶）

```python
    growth = _clean_num(data.get("net_profit_growth"))
    roe = _clean_num(data.get("ROE"))
    debt = _clean_num(data.get("debt_ratio"))
```

三分支改为（growth 示例，ROE/负债率同构，方向按现状）：

```python
    if growth is None:
        # 数据缺失 ≠ 比较失败（D1：与 PE 同款诚实分桶）
        failures.append("净利润增长率 数据缺失（未参与比较）")
        details["净利润增长率"] = None
        details["净利润增长率_missing"] = True
    elif growth <= 0.15:
        failures.append("净利润增长率 <= 15%")
        details["净利润增长率"] = growth
    else:
        details["净利润增长率"] = growth
```

- [ ] **Step 4: 跑绿** — 同 Step 2 → PASS；`uv run pytest tests/metrics/ -q` 无回归（注意 test_none_values 断言 len==2 应仍绿；若有断言旧 None 文案的用例，按新语义最小修正并在报告注明）
- [ ] **Step 5: ruff + mypy 持平 → Commit** — `git commit -m "fix(metrics): GARP 诚实分桶推广到 growth/ROE/负债率——缺失与 NaN 不得伪装成比较失败/通过（clear-valuation-chain-debts D1）"`

---

### Task 2: D2 fetch_peer_data 实现

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py`（AKShareClient 新增 fetch_peer_data，置于 fetch_block_trades 之后）、`src/finance_agent/nodes/fetch.py:358-362`（_fetch_peers 空结果归一）
- Test: `tests/data/test_akshare_client.py`（新增 TestFetchPeerData）

**Interfaces:**
- Consumes: `self.fetch_stock_quote(code)`（含单位归一与回退链）
- Produces: `fetch_peer_data(stock_codes: list[str]) -> pd.DataFrame | None`——全成功/部分成功返回 DataFrame（列 name/code/PE/PB），全部失败或输入空返回 None；fetch.py `_fetch_peers` 空表归一 None

- [ ] **Step 1: 写失败测试**

```python
class TestFetchPeerData:
    """delta clear-valuation-chain-debts D2：同业财务数据抓取。"""

    def test_mixed_success_skips_failed_peer(self, client, monkeypatch):
        calls = []

        def fake_quote(code):
            calls.append(code)
            if code == "688012":
                return {"name": "中微公司", "PE": 60.0, "PB": 10.0}
            raise ConnectionError("全源失败")

        monkeypatch.setattr(client, "fetch_stock_quote", fake_quote)
        df = client.fetch_peer_data(["688012", "002371"])
        assert df is not None and len(df) == 1
        assert df.iloc[0]["name"] == "中微公司"
        assert df.iloc[0]["PE"] == 60.0

    def test_quote_without_pe_pb_skipped(self, client, monkeypatch):
        monkeypatch.setattr(
            client, "fetch_stock_quote", lambda code: {"name": "X", "code": code}
        )
        df = client.fetch_peer_data(["600001"])
        assert df is None

    def test_all_failed_returns_none(self, client, monkeypatch):
        def fail(code):
            raise ConnectionError("down")

        monkeypatch.setattr(client, "fetch_stock_quote", fail)
        assert client.fetch_peer_data(["600001", "600002"]) is None

    def test_empty_input_returns_none(self, client):
        assert client.fetch_peer_data([]) is None
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/data/test_akshare_client.py::TestFetchPeerData -v` → FAIL（方法不存在）
- [ ] **Step 3: 实现**

```python
    def fetch_peer_data(self, stock_codes: list[str]) -> pd.DataFrame | None:
        """逐标的抓取同业名称/PE/PB（复用 fetch_stock_quote 主源+回退链）。

        单标的失败或无 PE/PB 跳过不拖垮整批；全部失败或输入空返回 None
        （delta clear-valuation-chain-debts ADDED「同业财务数据获取」）。
        """
        codes = [str(c).strip() for c in (stock_codes or []) if str(c).strip()]
        if not codes:
            return None
        rows: list[dict] = []
        for code in codes:
            try:
                q = self.fetch_stock_quote(code)
            except Exception as e:
                logger.warning("同业 %s 行情抓取失败，跳过: %s", code, e)
                continue
            pe = q.get("PE") or q.get("pe")
            pb = q.get("PB") or q.get("pb")
            if pe is None and pb is None:
                logger.warning("同业 %s 无 PE/PB（全回退失败），跳过", code)
                continue
            rows.append(
                {"name": q.get("name") or code, "code": code, "PE": pe, "PB": pb}
            )
        if not rows:
            return None
        return pd.DataFrame(rows, columns=["name", "code", "PE", "PB"])
```

`_fetch_peers` 归一（fetch.py）：

```python
def _fetch_peers(ak, code, state, industry_info):
    peer_codes = state.get("peer_codes")
    if not peer_codes or not industry_info:
        return None
    df = ak.fetch_peer_data(peer_codes)
    if df is None or df.empty:
        return None
    return df
```

- [ ] **Step 4: 跑绿 + 回归** — `uv run pytest tests/data/ tests/nodes/ -q`；注意 fetch.py 对 peer_financials 的既有异常分支不动
- [ ] **Step 5: Commit** — `git commit -m "feat(data): 实现 fetch_peer_data 同业抓取——相对估值从名存实亡到有 peer_codes 即可计算（clear-valuation-chain-debts D2）"`

---

### Task 3: D3 fetch_quarterly_income 出口 NaN 归一

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py`（fetch_quarterly_income 返回前归一）
- Test: `tests/data/test_akshare_client.py`（TestFetchQuarterlyIncomeExtended 追加）

**Interfaces:**
- Produces: 返回 DataFrame 全列 NaN → None（object dtype），消费端 `v is None` 可靠判空

- [ ] **Step 1: 写失败测试**（追加用例）

```python
    @patch("finance_agent.data.akshare_client.ak")
    def test_nan_normalized_to_none_at_exit(self, mock_ak, client):
        # D3：同比列缺同期数据时 records 值为 None，经 pd.DataFrame 变 float64 NaN——
        # 出口必须归一 None（「不产出伪值」契约）
        df = pd.DataFrame(
            {
                "REPORT_DATE": pd.to_datetime(["2026-06-30", "2025-06-30"]),
                "PARENT_NETPROFIT": [7.72e8, 0.94e8],
                "OPERATE_INCOME": [1.80e9, 0.95e9],
                "OPERATE_COST": [1.07e9, 0.65e9],
            }
        )
        mock_ak.stock_profit_sheet_by_quarterly_em.return_value = df
        out = client.fetch_quarterly_income("688072", quarters=2)
        assert out.iloc[0]["同比"] is None or out.iloc[0]["同比"] == out.iloc[0]["同比"]
        # 宽窗口含同期（2025Q2 即末行）时 2026Q2 有同比；2025Q6 行无 2024 同期 → None
        assert not any(
            isinstance(v, float) and pd.isna(v) for v in out["同比"].tolist()
        )
        assert not any(
            isinstance(v, float) and pd.isna(v) for v in out["环比"].tolist()
        )
```

（如构造中 2026Q2 同比实际可算，断言第一个分支恒真即可——核心是第二个 not any NaN 断言。）
- [ ] **Step 2: 跑红** — `uv run pytest tests/data/test_akshare_client.py::TestFetchQuarterlyIncomeExtended::test_nan_normalized_to_none_at_exit -v` → FAIL（存在 NaN）
- [ ] **Step 3: 实现**（`result = pd.DataFrame(records)` 之后、`head(quarters)` 之前）

```python
        # 出口 NaN 归一（D3）：records 中 None 经 DataFrame 构造变 float64 NaN，
        # 消费端 is None 判空失效——统一归回 None（「不产出伪值」契约）
        result = result.astype(object).where(result.notna(), None)
```

- [ ] **Step 4: 跑绿 + `uv run pytest tests/data/ tests/nodes/ -q` 无回归**
- [ ] **Step 5: Commit** — `git commit -m "fix(data): 季度利润表出口 NaN 归一 None——消费端判空可靠（clear-valuation-chain-debts D3）"`

---

### Task 4: D4 报告披露节编号化 + 暂缺去单位后缀

**Files:**
- Modify: `src/finance_agent/nodes/report.py`（_format_freshness_section 返回体 + generate_report 接线）
- Test: `tests/nodes/test_report_freshness_render.py`（更新断言）

**Interfaces:**
- Produces: `_format_freshness_section(state) -> str | None`（返回正文，不再含标题）；generate_report 以 `next_title("财务数据口径披露")` 编号呈现

- [ ] **Step 1: 更新测试**（先改测试跑红）

```python
def test_full_section_with_industry_override():
    state = {  # 同既有 fixture
    }
    section = _format_freshness_section(state)
    assert section is not None
    assert "###" not in section and "财务数据口径披露" not in section  # 标题由 generate_report 编号注入
    assert "毛利率 41.0%" in section
    assert "暂缺" not in section  # 全字段在位时无暂缺

def test_missing_fields_render_without_unit_suffix():
    state = {
        "latest_period_snapshot": {
            "报告日": "2026-06-30", "期类型": "中报",
            "毛利率(%)": None, "存货": None,
        },
    }
    section = _format_freshness_section(state)
    assert "毛利率 暂缺" in section and "存货 暂缺" in section
    assert "暂缺%" not in section and "暂缺 亿" not in section
    assert "None" not in section
```

（既有用例中 `assert "累计口径" in section` 等保留；generate_report 接线新增一个用例可选——用最小 state 断言报告含「财务数据口径披露」编号标题，需 mock 图表生成，若成本高则以 _format_freshness_section 纯函数测试为准，接线正确性由 Task 6 实跑验证。）
- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**

`_format_freshness_section`：
- 删除返回值中的 `### 财务数据口径披露` 标题行（正文照旧）
- 快照行改字段级拼接，缺失渲染「<label> 暂缺」无单位：

```python
    def _item(label: str, val, unit: str = "") -> str:
        return f"{label} 暂缺" if val is None else f"{label} {val}{unit}"

    lines.append(
        "- 最新报告期快照：{date}（{ptype}，利润表累计口径）— {gm}、{dr}、{inv}、{cl}，{rg}、{ng}{note}".format(
            date=_v(snap.get("报告日", "?")), ptype=_v(snap.get("期类型", "?")),
            gm=_item("毛利率", snap.get("毛利率(%)"), "%"),
            dr=_item("资产负债率", snap.get("资产负债率(%)"), "%"),
            inv=_item("存货", snap.get("存货"), " 亿"),
            cl=_item("合同负债", snap.get("合同负债"), " 亿"),
            rg=_item("营收同比", snap.get("营收同比(%)"), "%"),
            ng=_item("归母净利同比", snap.get("归母净利同比(%)"), "%"),
            note=missing_note,
        )
    )
```

`generate_report` 接线（替换现有 `sections.append(freshness_section)`）：

```python
    if freshness_section:
        sections.append(f"{next_title('财务数据口径披露')}\n{freshness_section}\n")
```

- [ ] **Step 4: 跑绿 + `uv run pytest tests/nodes/ -q` 无回归**
- [ ] **Step 5: Commit** — `git commit -m "fix(report): 披露节并入编号章节体系 + 缺失字段「暂缺」去单位后缀（clear-valuation-chain-debts D4）"`

---

### Task 5: D5 api 健康度死代码 + D6 门禁扩展 fetch 产出

**Files:**
- Modify: `src/finance_agent/api.py:451`、`tests/test_graph_5layer.py`
- Test: `tests/test_graph_5layer.py`（新增 fetch 门禁用例）

**Interfaces:**
- Produces: SSE 进度「健康度 <total>」恢复；门禁覆盖 fetch_data 产出键 ⊆ AnalysisState ⊆ 图通道

- [ ] **Step 1: 写失败测试**（test_graph_5layer.py 新增）

```python
    def test_fetch_outputs_all_declared_and_channeled(self, monkeypatch):
        from finance_agent.graph import build_5layer_graph
        from finance_agent.nodes.fetch import fetch_data
        from finance_agent.state import AnalysisState

        monkeypatch.setenv("TESTING", "1")
        produced = set(
            fetch_data({"stock_code": "600519", "stock_name": "贵州茅台"}).keys()
        )
        declared = set(AnalysisState.__annotations__)
        missing_declared = produced - declared
        assert not missing_declared, (
            f"fetch 产出未声明键会被 LangGraph 静默丢弃：{sorted(missing_declared)}"
        )
        channels = set(build_5layer_graph().channels)
        missing_channel = produced - channels
        assert not missing_channel, f"已声明但未建图通道：{sorted(missing_channel)}"
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/test_graph_5layer.py::TestNodeOutputChannels::test_fetch_outputs_all_declared_and_channeled -v`：若 stub 产出含未声明键则红（如实处置——键该声明的声明，不该产出的从 stub 移除并在报告注明）；门禁本身可能直接绿（守卫补强，非缺陷修复，绿即记录）
- [ ] **Step 3: D5 实现**（api.py:451）

```python
            score = hs.get("total")
```

- [ ] **Step 4: 跑绿** — `uv run pytest tests/test_graph_5layer.py tests/test_api_pipeline_resume.py -q` 无回归；grep 确认 `hs.get("score"` 全仓无其他实例
- [ ] **Step 5: Commit** — `git commit -m "fix(api)+test(graph): 健康度进度行取 total 恢复显示；图通道门禁扩展 fetch 产出键（clear-valuation-chain-debts D5/D6）"`

---

### Task 6: 收口验证 + 实跑 + validation 报告

**Files:**
- Modify: `openspec/changes/clear-valuation-chain-debts/tasks.md`（回填）
- Create: `tests/validation/2026-09-30-clear-valuation-chain-debts-validation.md`

- [ ] **Step 1: 静态门禁** — `uv run ruff check && uv run mypy src/ && uv run pytest tests/nodes tests/metrics tests/data tests/test_citation.py tests/test_citation_new_keys.py tests/test_metric_vocab.py tests/test_cache_node.py tests/test_graph_5layer.py tests/test_prompt_contracts.py -q` → 全绿（mypy 81 持平）
- [ ] **Step 2: 688072 实跑**（worktree 后端 :8010，隔离 DB/REPORTS_DIR，缓存清空）：携带 peer_codes（如 688012,002371）提交分析；断言 ①报告含同业相对估值结论（或诚实缺失声明）②GARP 缺数文案正确 ③披露节为编号章节且无「暂缺%」形态 ④东财若可用，披露节「市值 … 亿」量级正确（上一 delta 保留意见核验）
- [ ] **Step 3: validation 报告落 tests/validation/ + 回填 tasks.md + Commit**

---

## Self-Review 记录

- **Spec 覆盖**：valuation-signal-integrity MODIFIED → Task 1；analyst-data-sources ADDED 四场景 → Task 2（四测试一一对应）；D3/D4/D5/D6 为实现级修复无 spec 变更（D3 落实既有「不产出伪值」契约，D6 落实既有「至少 compute_metrics」的门禁条款）。
- **Placeholder**：无 TBD/TODO；Task 4 Step 1 的 generate_report 接线用例做了成本说明（实跑覆盖）。
- **类型一致**：fetch_peer_data 返回列 name/code/PE/PB ⊇ `_build_peers_list` 消费契约（name/PE/PB）；`_fetch_peers` 空表归一 None 与 fetch.py 既有 `if peers is not None` 分支兼容。
