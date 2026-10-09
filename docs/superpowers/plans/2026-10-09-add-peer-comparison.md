# add-peer-comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 激活休眠的 peer_codes 同业对比链路——「对比 A 和 B」编译成单次 `run_deep_analysis(主标的, peer_codes=[...])`，主标的报告基本面章节产出同业对比段。

**Architecture:** 三断点修复：数据层 `fetch_peer_data` 扩展估值组+财务组（财务组复用主标的同源 `fetch_latest_period_snapshot`）；材料层 compute 新增 `format_peer_comparison` 把 peer_financials 渲染成 markdown 对照表写入 `state.peer_comparison`（替换 Issue #4 标志位），analysts.py 注入点字符串直通；入口层 `run_deep_analysis` 工具暴露 `peer_codes` 参数（显式传参优先于请求闭包），deep_mode.md 新增「类型 D：点名多标的对比」分支。

**Tech Stack:** Python 3.12 / pandas / LangGraph / pytest / uv；prompts 为 git 跟踪的 markdown（权威源）。

**Delta 契约**: `openspec/changes/add-peer-comparison/`（proposal.md / design.md / specs/peer-comparison/spec.md / specs/analyst-data-sources/spec.md / tasks.md），实施以其中 Scenario 为验收锚点。

## Global Constraints

- 对比=单条管线：MUST NOT 为多标的串行/并行发起多次 `run_deep_analysis`（deep_mode 核心约束 2 不变）
- `fetch_peer_data` 返回 DataFrame 列名契约（逐字）：`name/code/PE/PB/total_mv/revenue_yoy/netprofit_yoy/gross_margin/report_period`；缺失字段 None 占位，MUST NOT 删列
- 口径：`total_mv` 亿元（quote `market_cap` 为元，÷1e8）；财务组复用 `fetch_latest_period_snapshot`（与主标的同函数同口径）；估值组复用 `_quote_via_chain`
- 降级语义（既有，不得破坏）：单标的行情失败跳过不拖垮整批；全部失败/空输入返回 None；未指定 peer 不触发抓取；新增：财务组失败 SHALL NOT 影响估值组（字段组级降级）
- 停牌 peer 的 NaN PE/PB 按缺数归一（既有行为，终审 C1），出口 `_normalize_nan` 保留
- 测试隔离红线：任何调用 `fetch_peer_data` 的存量/新增测试 MUST stub `fetch_latest_period_snapshot`，禁止真网络
- 本 delta 非交互类：不动 `frontend/`、不动 SSE/会话/状态流转
- Lint/类型：`uv run ruff check`、`uv run mypy` 保持干净
- Prompt 文件（`src/finance_agent/prompts/*.md`）改完不在本计划内发布——deploy 是合并后独立运维步骤（`scripts/deploy_prompts.py` + 指纹取证）
- 提交纪律：每个任务一个 commit，message 格式 `feat(peer-comparison): ...` / `test(peer-comparison): ...`

---

