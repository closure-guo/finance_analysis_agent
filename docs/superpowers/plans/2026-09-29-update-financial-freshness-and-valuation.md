# update-financial-freshness-and-valuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复拓荆科技报告暴露的三处结构性缺陷——财报数据只看年报（中报毛利率回升/负债率下降系统性失明）、估值链路断裂（PE 缺失被伪文案掩盖、市值从不进 LLM 上下文）、红黄绿灯阈值无半导体设备行业覆盖。

**Architecture:** 增量数据段方案：不动现有年报口径指标计算（ROE/杜邦/健康度全基于年报序列），新鲜度以「最新报告期快照 + 季度扩展字段」注入；估值以「compute 层 TTM 推导 + 诚实缺数文案 + 估值快照进上下文」修复；行业阈值走既有 INDUSTRY_OVERRIDES 覆盖机制。

**Tech Stack:** Python 3.12 / pandas / pytest / akshare（数据源）/ OpenSpec delta `update-financial-freshness-and-valuation`。

## Global Constraints

- **工作目录**: 一切实施在 `.worktrees/fin-freshness-valuation/`（分支 `feat/fin-freshness-valuation`），不得动主检出（有并发会话）。下文路径均相对 worktree 根。
- **TDD 铁律**: 没有先写失败测试的代码 → 删除重写。每个任务先红后绿再提交。
- **不改年报口径指标**: profitability/solvency/efficiency/cashflow/dupont/growth_rates 全部保持年报序列计算不变。
- **不产出伪值**: 任何推导输入缺失时结果为 None + 缺失原因，MUST NOT 产出 0/无穷/NaN 占位。
- **诚实文案**: 数据缺失与比较失败在 failures/details 分桶，缺失 MUST NOT 渲染成比较失败。
- **prompt 变更**: 改 `fundamental_analyst.md` 后必须 `uv run python scripts/deploy_prompts.py`，否则 eval 门禁拒绝运行。
- **Lint/类型**: 每任务提交前 `uv run ruff check src tests` 与 `uv run mypy` 对改动文件无新告警。
- **Commit 格式**: 常规 `feat(data): ...` / `fix(metrics): ...` 中文描述；不 push（收口后统一处理 PR）。
- **验收锚点（拓荆 688072 真实数）**: 中报毛利率 ≈41.0%（29.13 亿/17.18 亿）、负债率 ≈47.85%、存货 88.33 亿、合同负债 51.31 亿、TTM 归母净利 ≈21.76 亿（9.27−0.94+13.43）、市值 1910.23 亿 → PE_ttm ≈ 87.8；半导体设备阈值校准：存货周转 (1.2, 0.5) / 速动比率 (1.5, 0.6) / 应付账款周转率 (4.5, 1.5)。
- **东财单季利润表列名**（实测定）: `REPORT_DATE` / `PARENT_NETPROFIT` / `OPERATE_INCOME` / `OPERATE_COST`（单季口径）。

---

### Task 0: 携带 delta/incident 入分支 + 台账登记

**Files:**
- Modify: `docs/evals/metrics.md`（§1.9 之后新增 §1.10）
- 已拷贝待提交: `openspec/changes/update-financial-freshness-and-valuation/`（4 工件）、`docs/incidents/033-stale-financials-valuation-chain-break-20260929.md`、`docs/incidents/README.md`

**Interfaces:**
- Consumes: 无
- Produces: 台账切点声明「健康度评分自本 delta 起携带 industry_override 口径标注」——后续 Task 9 的行为依据

- [ ] **Step 1: 在 docs/evals/metrics.md §1.9 与 `---` 之间插入 §1.10**

```markdown
### 1.10 健康度/红黄绿灯行业口径（delta `update-financial-freshness-and-valuation`，2026-09-29 登记）

| 项 | 口径 |
|---|---|
| 定义 | 红黄绿灯/健康度评分新增行业阈值覆盖机制的行业实例：半导体设备（存货周转率 (1.2, 0.5) / 速动比率 (1.5, 0.6) / 应付账款周转率 (4.5, 1.5)，higher_is_better），校准依据 = 5 家代表公司（北方华创/中微/拓荆/芯源微/华海清科）FY2025 指标分布（design.md 附表） |
| 切点 | 覆盖生效起，健康度评分输出携带 `industry_override`（行业名+覆盖指标清单）；无覆盖时标注通用口径。**跨切点健康度分数不可直接对照**（拓荆 40 分为旧口径值） |
| 影响范围 | 仅灯色评判定性，不改四维度指标数值与年报序列口径 |
```

- [ ] **Step 2: 提交 delta/incident/台账**

```bash
git add openspec/changes/update-financial-freshness-and-valuation docs/incidents/033-stale-financials-valuation-chain-break-20260929.md docs/incidents/README.md docs/evals/metrics.md
git commit -m "docs(openspec): 立 delta update-financial-freshness-and-valuation + incident 033 + 台账 §1.10"
```

---

### Task 1: fetch_quarterly_income 扩展单季营收/营业成本

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py:343-414`（fetch_quarterly_income）
- Test: `tests/data/test_akshare_client.py`（新增 TestFetchQuarterlyIncomeExtended 类）

**Interfaces:**
- Consumes: 东财 `stock_profit_sheet_by_quarterly_em`（列 REPORT_DATE/PARENT_NETPROFIT/OPERATE_INCOME/OPERATE_COST）
- Produces: 返回 DataFrame 新增列 `营业收入(单季)`、`营业成本(单季)`（float，元；缺失为 None）——Task 2 消费

- [ ] **Step 1: 写失败测试**（追加到 tests/data/test_akshare_client.py 末尾）

```python
class TestFetchQuarterlyIncomeExtended:
    """季度利润表扩展：单季营收/营业成本列。"""

    @staticmethod
    def _quarterly_df() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "REPORT_DATE": pd.to_datetime(
                    ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30"]
                ),
                "PARENT_NETPROFIT": [7.72e8, 5.71e8, 3.70e8, 0.94e8],
                "OPERATE_INCOME": [1.80e9, 1.12e9, 2.10e9, 0.95e9],
                "OPERATE_COST": [1.07e9, 0.68e9, 1.30e9, 0.65e9],
            }
        )

    @patch("finance_agent.data.akshare_client.ak")
    def test_revenue_and_cost_columns_present(self, mock_ak, client):
        mock_ak.stock_profit_sheet_by_quarterly_em.return_value = self._quarterly_df()
        df = client.fetch_quarterly_income("688072", quarters=2)
        assert "营业收入(单季)" in df.columns
        assert "营业成本(单季)" in df.columns
        row = df[df["季度"] == "2026Q2"].iloc[0]
        assert row["营业收入(单季)"] == 1.80e9
        assert row["营业成本(单季)"] == 1.07e9

    @patch("finance_agent.data.akshare_client.ak")
    def test_missing_cost_yields_none_not_zero(self, mock_ak, client):
        df_partial = self._quarterly_df().drop(columns=["OPERATE_COST"])
        mock_ak.stock_profit_sheet_by_quarterly_em.return_value = df_partial
        df = client.fetch_quarterly_income("688072", quarters=4)
        assert df["营业成本(单季)"].isna().all()
        assert df["营业收入(单季)"].notna().all()
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/data/test_akshare_client.py::TestFetchQuarterlyIncomeExtended -v` → FAIL（列不存在）

- [ ] **Step 3: 最小实现**（fetch_quarterly_income 的 records.append dict 增两键）

```python
            rev = row.get("OPERATE_INCOME")
            cost = row.get("OPERATE_COST")
            records.append(
                {
                    "报告日": str(row["REPORT_DATE"])[:10],
                    "季度": curr_q,
                    "归母净利润(单季)": float(curr_np),
                    "营业收入(单季)": float(rev) if not pd.isna(rev) else None,
                    "营业成本(单季)": float(cost) if not pd.isna(cost) else None,
                    "环比": float(qoq) if not pd.isna(qoq) else None,
                    "同比": yoy,
                }
            )