### Task 1: fetch_peer_data 估值组+财务组扩展

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py`（`fetch_peer_data`，约 1243-1277 行）
- Test: `tests/data/test_akshare_client.py`（`TestFetchPeerData` 868 行起、`TestFetchPeerDataHeterogeneousRows` 942 行起、`TestFetchPeerDataSharedSpot` 975 行起三个存量类 + 新增 `TestFetchPeerDataFinancialGroup`）

**Interfaces:**
- Consumes: 既有 `_quote_via_chain(code, spot_df) -> tuple[dict, spot_df]`（quote 含 `market_cap`，单位元）、`fetch_latest_period_snapshot(code) -> dict`（键：`营收同比(%)`、`归母净利同比(%)`、`毛利率(%)`、`报告日`；利润表不可用 raise ValueError）
- Produces: `fetch_peer_data(stock_codes: list[str]) -> pd.DataFrame | None`，列契约 `name/code/PE/PB/total_mv/revenue_yoy/netprofit_yoy/gross_margin/report_period`（total_mv 亿元；财务组缺失=None）

- [ ] **Step 1: Write the failing tests**

在 `tests/data/test_akshare_client.py` 新增测试类（放在 `TestFetchPeerDataSharedSpot` 之后）：

```python
class TestFetchPeerDataFinancialGroup:
    """add-peer-comparison：估值组+财务组字段扩展与字段组级降级。"""

    def test_extended_columns_full_data(self, client, monkeypatch):
        monkeypatch.setattr(
            client,
            "_fetch_tencent_quote",
            lambda code: {
                "name": "五粮液", "code": code, "PE": 15.0, "PB": 3.2,
                "market_cap": 5e11,
            },
        )
        monkeypatch.setattr(
            client,
            "fetch_latest_period_snapshot",
            lambda code: {
                "营收同比(%)": 7.1, "归母净利同比(%)": 8.2,
                "毛利率(%)": 76.5, "报告日": "2026-06-30",
            },
        )
        df = client.fetch_peer_data(["000858"])
        assert df is not None and len(df) == 1
        assert list(df.columns) == [
            "name", "code", "PE", "PB", "total_mv",
            "revenue_yoy", "netprofit_yoy", "gross_margin", "report_period",
        ]
        row = df.iloc[0]
        assert row["total_mv"] == 5000.0  # 5e11 元 → 5000 亿
        assert row["revenue_yoy"] == 7.1
        assert row["netprofit_yoy"] == 8.2
        assert row["gross_margin"] == 76.5
        assert row["report_period"] == "2026-06-30"

    def test_financial_group_failure_degrades_fields_not_rows(self, client, monkeypatch):
        """财务组全失败：行保留（估值组完整），财务列缺失占位——字段组级降级。"""
        monkeypatch.setattr(
            client,
            "_fetch_tencent_quote",
            lambda code: {"name": "X", "code": code, "PE": 20.0, "PB": 3.0, "market_cap": 1e11},
        )

        def _boom(code):
            raise ValueError(f"股票 {code} 利润表数据不可用")

        monkeypatch.setattr(client, "fetch_latest_period_snapshot", _boom)
        df = client.fetch_peer_data(["000858"])
        assert df is not None and len(df) == 1
        row = df.iloc[0]
        assert row["PE"] == 20.0 and row["total_mv"] == 1000.0
        assert pd.isna(row["revenue_yoy"]) and pd.isna(row["netprofit_yoy"])
        assert pd.isna(row["gross_margin"]) and pd.isna(row["report_period"])

    def test_market_cap_missing_degrades_field_only(self, client, monkeypatch):
        """回退链 quote 无 market_cap：字段 None 占位，不丢行不阻断。"""
        monkeypatch.setattr(
            client,
            "_fetch_tencent_quote",
            lambda code: {"name": "X", "code": code, "PE": 20.0, "PB": 3.0},
        )
        monkeypatch.setattr(
            client,
            "fetch_latest_period_snapshot",
            lambda code: {"营收同比(%)": 1.0, "归母净利同比(%)": 2.0, "毛利率(%)": 50.0, "报告日": "2026-06-30"},
        )
        df = client.fetch_peer_data(["000858"])
        assert df is not None and len(df) == 1
        assert pd.isna(df.iloc[0]["total_mv"])
        assert df.iloc[0]["revenue_yoy"] == 1.0
```

同时在三个存量 peer 测试类（`TestFetchPeerData`、`TestFetchPeerDataHeterogeneousRows`、`TestFetchPeerDataSharedSpot`）各加一个 autouse fixture，stub 掉财务组以防真网络（存量断言只管估值组，财务组全降级不影响它们）：

```python
    @pytest.fixture(autouse=True)
    def _stub_financial_group(self, client, monkeypatch):
        """add-peer-comparison：存量用例不断言财务组——stub 为全失败（字段组级降级路径）。"""

        def _boom(code):
            raise ValueError("stub: 存量用例不覆盖财务组")

        monkeypatch.setattr(client, "fetch_latest_period_snapshot", _boom)
```

注意：`TestFetchPeerData` 已有名为 `client` 的 fixture 依赖（文件 22 行定义）；fixture 内 monkeypatch 用例级生效即可。若某存量类里 `client` 是 function 作用域 fixture 注入，autouse fixture 直接声明 `client` 参数即可拿到同一实例。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_akshare_client.py -q -k "PeerData"`
Expected: 新增 3 用例 FAIL（`assert list(df.columns) == [...]` 列数不符 / `KeyError 'total_mv'`）；存量用例在 stub 注入后仍 PASS（现状行为未变）。

- [ ] **Step 3: Implement fetch_peer_data extension**

`src/finance_agent/data/akshare_client.py` 的 `fetch_peer_data` 改为（docstring 同步更新）：

```python
    def fetch_peer_data(self, stock_codes: list[str]) -> pd.DataFrame | None:
        """逐标的抓取同业估值组（name/PE/PB/total_mv）+ 财务组（revenue_yoy/netprofit_yoy/gross_margin/report_period）。

        估值组复用 _quote_via_chain 三级链；total_mv 由 quote.market_cap（元）÷1e8 归一亿元。
        财务组复用 fetch_latest_period_snapshot（与主标的快照同源同口径），独立 try 边界：
        失败仅财务列置 None，不丢行不拖垮估值组（字段组级降级，spec analyst-data-sources）。
        单标的行情失败或无 PE/PB 跳过不拖垮整批；全部失败或输入空返回 None。
        spot 表惰性共享：腾讯主源健康时逐标的 1 请求、零 spot 调用；腾讯
        失败后首个标的触发一次全市场 spot 拉取，批内复用（N 标的 1×）。
        """
        codes = [str(c).strip() for c in (stock_codes or []) if str(c).strip()]
        if not codes:
            return None
        spot_df: pd.DataFrame | None = None
        rows: list[dict] = []
        for code in codes:
            try:
                q, spot_df = self._quote_via_chain(code, spot_df)
            except Exception as e:
                logger.warning("同业 %s 行情抓取失败，跳过: %s", code, e)
                continue
            pe = q.get("PE") or q.get("pe")
            pb = q.get("PB") or q.get("pb")
            # 停牌 peer 的 NaN PE/PB（东财 spot 实测行为）按缺数归一——NaN 真值
            # 直通会毒化同业均值（终审 C1 同源问题）
            if pe is not None and pd.isna(pe):
                pe = None
            if pb is not None and pd.isna(pb):
                pb = None
            if pe is None and pb is None:
                logger.warning("同业 %s 无 PE/PB（全回退失败），跳过", code)
                continue
            mc = q.get("market_cap")
            if mc is not None and pd.isna(mc):
                mc = None
            row = {
                "name": q.get("name") or code,
                "code": code,
                "PE": pe,
                "PB": pb,
                "total_mv": round(float(mc) / 1e8, 2) if mc is not None else None,
                "revenue_yoy": None,
                "netprofit_yoy": None,
                "gross_margin": None,
                "report_period": None,
            }
            # 财务组：独立 try 边界，失败不丢行（字段组级降级）
            try:
                snap = self.fetch_latest_period_snapshot(code)
                row["revenue_yoy"] = snap.get("营收同比(%)")
                row["netprofit_yoy"] = snap.get("归母净利同比(%)")
                row["gross_margin"] = snap.get("毛利率(%)")
                row["report_period"] = snap.get("报告日")
            except Exception as e:
                logger.warning("同业 %s 财务组抓取失败，字段置缺失: %s", code, e)
            rows.append(row)
        if not rows:
            return None
        # 出口根因归一（终审 C1）：混合行 DataFrame 构造把 None 强转回 float64
        # NaN 毒化同业均值——出口必须 _normalize_nan
        return self._normalize_nan(
            pd.DataFrame(
                rows,
                columns=[
                    "name", "code", "PE", "PB", "total_mv",
                    "revenue_yoy", "netprofit_yoy", "gross_margin", "report_period",
                ],
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_akshare_client.py -q`
Expected: 全文件 PASS（含存量 peer 三场景：单标的跳过 / 全失败 None / 共享 spot 1 次）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(peer-comparison): fetch_peer_data 扩展估值组+财务组（字段组级降级）"
```

---

### Task 2: format_peer_comparison 格式化器 + analysts 注入直通

**Files:**
- Modify: `src/finance_agent/nodes/compute.py`（新增函数 + 替换约 133-136 行的标志位块）
- Modify: `src/finance_agent/nodes/analysts.py:689-694`（`_build_fundamental_context` 同业对比注入点）
- Test: `tests/nodes/test_compute.py`、`tests/nodes/test_analysts.py`

**Interfaces:**
- Consumes: Task 1 的 `state.peer_financials` DataFrame 列契约；`state.latest_period_snapshot`（键 `营收同比(%)`/`归母净利同比(%)`/`毛利率(%)`/`报告日`）；compute 内 `result["valuation_snapshot"]`（键 `market_cap` 亿元/`PE`/`PE_ttm`/`PB`）
- Produces: `format_peer_comparison(state: AnalysisState, valuation_snapshot: dict | None) -> str | None`；`state.peer_comparison` 由标志位 dict 改为 markdown 字符串（None 时键不写入）

- [ ] **Step 1: Write the failing tests**

`tests/nodes/test_compute.py` 追加（文件已 import pandas as pd；若无则加）：

```python
from finance_agent.nodes.compute import format_peer_comparison