```

- [ ] **Step 4: 跑绿** — 同 Step 2 命令 → PASS；再跑该文件全量确认无回归
- [ ] **Step 5: Commit** — `git commit -m "feat(data): 季度利润表扩展单季营收/营业成本列（update-financial-freshness-and-valuation Task 1）"`

---

### Task 2: quarterly_trend 增加营收同比与单季毛利率序列

**Files:**
- Modify: `src/finance_agent/nodes/compute.py:267-315`（_calc_quarterly_trend）
- Test: `tests/nodes/` 下现有 compute 测试文件（`ls tests/nodes/` 找 test_compute*，无则新建 `tests/nodes/test_compute_quarterly_trend.py`，类内自建 q_income DataFrame 直调 `_calc_quarterly_trend`）

**Interfaces:**
- Consumes: Task 1 的 `营业收入(单季)`/`营业成本(单季)` 列
- Produces: `quarterly_trend` dict 新增键 `revenue`（亿元, round 2）、`revenue_yoy`（%, round 2 或 None）、`gross_margin`（%, round 2 或 None）——Task 8 上下文注入与 Task 11 citation 抽验消费

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from finance_agent.nodes.compute import _calc_quarterly_trend


def _q_income() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "季度": ["2026Q2", "2026Q1", "2025Q4", "2025Q3"],
            "归母净利润(单季)": [7.72e8, 5.71e8, 3.70e8, 4.62e8],
            "营业收入(单季)": [1.80e9, 1.12e9, 2.10e9, 0.95e9],
            "营业成本(单季)": [1.07e9, 0.68e9, 1.30e9, 0.65e9],
            "环比": [35.32, 54.13, -19.91, 91.60],
            "同比": [220.08, 488.29, -11.20, 225.07],
        }
    )


class TestQuarterlyTrendExtended:
    def test_revenue_gross_margin_series(self):
        trend = _calc_quarterly_trend(_q_income())
        assert trend["revenue"] == [18.0, 11.2, 21.0, 9.5]
        # 2026Q2: 1 - 10.7/18.0 = 40.56%
        assert trend["gross_margin"][0] == 40.56
        assert trend["gross_margin"][2] == 38.1

    def test_revenue_yoy_same_quarter_prev_year(self):
        trend = _calc_quarterly_trend(_q_income())
        # 2026Q2 vs 2025Q2 缺失 → None；2026Q1 同理；2025Q4/2025Q3 无 2024 数据 → None
        assert trend["revenue_yoy"] == [None, None, None, None]

    def test_missing_cost_yields_none_margin(self):
        df = _q_income()
        df.loc[df["季度"] == "2025Q3", "营业成本(单季)"] = None
        trend = _calc_quarterly_trend(df)
        assert trend["gross_margin"][3] is None

    def test_revenue_yoy_computed_when_prev_year_present(self):
        df = _q_income()
        extra = pd.DataFrame(
            {
                "季度": ["2025Q2"],
                "归母净利润(单季)": [0.94e8],
                "营业收入(单季)": [0.95e9],
                "营业成本(单季)": [0.65e9],
                "环比": [10.0],
                "同比": [50.0],
            }
        )
        trend = _calc_quarterly_trend(pd.concat([df, extra], ignore_index=True))
        # 2026Q2 vs 2025Q2: (18.0 - 9.5) / 9.5 * 100 = 89.47
        assert trend["revenue_yoy"][0] == 89.47
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/nodes/test_compute_quarterly_trend.py -v` → FAIL（KeyError 'revenue'）

- [ ] **Step 3: 最小实现**（_calc_quarterly_trend）

```python
    trend: dict = {
        "quarters": [],
        "net_profit": [],
        "revenue": [],
        "revenue_yoy": [],
        "gross_margin": [],
        "qoq": [],
        "yoy": [],
        "warnings": [],
    }

    for _, row in q_income.iterrows():
        trend["quarters"].append(row.get("季度", ""))
        np_val = row.get("归母净利润(单季)")
        trend["net_profit"].append(round(np_val / 1e8, 2) if pd.notna(np_val) else None)
        rev = row.get("营业收入(单季)")
        cost = row.get("营业成本(单季)")
        trend["revenue"].append(round(rev / 1e8, 2) if pd.notna(rev) else None)
        if pd.notna(rev) and pd.notna(cost) and rev:
            trend["gross_margin"].append(round((1 - cost / rev) * 100, 2))
        else:
            trend["gross_margin"].append(None)
        qoq = row.get("环比")
        trend["qoq"].append(qoq)
        yoy = row.get("同比")
        trend["yoy"].append(yoy)

    # 营收同比：去年同期（同季度标签上一年）
    rev_by_q = {q: r for q, r in zip(trend["quarters"], trend["revenue"]) if r is not None}
    for q, r in zip(trend["quarters"], trend["revenue"]):
        prev = None
        if r is not None and q:
            prev_q = f"{int(q[:4]) - 1}{q[4:]}"
            prev = rev_by_q.get(prev_q)
        trend["revenue_yoy"].append(round((r - prev) / prev * 100, 2) if prev else None)
```

- [ ] **Step 4: 跑绿** — 同 Step 2 → PASS；`uv run pytest tests/nodes/ -q` 无回归
- [ ] **Step 5: Commit** — `git commit -m "feat(metrics): quarterly_trend 增单季营收同比与毛利率序列（Task 2）"`

---