def _peer_df(rows):
    cols = ["name", "code", "PE", "PB", "total_mv",
            "revenue_yoy", "netprofit_yoy", "gross_margin", "report_period"]
    return pd.DataFrame(rows, columns=cols)


class TestFormatPeerComparison:
    def test_full_table_target_first_row(self):
        state = {
            "stock_code": "600519", "stock_name": "贵州茅台",
            "peer_financials": _peer_df([{
                "name": "五粮液", "code": "000858", "PE": 15.0, "PB": 3.2,
                "total_mv": 5000.0, "revenue_yoy": 7.1, "netprofit_yoy": 8.2,
                "gross_margin": 76.5, "report_period": "2026-06-30",
            }]),
            "latest_period_snapshot": {
                "营收同比(%)": 9.1, "归母净利同比(%)": 10.2,
                "毛利率(%)": 91.3, "报告日": "2026-06-30",
            },
        }
        vs = {"PE": 22.0, "PE_ttm": None, "PB": 8.0, "market_cap": 18000.0}
        text = format_peer_comparison(state, vs)
        assert text is not None
        lines = text.splitlines()
        assert "总市值(亿)" in lines[1] and "毛利率(%)" in lines[1]
        target_row = next(l for l in lines if "600519" in l)
        peer_row = next(l for l in lines if "000858" in l)
        assert "贵州茅台" in target_row and "22.0" in target_row and "91.3" in target_row
        assert "五粮液" in peer_row and "15.0" in peer_row and "76.5" in peer_row
        # 主标的必须在首行（对标股之前）
        assert lines.index(target_row) < lines.index(peer_row)

    def test_financial_group_missing_rendered_as_dash(self):
        state = {
            "stock_code": "600519", "stock_name": "贵州茅台",
            "peer_financials": _peer_df([{
                "name": "五粮液", "code": "000858", "PE": 15.0, "PB": 3.2,
                "total_mv": 5000.0, "revenue_yoy": None, "netprofit_yoy": None,
                "gross_margin": None, "report_period": None,
            }]),
            "latest_period_snapshot": {},
        }
        vs = {"PE": 22.0, "PE_ttm": None, "PB": 8.0, "market_cap": 18000.0}
        text = format_peer_comparison(state, vs)
        assert text is not None
        peer_row = next(l for l in text.splitlines() if "000858" in l)
        assert "—" in peer_row  # 缺失标记，列不消失
        assert "毛利率" in text  # 表头仍在

    def test_no_peer_data_returns_none(self):
        assert format_peer_comparison({"stock_code": "600519"}, {"PE": 22.0}) is None

    def test_pe_ttm_fallback_caliber_note(self):
        """主标的静态 PE 缺失回落 PE_ttm 时，附跨口径提示（与 relative_valuation 口径标注同族）。"""
        state = {
            "stock_code": "600519", "stock_name": "贵州茅台",
            "peer_financials": _peer_df([{
                "name": "五粮液", "code": "000858", "PE": 15.0, "PB": 3.2,
                "total_mv": 5000.0, "revenue_yoy": 7.1, "netprofit_yoy": 8.2,
                "gross_margin": 76.5, "report_period": "2026-06-30",
            }]),
            "latest_period_snapshot": {},
        }
        vs = {"PE": None, "PE_ttm": 21.5, "PB": 8.0, "market_cap": 18000.0}
        text = format_peer_comparison(state, vs)
        assert text is not None
        assert "TTM" in text and "跨口径" in text
        target_row = next(l for l in text.splitlines() if "600519" in l)
        assert "21.5" in target_row
```

`tests/nodes/test_analysts.py` 追加：

```python
class TestFundamentalPeerComparisonInjection:
    def test_peer_comparison_string_injected_verbatim(self):
        from finance_agent.nodes.analysts import _build_fundamental_context

        state = {"peer_comparison": "同业对比（主标的首行）：\n| 名称 | ..."}
        ctx = _build_fundamental_context(state)
        assert "同业对比（state 键 peer_comparison）" in ctx
        assert "同业对比（主标的首行）：" in ctx  # 字符串直通，不再 json.dumps

    def test_legacy_dict_still_rendered(self):
        """防御：存量标志位 dict 形态不炸（向后兼容）。"""
        from finance_agent.nodes.analysts import _build_fundamental_context

        ctx = _build_fundamental_context({"peer_comparison": {"available": True}})
        assert "peer_comparison" in ctx

    def test_no_peer_comparison_no_section(self):
        from finance_agent.nodes.analysts import _build_fundamental_context

        ctx = _build_fundamental_context({})
        assert "peer_comparison" not in ctx
```

注意：`_build_fundamental_context` 若对缺省键有必填依赖导致 `{}` 炸掉，把 state 补到最小可跑集合（全部 `state.get` 读取，预期无必填），以实际行为为准调整用例输入。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/nodes/test_compute.py -q -k PeerComparison; uv run pytest tests/nodes/test_analysts.py -q -k PeerComparison`
Expected: FAIL（`ImportError: cannot import name 'format_peer_comparison'` / 字符串直通断言失败——现状注入是 `json.dumps({"available": True})`）

- [ ] **Step 3: Implement formatter + injection**

`src/finance_agent/nodes/compute.py`（`import pandas as pd` 已有）新增函数，并替换文件尾部「同业对比」标志位块：

```python
_PEER_TABLE_COLUMNS = [
    ("name", "名称"), ("code", "代码"), ("PE", "PE"), ("PB", "PB"),
    ("total_mv", "总市值(亿)"), ("revenue_yoy", "营收同比(%)"),
    ("netprofit_yoy", "归母净利同比(%)"), ("gross_margin", "毛利率(%)"),
    ("report_period", "报告期"),
]


def _peer_fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def format_peer_comparison(state: AnalysisState, valuation_snapshot: dict | None) -> str | None:
    """peer_financials + 主标的估值快照/最新期快照 → markdown 对照表（主标的首行）。

    财务组主标的与对标股同源自 latest_period_snapshot（同口径）；主标的 PE 取
    估值快照已选口径（static 优先，回落 PE_ttm 时附跨口径提示）。peer 数据缺失
    返回 None（调用方不写入 state.peer_comparison，与既有 optional 降级一致）。
    """
    peer_df = state.get("peer_financials")
    if peer_df is None or peer_df.empty:
        return None
    vs = valuation_snapshot or {}
    snap = state.get("latest_period_snapshot") or {}
    pe = vs.get("PE")
    pe_ttm_fallback = False
    if pe is None and vs.get("PE_ttm") is not None:
        pe = vs.get("PE_ttm")
        pe_ttm_fallback = True
    target = {
        "name": state.get("stock_name") or state.get("stock_code"),
        "code": state.get("stock_code"),
        "PE": pe,
        "PB": vs.get("PB"),
        "total_mv": vs.get("market_cap"),
        "revenue_yoy": snap.get("营收同比(%)"),
        "netprofit_yoy": snap.get("归母净利同比(%)"),
        "gross_margin": snap.get("毛利率(%)"),
        "report_period": snap.get("报告日"),
    }
    header = "| " + " | ".join(label for _, label in _PEER_TABLE_COLUMNS) + " |"
    sep = "|" + "---|" * len(_PEER_TABLE_COLUMNS)

    def _row(d: dict) -> str:
        return "| " + " | ".join(_peer_fmt(d.get(k)) for k, _ in _PEER_TABLE_COLUMNS) + " |"

    lines = [
        "同业对比（主标的首行；估值为行情快照口径，财务组为最新报告期累计同比口径）：",
        header,
        sep,
        _row(target),
    ]
    for _, r in peer_df.iterrows():
        lines.append(_row(r.to_dict()))
    if pe_ttm_fallback:
        lines.append("注：主标的 PE 为 TTM 推导口径，对标股 PE 为行情快照口径，跨口径比较仅供参考。")
    return "\n".join(lines)
```