### Task 3: fetch_latest_period_snapshot（最新报告期快照）

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py`（AKShareClient 内新增方法，置于 fetch_quarterly_income 之后）
- Test: `tests/data/test_akshare_client.py`（新增 TestFetchLatestPeriodSnapshot）

**Interfaces:**
- Consumes: `_sina_report(stock, "利润表"/"资产负债表")`（全报告期原始数据）、`_rename_parent_cols`
- Produces: `fetch_latest_period_snapshot(stock_code: str) -> dict`，schema（金额单位亿元、比率%）：
  `{"报告日": str, "期类型": "一季报"|"中报"|"三季报"|"年报", "营业总收入(累计)": float, "归母净利润(累计)": float, "营业成本(累计)": float, "毛利率(%)": float, "资产负债率(%)": float, "存货": float, "合同负债": float, "上年同期营业总收入": float|None, "上年同期归母净利润": float|None, "营收同比(%)": float|None, "归母净利同比(%)": float|None, "missing": list[str]}`
  金额字段均亿元 round 2；无同期数据 → 同比 None + missing 标注；利润表整体失败 → raise（由 fetch.py 降级）——Task 4/5/8/11 消费

- [ ] **Step 1: 写失败测试**

```python
class TestFetchLatestPeriodSnapshot:
    """最新报告期快照：不限年报，取最新已披露报告期。"""

    @staticmethod
    def _inc_df() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "报告日": ["20260630", "20251231", "20250630", "20241231"],
                "营业总收入": [2912864261.46, 6519094874.63, 1954146173.65, 5000000000.0],
                "营业成本": [1718464963.55, 4240523945.89, 1329638462.72, 3200000000.0],
                "归母净利润": [1342753980.93, 927000000.0, 94000000.0, 700000000.0],
            }
        )

    @staticmethod
    def _bs_df() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "报告日": ["20260630", "20251231", "20250630"],
                "资产总计": [25312149848.91, 19823566917.19, 17553660550.0],
                "负债合计": [12112639298.53, 12708096577.24, 12127248749.77],
                "存货": [8832503986.79, 7825778934.48, 8322530306.59],
                "合同负债": [5130654458.79, 4851847248.0, 4535774320.25],
            }
        )

    @patch("finance_agent.data.akshare_client.ak")
    def test_snapshot_from_h1_report(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.side_effect = (
            lambda stock, symbol: self._inc_df() if symbol == "利润表" else self._bs_df()
        )
        snap = client.fetch_latest_period_snapshot("688072")
        assert snap["报告日"] == "2026-06-30"
        assert snap["期类型"] == "中报"
        assert snap["营业总收入(累计)"] == 29.13
        assert snap["归母净利润(累计)"] == 13.43
        # 毛利率 = 1 - 17.18/29.13 = 41.0%
        assert snap["毛利率(%)"] == 41.0
        # 负债率 = 121.13/253.12 = 47.85%
        assert snap["资产负债率(%)"] == 47.85
        assert snap["存货"] == 88.33
        assert snap["合同负债"] == 51.31

    @patch("finance_agent.data.akshare_client.ak")
    def test_yoy_vs_same_period_prior_year(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.side_effect = (
            lambda stock, symbol: self._inc_df() if symbol == "利润表" else self._bs_df()
        )
        snap = client.fetch_latest_period_snapshot("688072")
        # 营收同比 = (29.13 - 19.54)/19.54 = 49.08%
        assert snap["营收同比(%)"] == 49.08
        assert snap["上年同期归母净利润"] == 0.94
        # 归母净利同比 = (13.43 - 0.94)/0.94 = 1328.72%
        assert snap["归母净利同比(%)"] == 1328.72

    @patch("finance_agent.data.akshare_client.ak")
    def test_no_prior_period_yoy_none_marked_missing(self, mock_ak, client):
        inc = self._inc_df()[self._inc_df()["报告日"] != "20250630"]
        mock_ak.stock_financial_report_sina.side_effect = (
            lambda stock, symbol: inc if symbol == "利润表" else self._bs_df()
        )
        snap = client.fetch_latest_period_snapshot("688072")
        assert snap["营收同比(%)"] is None
        assert "上年同期数据缺失" in " ".join(snap["missing"])

    @patch("finance_agent.data.akshare_client.ak")
    def test_balance_sheet_missing_fields_partial_snapshot(self, mock_ak, client):
        bs = pd.DataFrame({"报告日": ["20260630"]})
        mock_ak.stock_financial_report_sina.side_effect = (
            lambda stock, symbol: self._inc_df() if symbol == "利润表" else bs
        )
        snap = client.fetch_latest_period_snapshot("688072")
        assert snap["存货"] is None
        assert "存货" in snap["missing"]
        assert snap["毛利率(%)"] == 41.0  # 利润表部分照常装配

    @patch("finance_agent.data.akshare_client.ak")
    def test_income_statement_failure_raises(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.side_effect = ConnectionError("RST")
        with pytest.raises(Exception):
            client.fetch_latest_period_snapshot("688072")
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/data/test_akshare_client.py::TestFetchLatestPeriodSnapshot -v` → FAIL（方法不存在）

- [ ] **Step 3: 最小实现**（AKShareClient 内、fetch_quarterly_income 之后）

```python
    _PERIOD_TYPE = {"1231": "年报", "0630": "中报", "0331": "一季报", "0930": "三季报"}

    @staticmethod
    def _yi(v) -> float | None:
        """元 → 亿元，round 2；缺失返回 None。"""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return round(float(v) / 1e8, 2)

    def fetch_latest_period_snapshot(self, stock_code: str) -> dict:
        """最新报告期快照（不限年报）：中报/季报关键科目 + 同比，供基本面分析消费。

        金额单位亿元、比率%；同期数据缺失时同比为 None 并在 missing 标注。
        利润表整体不可用时 raise（由 fetch 层降级）；资产负债表缺失降级为部分快照。
        """
        stock = _add_prefix(stock_code)
        inc = _sina_report(stock, "利润表")
        if inc.empty:
            raise ValueError(f"股票 {stock_code} 利润表数据不可用")
        inc = self._rename_parent_cols(inc)
        inc = inc.sort_values("报告日", ascending=False).reset_index(drop=True)
        latest = inc.iloc[0]
        report_date = str(latest["报告日"])[:10]
        period_type = self._PERIOD_TYPE.get(report_date[4:], "定期报告")

        missing: list[str] = []

        revenue = self._yi(latest.get("营业总收入"))
        cost = self._yi(latest.get("营业成本"))
        np_attr = self._yi(latest.get("归母净利润") or latest.get("归属于母公司股东的净利润"))
        gross_margin = (
            round((1 - latest["营业成本"] / latest["营业总收入"]) * 100, 2)
            if revenue not in (None, 0) and cost is not None
            else None
        )
        if gross_margin is None:
            missing.append("毛利率")

        # 同期数据（上一年同月日）
        prior_mask = inc["报告日"].astype(str).str.startswith(report_date[:4])
        prior_mask = (
            inc["报告日"].astype(str).str.slice(4) == report_date[4:]
        ) & (inc["报告日"].astype(str).str.slice(0, 4) == str(int(report_date[:4]) - 1))
        prior_rows = inc[prior_mask]
        if prior_rows.empty:
            prior_rev = prior_np = None
            missing.append("上年同期数据缺失")
        else:
            prior = prior_rows.iloc[0]
            prior_rev = self._yi(prior.get("营业总收入"))
            prior_np = self._yi(prior.get("归母净利润") or prior.get("归属于母公司股东的净利润"))
        rev_yoy = (
            round((revenue - prior_rev) / abs(prior_rev) * 100, 2)
            if revenue is not None and prior_rev not in (None, 0)
            else None
        )
        np_yoy = (
            round((np_attr - prior_np) / abs(prior_np) * 100, 2)
            if np_attr is not None and prior_np not in (None, 0)
            else None
        )

        # 资产负债表（取同一报告日；缺失取最新一期并标注）
        snap: dict = {
            "报告日": report_date,
            "期类型": period_type,
            "营业总收入(累计)": revenue,
            "归母净利润(累计)": np_attr,
            "营业成本(累计)": cost,
            "毛利率(%)": gross_margin,
            "资产负债率(%)": None,
            "存货": None,
            "合同负债": None,
            "上年同期营业总收入": prior_rev,
            "上年同期归母净利润": prior_np,
            "营收同比(%)": rev_yoy,
            "归母净利同比(%)": np_yoy,
            "missing": missing,
        }

        bs = _sina_report(stock, "资产负债表")
        if not bs.empty:
            bs = bs.sort_values("报告日", ascending=False).reset_index(drop=True)
            bs_rows = bs[bs["报告日"].astype(str).str.startswith(report_date.replace("-", ""))]
            row_bs = bs_rows.iloc[0] if not bs_rows.empty else bs.iloc[0]
            assets = self._yi(row_bs.get("资产总计"))
            liab = self._yi(row_bs.get("负债合计"))
            snap["存货"] = self._yi(row_bs.get("存货"))
            snap["合同负债"] = self._yi(row_bs.get("合同负债"))
            if assets not in (None, 0) and liab is not None:
                snap["资产负债率(%)"] = round(liab / assets * 100, 2)
            else:
                missing.append("资产负债率")
            if snap["存货"] is None:
                missing.append("存货")
            if snap["合同负债"] is None:
                missing.append("合同负债")
        else:
            missing.extend(["资产负债率", "存货", "合同负债"])
        return snap
```

（注意：`prior_mask` 只保留第二个赋值，第一个是死代码，实现时只写正确的那行。资产负债率旧值 vs 中报新值差异本身即 Task 8 要求 LLM 并陈的素材，不在此做口径合并。）

- [ ] **Step 4: 跑绿** — 同 Step 2 → PASS；该测试文件全量无回归
- [ ] **Step 5: Commit** — `git commit -m "feat(data): 新增 fetch_latest_period_snapshot 最新报告期快照（Task 3）"`

---

### Task 4: fetch.py 接线 latest_period_snapshot

**Files:**
- Modify: `src/finance_agent/nodes/fetch.py:128-137`（_set_optional_fallback）、`:196-200`（futures）、`:255-262` 附近（结果处理）、except 分支
- Test: `tests/nodes/` 新增 fetch 接线测试（mock client 对象即可——fetch_data(state, cache=None, client=fake) 支持注入 client）

**Interfaces:**
- Consumes: Task 3 的 `fetch_latest_period_snapshot`
- Produces: state 键 `latest_period_snapshot`（dict）；总失败 → `{}` + ERROR 日志（区别于其他 optional 的 warning）；TESTING=1 stub 路径同步加桩数据

- [ ] **Step 1: 写失败测试**（tests/nodes/test_fetch_snapshot.py）

```python
from finance_agent.nodes.fetch import fetch_data


class _FakeClient:
    """最小 client stub：只实现 snapshot 用到的接口，其余抛错走 optional 降级。"""

    def fetch_latest_period_snapshot(self, code: str) -> dict:
        return {"报告日": "2026-06-30", "期类型": "中报", "毛利率(%)": 41.0}

    def __getattr__(self, name):
        def _raise(*a, **k):
            raise ConnectionError(f"{name} unavailable")

        return _raise


class _BrokenClient(_FakeClient):
    def fetch_latest_period_snapshot(self, code: str) -> dict:
        raise ConnectionError("snapshot source down")


def test_fetch_wires_snapshot(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    result = fetch_data({"stock_code": "688072"}, cache=None, client=_FakeClient())
    assert result["latest_period_snapshot"]["毛利率(%)"] == 41.0


def test_fetch_snapshot_failure_degrades_to_empty_dict(monkeypatch, caplog):
    monkeypatch.delenv("TESTING", raising=False)
    with caplog.at_level("ERROR"):
        result = fetch_data({"stock_code": "688072"}, cache=None, client=_BrokenClient())
    assert result["latest_period_snapshot"] == {}
    assert any("latest_period_snapshot" in r.message for r in caplog.records if r.levelname == "ERROR")
```

（注意：fetch_data 必需数据 balance/income/cashflow 失败会 raise 终止管线——FakeClient 让它们也抛错会导致测试失败。实现者须先读 fetch_data 确认必需数据失败路径，FakeClient 改为：三大报表返回 `pd.DataFrame({"报告日": []})` 触发 ValueError→同样 raise… 不可行。**正确做法**：FakeClient 对三大报表返回最小合法 DataFrame（2 行年报，参照 tests/ 内现有 fetch 测试的 stub 数据），或改测 `_set_optional_fallback`/收集逻辑的单元边界。实现者按现有 tests/data/test_data_coverage_fetchers.py 的既定模式处理——该文件已测过 optional 降级，直接扩展。）

- [ ] **Step 2: 跑红** — `uv run pytest tests/data/test_data_coverage_fetchers.py -v` → FAIL（键不存在）
- [ ] **Step 3: 最小实现**

`_set_optional_fallback` 的 fallback dict 增 `"latest_period_snapshot": {}`；futures 增：

```python
        futures[pool.submit(ak.fetch_latest_period_snapshot, code)] = "latest_period_snapshot"
```

成功分支增：

```python
            elif label == "latest_period_snapshot":
                c.set(f"{code}:latest_period_snapshot", value, ttl_seconds=2_592_000)
                result["latest_period_snapshot"] = value
```

失败分支在现有 warning 前特判：

```python
                    if label == "latest_period_snapshot":
                        logger.error("最新报告期快照获取失败，估值外的最新期数据缺失: %s", e)
                    else:
                        logger.warning("%s 拉取失败: %s", label, e)
```

`_stub_fetch_data` 增桩：

```python
        "latest_period_snapshot": {
            "报告日": "2025-12-31",
            "期类型": "年报",
            "营业总收入(累计)": 65.19,
            "归母净利润(累计)": 9.27,
            "营业成本(累计)": 42.41,
            "毛利率(%)": 34.95,
            "资产负债率(%)": 64.11,
            "存货": 78.26,
            "合同负债": 48.52,
            "上年同期营业总收入": 41.03,
            "上年同期归母净利润": 6.88,
            "营收同比(%)": 58.87,
            "归母净利同比(%)": 34.74,
            "missing": [],
        },
```

- [ ] **Step 4: 跑绿 + `TESTING=1` 相关测试无回归**（test_pipeline_stub.py）
- [ ] **Step 5: Commit** — `git commit -m "feat(fetch): 接线 latest_period_snapshot（失败降级空 dict + ERROR 日志）（Task 4）"`

---

### Task 5: compute PE_ttm 推导 + valuation_snapshot 装配

**Files:**
- Modify: `src/finance_agent/nodes/compute.py`（新增 `_derive_pe_ttm`/`_build_valuation_snapshot`；compute_metrics 在 garp 之后装配）
- Test: `tests/nodes/test_compute_valuation.py`（新建）

**Interfaces:**
- Consumes: Task 3/4 的 `latest_period_snapshot`（亿元口径）、state `stock_quote`（market_cap 亿元/PB/PE）、state `income_statement`（年报归母净利润，元）
- Produces: state 键 `valuation_snapshot`：
  `{"market_cap": float|None, "PE": float|None, "PE_ttm": float|None, "PE_caliber": "static"|"derived_ttm"|None, "PB": float|None, "missing_reasons": list[str]}`
  ——Task 6（GARP 用 PE_ttm）、Task 7（相对估值）、Task 8（上下文注入）、Task 11（citation）消费

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from finance_agent.nodes.compute import _derive_pe_ttm, _build_valuation_snapshot

SNAP_H1 = {
    "报告日": "2026-06-30", "期类型": "中报",
    "归母净利润(累计)": 13.43, "上年同期归母净利润": 0.94,
    "营业总收入(累计)": 29.13, "毛利率(%)": 41.0,
}


class TestDerivePeTtm:
    def test_ttm_blended_from_h1(self):
        # 9.27 - 0.94 + 13.43 = 21.76；1910.23/21.76 = 87.78
        pe, reason = _derive_pe_ttm(1910.23, 9.27, SNAP_H1)
        assert pe == 87.78
        assert reason is None

    def test_annual_snapshot_takes_annual_value(self):
        snap = {"报告日": "2025-12-31", "期类型": "年报", "归母净利润(累计)": 9.27}
        pe, reason = _derive_pe_ttm(92.7, 9.27, snap)
        assert pe == 10.0

    def test_missing_market_cap_returns_none_with_reason(self):
        pe, reason = _derive_pe_ttm(None, 9.27, SNAP_H1)
        assert pe is None and "market_cap" in reason

    def test_missing_snapshot_returns_none_not_static_fallback(self):
        pe, reason = _derive_pe_ttm(1910.23, 9.27, {})
        assert pe is None and "快照" in reason

    def test_negative_ttm_returns_none(self):
        snap = {"报告日": "2026-06-30", "期类型": "中报", "归母净利润(累计)": -30.0, "上年同期归母净利润": 0.94}
        pe, reason = _derive_pe_ttm(100.0, 9.27, snap)
        assert pe is None and "非正" in reason


class TestBuildValuationSnapshot:
    def _state(self, quote):
        inc = pd.DataFrame(
            {"报告日": ["20251231", "20241231"], "归母净利润": [9.27e8, 6.88e8]}
        )
        return {"stock_quote": quote, "income_statement": inc, "latest_period_snapshot": SNAP_H1}

    def test_assembly_with_derived_ttm(self):
        vs = _build_valuation_snapshot(
            self._state({"market_cap": 1910.23, "PB": 15.02})
        )
        assert vs["PE"] is None
        assert vs["PE_ttm"] == 87.78
        assert vs["PE_caliber"] == "derived_ttm"
        assert vs["market_cap"] == 1910.23
        assert vs["PB"] == 15.02
        assert vs["missing_reasons"] == []

    def test_static_pe_wins_caliber_static(self):
        vs = _build_valuation_snapshot(self._state({"market_cap": 1910.23, "PE": 95.0, "PB": 15.02}))
        assert vs["PE"] == 95.0 and vs["PE_caliber"] == "static"

    def test_all_missing_reasons_listed(self):
        vs = _build_valuation_snapshot(self._state({}))
        assert vs["PE_caliber"] is None
        assert any("market_cap" in r for r in vs["missing_reasons"])
```

- [ ] **Step 2: 跑红** — `uv run pytest tests/nodes/test_compute_valuation.py -v` → FAIL（ImportError）

- [ ] **Step 3: 最小实现**（compute.py；`_derive_pe_ttm(quote_market_cap_yi, annual_np_yi, snapshot)`、`_build_valuation_snapshot(state)`）

```python
def _derive_pe_ttm(
    market_cap_yi: float | None,
    annual_np_yi: float | None,
    snapshot: dict | None,
) -> tuple[float | None, str | None]:
    """TTM PE 推导（纯规则）。市值与净利润均亿元口径。

    TTM = 年报归母净利 − 上年同期累计 + 最新累计；最新期即年报时直取年报值。
    返回 (pe_ttm, 失败原因)；输入缺失/TTM 非正 → (None, reason)。
    """
    if market_cap_yi is None or market_cap_yi <= 0:
        return None, "market_cap 缺失或非正"
    if annual_np_yi is None or annual_np_yi <= 0:
        return None, "年报归母净利润缺失或非正"
    snap = snapshot or {}
    if snap.get("期类型") == "年报":
        ttm = annual_np_yi
    else:
        cur = snap.get("归母净利润(累计)")
        prev = snap.get("上年同期归母净利润")
        if cur is None or prev is None:
            return None, "最新报告期快照缺失或同期数据缺失，无法拼合 TTM"
        ttm = annual_np_yi - prev + cur
    if ttm is None or ttm <= 0:
        return None, f"TTM 归母净利润({ttm})非正，PE 无意义"
    return round(market_cap_yi / ttm, 2), None


def _build_valuation_snapshot(state: dict) -> dict:
    """估值快照：PE/PB/市值 + PE_ttm 推导与口径标注。"""
    quote = state.get("stock_quote") or {}
    inc = state.get("income_statement")
    annual_np_yi: float | None = None
    if inc is not None and not inc.empty and "归母净利润" in inc.columns:
        v = inc.iloc[0].get("归母净利润")
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            annual_np_yi = round(float(v) / 1e8, 2)

    pe_ttm, reason = _derive_pe_ttm(
        quote.get("market_cap"), annual_np_yi, state.get("latest_period_snapshot")
    )
    static_pe = quote.get("PE") or quote.get("pe")
    if static_pe is not None:
        caliber = "static"
    elif pe_ttm is not None:
        caliber = "derived_ttm"
    else:
        caliber = None

    missing: list[str] = []
    if quote.get("market_cap") is None:
        missing.append("market_cap 缺失")
    if static_pe is None and pe_ttm is None and reason:
        missing.append(reason)
    if quote.get("PB") is None:
        missing.append("PB 缺失")
    return {
        "market_cap": quote.get("market_cap"),
        "PE": static_pe,
        "PE_ttm": pe_ttm,
        "PE_caliber": caliber,
        "PB": quote.get("PB"),
        "missing_reasons": missing,
    }
```

compute_metrics 在 garp_result 之后装配：

```python
    result["valuation_snapshot"] = _build_valuation_snapshot(state)
```

- [ ] **Step 4: 跑绿** — 同 Step 2 → PASS；`uv run pytest tests/nodes/ -q` 无回归
- [ ] **Step 5: Commit** — `git commit -m "feat(compute): PE_ttm 确定性推导 + valuation_snapshot 装配（Task 5）"`

---

### Task 6: GARP 诚实缺数分桶 + industry_pe 接线

**Files:**
- Modify: `src/finance_agent/metrics/garp.py:29-42`（PE 分支三分桶）、`src/finance_agent/nodes/compute.py:241-264`（_try_garp 读 state industry_pe）
- Test: `tests/metrics/test_garp.py`（更新既有 None 断言 + 新增缺失分桶用例）

**Interfaces:**
- Consumes: state `industry_pe`（`{"avg_pe": ...}`，fetch 已产）；valuation_snapshot 的 PE/PE_ttm（由 compute 选择有效 PE 传入）
- Produces: `calc_garp` 缺失文案 `"<指标> 数据缺失（未参与比较）"` + `details["<指标>_missing"] = True`；真实比较失败仍为 `"PE >= 行业平均"`

- [ ] **Step 1: 更新/新增测试**（先跑 `uv run pytest tests/metrics/test_garp.py -v` 看既有 None 用例；凡断言「PE=None → 'PE >= 行业平均'」的改为新文案）

```python
    def test_pe_missing_honest_message(self):
        data = {"PE": None, "industry_avg_PE": 25.0, "net_profit_growth": 0.25, "ROE": 0.20, "debt_ratio": 0.45}
        result = calc_garp(data)
        assert "PE 数据缺失（未参与比较）" in result["failures"]
        assert "PE >= 行业平均" not in result["failures"]
        assert result["details"]["PE_missing"] is True

    def test_industry_pe_missing_honest_message(self):
        data = {"PE": 20.0, "industry_avg_PE": None, "net_profit_growth": 0.25, "ROE": 0.20, "debt_ratio": 0.45}
        result = calc_garp(data)
        assert "行业平均 PE 数据缺失（未参与比较）" in result["failures"]
        assert result["details"]["PE_missing"] is True

    def test_real_comparison_failure_kept(self):
        data = {"PE": 30.0, "industry_avg_PE": 25.0, "net_profit_growth": 0.25, "ROE": 0.20, "debt_ratio": 0.45}
        result = calc_garp(data)
        assert "PE >= 行业平均" in result["failures"]
        assert "PE_missing" not in result["details"]
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**（garp.py PE 分支）

```python
    if pe is None:
        failures.append("PE 数据缺失（未参与比较）")
        details["PE"] = None
        details["PE_missing"] = True
    elif industry_pe is None:
        failures.append("行业平均 PE 数据缺失（未参与比较）")
        details["PE"] = pe
        details["PE_missing"] = True
    elif pe >= industry_pe:
        failures.append("PE >= 行业平均")
        details["PE"] = pe
    else:
        details["PE"] = pe
```

compute._try_garp 签名与取值：

```python
def _try_garp(quote, profitability, solvency, indicators, net_profit_growth, latest_year, industry_pe_avg=None):
    pe = (quote or {}).get("PE") or (quote or {}).get("pe") or (quote or {}).get("PE_ttm")
    ...
    data = {"PE": pe, "industry_avg_PE": industry_pe_avg, ...}
```

compute_metrics 调用处：`_try_garp(quote, profitability, solvency, ind, net_profit_growth, latest_year, industry_pe_avg=(state.get("industry_pe") or {}).get("avg_pe"))`。**注意 PE 优先级**：valuation_snapshot 已选好口径——改为 `vs = result["valuation_snapshot"]; pe = vs["PE"] or vs["PE_ttm"]`（valuation_snapshot 装配在 garp 之前，需将 garp 调用移到其后）。

- [ ] **Step 4: 跑绿 + tests/metrics/ 全量无回归**
- [ ] **Step 5: Commit** — `git commit -m "fix(metrics): GARP 缺数据诚实分桶 + industry_pe 接线（Task 6）"`

---

### Task 7: relative_valuation 接受 PE_ttm + 口径标注

**Files:**
- Modify: `src/finance_agent/nodes/compute.py:87-97`（relative valuation 段）
- Test: `tests/nodes/test_compute_valuation.py`（追加 TestRelativeValuationWithDerivedPe）

**Interfaces:**
- Consumes: Task 5 的 valuation_snapshot、state `peer_financials`（同业 PE/PB）
- Produces: `result["relative_valuation"]` 用有效 PE 计算；valuation_snapshot 增 `"used_in_relative": True|False`（可选，保持简单则不加——spec 只要求相对估值结论入上下文，此处取「PE 有效即可算」）

- [ ] **Step 1: 写失败测试**

```python
class TestRelativeValuationWithDerivedPe:
    def test_relative_uses_ttm_when_static_missing(self, monkeypatch):
        from finance_agent.nodes import compute as compute_mod

        state = {
            "stock_quote": {"market_cap": 1910.23, "PB": 15.02},
            "income_statement": pd.DataFrame({"报告日": ["20251231", "20241231"], "归母净利润": [9.27e8, 6.88e8]}),
            "latest_period_snapshot": SNAP_H1,
            "peer_financials": [{"name": "中微", "PE": 60.0, "PB": 10.0}, {"name": "北方华创", "PE": 50.0, "PB": 9.0}],
        }
        result = compute_mod.compute_metrics(state)
        rel = result["relative_valuation"]["PE"]
        assert rel["target"] == 87.78
        assert rel["conclusion"] == "overvalued"
```

（compute_metrics 对 state 缺键的容忍度：实现者先读 compute_metrics 开头——`state["balance_sheet"]` 等为必填键，测试 state 需补最小合法三大报表 DataFrame，参照 tests/nodes/ 既有 compute 测试的 fixture。）

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**（compute.py relative 段）

```python
    vs = result.get("valuation_snapshot") or {}
    effective_pe = vs.get("PE") or vs.get("PE_ttm")
    if peer_financials is not None and quote:
        pb = quote.get("PB") or quote.get("pb")
        if effective_pe is not None or pb is not None:
            target = {"PE": effective_pe, "PB": pb}
            peers_list = _build_peers_list(peer_financials)
            if peers_list:
                result["relative_valuation"] = calc_relative_valuation(target, peers_list)
```

- [ ] **Step 4: 跑绿**
- [ ] **Step 5: Commit** — `git commit -m "feat(compute): 相对估值接受 PE_ttm 并保持口径可辨（Task 7）"`

---

### Task 8: 分析师上下文注入估值快照 + 最新报告期快照

**Files:**
- Modify: `src/finance_agent/nodes/analysts.py:643-678`（_build_fundamental_context，GARP 段之后）
- Test: `tests/nodes/` 新增 `tests/nodes/test_fundamental_context_sections.py`（直调 context 构建函数断言段落存在/缺失声明存在——先读该函数当前签名与可见性，私有函数可 import）

**Interfaces:**
- Consumes: state `valuation_snapshot`（Task 5）、`latest_period_snapshot`（Task 3/4）、`relative_valuation`
- Produces: 基本面 context 新增两个数据段与两个缺失声明段（文案见下）——citation claim field_ref 根 `valuation_snapshot.*` / `latest_period_snapshot.*` 可引用

- [ ] **Step 1: 写失败测试**

```python
from finance_agent.nodes.analysts import _build_fundamental_context


class TestContextValuationAndSnapshot:
    def test_valuation_and_snapshot_sections_present(self):
        state = {
            "valuation_snapshot": {"market_cap": 1910.23, "PE": None, "PE_ttm": 87.78,
                                    "PE_caliber": "derived_ttm", "PB": 15.02, "missing_reasons": []},
            "latest_period_snapshot": {"报告日": "2026-06-30", "期类型": "中报", "毛利率(%)": 41.0},
        }
        ctx = _build_fundamental_context(state)
        assert "估值快照（state 键 valuation_snapshot" in ctx
        assert "PE_caliber" in ctx and "derived_ttm" in ctx
        assert "最新报告期快照（state 键 latest_period_snapshot" in ctx
        assert "累计口径" in ctx

    def test_missing_sections_declared(self):
        ctx = _build_fundamental_context({})
        assert "估值数据缺失" in ctx
        assert "最新报告期快照缺失" in ctx
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**（GARP 段之后插入）

```python
    # 估值快照（PE/PB/市值 + 推导口径）
    vsnap = state.get("valuation_snapshot")
    if vsnap:
        sections.append(
            f"估值快照（state 键 valuation_snapshot，市值单位亿元，PE_caliber 标注口径 static=主源/derived_ttm=TTM推导）:\n"
            f"{json.dumps(vsnap, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("估值数据缺失（valuation_snapshot 未生成）：估值维度不可知，报告中 MUST 显式声明，不得在无数值情况下断言贵贱")

    # 最新报告期快照（累计口径）
    snap = state.get("latest_period_snapshot")
    if snap:
        sections.append(
            f"最新报告期快照（state 键 latest_period_snapshot，利润表科目为累计口径，金额单位亿元）:\n"
            f"{json.dumps(snap, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("最新报告期快照缺失（latest_period_snapshot 为空）：年报趋势论断 MUST 附「最新报告期数据缺失」限定")
```

- [ ] **Step 4: 跑绿 + tests/test_analysts_parse.py 无回归**
- [ ] **Step 5: Commit** — `git commit -m "feat(analysts): 基本面上下文注入估值快照与最新报告期快照（Task 8）"`

---

### Task 9: 半导体设备行业阈值覆盖 + industry_override 披露

**Files:**
- Modify: `src/finance_agent/metrics/traffic_light.py`（INDUSTRY_OVERRIDES + matched_industry_overrides + compute_health_score 签名）、`src/finance_agent/nodes/compute.py:69`（传 industry）
- Test: `tests/metrics/test_traffic_light.py`（追加）

**Interfaces:**
- Consumes: 既有 `_get_thresholds` 行业覆盖机制（子串匹配）
- Produces: `matched_industry_overrides(industry) -> dict[str, tuple]`；`compute_health_score(traffic_lights, year, industry=None)` 结果 dict 增键 `industry_override: {"industry": str|None, "metrics": list[str]}`——citation 重算走 compute_metrics 同 state，口径一致

- [ ] **Step 1: 写失败测试**（追加到 tests/metrics/test_traffic_light.py）

```python
class TestSemiconductorEquipmentCoverage:
    def test_inventory_turnover_industry_thresholds(self):
        from finance_agent.metrics.traffic_light import _assess_absolute
        # 拓荆 0.56：通用阈值红灯，行业覆盖黄灯（>=0.5）
        assert _assess_absolute("存货周转率", 0.56, industry="半导体设备") == "yellow"
        assert _assess_absolute("存货周转率", 0.56, industry=None) == "red"

    def test_quick_ratio_industry_thresholds(self):
        from finance_agent.metrics.traffic_light import _assess_absolute
        assert _assess_absolute("速动比率", 0.74, industry="半导体设备") == "yellow"
        assert _assess_absolute("速动比率", 0.30, industry="半导体设备") == "red"

    def test_ap_turnover_industry_thresholds(self):
        from finance_agent.metrics.traffic_light import _assess_absolute
        assert _assess_absolute("应付账款周转率", 2.45, industry="半导体设备") == "yellow"

    def test_matched_overrides_listing(self):
        from finance_agent.metrics.traffic_light import matched_industry_overrides
        m = matched_industry_overrides("半导体设备")
        assert set(m) == {"存货周转率", "速动比率", "应付账款周转率"}
        assert matched_industry_overrides("白酒")["存货周转率"] == (0.5, 0.2, True)
        assert matched_industry_overrides(None) == {}

    def test_health_score_carries_industry_override(self):
        from finance_agent.metrics.traffic_light import compute_health_score
        lights = {"solvency": {"速动比率": {"2025": {"absolute": "yellow", "change": None, "final": "yellow"}}}}
        hs = compute_health_score(lights, "2025", industry="半导体设备")
        assert hs["industry_override"]["industry"] == "半导体设备"
        assert "速动比率" in hs["industry_override"]["metrics"]
        hs_generic = compute_health_score(lights, "2025", industry=None)
        assert hs_generic["industry_override"]["industry"] is None
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**

INDUSTRY_OVERRIDES 增：

```python
    # 半导体设备：验收确认收入+合同负债预收模式，通用制造业阈值系统性误判红灯
    # 校准：北方华创/中微/拓荆/芯源微/华海清科 FY2025 分布（design.md）：
    # 存货周转 0.56-1.06 / 速动 0.74-1.90 / 应付周转 2.08-4.26
    "半导体设备": {
        "存货周转率": (1.2, 0.5, True),
        "速动比率": (1.5, 0.6, True),
        "应付账款周转率": (4.5, 1.5, True),
    },
```

新函数（_get_thresholds 之后）：

```python
def matched_industry_overrides(industry: str | None) -> dict[str, tuple]:
    """返回该行业命中的覆盖指标集合（用于口径披露）。"""
    if not industry:
        return {}
    for key, overrides in INDUSTRY_OVERRIDES.items():
        if key in industry:
            return {m: t for m, t in overrides.items() if m in ABSOLUTE_THRESHOLDS}
    return {}
```

compute_health_score 加参并在返回 dict 增键：

```python
def compute_health_score(traffic_lights, year, industry: str | None = None) -> dict:
    ...
    matched = matched_industry_overrides(industry)
    result["industry_override"] = {
        "industry": industry if matched else None,
        "metrics": sorted(matched),
    }
    return result
```

compute.py:69：`result["health_score"] = compute_health_score(traffic_lights, latest_year, industry=industry)`

- [ ] **Step 4: 跑绿 + `uv run pytest tests/ -q -k "traffic or health or citation" ` 无回归（citation 重算 health_score 用同 state，industry_override 两边一致）**
- [ ] **Step 5: Commit** — `git commit -m "feat(metrics): 半导体设备行业阈值覆盖 + 健康度 industry_override 口径披露（Task 9）"`

---

### Task 10: fundamental_analyst.md 更新 + deploy_prompts 发布

**Files:**
- Modify: `src/finance_agent/prompts/fundamental_analyst.md`（输入清单、分析要点、claim 词表注记）
- Test: `uv run pytest tests/test_prompt_contracts.py tests/test_prompt_loader.py -v`（回归）；部署门禁见 prompt-deploy-consistency

**Interfaces:**
- Consumes: Task 8 的两个新数据段
- Produces: prompt 指示语（估值有数字依据/最新期校验年报趋势/缺数声明）

- [ ] **Step 1: prompt 修改**（三处）

「## 输入」清单增两行：

```markdown
- 估值快照（PE/PB/市值，PE_caliber 标注口径：static=主源 / derived_ttm=TTM 推导）
- 最新报告期快照（最新已披露中报/季报的毛利率、负债率、存货、合同负债与同比，累计口径）
```

「## 分析要点」增两条（置于估值条目后）：

```markdown
11. 最新报告期校验：涉及盈利能力、负债水平、存货等论断时，以最新报告期快照校验年报趋势是否已被打破；
    年报序列与最新报告期冲突时 MUST 显式说明（如「年报毛利率连续下滑，但最新中报同比回升」），不得只引其一
12. 估值结论必须有数字依据：引用估值快照的 PE/PE_ttm（注明口径）/PB/市值；估值数据缺失时显式声明
    「估值数据缺失，无法判断贵贱」，不得在无数值情况下断言估值高低
```

- [ ] **Step 2: prompt 回归** — `uv run pytest tests/test_prompt_contracts.py tests/test_prompt_loader.py -q` → PASS（如契约测试锁了输入清单行数/字面，按实际断言更新契约并保证语义一致）
- [ ] **Step 3: 发布** — `uv run python scripts/deploy_prompts.py` → 输出 fundamental_analyst 部署成功（Langfuse 须在线）
- [ ] **Step 4: Commit** — `git commit -m "feat(prompts): 基本面分析增最新报告期校验与估值数字依据要点并发布（Task 10）"`

---

### Task 11: citation 解析覆盖新键

**Files:**
- Test: `tests/test_citation_new_keys.py`（新建）
- Modify（如解析失败）: `src/finance_agent/citation.py`（仅在有实证失败时改；不改主规范库）

**Interfaces:**
- Consumes: Task 2/5/8 产出的 `latest_period_snapshot.*` / `quarterly_trend.revenue_yoy[N]` / `valuation_snapshot.*` field_ref
- Produces: 解析通过的验证测试——`latest_period_snapshot.毛利率(%)`（dict 点路径）、`quarterly_trend.gross_margin[0]`（[N] 括号展开）两类 claim 均判 PASS/正确取值

- [ ] **Step 1: 写测试**（先读 `src/finance_agent/citation.py:1174` verify_claims 与 Claim 模型字段，按 tests/test_citation_contract.py 现有构造方式）

```python
"""新增数据键的 citation 解析验证：latest_period_snapshot / quarterly_trend 扩展 / valuation_snapshot。"""
import pandas as pd
import pytest
from finance_agent.citation import Claim, verify_claims


@pytest.fixture
def state():
    return {
        "latest_period_snapshot": {
            "报告日": "2026-06-30", "期类型": "中报",
            "毛利率(%)": 41.0, "资产负债率(%)": 47.85,
        },
        "quarterly_trend": {
            "quarters": ["2026Q2", "2026Q1"],
            "revenue": [18.0, 11.2],
            "gross_margin": [40.56, 39.29],
        },
        "valuation_snapshot": {"PE_ttm": 87.78, "PE_caliber": "derived_ttm"},
    }


def test_snapshot_dict_path_claim(state):
    claims = [Claim(agent_name="fundamental", claim_type="numerical", source_type="data",
                    field_ref="latest_period_snapshot.毛利率(%)", stated_value=41.0,
                    interpretation="中报毛利率 41.0%", metric_name="毛利率", period="2026H1")]
    results = verify_claims(claims, state)
    assert results[0].status in ("PASS", "PASS(echo)")


def test_quarterly_gross_margin_bracket_index(state):
    claims = [Claim(agent_name="fundamental", claim_type="numerical", source_type="data",
                    field_ref="quarterly_trend.gross_margin[0]", stated_value=40.56,
                    interpretation="2026Q2 单季毛利率 40.56%", metric_name="毛利率", period="2026Q2")]
    results = verify_claims(claims, state)
    assert results[0].status in ("PASS", "PASS(echo)")


def test_valuation_snapshot_derived_ttm(state):
    claims = [Claim(agent_name="fundamental", claim_type="numerical", source_type="data",
                    field_ref="valuation_snapshot.PE_ttm", stated_value=87.78,
                    interpretation="TTM PE 约 87.8 倍", metric_name="PE", period="2026Q2")]
    results = verify_claims(claims, state)
    assert results[0].status in ("PASS", "PASS(echo)")
```

（Claim 模型必填字段以 citation.py:40 实际定义为准——实现者读后补齐缺省字段，断言语义不变。若解析器对含 `%`/括号中文列名的 dict 键有歧义，按 citation.py 既有 `_resolve_field_ref` 逻辑修，不改 RED 行为语义。）

- [ ] **Step 2: 跑** — `uv run pytest tests/test_citation_new_keys.py -v`：预期多数直接 PASS（dict 路径解析已通用）；任何 FAIL 按 incident 026 纪律先分桶（解析病 → 修解析器；契约病 → 修本测试）
- [ ] **Step 3: 修复至绿（如需）+ Commit** — `git commit -m "test(citation): 新数据键 claim 解析验证（Task 11）"`

---

### Task 12: 收口验证 + 688072 实跑 + validation 报告

**Files:**
- Modify: `openspec/changes/update-financial-freshness-and-valuation/tasks.md`（回填勾选）
- Create: `tests/validation/2026-09-29-update-financial-freshness-and-valuation-validation.md`

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 验证证据 + 人工验证报告（archive 前置条件）

- [ ] **Step 1: 静态门禁**

```bash
uv run ruff check
uv run mypy
uv run pytest tests/metrics tests/nodes tests/data tests/test_citation_new_keys.py -q
```

Expected: 全绿（ruff 0 告警 / mypy 无新错误 / pytest 0 failed）

- [ ] **Step 2: 688072 真实数据实跑**（worktree 代码 + 独立端口/DB，不动主检出后端）

```bash
cd .worktrees/fin-freshness-valuation
LANGFUSE_PUBLIC_KEY=pk-lf-... LANGFUSE_SECRET_KEY=sk-lf-... \
SESSIONS_DB_PATH=data/sessions_worktree.db REPORTS_DIR=reports_worktree \
uv run uvicorn finance_agent.api:app --host 127.0.0.1 --port 8010
```

POST /api/analyze 提交 688072 深度分析，等待报告完成（LLM 真实调用，Langfuse 在线）。

- [ ] **Step 3: 报告断言**（逐条核对，全部命中才算过）

1. 基本面章节出现「最新报告期快照」数据（毛利率约 41%、负债率约 47.9%、存货/合同负债）
2. 盈利质量论断反映中报毛利率回升（与年报下滑并陈，非只引其一）
3. 估值讨论含具体数字：市值约 1910 亿、PE_ttm 约 87.8（或 PE 缺失时明示 derived_ttm 不可得的原因）
4. 健康度评分携带行业口径标注（半导体设备覆盖）
5. 无「PE >= 行业平均」伪文案（PE 缺失时为「数据缺失」表述）

- [ ] **Step 4: 人工验证报告落 tests/validation/**（模板见 project-workflow.md §3 Step 5，含 Langfuse trace id 与报告路径）
- [ ] **Step 5: 回填 tasks.md 勾选 + Commit** — `git commit -m "test(validation): update-financial-freshness-and-valuation 人工验证报告（Task 12）"`

---

## Self-Review 记录

- **Spec coverage**: delta 四 capability 逐条对照——快照获取/消费（Task 3/4/8）、季度扩展（Task 1/2）、PE 推导/诚实文案/上下文注入（Task 5/6/7/8）、行业覆盖/披露（Task 9）、citation 抽验（Task 11）、台账（Task 0）、验收（Task 12）。无缺口。
- **Placeholder scan**: 无 TBD/TODO；Task 4/11 有「实现者先读 X 按既有模式」的指引，均为给出现成参照文件而非占位。
- **Type consistency**: `latest_period_snapshot` schema（Task 3 Produces）与 Task 5 消费键（`归母净利润(累计)`/`上年同期归母净利润`/`期类型`）一致；`valuation_snapshot` schema（Task 5）与 Task 6/7/8 消费键一致；`compute_health_score(…, industry=)` 与 compute.py 调用一致。