替换 compute 尾部（现 133-136 行附近）：

```python
    # ── 同业对比（add-peer-comparison：格式化材料注入，关闭 Issue #4 标志位占位）──
    peer_text = format_peer_comparison(state, result.get("valuation_snapshot"))
    if peer_text is not None:
        result["peer_comparison"] = peer_text
```

`src/finance_agent/nodes/analysts.py` 注入点（689-694 行）改为字符串直通：

```python
    # 同业对比
    peer = state.get("peer_comparison")
    if peer:
        text = peer if isinstance(peer, str) else json.dumps(peer, ensure_ascii=False, default=str)
        sections.append(
            f"同业对比（state 键 peer_comparison）:\n{text}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/nodes/test_compute.py tests/nodes/test_analysts.py -q`
Expected: 全 PASS（含存量 compute/analysts 用例）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/compute.py src/finance_agent/nodes/analysts.py tests/nodes/test_compute.py tests/nodes/test_analysts.py
git commit -m "feat(peer-comparison): 同业指标格式化器注入基本面 context（关闭 Issue #4）"
```

---

### Task 3: run_deep_analysis 暴露 peer_codes 参数

**Files:**
- Modify: `src/finance_agent/agent_factory.py`（`_make_run_deep_analysis`，526 行起；新增模块级 `_resolve_peer_codes`）
- Test: `tests/test_agent_factory.py`

**Interfaces:**
- Consumes: 既有闭包 `peer_codes`（`build_agent(mode="deep", peer_codes=[...])` 路径，api.py:1690 注入）
- Produces: `_resolve_peer_codes(llm_codes: list | None, closure_codes: list | None, exclude: str | None = None) -> list[str] | None`；`run_deep_analysis(stock_code: str, stock_name: str = "", peer_codes: list[str] | None = None)`——LLM 显式传参优先于闭包；归一化=strip/剔非 6 位数字/去重/剔主标的/上限 3

- [ ] **Step 1: Write the failing tests**

`tests/test_agent_factory.py` 追加：

```python
import inspect

from finance_agent.agent_factory import _make_run_deep_analysis, _resolve_peer_codes


class TestRunDeepAnalysisPeerCodes:
    def test_tool_signature_has_peer_codes(self):
        fn = _make_run_deep_analysis()
        sig = inspect.signature(fn)
        assert "peer_codes" in sig.parameters
        assert sig.parameters["peer_codes"].default is None

    def test_tool_docstring_documents_peer_codes(self):
        fn = _make_run_deep_analysis()
        assert "peer_codes" in (fn.__doc__ or "")

    def test_resolve_explicit_overrides_closure(self):
        assert _resolve_peer_codes(["000858"], ["601318"]) == ["000858"]
        assert _resolve_peer_codes(None, ["601318"]) == ["601318"]
        assert _resolve_peer_codes(None, None) is None
        assert _resolve_peer_codes([], None) is None

    def test_resolve_sanitizes_and_excludes_target(self):
        assert _resolve_peer_codes(
            [" 000858 ", "bad", "000858", "600519"], None, exclude="600519"
        ) == ["000858"]

    def test_resolve_caps_at_three(self):
        assert _resolve_peer_codes(
            ["000001", "000002", "600000", "600519"], None
        ) == ["000001", "000002", "600000"]

    def test_llm_schema_exposes_peer_codes(self):
        """工具 schema 对 LLM 可见 peer_codes（build_schema_from_function 从签名内省）。"""
        agent = build_agent(mode="deep", api_key="test-key")
        schemas = agent.tools.get_schemas_for_llm()
        rda = next(s for s in schemas if s.get("function", {}).get("name") == "run_deep_analysis"
                   or s.get("name") == "run_deep_analysis")
        params = rda.get("function", rda).get("parameters", {})
        assert "peer_codes" in params.get("properties", {})
```

（若 `get_schemas_for_llm()` 的实际 dict 形状与上面两种猜测都不同，读 `harness/llm_client.py` 的 `ToolSchema.to_function_dict` 以实际键路径为准调整断言——形状只改键路径，不断言内容放水。）

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_factory.py -q -k PeerCodes`
Expected: FAIL（`ImportError: _resolve_peer_codes` / 签名断言失败 / schema 无 peer_codes）

- [ ] **Step 3: Implement**

`src/finance_agent/agent_factory.py` 模块级新增（放在 `_make_run_deep_analysis` 之前）：

```python
def _resolve_peer_codes(
    llm_codes: list | None,
    closure_codes: list | None,
    exclude: str | None = None,
) -> list[str] | None:
    """对标股代码归一化（add-peer-comparison）。

    LLM 显式传参优先于请求级闭包注入；归一化=strip/剔非 6 位数字/去重/
    剔除主标的自身/上限 3 只。全无效返回 None（不阻断主标的分析）。
    """
    raw = llm_codes if llm_codes else closure_codes
    if not raw:
        return None
    seen: list[str] = []
    for c in raw:
        s = str(c).strip()
        if len(s) == 6 and s.isdigit() and s != exclude and s not in seen:
            seen.append(s)
    return seen[:3] or None
```

`_make_run_deep_analysis` 内：内层工具函数签名与 docstring 扩展，initial_state 改用归一化结果。注意外层闭包参数与内层参数同名——闭包值先另存：

```python
    # LLM 工具参数与闭包参数同名：闭包值另存，内层 peer_codes 为 LLM 显式传参
    _closure_peer_codes = peer_codes

    async def run_deep_analysis(
        stock_code: str, stock_name: str = "", peer_codes: list[str] | None = None
    ):
        """运行 5 层深度分析管线

        Args:
            stock_code: A 股股票代码，如 "600519"
            stock_name: 股票名称，如 "贵州茅台"
            peer_codes: 对比请求时的对标股代码列表（1-3 个 6 位代码，须先经
                search_stock 解析确认）；非对比请求留空。同业对比会注入主标的报告，
                不要为对比发起多次调用
        """
```

`initial_state` 里 `"peer_codes": peer_codes` 改为：

```python
            "peer_codes": _resolve_peer_codes(peer_codes, _closure_peer_codes, exclude=stock_code),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_factory.py tests/test_agent_factory_testing_branch.py -q`
Expected: 全 PASS（含存量工具注册/TESTING stub 用例）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/agent_factory.py tests/test_agent_factory.py
git commit -m "feat(peer-comparison): run_deep_analysis 暴露 peer_codes 参数（显式优先于闭包）"
```

---

### Task 4: deep_mode 类型 D 分支 + fundamental 消费指令 + prompt 契约测试

**Files:**
- Modify: `src/finance_agent/prompts/deep_mode.md`（核心约束 3 改写、新增类型 D、澄清规则 2 修订、Tool Policy 更新）
- Modify: `src/finance_agent/prompts/fundamental_analyst.md`（分析要点新增第 13 条）
- Test: `tests/test_prompt_contracts.py`

**Interfaces:**
- Consumes: Task 3 的工具参数 `peer_codes`（prompt 文档与工具签名逐字一致）
- Produces: prompt 文本契约——契约测试锚定的关键串：deep_mode 含「类型 D」「peer_codes」「单次」；fundamental_analyst 含「同业对比材料消费」「peer_comparison」「—」

- [ ] **Step 1: Write the failing tests**

`tests/test_prompt_contracts.py` 追加（`_load` 辅助函数既有）：

```python
class TestDeepModePeerComparison:
    def test_has_peer_comparison_branch(self):
        text = _load("deep_mode.md")
        assert "类型 D" in text
        assert "peer_codes" in text

    def test_single_pipeline_constraint_preserved(self):
        """对比=单次管线：禁止多跑的纪律仍在。"""
        text = _load("deep_mode.md")
        assert "单次" in text
        assert "禁止为多标的分别发起多次完整分析" in text

    def test_ambiguous_primary_disclosure(self):
        text = _load("deep_mode.md")
        assert "已以" in text and "主视角" in text


class TestFundamentalPeerConsumption:
    def test_has_peer_consumption_rule(self):
        text = _load("fundamental_analyst.md")
        assert "同业对比材料消费" in text
        assert "peer_comparison" in text

    def test_missing_marker_and_caliber(self):
        text = _load("fundamental_analyst.md")
        assert "—" in text  # 缺失标记不得虚构补齐
        assert "口径" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_contracts.py -q -k "PeerComparison or PeerConsumption"`
Expected: FAIL（断言串不存在）

- [ ] **Step 3: Edit prompts**

`src/finance_agent/prompts/deep_mode.md` 四处修改：

① 核心约束 3（现 18 行）改为：

```markdown
3. 多标的对比请求：以主标的+对标股形态在单次管线内完成（见「类型 D」）；不做多股票串行分析（每只各跑一次完整管线）
```

② 「类型 C：追问指代」之后新增分支：

```markdown
### 类型 D：点名多标的对比

用户在同一输入中点名两只及以上明确标的并要求对比（如"对比 A 和 B"、"A 和 B 哪个好"、"分析 A 对比 B"）：

1. 确定主标的：以用户语义的被分析主体为主标的；无法判定时取点名顺序的第一只，并在应答中说明"已以 X 为主视角，回复可换 Y 为主视角重跑"
2. 用 search_stock 逐个解析全部标的为 6 位代码；解析失败的标的剔除并在应答中告知
3. 单次调用 run_deep_analysis(stock_code=主标的, stock_name=主标的名称, peer_codes=[对标股代码])
4. 对标股最多 3 只，超出截断并告知被舍弃的标的
5. 禁止为多标的分别发起多次完整分析——同业对比会以「主标的+对标股」形态注入主标的报告基本面章节
```

③ 澄清状态规则 2（现 83-86 行）改为：

```markdown
2. 用户回复多只（如"都分析"、"1 和 2"）：
   - 先判意图：想对比几只 → 按类型 D 处理（主标的=序号第一只，其余为 peer_codes）
   - 想分别完整分析多只 → 告知"一次只能分析一只股票"
   - 要求用户指定一只，给出示例："回复'1'我将分析中际旭创"
   - 用户指定后再执行
```

④ Tool Policy 的 run_deep_analysis 条目（现 107 行）改为：

```markdown
- run_deep_analysis: 股票代码已确认且用户意图明确后调用，运行 5 层分析管线。每次只分析一只股票。对比请求通过 peer_codes 传入 1-3 只对标股代码（须先经 search_stock 解析），同业对比会注入主标的报告，不要为对比发起多次调用。
```

`src/finance_agent/prompts/fundamental_analyst.md` 分析要点第 12 条之后新增：

```markdown
13. 同业对比材料消费：输入含「同业对比（state 键 peer_comparison）」时，分析中 MUST 产出
   同业对比段——对照主标的与各对标股的估值（PE/PB/总市值）与最新报告期财务（营收同比/
   归母净利同比/毛利率），结合相对估值得出结论。口径标注：估值为行情快照口径、财务为
   最新报告期累计同比口径（各行报告期以表中「报告期」列为准）。对比段数值 MUST 全部
   来自该材料；「—」为缺失标记，不得虚构补齐；材料缺席时不得编造同业数据
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_contracts.py -q`
Expected: 全 PASS（含存量 prompt 契约）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/prompts/deep_mode.md src/finance_agent/prompts/fundamental_analyst.md tests/test_prompt_contracts.py
git commit -m "feat(peer-comparison): deep_mode 类型 D 对比分支 + 基本面同业材料消费指令"
```

---

## Self-Review 记录

- **Spec 覆盖**：delta 四需求 ↔ 任务映射——对比请求识别（Task 4 prompt）；对标股参数传递含显式优先/剔除/截断（Task 3）；格式化注入含降级标注/无 peer 不注入（Task 2）；报告对比段呈现含溯源/缺失声明（Task 4 prompt + Task 2 材料结构）；analyst-data-sources MODIFIED 五场景（Task 1 测试覆盖：扩展列/字段组降级/市值缺失 + 存量三场景回归）
- **存量回归锚点**：`tests/data/test_akshare_client.py` 三个 peer 类、`tests/nodes/test_compute.py`、`tests/test_agent_factory*.py`、`tests/test_prompt_contracts.py` 全量绿
- **类型一致性**：`format_peer_comparison(state, valuation_snapshot)` 在 Task 2 定义/消费一致；`_resolve_peer_codes(llm, closure, exclude)` 在 Task 3 定义/测试一致；列契约逐字贯穿 Task 1→2
- **部署外置**：prompt 发布（deploy_prompts.py 指纹取证）与实跑人工验证不在本计划任务内，属合并后运维/验收步骤（tasks.md 已列）
