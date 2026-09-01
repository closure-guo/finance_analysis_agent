# harden-citation-semantic-coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 堵引用校验四类系统性缺口：context 序列语义机生头、Claim 术语/期次/内部一致性校验（分桶）、正文数字普查覆盖率、值级 FAIL 定向重试；evaluation 侧落地基准集 v1.1、citation_coverage 实验指标与 decision_grounding rubric v3。

**Architecture:** 全部校验逻辑为纯 Python 确定性代码（不调 LLM），落在 `citation.py`（校验器）+ 新模块 `metric_vocab.py`（指标词表/期次归一化）与 `citation_coverage.py`（数字普查）。citation_node 按分析师归属聚合并产出重试目标/失败明细/覆盖率 Score；routing 按桶分流，route_to_analysts 按 `citation_retry_targets` 过滤 Send；analysts context 注入机生语义头与重试反馈。evals 侧新增 `build_v11.py`（篡改生成 near_miss 四档 + semantic_mismatch 子集），rejudge/measure 扩展语义复判与子集分列披露，run.py 增加 citation_pass/citation_coverage 指标。

**Tech Stack:** Python 3.13 / pydantic / pytest / ruff / mypy；Langfuse Score（`score_current_trace`）。

## Global Constraints

- 校验器纯 Python，SHALL NOT 调 LLM；容差语义不变：数值型 `tol = max(0.01, |gt| * 0.005)`，计算型 `delta < 0.01 if gt == 0 else delta / |gt| < 0.005`。
- FAIL 桶枚举冻结：`"value_mismatch" | "path_unresolvable" | "semantic_term_mismatch" | "semantic_period_mismatch" | "internal_inconsistency"`；仅 `value_mismatch` 触发定向重试。
- Claim 新字段 `metric_name: str | None = None`、`period: str | None = None`；为 None/空串时跳过对应检查并在 result 上置 `coverage_gap=True`（显式降级 + 计数，不静默 PASS）。
- `citation_coverage` 阈值默认 `< 0.8` 告警（log WARNING + span metadata），SHALL NOT 进 after_citation 路由。
- 重试上限语义不变：`iteration_count < 3`；`citation_retry_stagnated` 降级逻辑不变；重跑后该分析师全部 claim 重新校验。
- 校验器 SHALL NOT 为 field_ref 路径解析建中文映射表（既有「单一词表」契约）；metric_vocab 的别名表仅用于 metric_name 术语核对，不参与路径解析。
- 所有新代码中文注释、类型注解齐全，`uv run ruff check` 与 `uv run mypy` 零错误。
- prompts 修改后须执行 `uv run python scripts/deploy_prompts.py` 发布（live 步骤，见文末 Live follow-ups）。
- 测试文件位置约定：校验器 → `tests/`；节点 → `tests/nodes/`；evals → `tests/evals/` 与 `tests/evals/claim_benchmark/`。

---

### Task 1: metric_vocab 模块（指标词表 + 期次/数值归一化）

**Files:**
- Create: `src/finance_agent/metric_vocab.py`
- Test: `tests/test_metric_vocab.py`

**Interfaces:**
- Produces（后续任务依赖的签名）:
  - `canonical_metric(name: str | None) -> str | None` — 别名 → 规范键；无法识别返回 None
  - `field_ref_metric_segments(field_ref: str) -> list[str]` — field_ref 去根键、去期次段、去纯整数段后的指标段
  - `field_ref_period_segment(field_ref: str) -> str | None` — 首个期次形态段（年/YYYYMMDD/YYYY-MM-DD/YYYYQn）
  - `normalize_period(period: str) -> str | None` — "2024年"→"2024"，"2026年07月份"→"2026-07"，"2026/8/28"→"2026-08-28"
  - `period_matches(declared: str, actual: str) -> bool` — 归一化后相等或互为前缀（年 ⊂ 年月 ⊂ 年月日）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metric_vocab.py
"""TDD tests for metric_vocab.py — 指标词表与期次/数值归一化。"""

from finance_agent.metric_vocab import (
    canonical_metric,
    field_ref_metric_segments,
    field_ref_period_segment,
    normalize_period,
    period_matches,
)


class TestCanonicalMetric:
    def test_chinese_canonical_passthrough(self):
        assert canonical_metric("毛利率") == "毛利率"

    def test_english_alias_maps_to_chinese(self):
        assert canonical_metric("gross_margin") == "毛利率"
        assert canonical_metric("净利率") == "净利率"
        assert canonical_metric("net margin") == "净利率"

    def test_roe_aliases(self):
        assert canonical_metric("净资产收益率") == "ROE"
        assert canonical_metric("roe") == "ROE"

    def test_technical_aliases(self):
        assert canonical_metric("MA5") == "MA"
        assert canonical_metric("布林带") == "BOLL"
        assert canonical_metric("相对强弱指数") == "RSI"

    def test_macro_aliases(self):
        assert canonical_metric("CPI") == "cpi"
        assert canonical_metric("贷款市场报价利率") == "lpr"

    def test_unknown_returns_none(self):
        assert canonical_metric("不存在的指标") is None
        assert canonical_metric(None) is None
        assert canonical_metric("") is None


class TestFieldRefSegments:
    def test_metric_dict_ref(self):
        assert field_ref_metric_segments("profitability_metrics.毛利率.2024") == ["毛利率"]

    def test_technical_ref_drops_index_and_param(self):
        assert field_ref_metric_segments("technical_indicators.MA.5.-1") == ["MA"]
        assert field_ref_metric_segments("technical_indicators.MACD.DIF.-1") == ["MACD", "DIF"]

    def test_macro_ref(self):
        assert field_ref_metric_segments("macro_indicators.cpi.0.全国-同比增长") == [
            "cpi",
            "全国-同比增长",
        ]

    def test_statement_ref_drops_date_rowkey(self):
        assert field_ref_metric_segments("income_statement.20251231.营业总收入") == ["营业总收入"]

    def test_period_segment_detection(self):
        assert field_ref_period_segment("profitability_metrics.毛利率.2024") == "2024"
        assert field_ref_period_segment("income_statement.20251231.营业总收入") == "20251231"
        assert field_ref_period_segment("technical_indicators.MA.5.-1") is None
        assert field_ref_period_segment("risk_metrics.max_drawdown") is None


class TestNormalizePeriod:
    def test_year_forms(self):
        assert normalize_period("2024") == "2024"
        assert normalize_period("2024年") == "2024"
        assert normalize_period("2024年报") == "2024"

    def test_quarter_forms(self):
        assert normalize_period("2025Q2") == "2025Q2"
        assert normalize_period("2025年二季度") == "2025Q2"
        assert normalize_period("2025q3") == "2025Q3"

    def test_date_forms(self):
        assert normalize_period("2026-08-28") == "2026-08-28"
        assert normalize_period("2026/8/5") == "2026-08-05"
        assert normalize_period("20260828") == "2026-08-28"

    def test_month_forms(self):
        assert normalize_period("2026年07月份") == "2026-07"
        assert normalize_period("2026-07") == "2026-07"

    def test_garbage_returns_none(self):
        assert normalize_period("最近") is None
        assert normalize_period("") is None


class TestPeriodMatches:
    def test_exact(self):
        assert period_matches("2024", "2024")

    def test_year_prefix_of_date(self):
        assert period_matches("2025", "20251231")
        assert period_matches("2025", "2025-12-31")
        assert period_matches("2026-08", "2026-08-28")

    def test_mismatch(self):
        assert not period_matches("2023", "2024")
        assert not period_matches("2025Q1", "2025Q2")
        assert not period_matches("2026-07", "2026-08-01")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metric_vocab.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finance_agent.metric_vocab'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/finance_agent/metric_vocab.py
"""指标词表与期次/数值归一化（harden-citation-semantic-coverage delta）。

术语一致性校验的词表来源：metrics/ 注册表键（规范键）+ 中英文别名映射。
注意边界：本模块只服务 metric_name 术语核对与 period 期次核对，
SHALL NOT 用于 field_ref 路径解析（「单一词表」契约：解析层不认中文映射）。
"""

from __future__ import annotations

import re

# 规范键 → 别名列表（含规范键自身小写形式）。比较统一走 lower()。
_METRIC_ALIASES: dict[str, list[str]] = {
    # profitability_metrics
    "ROE": ["roe", "净资产收益率"],
    "ROA": ["roa", "总资产收益率"],
    "ROIC": ["roic", "投入资本回报率"],
    "毛利率": ["毛利率", "gross_margin", "gross margin", "销售毛利率"],
    "净利率": ["净利率", "net_margin", "net margin", "净利润率", "销售净利率"],
    # solvency_metrics
    "资产负债率": ["资产负债率", "负债率", "debt_ratio", "debt ratio", "杠杆率"],
    "流动比率": ["流动比率", "current_ratio", "current ratio"],
    "速动比率": ["速动比率", "quick_ratio", "quick ratio"],
    "利息覆盖倍数": ["利息覆盖倍数", "利息保障倍数", "interest_coverage", "interest coverage"],
    "净债务/EBITDA": ["净债务/ebitda", "net_debt_ebitda", "net debt/ebitda"],
    # efficiency_metrics
    "存货周转率": ["存货周转率", "inventory_turnover", "inventory turnover"],
    "应收账款周转率": ["应收账款周转率", "receivables_turnover", "receivables turnover"],
    "应付账款周转率": ["应付账款周转率", "payables_turnover", "payables turnover"],
    "总资产周转率": ["总资产周转率", "total_asset_turnover", "total asset turnover"],
    # cashflow_metrics
    "经营现金流/净利润": ["经营现金流/净利润", "经营现金流净利润比", "ocf_to_profit"],
    "FCF": ["fcf", "自由现金流"],
    "FCF收益率": ["fcf收益率", "fcf_yield", "fcf yield"],
    "现金流覆盖比率": ["现金流覆盖比率"],
    "留存现金流比率": ["留存现金流比率"],
    "资本支出/折旧": ["资本支出/折旧"],
    # dupont_tree
    "权益乘数": ["权益乘数", "equity_multiplier", "equity multiplier"],
    # technical_indicators
    "MA": ["ma", "均线", "移动平均", "ma5", "ma10", "ma20", "ma60"],
    "MACD": ["macd", "指数平滑异同移动平均线"],
    "DIF": ["dif"],
    "DEA": ["dea"],
    "RSI": ["rsi", "相对强弱指数", "相对强弱指标"],
    "BOLL": ["boll", "布林带", "布林线", "bollinger"],
    "KDJ": ["kdj", "随机指标"],
    # risk_metrics
    "max_drawdown": ["max_drawdown", "最大回撤"],
    "volatility": ["volatility", "波动率"],
    "beta": ["beta", "贝塔"],
    "var_95": ["var_95", "var", "在险价值"],
    # macro_indicators
    "cpi": ["cpi", "居民消费价格指数", "通胀率"],
    "pmi": ["pmi", "采购经理指数", "制造业pmi"],
    "m2": ["m2", "广义货币供应量", "广义货币"],
    "lpr": ["lpr", "贷款市场报价利率"],
    # 报表常用行（field_ref 指标段即列名，别名收敛到真实列名）
    "营业总收入": ["营业总收入", "营业收入", "营收", "总收入", "revenue"],
    "净利润": ["净利润", "net_profit", "net profit"],
    "归母净利润": ["归母净利润", "归属母公司净利润", "归母净利润(单季)"],
}

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical
    for canonical, aliases in _METRIC_ALIASES.items()
    for alias in aliases
}

# 期次形态：年（2024）、报告日（20251231）、ISO 日期（2026-08-28）、季度（2025Q2）
_PERIOD_PATTERNS = [
    re.compile(r"^(19|20)\d{2}$"),
    re.compile(r"^(19|20)\d{2}[01]\d[0-3]\d$"),
    re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}$"),
    re.compile(r"^(19|20)\d{2}[Qq][1-4]$"),
]
_INT_SEGMENT = re.compile(r"^-?\d+$")


def canonical_metric(name: str | None) -> str | None:
    """别名 → 规范键；None/空串/未收录返回 None。"""
    if not name:
        return None
    return _ALIAS_TO_CANONICAL.get(name.strip().lower())


def _is_period_segment(seg: str) -> bool:
    return any(p.match(seg) for p in _PERIOD_PATTERNS)


def field_ref_metric_segments(field_ref: str) -> list[str]:
    """field_ref 的指标段：去根键、去期次段、去纯整数段（索引/参数）。

    例：profitability_metrics.毛利率.2024 → [毛利率]；
    technical_indicators.MA.5.-1 → [MA]；
    macro_indicators.cpi.0.全国-同比增长 → [cpi, 全国-同比增长]。
    """
    parts = field_ref.split(".")
    out: list[str] = []
    for seg in parts[1:]:
        base = re.sub(r"\[(-?\d+)\]$", "", seg)  # yoy[1] → yoy
        if not base:
            continue
        if _is_period_segment(base) or _INT_SEGMENT.match(base):
            continue
        out.append(base)
    return out


def field_ref_period_segment(field_ref: str) -> str | None:
    """首个期次形态段；无则 None（如索引锚定的序列引用）。"""
    for seg in field_ref.split("."):
        base = re.sub(r"\[(-?\d+)\]$", "", seg)
        if _is_period_segment(base):
            return base
    return None


_QUARTER_CN = {"一": "1", "二": "2", "三": "3", "四": "4"}


def normalize_period(period: str) -> str | None:
    """期次表述归一化：年→YYYY，季度→YYYYQn，日期→YYYY-MM-DD，月份→YYYY-MM。"""
    text = period.strip()
    if not text:
        return None
    m = re.match(r"^((?:19|20)\d{2})年?([一二三四])季度$", text)
    if m:
        return f"{m.group(1)}Q{_QUARTER_CN[m.group(2)]}"
    m = re.match(r"^((?:19|20)\d{2})[Qq]([1-4])季?度?$", text)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    m = re.match(r"^((?:19|20)\d{2})年(\d{1,2})月(?:份)?$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})日?$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^((?:19|20)\d{2})(\d{2})(\d{2})$", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^((?:19|20)\d{2})[-/](\d{1,2})$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^((?:19|20)\d{2})(?:年|年报|年度)?$", text)
    if m:
        return m.group(1)
    return None


def period_matches(declared: str, actual: str) -> bool:
    """归一化后相等或互为前缀（年 ⊂ 年月 ⊂ 年月日 视为一致）。

    declared/actual 任一侧无法归一化 → False（调用方按缺口或 FAIL 裁决）。
    """
    d, a = normalize_period(declared), normalize_period(actual)
    if d is None or a is None:
        return False
    if d == a:
        return True
    # 季度只与季度比；年/月/日按连字符前缀逐级包含
    if ("Q" in d) != ("Q" in a):
        return False
    if "Q" in d:
        return False  # 季度已判等，不等即不一致（2025 ≠ 2025Q2：粒度不同判不一致）
    return d.startswith(a) or a.startswith(d)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metric_vocab.py -v`
Expected: PASS（24 项）

- [ ] **Step 5: Commit**

```bash
git add tests/test_metric_vocab.py src/finance_agent/metric_vocab.py
git commit -m "feat(citation): metric_vocab 指标词表 + 期次归一化（harden-citation-semantic-coverage T1）"
```

---

### Task 2: Claim schema 扩展 + FAIL 桶

**Files:**
- Modify: `src/finance_agent/citation.py:26-51`（Claim、CitationResult）
- Modify: `src/finance_agent/nodes/analysts.py:73-77`（_sanitize_claims 新字段类型兜底）
- Test: `tests/test_citation_buckets.py`

**Interfaces:**
- Consumes: Task 1 的 metric_vocab（本任务只用其存在性，检查逻辑在 T3 接入）
- Produces:
  - `Claim.metric_name: str | None = None`、`Claim.period: str | None = None`
  - `CitationResult.bucket: Literal["value_mismatch","path_unresolvable","semantic_term_mismatch","semantic_period_mismatch","internal_inconsistency"] | None = None`
  - 既有 FAIL 路径全部带桶：解析不到/非数值 → `path_unresolvable`；超容差/方向错 → `value_mismatch`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_citation_buckets.py
"""TDD tests for citation.py — Claim schema 扩展与 FAIL 分桶。"""

from finance_agent.citation import Claim, verify_claims


class TestClaimSchemaCompat:
    """D5：旧格式 claim（无 metric_name/period）反序列化兼容。"""

    def test_old_claim_without_new_fields(self):
        claim = Claim.model_validate(
            {
                "claim_type": "numerical",
                "source_type": "data",
                "field_ref": "solvency_metrics.资产负债率.2024",
                "stated_value": 40.0,
                "interpretation": "资产负债率为 40%",
            }
        )
        assert claim.metric_name is None
        assert claim.period is None

    def test_new_fields_accepted(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 45.2%",
            metric_name="毛利率",
            period="2024",
        )
        assert claim.metric_name == "毛利率"
        assert claim.period == "2024"


class TestFailBuckets:
    def _state(self) -> dict:
        return {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}

    def test_value_mismatch_bucket(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=45.0,
            interpretation="x",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "FAIL"
        assert r.bucket == "value_mismatch"

    def test_path_unresolvable_bucket(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.不存在.2024",
            stated_value=40.0,
            interpretation="x",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "FAIL"
        assert r.bucket == "path_unresolvable"

    def test_pass_has_no_bucket(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="x",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "PASS"
        assert r.bucket is None

    def test_unverifiable_has_no_bucket(self):
        claim = Claim(
            claim_type="numerical",
            source_type="llm_inference",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0,
            interpretation="x",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "UNVERIFIABLE"
        assert r.bucket is None

    def test_comparative_wrong_direction_is_value_mismatch(self):
        state = {"profitability_metrics": {"ROE": {"2024": 28.0, "2023": 25.0}}}
        claim = Claim(
            claim_type="comparative",
            source_type="data",
            field_ref="profitability_metrics.ROE.2024",
            stated_value="less_than",
            interpretation="2024 年 ROE 低于 2023 年",
            field_ref_b="profitability_metrics.ROE.2023",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "value_mismatch"

    def test_event_not_found_is_path_unresolvable(self):
        claim = Claim(
            claim_type="temporal",
            source_type="event",
            field_ref="不存在的事件",
            stated_value="",
            interpretation="x",
        )
        (r,) = verify_claims([claim], {"key_events": []})
        assert r.status == "FAIL"
        assert r.bucket == "path_unresolvable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citation_buckets.py -v`
Expected: FAIL — `TypeError: Claim() got an unexpected keyword argument 'metric_name'` / `AttributeError: bucket`

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/citation.py` 修改点（其余行不变）：

```python
# Claim 增加两字段（file_ref_b 之后）：
    field_ref_b: str | None = None  # 比较型 claim 的第二个值路径
    # harden-citation-semantic-coverage：术语/期次申报。None = 未申报（旧格式），
    # 校验器跳过对应检查并计覆盖缺口（显式降级，不静默 PASS）。
    metric_name: str | None = None  # 指标枚举（中文规范键或别名，见 metric_vocab）
    period: str | None = None  # 期次（2024 / 2025Q2 / 2026-08-28 / 2026-07）

# CitationResult 增加 bucket：
    coverage_gap: bool = False  # 覆盖缺口（未注册根键 / 未申报术语期次）
    # FAIL 分桶（harden-citation-semantic-coverage）：value_mismatch=值级（gt 存在且
    # 超容差，定向重试）；path_unresolvable=路径/事件不可解析；semantic_*=术语/期次
    # 张冠李戴；internal_inconsistency=stated 与 interpretation 两张皮/方向矛盾。
    bucket: Literal[
        "value_mismatch",
        "path_unresolvable",
        "semantic_term_mismatch",
        "semantic_period_mismatch",
        "internal_inconsistency",
    ] | None = None
```

既有 FAIL 路径逐处补 `bucket=`：
- `_verify_computational`：`current is None`、非数值、float 转换失败三处 → `bucket="path_unresolvable"`；最终 `status="FAIL"` 分支 → `bucket="value_mismatch"`（PASS 分支 bucket 默认 None）。
- `_verify_numerical`：解析非数值 / float 失败两处 → `bucket="path_unresolvable"`；最终 FAIL → `bucket="value_mismatch"`。
- `_verify_comparative`：解析失败两处 → `path_unresolvable`；方向 FAIL → `value_mismatch`。
- `_verify_event`：事件不存在 / key_events 非 list → `path_unresolvable`；日期不等 → `value_mismatch`。

`src/finance_agent/nodes/analysts.py` `_sanitize_claims` 末尾（`for field in ("field_ref", ...)` 循环之后）追加：

```python
        # metric_name/period 为可选申报字段：非 None 时统一转 str（LLM 偶发
        # 把 period 输出成 int 2024），缺省保持 None（None = 未申报，校验跳过）。
        for field in ("metric_name", "period"):
            if claim.get(field) is not None:
                claim[field] = str(claim[field])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citation_buckets.py tests/test_citation.py tests/test_citation_contract.py -v`
Expected: PASS（新 8 项 + 存量全绿；存量测试未带新字段，默认 None 不触发新检查）

- [ ] **Step 5: Commit**

```bash
git add tests/test_citation_buckets.py src/finance_agent/citation.py src/finance_agent/nodes/analysts.py
git commit -m "feat(citation): Claim 扩 metric_name/period + FAIL 分桶（harden-citation-semantic-coverage T2）"
```

---

### Task 3: 术语/期次一致性校验（semantic_term_mismatch / semantic_period_mismatch）

**Files:**
- Modify: `src/finance_agent/citation.py`（新增 `_check_metric_term`、`_check_period`、`_resolve_index_period`，verify_claims 重排）
- Test: `tests/test_citation_semantic.py`

**Interfaces:**
- Consumes: Task 1 `canonical_metric/field_ref_metric_segments/field_ref_period_segment/normalize_period/period_matches`；Task 2 schema 与桶
- Produces:
  - `_check_metric_term(claim: Claim) -> CitationResult | None` — FAIL 或 None
  - `_check_period(claim: Claim, state: dict) -> tuple[CitationResult | None, bool]` — (FAIL 或 None, 是否缺口)
  - verify_claims 对 `claim_type in {numerical, computational, comparative}` 且 `source_type in {data, mixed}` 的 claim 走 `_verify_data_claim`：术语 → 期次 → 值级（既有函数），首个 FAIL 短路；跳过项累计 `coverage_gap=True`

规则（钉死）：
- metric_name 非空：canonical 为 None（词表外术语）→ FAIL `semantic_term_mismatch`；canonical 与任一指标段（各自 canonical 化后比较，段不可 canonical 时裸串比较）相等 → 过；否则 FAIL。
- period 非空：field_ref 有显式期次段 → `period_matches(claim.period, 段)`，不一致 FAIL `semantic_period_mismatch`；无显式段（索引锚定）→ `_resolve_index_period` 从 state 解析实际期次（technical→`state["kline"]` 日期列按索引取值；macro→`records[idx]["月份"]`；quarterly_trend→`quarters[idx]`），解析不出 → 不 FAIL，计缺口；解析出但不匹配 → FAIL。
- metric_name/period 为空 → 跳过该检查，result 置 `coverage_gap=True`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_citation_semantic.py
"""TDD tests for citation.py — 术语/期次一致性校验（语义层张冠李戴拦截）。"""

import pandas as pd

from finance_agent.citation import Claim, verify_claims


def _state() -> dict:
    return {
        "profitability_metrics": {"毛利率": {"2024": 45.2}, "净利率": {"2024": 18.0}},
        "technical_indicators": {"MA": {"5": [100.0, 101.0, 102.0]}},
        "kline": pd.DataFrame({"日期": ["2026-08-26", "2026-08-27", "2026-08-28"]}),
        "macro_indicators": {
            "cpi": {
                "records": [{"月份": "2026年07月份", "全国-同比增长": 0.4}],
                "as_of_date": "2026-07-01",
                "freshness": "fresh",
            }
        },
    }


class TestSemanticTermCheck:
    def test_term_mismatch_fails_even_when_value_correct(self):
        """spec 场景：field_ref 指向毛利率，metric_name 写净利率 → FAIL。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="净利率",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_term_mismatch"

    def test_term_match_passes(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="毛利率",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is False

    def test_term_alias_match_passes(self):
        """metric_name 用英文别名，canonical 化后与中文指标段一致 → 过。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="gross_margin",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_unknown_term_fails(self):
        """词表外术语 = 契约违规 → FAIL（不静默放行）。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="神秘指标",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_term_mismatch"

    def test_missing_metric_name_skips_and_counts_gap(self):
        """D5：缺省 → 跳过检查 + 覆盖缺口，不静默 PASS 语义（值级检查照常）。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is True


class TestSemanticPeriodCheck:
    def test_period_mismatch_fails(self):
        """年报值说成其他年份 → FAIL semantic_period_mismatch。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="2023 年毛利率为 45.2%",
            metric_name="毛利率",
            period="2023",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_period_mismatch"

    def test_period_match_passes(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="2024 年毛利率为 45.2%",
            metric_name="毛利率",
            period="2024年",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_technical_index_period_resolved_from_kline(self):
        """索引锚定（-1）→ 从 kline 解析实际交易日比对期次。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.-1",
            stated_value=102.0,
            interpretation="2026-08-28 MA5 为 102.0",
            metric_name="MA",
            period="2026-08-28",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_technical_index_period_mismatch_fails(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.-1",
            stated_value=102.0,
            interpretation="2026-08-01 MA5 为 102.0",
            metric_name="MA",
            period="2026-08-01",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "FAIL"
        assert r.bucket == "semantic_period_mismatch"

    def test_macro_index_period_resolved_from_records(self):
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.cpi.0.全国-同比增长",
            stated_value=0.4,
            interpretation="2026 年 7 月 CPI 同比 0.4%",
            metric_name="CPI",
            period="2026-07",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"

    def test_index_period_unresolvable_counts_gap_not_fail(self):
        """state 缺 kline 时索引期次解析不出 → 缺口计数，不 FAIL。"""
        state = _state()
        del state["kline"]
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MA.5.-1",
            stated_value=102.0,
            interpretation="MA5 为 102.0",
            metric_name="MA",
            period="2026-08-28",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"
        assert r.coverage_gap is True

    def test_garbage_period_counts_gap_not_fail(self):
        """period 无法归一化（"最近"）→ 缺口，不 FAIL。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率为 45.2%",
            metric_name="毛利率",
            period="最近",
        )
        (r,) = verify_claims([claim], _state())
        assert r.status == "PASS"
        assert r.coverage_gap is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citation_semantic.py -v`
Expected: FAIL（semantic_term_mismatch 未实现，断言 bucket 失败）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/citation.py`：

```python
# 文件头 import 追加：
from finance_agent.metric_vocab import (
    canonical_metric,
    field_ref_metric_segments,
    field_ref_period_segment,
    normalize_period,
    period_matches,
)

# ── 语义层检查（harden-citation-semantic-coverage）──

def _check_metric_term(claim: Claim) -> CitationResult | None:
    """术语一致性：metric_name 规范键须命中 field_ref 指标段。不一致/词表外 → FAIL。"""
    name = (claim.metric_name or "").strip()
    if not name:
        return None
    canonical = canonical_metric(name)
    segments = field_ref_metric_segments(claim.field_ref)
    seg_keys = {(canonical_metric(s) or s) for s in segments}
    if canonical is None or canonical not in seg_keys:
        return CitationResult(
            status="FAIL", claim=claim, bucket="semantic_term_mismatch"
        )
    return None


def _resolve_index_period(field_ref: str, state: dict) -> str | None:
    """索引锚定引用（无显式期次段）从 state 解析实际期次标签；解析不出返回 None。

    technical_indicators.X.Y.<idx> → kline 日期列同索引（序列与 kline 等长、升序）；
    macro_indicators.<key>.<idx>.<列> → records[idx]["月份"]；
    quarterly_trend.<key>[<idx>] → quarters[idx]。
    """
    import re as _re

    parts = field_ref.split(".")
    root = parts[0] if parts else ""
    idx: int | None = None
    m = _re.match(r"^-?\d+$", parts[-1]) if parts else None
    bracket = _re.search(r"\[(-?\d+)\]$", parts[-1]) if parts else None
    if bracket:
        idx = int(bracket.group(1))
    elif m and root in {"technical_indicators", "macro_indicators", "quarterly_trend"}:
        idx = int(parts[-1])
    if idx is None:
        return None
    try:
        if root == "technical_indicators":
            dates = state["kline"]["日期"]
            return str(dates.iloc[idx])
        if root == "macro_indicators" and len(parts) >= 3:
            recs = state["macro_indicators"][parts[1]]
            if isinstance(recs, dict):
                recs = recs.get("records") or []
            return str(recs[idx].get("月份", "")) or None
        if root == "quarterly_trend":
            return str(state["quarterly_trend"]["quarters"][idx]) or None
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    return None


def _check_period(claim: Claim, state: dict) -> tuple[CitationResult | None, bool]:
    """期次一致性。返回 (FAIL 结果或 None, 是否覆盖缺口)。"""
    declared = (claim.period or "").strip()
    if not declared:
        return None, False
    if normalize_period(declared) is None:
        return None, True  # 期次表述无法归一化 → 缺口，不误伤
    actual = field_ref_period_segment(claim.field_ref)
    if actual is None:
        actual = _resolve_index_period(claim.field_ref, state)
        if actual is None:
            return None, True  # 索引期次解析不出 → 缺口
    if period_matches(declared, actual):
        return None, False
    return (
        CitationResult(status="FAIL", claim=claim, bucket="semantic_period_mismatch"),
        False,
    )
```

`verify_claims` 重排为（保持既有分支顺序语义）：

```python
def verify_claims(claims: list[Claim], state: dict) -> list[CitationResult]:
    """校验所有 Claim，返回逐条结果。"""
    results: list[CitationResult] = []
    for claim in claims:
        if claim.source_type == "llm_inference":
            results.append(CitationResult(status="UNVERIFIABLE", claim=claim))
        elif claim.source_type == "event":
            results.append(_verify_event(claim, state))
        elif claim.claim_type == "numerical":
            results.append(_verify_data_claim(claim, state, _verify_numerical))
        elif claim.claim_type == "computational":
            results.append(_verify_data_claim(claim, state, _verify_computational))
        elif claim.claim_type == "comparative":
            results.append(_verify_data_claim(claim, state, _verify_comparative))
        else:
            results.append(CitationResult(status="UNVERIFIABLE", claim=claim))
    return results


def _verify_data_claim(
    claim: Claim,
    state: dict,
    value_fn: Callable[[Claim, dict], CitationResult],
) -> CitationResult:
    """data/mixed 数值族 claim 的完整校验链：术语 → 期次 → 值级。

    首个 FAIL 短路（桶即首个失败因）；术语/期次缺省或不可解析计覆盖缺口
    （coverage_gap=True），不静默 PASS（D5）。
    """
    term_fail = _check_metric_term(claim)
    if term_fail is not None:
        return term_fail
    period_fail, period_gap = _check_period(claim, state)
    if period_fail is not None:
        return period_fail
    result = value_fn(claim, state)
    gap = period_gap or not (claim.metric_name or "").strip() or not (claim.period or "").strip()
    if gap:
        result.coverage_gap = True
    return result
```

注意：`_verify_data_claim` 里 `not metric_name and not period` 的缺口语义——只要任一申报字段缺失即记缺口（与 D5「为 None 时跳过并计缺口」一致）。`_verify_event` 与 UNVERIFIABLE 分支不受影响。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citation_semantic.py tests/test_citation.py tests/test_citation_buckets.py tests/test_citation_contract.py tests/nodes/test_citation_node.py -v`
Expected: PASS。注意存量测试构造的 claim 不带 metric_name/period → `coverage_gap=True` 但 status 不变，存量断言不受影响（`tests/evals/claim_benchmark/test_rejudge.py` 钉的是 rejudge.py，不涉及本改动）。

- [ ] **Step 5: Commit**

```bash
git add tests/test_citation_semantic.py src/finance_agent/citation.py
git commit -m "feat(citation): 术语/期次一致性校验（semantic_term/period_mismatch 桶）（T3）"
```

---

### Task 4: claim 内部一致性校验（internal_inconsistency）

**Files:**
- Modify: `src/finance_agent/citation.py`（新增 `_extract_numbers`、`_check_internal_echo`、`_check_direction_words`，接入 `_verify_data_claim`）
- Test: `tests/test_citation_internal.py`

**Interfaces:**
- Consumes: Task 2/3 的 `_verify_data_claim` 链
- Produces:
  - `value_close(a: float, b: float) -> bool` — `abs(a-b) < max(0.01, 0.005*max(|a|,|b|))`
  - `_extract_numbers(text: str) -> list[float]` — 从自由文本提取数值（含 %/亿/万/元 缩放 + 修饰词剥离），供 T5 复用

规则（fixture 钉死）：
- (a) 数值回声：claim_type ∈ {numerical, computational} 且 stated_value 可转 float：interpretation 含 ≥1 个数值且无一与 stated 在容差内匹配（候选值 ×{1, 100, 0.01, 1e4, 1e8} 缩放后比）→ FAIL `internal_inconsistency`；interpretation 不含任何数值 → 跳过（不 FAIL，定性表述合法，由覆盖率普查管召回）；interpretation 空串 → 跳过。
- (b) 方向词：仅当值级结果 PASS 时检查。负向词表 `("负增长","下降","下滑","下跌","回落","走低","减少","降低","恶化","走弱")` 优先匹配，正向词表 `("增长","上升","上涨","提升","提高","改善","走高","回升","向好")` 匹配时排除紧邻「负/未/无」前缀的命中。适用面：(i) comparative claim（greater_than 期望正向，less_than 期望负向）；(ii) numerical/computational 且（根键 == growth_rates 或指标段含「同比/环比/增速/增长率」或 stated_value < 0 且 metric 为率类）— v1 收敛为：根键 growth_rates 或指标段含 同比/环比/增速。正向-only 而期望负向（或反向）→ FAIL `internal_inconsistency`；双向词均出现或均无 → 跳过。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_citation_internal.py
"""TDD tests for citation.py — claim 内部一致性（数值回声 + 方向词核对）。"""

from finance_agent.citation import Claim, _extract_numbers, verify_claims


class TestExtractNumbers:
    """归一化口径 fixture（"约 45%"/"45.2%" 同源）。"""

    def test_percent(self):
        assert _extract_numbers("毛利率约 45.2%") == [45.2]
        assert _extract_numbers("毛利率约 45%") == [45.0]

    def test_amount_scaling(self):
        assert _extract_numbers("营收 10.39 亿") == [10.39e8]
        assert _extract_numbers("净利润 1038.76 万元") == [1038.76e4]
        assert _extract_numbers("股价 5.2 元") == [5.2]

    def test_thousands_and_negative(self):
        assert _extract_numbers("营收 1,038.76 亿") == [1038.76e8]
        assert _extract_numbers("同比 -5.2%") == [-5.2]

    def test_plain_number(self):
        assert _extract_numbers("ROE 为 30.5") == [30.5]

    def test_no_number(self):
        assert _extract_numbers("处于行业较高水平") == []


class TestInternalEcho:
    def _state(self) -> dict:
        return {"profitability_metrics": {"毛利率": {"2024": 45.2}}}

    def test_value_two_faces_fails(self):
        """spec 场景：stated 45.2，interpretation 写「约 30%」→ FAIL。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 30%",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"

    def test_hedged_echo_passes(self):
        """「约 45%」与 stated 45.2 在 0.5% 容差内 → PASS。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 45%",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "PASS"

    def test_qualitative_interpretation_skipped(self):
        """interpretation 不含数值 → 跳过回声检查（不误伤定性表述）。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率处于行业较高水平",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "PASS"

    def test_amount_unit_echo_passes(self):
        state = {"income_statement": {"20251231": {"营业总收入": 1038756658.94}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="income_statement.20251231.营业总收入",
            stated_value=1038756658.94,
            interpretation="营业总收入约 10.39 亿",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"


class TestDirectionWords:
    def test_comparative_direction_contradiction_fails(self):
        """greater_than 但 interpretation 只说「下降」→ FAIL。"""
        state = {"profitability_metrics": {"ROE": {"2024": 28.0, "2023": 25.0}}}
        claim = Claim(
            claim_type="comparative",
            source_type="data",
            field_ref="profitability_metrics.ROE.2024",
            stated_value="greater_than",
            interpretation="ROE 同比下降",
            field_ref_b="profitability_metrics.ROE.2023",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"

    def test_growth_negative_but_says_growth_fails(self):
        """增长率 claim 断言 -5.2% 却说「大幅增长」→ FAIL。"""
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="毛利率大幅增长",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"

    def test_negative_growth_correctly_described_passes(self):
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="毛利率同比下降 5.2%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"

    def test_non_growth_metric_negative_value_not_checked(self):
        """非增长类 claim（MACD DIF 负值）说「走弱」不误判——指标段无同比/增速。"""
        state = {"technical_indicators": {"MACD": {"DIF": [-1.0, -44.09]}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MACD.DIF.-1",
            stated_value=-44.09,
            interpretation="DIF 为 -44.09，动能走弱",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"

    def test_both_direction_words_skipped(self):
        """正/负向词同时出现（如「营收增长但毛利率下降」）→ 跳过，不赌语义。"""
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="营收增长但毛利率下降 5.2%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citation_internal.py -v`
Expected: FAIL（`_extract_numbers` 不存在）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/citation.py` 追加：

```python
# ── claim 内部一致性（harden-citation-semantic-coverage）──
import re as _re  # 文件顶部已有 from __future__；re 统一在 import 区引入

_NUMBER_PATTERN = _re.compile(
    r"-?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|％|亿|万|元)?"
)
_UNIT_SCALE = {"亿": 1e8, "万": 1e4, "元": 1.0, "%": 1.0, "％": 1.0, "": 1.0}

_NEGATIVE_WORDS = ("负增长", "下降", "下滑", "下跌", "回落", "走低", "减少", "降低", "恶化", "走弱")
_POSITIVE_WORDS = ("增长", "上升", "上涨", "提升", "提高", "改善", "走高", "回升", "向好")
_NEGATION_PREFIXES = ("负", "未", "无", "不")


def _extract_numbers(text: str) -> list[float]:
    """从自由文本提取数值（去千分位，亿/万缩放为原始单位，% 取面值）。"""
    out: list[float] = []
    for m in _NUMBER_PATTERN.finditer(text):
        token = m.group(0)
        unit = token[-1] if token and token[-1] in _UNIT_SCALE else ""
        digits = token[: -1] if unit else token
        try:
            out.append(float(digits.replace(",", "").strip()) * _UNIT_SCALE[unit])
        except ValueError:
            continue
    return out


def value_close(a: float, b: float) -> bool:
    """容差比对（max(0.01, 0.5%)，与数值型校验同族，允许双向不对称）。"""
    return abs(a - b) < max(0.01, 0.005 * max(abs(a), abs(b)))


def _check_internal_echo(claim: Claim) -> CitationResult | None:
    """数值回声：interpretation 含数值但无一与 stated_value 匹配 → FAIL。"""
    try:
        stated = float(claim.stated_value)
    except (TypeError, ValueError):
        return None  # 非数值 stated（比较方向等）不适用回声检查
    candidates = _extract_numbers(claim.interpretation or "")
    if not candidates:
        return None  # 定性表述不强制回声（召回由正文覆盖率普查承担）
    for cand in candidates:
        for scale in (1.0, 100.0, 0.01, 1e4, 1e8):
            if value_close(stated, cand * scale):
                return None
    return CitationResult(status="FAIL", claim=claim, bucket="internal_inconsistency")


def _direction_hits(text: str, words: tuple[str, ...]) -> list[int]:
    """方向词命中位置；排除紧邻否定前缀的「增长」类命中（负增长 ≠ 增长）。"""
    hits: list[int] = []
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            if w in _POSITIVE_WORDS and i > 0 and text[i - 1] in _NEGATION_PREFIXES:
                start = i + len(w)
                continue
            hits.append(i)
            start = i + len(w)
    return hits


def _check_direction_words(claim: Claim, base: CitationResult) -> CitationResult | None:
    """方向词核对（仅值级 PASS 时）：方向词与比较方向/增长符号矛盾 → FAIL。

    适用面收敛（v1 防误报）：comparative 全量；numerical/computational 仅
    growth_rates 根键或指标段含 同比/环比/增速 的增长类 claim。
    正负向词同时出现或均不出现 → 跳过（不赌复杂句语义）。
    """
    text = claim.interpretation or ""
    pos = bool(_direction_hits(text, _POSITIVE_WORDS))
    neg = bool(_direction_hits(text, _NEGATIVE_WORDS))
    if pos == neg:
        return None
    expect_positive: bool | None = None
    if claim.claim_type == "comparative":
        if claim.stated_value == "greater_than":
            expect_positive = True
        elif claim.stated_value == "less_than":
            expect_positive = False
    else:
        is_growth = claim.field_ref.split(".")[0] == "growth_rates" or any(
            k in claim.field_ref for k in ("同比", "环比", "增速")
        )
        if is_growth:
            try:
                expect_positive = float(claim.stated_value) > 0
            except (TypeError, ValueError):
                return None
    if expect_positive is None:
        return None
    if expect_positive and neg:
        return CitationResult(status="FAIL", claim=claim, bucket="internal_inconsistency")
    if not expect_positive and pos:
        return CitationResult(status="FAIL", claim=claim, bucket="internal_inconsistency")
    return None
```

`_verify_data_claim` 在值级校验前后接入（替换 T3 版本尾部）：

```python
def _verify_data_claim(
    claim: Claim,
    state: dict,
    value_fn: Callable[[Claim, dict], CitationResult],
) -> CitationResult:
    """data/mixed 数值族 claim 的完整校验链：术语 → 期次 → 内部回声 → 值级 → 方向词。

    首个 FAIL 短路；术语/期次缺省或不可解析计覆盖缺口（D5 显式降级）。
    方向词检查只在值级 PASS 上执行（值级 FAIL 已由重试反馈携带真值）。
    """
    term_fail = _check_metric_term(claim)
    if term_fail is not None:
        return term_fail
    period_fail, period_gap = _check_period(claim, state)
    if period_fail is not None:
        return period_fail
    echo_fail = _check_internal_echo(claim)
    if echo_fail is not None:
        return echo_fail
    result = value_fn(claim, state)
    if result.status == "PASS":
        direction_fail = _check_direction_words(claim, result)
        if direction_fail is not None:
            return direction_fail
    gap = period_gap or not (claim.metric_name or "").strip() or not (claim.period or "").strip()
    if gap:
        result.coverage_gap = True
    return result
```

注意 `_check_direction_words` 的 `base` 参数当前未使用但保留签名（后续可用 delta 精细化）——若 ruff 报未用参数，移除该参数改为 `_check_direction_words(claim)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citation_internal.py tests/test_citation.py tests/test_citation_semantic.py tests/test_citation_buckets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_citation_internal.py src/finance_agent/citation.py
git commit -m "feat(citation): claim 内部一致性校验（数值回声 + 方向词核对）（T4）"
```

---

### Task 5: 正文覆盖率普查模块（citation_coverage.py）

**Files:**
- Create: `src/finance_agent/citation_coverage.py`
- Test: `tests/test_citation_coverage.py`

**Interfaces:**
- Consumes: Task 4 `value_close`、`_extract_numbers`（从 citation.py 导入复用）
- Produces:
  - `CensusNumber(NamedTuple)`: `raw: str; value: float; kind: str`（kind ∈ percent/amount/multiple）
  - `extract_census_numbers(markdown: str) -> list[CensusNumber]` — 只普查带单位形态（%/百分点/亿/万/元/倍/x），去重（kind+value）
  - `compute_coverage(markdown: str, stated_values: list[float]) -> CoverageReport`
  - `CoverageReport(NamedTuple)`: `coverage: float; total: int; matched: int; unmatched: list[str]`

豁免（隐式 + 显式，fixture 钉死）：无单位裸数不普查（年份 2024年、编号 5层/三大、MA5/RSI14 参数、6 位股票代码、日期段 2026-08-28 天然豁免）；「N 期/N 个百分点」中期不普查、个百分点按 percent 计；`%` 后随中文正常计入。匹配口径：普查值 vs 任一 stated ×{1, 100, 0.01, 1e4, 1e8} 缩放后 `value_close` → 已认领。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_citation_coverage.py
"""TDD tests for citation_coverage.py — 正文数字普查（citation recall 近似）。

≥15 条例化 fixture 钉死归一化与豁免口径（design D1 口径风险对策）。
"""

from finance_agent.citation_coverage import compute_coverage, extract_census_numbers


def _values(text: str) -> list[float]:
    return [n.value for n in extract_census_numbers(text)]


class TestCensusExtraction:
    def test_percent(self):
        assert _values("毛利率 45.2%") == [45.2]

    def test_percent_fullwidth(self):
        assert _values("毛利率 45.2％") == [45.2]

    def test_hedged_percent(self):
        assert _values("毛利率约 45%") == [45.0]

    def test_percentage_point(self):
        assert _values("上升 2 个百分点") == [2.0]

    def test_amount_yi(self):
        assert _values("营收 10.39 亿") == [10.39e8]

    def test_amount_wan(self):
        assert _values("净利润 500 万") == [500e4]

    def test_amount_yuan(self):
        assert _values("股价 5.2 元") == [5.2]

    def test_multiple(self):
        assert _values("PE 2.5 倍") == [2.5]
        assert _values("PE 2.5x") == [2.5]

    def test_negative(self):
        assert _values("同比 -5.2%") == [-5.2]

    def test_year_exempt(self):
        assert _values("2024 年营收增长") == []

    def test_bare_number_exempt(self):
        assert _values("5 层架构与 3 大报表") == []

    def test_indicator_param_exempt(self):
        assert _values("MA5 与 RSI14 金叉") == []

    def test_stock_code_exempt(self):
        assert _values("贵州茅台 600519 上涨") == []

    def test_date_exempt(self):
        assert _values("截至 2026-08-28 收盘") == []

    def test_window_count_exempt(self):
        assert _values("近 60 期均线") == []

    def test_rating_exempt(self):
        assert _values("评级 AAA，得分 85 分") == []

    def test_dedup_same_value(self):
        nums = extract_census_numbers("毛利率 45.2%，净利率低于 45.2% 是常态")
        assert len(nums) == 1


class TestCoverage:
    def test_all_claimed(self):
        md = "毛利率 45.2%，营收 10.39 亿"
        rep = compute_coverage(md, [45.2, 1038756658.94])
        assert rep.coverage == 1.0
        assert rep.total == 2
        assert rep.matched == 2

    def test_dark_number_exposed(self):
        """spec 场景：正文「营收 10.39 亿」无任何 claim 认领 → 覆盖率下降。"""
        md = "毛利率 45.2%，营收 10.39 亿"
        rep = compute_coverage(md, [45.2])
        assert rep.coverage == 0.5
        assert rep.unmatched == ["10.39亿"]

    def test_empty_markdown_full_coverage(self):
        rep = compute_coverage("", [1.0])
        assert rep.total == 0
        assert rep.coverage == 1.0

    def test_stated_in_yi_matches_amount(self):
        """LLM 以「亿」为单位申报 stated（10.39），正文 10.39 亿 → 缩放匹配。"""
        rep = compute_coverage("营收 10.39 亿", [10.39])
        assert rep.coverage == 1.0

    def test_fraction_claim_matches_percent(self):
        """claim stated 为小数形态（0.452），正文 45.2% → 缩放匹配。"""
        rep = compute_coverage("毛利率 45.2%", [0.452])
        assert rep.coverage == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citation_coverage.py -v`
Expected: FAIL（module 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# src/finance_agent/citation_coverage.py
"""正文数字普查（citation recall 的确定性近似，ALCE 对齐）。

口径（design D1，fixture 钉死）：
- 只普查带单位形态的数值：%/％/个百分点 → percent（面值）；亿/万/元 → amount
  （缩放为原始单位）；倍/x/X → multiple（面值）；修饰词（约/接近/左右…）剥离。
- 无单位裸数一律豁免 → 年份、编号（5 层/3 大）、指标参数（MA5/RSI14）、
  股票代码（600519）、日期段天然不计入；「N 期」不普查，「N 个百分点」按
  percent 计；评级刻度（AAA/85 分）无命中。
- 认领判定：普查值 vs 任一 claim stated_value ×{1, 100, 0.01, 1e4, 1e8}
  缩放后容差比对（value_close）。覆盖率只监控告警，不进路由。
"""

from __future__ import annotations

import re
from typing import NamedTuple

from finance_agent.citation import value_close

_CENSUS_RE = re.compile(
    r"(?P<num>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>个百分点|%|％|亿|万|元|倍|[xX])"
)
_UNIT_KIND = {
    "%": "percent",
    "％": "percent",
    "个百分点": "percent",
    "亿": "amount",
    "万": "amount",
    "元": "amount",
    "倍": "multiple",
    "x": "multiple",
    "X": "multiple",
}
_UNIT_SCALE = {"亿": 1e8, "万": 1e4}
# 「N 期」（窗口期数）豁免；「N 个百分点」属 percent 命中，不在此列
_EXEMPT_SUFFIX_RE = re.compile(r"^\d+(?:\.\d+)?\s*期")

_CLAIM_SCALES = (1.0, 100.0, 0.01, 1e4, 1e8)


class CensusNumber(NamedTuple):
    raw: str  # 原文片段（去空白，如 "10.39亿"），用于 unmatched 披露
    value: float
    kind: str  # percent | amount | multiple


class CoverageReport(NamedTuple):
    coverage: float  # 已认领 / 普查总数；total=0 时 1.0（无数字即无黑数字）
    total: int
    matched: int
    unmatched: list[str]  # 未认领原文片段（稳定序）


def extract_census_numbers(markdown: str) -> list[CensusNumber]:
    """从 markdown 提取带单位数值，按 (kind, value) 去重（保持首次出现序）。"""
    seen: set[tuple[str, float]] = set()
    out: list[CensusNumber] = []
    for m in _CENSUS_RE.finditer(markdown):
        start = m.start()
        # 日期段保护：紧邻前字符为 '-' 且本身是日期一部分（2026-08-28 的 28）——
        # 无单位不命中本正则，无需处理；此处防御「-08」类碎片
        if start > 0 and markdown[start - 1] == "-" and not m.group("num").startswith("-"):
            continue
        unit = m.group("unit")
        digits = m.group("num").replace(",", "")
        try:
            value = float(digits) * _UNIT_SCALE.get(unit, 1.0)
        except ValueError:
            continue
        kind = _UNIT_KIND[unit]
        key = (kind, round(value, 6))
        if key in seen:
            continue
        seen.add(key)
        raw = f"{m.group('num')}{unit}".replace(" ", "")
        out.append(CensusNumber(raw=raw, value=value, kind=kind))
    return out


def compute_coverage(markdown: str, stated_values: list[float]) -> CoverageReport:
    """普查 markdown，逐一与 claim stated_value 集合匹配，产出覆盖率。"""
    numbers = extract_census_numbers(markdown)
    unmatched: list[str] = []
    for n in numbers:
        claimed = any(
            value_close(n.value, sv * scale) for sv in stated_values for scale in _CLAIM_SCALES
        )
        if not claimed:
            unmatched.append(n.raw)
    total = len(numbers)
    matched = total - len(unmatched)
    coverage = matched / total if total else 1.0
    return CoverageReport(coverage=coverage, total=total, matched=matched, unmatched=unmatched)
```

说明：`extract_census_numbers` 的「N 期豁免」由正则天然实现（期不在 unit 枚举内）；`_EXEMPT_SUFFIX_RE` 为防御保留可不使用——若 ruff 报未用变量则删除。日期保护：`2026-08-28` 中 `08-28` 不会带单位，无命中；写下「-5.2%」时 num 含负号正常命中。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citation_coverage.py -v`
Expected: PASS（23 项）

- [ ] **Step 5: Commit**

```bash
git add tests/test_citation_coverage.py src/finance_agent/citation_coverage.py
git commit -m "feat(citation): 正文数字普查模块 citation_coverage（citation recall 近似）（T5）"
```

---

### Task 6: citation_node 集成（分桶聚合 + 定向重试目标 + 覆盖率 Score）

**Files:**
- Modify: `src/finance_agent/nodes/citation_node.py`（verify_citations 重构 + _report_to_langfuse 扩展）
- Modify: `src/finance_agent/state.py:101-107`（新增 5 个 state 字段）
- Test: `tests/nodes/test_citation_node.py`（追加 Test 类，存量不动）

**Interfaces:**
- Consumes: T2 桶、T5 `compute_coverage`、既有 `_extract_claims`
- Produces（state 输出键，T7 消费）:
  - `citation_retry_targets: list[str]` — 含 ≥1 条 value_mismatch FAIL 的分析师名（排序去重）
  - `citation_retry_feedback: dict[str, list[dict]]` — 每分析师的失败明细 `[{field_ref, stated_value, ground_truth, delta, interpretation}]`（仅 value_mismatch）
  - `citation_fail_buckets: dict[str, int]` — 桶计数
  - `citation_coverage: float` — 四分析师 markdown 合并普查覆盖率
  - `citation_minor_fail: bool`（补声明到 state.py）

- [ ] **Step 1: Write the failing test**

```python
# tests/nodes/test_citation_node.py 追加：

from finance_agent.citation import Claim
from finance_agent.models import AnalystReport
from finance_agent.nodes.citation_node import verify_citations


def _report(agent: str, claims: list[Claim], markdown: str) -> AnalystReport:
    return AnalystReport(
        agent_name=agent,
        summary=f"{agent} 分析",
        key_findings=[],
        claims=claims,
        markdown=markdown,
    )


class TestFailBucketAggregation:
    def test_value_mismatch_produces_retry_target_and_feedback(self):
        """基本面 1 条值级 FAIL → 仅基本面进重试目标，反馈带 gt 明细。"""
        good = Claim(
            claim_type="numerical", source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0, interpretation="资产负债率 40%",
        )
        bad = Claim(
            claim_type="numerical", source_type="data",
            field_ref="solvency_metrics.资产负债率.2023",
            stated_value=99.0, interpretation="2023 年资产负债率 99%",
        )
        state = {
            "analyst_reports": {
                "fundamental": _report("fundamental", [good, bad], "资产负债率 40%"),
                "macro": _report("macro", [], "CPI 温和"),
            },
            "solvency_metrics": {"资产负债率": {"2024": 40.0, "2023": 38.0}},
        }
        result = verify_citations(state)
        assert result["citation_retry_targets"] == ["fundamental"]
        fb = result["citation_retry_feedback"]["fundamental"]
        assert len(fb) == 1
        assert fb[0]["field_ref"] == "solvency_metrics.资产负债率.2023"
        assert fb[0]["ground_truth"] == 38.0
        assert fb[0]["stated_value"] == 99.0
        assert result["citation_fail_buckets"] == {"value_mismatch": 1}

    def test_format_class_fail_no_retry_target(self):
        """纯格式类 FAIL（路径不可解析）→ 无重试目标，桶计数照记。"""
        bad = Claim(
            claim_type="numerical", source_type="data",
            field_ref="solvency_metrics.不存在.2024",
            stated_value=40.0, interpretation="x",
        )
        state = {
            "analyst_reports": {"fundamental": _report("fundamental", [bad], "x")},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        assert result["citation_retry_targets"] == []
        assert result["citation_retry_feedback"] == {}
        assert result["citation_fail_buckets"] == {"path_unresolvable": 1}
        assert result["citation_pass"] is False

    def test_semantic_fail_no_retry_target(self):
        """术语张冠李戴 → 格式类桶，不触发重试。"""
        bad = Claim(
            claim_type="numerical", source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2, interpretation="净利率为 45.2%",
            metric_name="净利率",
        )
        state = {
            "analyst_reports": {"fundamental": _report("fundamental", [bad], "净利率 45.2%")},
            "profitability_metrics": {"毛利率": {"2024": 45.2}},
        }
        result = verify_citations(state)
        assert result["citation_retry_targets"] == []
        assert result["citation_fail_buckets"] == {"semantic_term_mismatch": 1}


class TestCoverageScore:
    def test_coverage_computed_from_markdown(self):
        """markdown 黑数字拉低 citation_coverage。"""
        claim = Claim(
            claim_type="numerical", source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0, interpretation="资产负债率 40%",
        )
        state = {
            "analyst_reports": {
                "fundamental": _report(
                    "fundamental", [claim], "资产负债率 40%，营收 10.39 亿"
                )
            },
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        # 40% 被认领、10.39 亿未认领 → 1/2
        assert result["citation_coverage"] == 0.5

    def test_coverage_full_when_no_dark_numbers(self):
        claim = Claim(
            claim_type="numerical", source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0, interpretation="资产负债率 40%",
        )
        state = {
            "analyst_reports": {"fundamental": _report("fundamental", [claim], "资产负债率 40%")},
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        result = verify_citations(state)
        assert result["citation_coverage"] == 1.0

    def test_coverage_reported_to_langfuse(self, monkeypatch):
        """citation_coverage 作为 NUMERIC Score 上报；<0.8 产生告警 metadata。"""
        import finance_agent.nodes.citation_node as cn

        calls: list[dict] = []

        class _FakeClient:
            def score_current_trace(self, **kwargs):
                calls.append(kwargs)

            def update_current_span(self, **kwargs):
                calls.append(kwargs)

        monkeypatch.setattr(cn, "get_langfuse", lambda: _FakeClient())
        claim = Claim(
            claim_type="numerical", source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=40.0, interpretation="资产负债率 40%",
        )
        state = {
            "analyst_reports": {
                "fundamental": _report("fundamental", [claim], "资产负债率 40%，营收 10.39 亿")
            },
            "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        }
        verify_citations(state)
        score = next(c for c in calls if c.get("name") == "citation_coverage")
        assert score["data_type"] == "NUMERIC"
        assert score["value"] == 0.5
        span = next(
            c for c in calls if "metadata" in c and "citation_coverage_alert" in c["metadata"]
        )
        assert span["metadata"]["citation_coverage_alert"] is True
        assert span["level"] == "WARNING"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_citation_node.py -v`
Expected: FAIL（`KeyError: 'citation_retry_targets'` 等）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/state.py` 在 `citation_fail_rates` 后追加：

```python
    citation_minor_fail: bool  # 轻微失败降级放行（skip-citation-retry-on-minor-failures）
    # harden-citation-semantic-coverage：FAIL 分桶与定向重试
    citation_retry_targets: list[str]  # 值级 FAIL 分析师（Send 定向重跑）
    citation_retry_feedback: dict[str, list[dict]]  # 每分析师失败明细（重试上下文注入）
    citation_fail_buckets: dict[str, int]  # 桶计数（value_mismatch/path_unresolvable/...）
    citation_coverage: float  # 正文数字普查覆盖率（0-1，监控不进路由）
```

`src/finance_agent/nodes/citation_node.py` 重构 `verify_citations`（替换函数体，保留 docstring 与 `_report_to_langfuse` 既有两 Score 逻辑）：

```python
def verify_citations(state: dict) -> dict:
    """从 analyst_reports 提取所有 Claim，批量校验（按分析师归属聚合）。

    harden-citation-semantic-coverage：FAIL 分桶；值级 FAIL 产出定向重试目标
    与失败明细（供 after_citation 分流与重试上下文注入）；正文 markdown 数字
    普查产出 citation_coverage（监控告警，不进路由）。
    """
    reports = state.get("analyst_reports") or {}

    per_agent: dict[str, list[CitationResult]] = {}
    claims_by_agent: dict[str, list[Claim]] = {}
    for agent, report in reports.items():
        claims = _extract_claims(report)
        claims_by_agent[agent] = claims
        per_agent[agent] = verify_claims(claims, state)
    results = [r for rs in per_agent.values() for r in rs]
    report = CitationReport.from_results(results)

    # 分桶聚合：仅 value_mismatch 触发定向重试（D3）；格式类 FAIL 直判不重试
    retry_targets: list[str] = []
    retry_feedback: dict[str, list[dict]] = {}
    fail_buckets: dict[str, int] = {}
    for agent, rs in per_agent.items():
        for r in rs:
            if r.status != "FAIL" or r.bucket is None:
                continue
            fail_buckets[r.bucket] = fail_buckets.get(r.bucket, 0) + 1
            if r.bucket != "value_mismatch":
                continue
            if agent not in retry_targets:
                retry_targets.append(agent)
            retry_feedback.setdefault(agent, []).append(
                {
                    "field_ref": r.claim.field_ref,
                    "stated_value": r.claim.stated_value,
                    "ground_truth": r.ground_truth,
                    "delta": r.delta,
                    "interpretation": r.claim.interpretation,
                }
            )
    retry_targets.sort()

    # 正文覆盖率：合并四分析师 markdown 普查，claim stated_value 全集为认领池
    all_stated = [
        float(c.stated_value)
        for claims in claims_by_agent.values()
        for c in claims
        if _is_float(c.stated_value)
    ]
    markdown = "\n\n".join(_markdown_of(r) for r in reports.values())
    coverage = compute_coverage(markdown, all_stated)

    _report_to_langfuse(report, coverage)

    iteration_count = state.get("iteration_count", 0)
    fail_count = sum(1 for r in results if r.status == "FAIL")
    fail_rate = fail_count / len(results) if results else 0.0
    fail_rates = list(state.get("citation_fail_rates") or []) + [fail_rate]

    minor_fail = (not report.all_passed) and fail_count <= 1 and fail_rate <= 0.05
    if minor_fail:
        update_current_span(
            metadata={"citation_minor_fail_deescalated": True, "fail_rates": fail_rates},
            level="WARNING",
        )

    # 格式类 FAIL 直判放行（D3）：有 FAIL 但无值级重试目标 → incident 候选可观测
    if not report.all_passed and not retry_targets:
        update_current_span(
            metadata={
                "citation_format_fail_incident_candidate": True,
                "fail_buckets": fail_buckets,
            },
            level="WARNING",
        )

    if not report.all_passed and iteration_count + 1 < 3 and citation_retry_stagnated(fail_rates):
        update_current_span(
            metadata={"citation_retry_deescalated": True, "fail_rates": fail_rates},
            level="WARNING",
        )

    return {
        "citation_report": report.model_dump(),
        "citation_pass": report.all_passed,
        "iteration_count": iteration_count + 1,
        "citation_fail_rates": fail_rates,
        "citation_minor_fail": minor_fail,
        "citation_retry_targets": retry_targets,
        "citation_retry_feedback": retry_feedback,
        "citation_fail_buckets": fail_buckets,
        "citation_coverage": coverage.coverage,
    }


def _is_float(v: object) -> bool:
    try:
        float(v)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False


def _markdown_of(report: AnalystReport | dict) -> str:
    if isinstance(report, AnalystReport):
        return report.markdown
    if isinstance(report, dict):
        return str(report.get("markdown") or "")
    return ""
```

`_report_to_langfuse` 改签名 `def _report_to_langfuse(report: CitationReport, coverage: CoverageReport) -> None:`，在两既有 Score 之后追加：

```python
        # citation_coverage（harden-citation-semantic-coverage）：NUMERIC 0-1，
        # 只监控不进路由；< 0.8 告警（span WARNING + 日志）
        client.score_current_trace(
            name="citation_coverage",
            value=round(coverage.coverage, 4),
            data_type="NUMERIC",
            comment=f"{coverage.matched}/{coverage.total} numbers claimed",
            metadata={"unmatched": coverage.unmatched[:20]},
        )
        if coverage.coverage < 0.8:
            logger.warning(
                "citation_coverage %.4f < 0.8：%d/%d 未认领 %s",
                coverage.coverage, len(coverage.unmatched), coverage.total, coverage.unmatched[:10],
            )
            client.update_current_span(
                metadata={
                    "citation_coverage_alert": True,
                    "citation_coverage": coverage.coverage,
                    "unmatched": coverage.unmatched[:20],
                },
                level="WARNING",
            )
```

文件 import 区追加：`from finance_agent.citation_coverage import CoverageReport, compute_coverage`、`from finance_agent.citation import CitationResult`（连同既有 import 调整）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_citation_node.py -v`
Expected: PASS（存量 + 新增 7 项）

- [ ] **Step 5: Commit**

```bash
git add tests/nodes/test_citation_node.py src/finance_agent/nodes/citation_node.py src/finance_agent/state.py
git commit -m "feat(citation): citation_node 分桶聚合 + 定向重试目标 + citation_coverage Score（T6）"
```

---

### Task 7: 重试分流路由 + 定向 Send + 重试反馈注入 context

**Files:**
- Modify: `src/finance_agent/routing.py`（after_citation 分桶、route_to_analysts 过滤）
- Modify: `src/finance_agent/nodes/analysts.py`（4 个分析师节点注入重试反馈段）
- Test: `tests/test_routing.py`（追加 Test 类）、`tests/nodes/test_analysts.py`（追加 Test 类）

**Interfaces:**
- Consumes: T6 state 输出（citation_retry_targets / citation_retry_feedback）
- Produces:
  - `after_citation` 新语义：PASS/minor → render；无值级目标 → render（格式类直判）；有目标且未停滞且 `iteration_count < 3` → retry
  - `route_to_analysts`：`state.get("citation_retry_targets")` 非空时只 Send 目标分析师
  - `_retry_feedback_section(state: dict, agent_name: str) -> str` — 重试反馈 context 段（无反馈返回 ""）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_routing.py 追加：

from finance_agent.routing import after_citation, route_to_analysts


class TestAfterCitationBucketRouting:
    def test_pass_goes_render(self):
        assert after_citation({"citation_pass": True}) == "render"

    def test_minor_fail_goes_render(self):
        assert after_citation({"citation_pass": False, "citation_minor_fail": True}) == "render"

    def test_value_mismatch_triggers_retry(self):
        state = {
            "citation_pass": False,
            "citation_minor_fail": False,
            "citation_retry_targets": ["fundamental"],
            "iteration_count": 1,
            "citation_fail_rates": [0.1],
        }
        assert after_citation(state) == "retry"

    def test_format_only_fail_goes_render(self):
        """格式类 FAIL（无值级目标）→ 直判放行，不重试（D3）。"""
        state = {
            "citation_pass": False,
            "citation_minor_fail": False,
            "citation_retry_targets": [],
            "citation_fail_buckets": {"semantic_term_mismatch": 2},
            "iteration_count": 1,
            "citation_fail_rates": [0.1],
        }
        assert after_citation(state) == "render"

    def test_retry_cap_unchanged(self):
        """iteration_count 上限 3 语义不回归。"""
        state = {
            "citation_pass": False,
            "citation_minor_fail": False,
            "citation_retry_targets": ["fundamental"],
            "iteration_count": 3,
            "citation_fail_rates": [0.3, 0.2, 0.1],
        }
        assert after_citation(state) == "render"

    def test_stagnation_still_deescalates(self):
        state = {
            "citation_pass": False,
            "citation_minor_fail": False,
            "citation_retry_targets": ["fundamental"],
            "iteration_count": 2,
            "citation_fail_rates": [0.10, 0.09],
        }
        assert after_citation(state) == "render"


class TestTargetedRetryDispatch:
    def test_initial_run_sends_all_four(self):
        sends = route_to_analysts({"stock_code": "600519"})
        assert len(sends) == 4

    def test_retry_sends_only_targets(self):
        sends = route_to_analysts(
            {"stock_code": "600519", "citation_retry_targets": ["fundamental"]}
        )
        assert len(sends) == 1
        assert sends[0].node == "fundamental_analyst"
```

```python
# tests/nodes/test_analysts.py 追加：

from finance_agent.nodes.analysts import _retry_feedback_section


class TestRetryFeedbackSection:
    def test_no_feedback_returns_empty(self):
        assert _retry_feedback_section({}, "fundamental") == ""

    def test_feedback_renders_failed_claims(self):
        state = {
            "citation_retry_feedback": {
                "fundamental": [
                    {
                        "field_ref": "solvency_metrics.资产负债率.2023",
                        "stated_value": 99.0,
                        "ground_truth": 38.0,
                        "delta": 61.0,
                        "interpretation": "2023 年资产负债率 99%",
                    }
                ]
            }
        }
        section = _retry_feedback_section(state, "fundamental")
        assert "上轮引用校验失败" in section
        assert "solvency_metrics.资产负债率.2023" in section
        assert "38.0" in section  # ground_truth 必须随反馈给出（与旧盲目重跑的关键区别）
        assert "99.0" in section

    def test_feedback_scoped_to_agent(self):
        state = {"citation_retry_feedback": {"macro": [{"field_ref": "x", "stated_value": 1, "ground_truth": 2, "delta": 1, "interpretation": "y"}]}}
        assert _retry_feedback_section(state, "fundamental") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_routing.py tests/nodes/test_analysts.py -v`
Expected: FAIL（新路由语义未实现 / `_retry_feedback_section` 不存在）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/routing.py`：

```python
def after_citation(state: dict) -> str:
    """引用校验路由（harden-citation-semantic-coverage 按桶分流）：

    PASS / 轻微失败 → 渲染；仅值级 FAIL（value_mismatch）触发定向重试
    （citation_retry_targets 非空）；格式类 FAIL（术语/期次/内部不一致、
    路径不可解析）与 UNVERIFIABLE 直判放行不重试（实测三轮停滞
    35%→38%→31%，重试零收益）；轮次上限与停滞降级语义不变。
    """
    if state.get("citation_pass", False) or state.get("citation_minor_fail", False):
        return "render"
    if not state.get("citation_retry_targets"):
        return "render"
    if state.get("iteration_count", 0) < 3:
        if citation_retry_stagnated(state.get("citation_fail_rates") or []):
            return "render"
        return "retry"
    return "render"


def route_to_analysts(state: dict) -> list[Send]:
    """Layer I 派发：首轮 4 分析师并行；引用校验重试轮只 Send 值级 FAIL 的目标
    分析师（harden-citation-semantic-coverage 定向重试），其余分析师结果复用
    （analyst_reports merge_dicts 保留旧值，重跑覆盖目标键）。"""
    all_sends = {
        "technical": Send("technical_analyst", state),
        "macro": Send("macro_analyst", state),
        "fundamental": Send("fundamental_analyst", state),
        "sentiment": Send("sentiment_analyst", state),
    }
    targets = state.get("citation_retry_targets") or []
    if targets:
        return [all_sends[t] for t in targets if t in all_sends]
    return list(all_sends.values())
```

`src/finance_agent/nodes/analysts.py`：

```python
def _retry_feedback_section(state: dict, agent_name: str) -> str:
    """定向重试反馈段（harden-citation-semantic-coverage D3）：值级 FAIL 明细 +
    ground_truth 注入重试上下文——与旧「盲目重跑」的关键区别是给 LLM 改错信息。
    """
    feedback = (state.get("citation_retry_feedback") or {}).get(agent_name) or []
    if not feedback:
        return ""
    lines = ["## 上轮引用校验失败（必须修正以下数据引用，ground_truth 为真实值）"]
    for item in feedback:
        lines.append(
            f"- field_ref={item['field_ref']}：你写的值 {item['stated_value']}，"
            f"真实值 {item['ground_truth']}（偏差 {item['delta']}）。"
            f"原表述：{item['interpretation']}"
        )
    return "\n".join(lines)
```

4 个分析师节点函数中 context 构建后追加（以 technical_analyst 为例，其余三个同构）：

```python
def technical_analyst(state: dict) -> dict:
    """Layer I 技术面分析师 Agent。"""
    context = _build_technical_context(state)
    feedback = _retry_feedback_section(state, "technical")
    if feedback:
        context = f"{context}\n\n{feedback}"
    ...
```

（macro → `_retry_feedback_section(state, "macro")`，fundamental/sentiment 同理。）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_routing.py tests/nodes/test_analysts.py tests/test_graph_5layer.py -v`
Expected: PASS（含存量图结构回归）

- [ ] **Step 5: Commit**

```bash
git add tests/test_routing.py tests/nodes/test_analysts.py src/finance_agent/routing.py src/finance_agent/nodes/analysts.py
git commit -m "feat(citation): after_citation 按桶分流 + Send 定向重试 + 重试反馈注入（T7）"
```

---

### Task 8: context 序列语义头（机生注入，technical/macro/fundamental）

**Files:**
- Modify: `src/finance_agent/nodes/analysts.py`（`_series_semantic_header` + 三个 context 构建器接入）
- Test: `tests/nodes/test_analysts.py`（追加 Test 类）

**Interfaces:**
- Consumes: state 的 kline/macro_indicators/quarterly_trend/报表 DataFrame 实际形态
- Produces: `_series_semantic_header(direction: str, latest_label: str, count: int) -> str`，返回 `# 序列语义: {direction}, {latest_label}, 共{count}期`

注入点（D4：机器生成，内容须与 state 实际数据形态一致）：
- technical：kline 末行日期 + 窗口后期数（`min(len(kline), 60)`，kline 缺失时退化为无期次的方向声明）
- macro：首个含 records 指标的 `records[0]["月份"]` + 展示期数（`min(len(records), 3)`）
- fundamental：三大报表段（首行报告日 + `min(len(df),3)`，表格为降序）、指标 dict 段（最新年键）、季度趋势段（`quarters[0]` + 期数）

- [ ] **Step 1: Write the failing test**

```python
# tests/nodes/test_analysts.py 追加：

import pandas as pd

from finance_agent.nodes.analysts import (
    _build_fundamental_context,
    _build_macro_context,
    _build_technical_context,
    _series_semantic_header,
)


class TestSeriesSemanticHeader:
    def test_header_format(self):
        h = _series_semantic_header("时间正序(旧→新)", "index -1 = 最新交易日(2026-08-28)", 60)
        assert h == "# 序列语义: 时间正序(旧→新), index -1 = 最新交易日(2026-08-28), 共60期"

    def test_technical_header_declares_direction_and_latest_date(self):
        """incident 022 修复：语义头机生，期次与 state 实际数据一致。"""
        state = {
            "stock_name": "中际旭创",
            "stock_code": "300308",
            "kline": pd.DataFrame(
                {"日期": [f"2026-08-{d:02d}" for d in range(1, 29)], "收盘": [100.0] * 28}
            ),
            "technical_indicators": {"MA": {"5": [100.0 + i for i in range(28)]}},
        }
        ctx = _build_technical_context(state)
        assert "# 序列语义: 时间正序(旧→新)" in ctx
        assert "index -1 = 最新交易日(2026-08-28)" in ctx
        assert "共28期" in ctx
        # 与校验语义一致：列表末尾为最新一期（既有负索引声明仍在）
        assert "-1=最新一期" in ctx

    def test_technical_header_without_kline_degrades(self):
        """kline 缺失 → 方向声明保留，日期省略（不编造期次）。"""
        state = {"technical_indicators": {"MA": {"5": [1.0, 2.0]}}}
        ctx = _build_technical_context(state)
        assert "时间正序(旧→新)" in ctx
        assert "最新交易日" not in ctx

    def test_macro_header_declares_descending_and_latest_month(self):
        state = {
            "stock_name": "x",
            "stock_code": "x",
            "macro_indicators": {
                "cpi": {
                    "records": [
                        {"月份": "2026年07月份", "全国-同比增长": 0.4},
                        {"月份": "2026年06月份", "全国-同比增长": 0.5},
                    ],
                    "freshness": "fresh",
                }
            },
        }
        ctx = _build_macro_context(state)
        assert "# 序列语义: 时间降序(新→旧)" in ctx
        assert "index 0 = 最新一期(2026年07月份)" in ctx
        assert "共2期" in ctx

    def test_fundamental_headers(self):
        """报表段声明降序 + 首行最新期；季度趋势段声明 index 0 最新。"""
        df = pd.DataFrame(
            {"报告日": ["20251231", "20241231", "20231231"], "营业总收入": [1.0, 2.0, 3.0]}
        )
        state = {
            "stock_name": "x",
            "stock_code": "x",
            "balance_sheet": df,
            "income_statement": df,
            "cash_flow_statement": df,
            "quarterly_trend": {
                "quarters": ["2025Q4", "2025Q3"],
                "net_profit": [1.0, 2.0],
                "qoq": [1.0, 2.0],
                "yoy": [1.0, 2.0],
                "warnings": [],
            },
        }
        ctx = _build_fundamental_context(state)
        assert "行按报告期降序(新→旧), 首行 = 最新报告期(20251231)" in ctx
        assert "# 序列语义: 时间降序(新→旧), index 0 = 最新季度(2025Q4), 共2期" in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_analysts.py -v -k SemanticHeader`
Expected: FAIL（`_series_semantic_header` 不存在 / 断言缺头）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/nodes/analysts.py`：

```python
def _series_semantic_header(direction: str, latest_label: str, count: int) -> str:
    """序列语义头（harden-citation-semantic-coverage D4）：机生声明排序方向 +
    最新期定位 + 期数。内容由代码依据 state 实际数据形态生成，LLM 所见语义
    与校验器解析语义一致（incident 022 期次错位疾病的主防线）。"""
    return f"# 序列语义: {direction}, {latest_label}, 共{count}期"
```

`_build_technical_context` 中 `sections.append(...)` 改为：

```python
        trimmed, did_trim = _trim_technical_indicators(indicators)
        # 机生语义头（incident 022）：方向 + 最新交易日（取自 kline 末行）+ 期数。
        # 技术序列与 kline 等长升序，裁剪后期数 = min(序列长, 窗口)。
        n_shown = _TECHNICAL_CONTEXT_WINDOW if did_trim else _series_len(trimmed)
        kline = state.get("kline")
        latest_date = ""
        try:
            latest_date = str(kline["日期"].iloc[-1]) if kline is not None and len(kline) else ""
        except (KeyError, IndexError, TypeError):
            latest_date = ""
        latest_label = (
            f"index -1 = 最新交易日({latest_date})" if latest_date else "index -1 = 最新一期"
        )
        header = _series_semantic_header("时间正序(旧→新)", latest_label, n_shown)
        note = (
            f"各序列为最近 {_TECHNICAL_CONTEXT_WINDOW} 期，更早历史已省略；序列为时间正序（旧→新），列表末尾为最新一期；"
            if did_trim
            else "序列为时间正序（旧→新），列表末尾为最新一期；"
        )
        sections.append(
            f"{header}\n技术指标数据（state 键 technical_indicators；"
            f"{note}field_ref 引用序列值时用负索引：-1=最新一期）:\n"
            f"{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
```

并新增辅助：

```python
def _series_len(trimmed: dict) -> int:
    """裁剪结构内任一序列的长度（各序列等长；无序列返回 0）。"""
    for series in trimmed.values():
        if isinstance(series, dict):
            for values in series.values():
                if isinstance(values, list):
                    return len(values)
        elif isinstance(series, list):
            return len(series)
    return 0
```

`_build_macro_context` 的 sections.append 改为：

```python
        # 机生语义头：宏观序列降序（index 0 = 最新），期次取首个含 records 指标
        # 的最新月份与展示期数（records[:3] 截断后实际长度）
        latest_month, n_shown = "", 0
        for value in macro.values():
            if isinstance(value, dict):
                recs = value.get("records") or []
                if recs:
                    latest_month = str(recs[0].get("月份", ""))
                    n_shown = min(len(recs), 3)
                    break
        if latest_month:
            sections.append(
                _series_semantic_header("时间降序(新→旧)", f"index 0 = 最新一期({latest_month})", n_shown)
            )
        sections.append(
            f"宏观经济指标（state 键 macro_indicators，近3期）:\n"
            f"{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
```

`_build_fundamental_context` 三处改动：

```python
        # 报表段：降序声明 + 首行最新报告期（机生）
        recent = df.head(3) if len(df) > 3 else df
        latest_period = str(recent["报告日"].iloc[0]) if "报告日" in recent.columns and len(recent) else ""
        period_label = f", 首行 = 最新报告期({latest_period})" if latest_period else ""
        sections.append(
            f"# 表格语义: 行按报告期降序(新→旧){period_label}, 共{len(recent)}期\n"
            f"{name}（state 键 {key}，近3年）:\n{recent.to_string(index=False)}"
        )
```

季度趋势段：

```python
    qtrend = state.get("quarterly_trend")
    if qtrend:
        quarters = qtrend.get("quarters") or []
        if quarters:
            sections.append(
                _series_semantic_header("时间降序(新→旧)", f"index 0 = 最新季度({quarters[0]})", len(quarters))
            )
        sections.append(
            f"季度趋势（state 键 quarterly_trend）:\n{json.dumps(qtrend, ensure_ascii=False, default=str)}"
        )
```

指标 dict 段（盈利能力等四维度 + 杜邦 + 增长率）在各自标题内补最新年键——取 `financial_indicators` 首行报告日年份或 profitability_metrics 任意指标的最大年键：

```python
    # 指标 dict 以年份为键：声明最新年（机生，取自任一有值指标的最大年键）
    latest_year = ""
    prof = state.get("profitability_metrics") or {}
    for metric_values in prof.values():
        if isinstance(metric_values, dict) and metric_values:
            latest_year = max(str(y) for y in metric_values)
            break
    year_note = f"，dict 以年份为键，最新年 = {latest_year}" if latest_year else ""
    for label, key in [
        ("盈利能力", "profitability_metrics"),
        ("偿债能力", "solvency_metrics"),
        ("运营效率", "efficiency_metrics"),
        ("现金流", "cashflow_metrics"),
    ]:
        val = state.get(key)
        if val:
            sections.append(
                f"{label}（state 键 {key}{year_note}）:\n{json.dumps(val, ensure_ascii=False, default=str)}"
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_analysts.py -v`
Expected: PASS（存量 + 新增 6 项）

- [ ] **Step 5: Commit**

```bash
git add tests/nodes/test_analysts.py src/finance_agent/nodes/analysts.py
git commit -m "feat(analysts): context 序列语义头机生注入（technical/macro/fundamental，incident 022 主防线）（T8）"
```

---

### Task 9: 分析师 prompts 声明 metric_name/period + 覆盖纪律

**Files:**
- Modify: `src/finance_agent/prompts/technical_analyst.md`、`macro_analyst.md`、`fundamental_analyst.md`、`sentiment_analyst.md`
- Test: `tests/test_prompt_contracts.py`（先跑存量确认不被破坏；如存量断言覆盖 claim schema 则按其口径补断言）

- [ ] **Step 1: Write the failing test**

`tests/test_prompt_contracts.py` 追加（如已有同类类则并入）：

```python
class TestClaimSemanticDeclarationPrompts:
    """harden-citation-semantic-coverage：分析师 prompt 声明 metric_name/period。"""

    @pytest.mark.parametrize(
        "prompt", ["technical_analyst", "macro_analyst", "fundamental_analyst"]
    )
    def test_data_analyst_prompts_declare_metric_name_and_period(self, prompt):
        text = (PROMPTS_DIR / f"{prompt}.md").read_text(encoding="utf-8")
        assert '"metric_name"' in text
        assert '"period"' in text

    def test_prompts_declare_coverage_discipline(self):
        """覆盖纪律：正文每个关键数值须可追溯到 claim（ALCE recall 压力）。"""
        for prompt in ("technical_analyst", "macro_analyst", "fundamental_analyst"):
            text = (PROMPTS_DIR / f"{prompt}.md").read_text(encoding="utf-8")
            assert "正文" in text and "claim" in text.lower()

    def test_sentiment_prompt_declares_optional_fields(self):
        """舆情分析师以 entity claim 为主：metric_name/period 标注为可选。"""
        text = (PROMPTS_DIR / "sentiment_analyst.md").read_text(encoding="utf-8")
        assert "metric_name" in text
```

先读 `tests/test_prompt_contracts.py` 现有常量名（如 `PROMPTS_DIR` 不存在则用该文件既有的路径构造方式），保持与该文件风格一致。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: FAIL（prompts 未含新字段）

- [ ] **Step 3: Write minimal implementation**

四个 prompt 的 claims JSON 示例与「要求」列表修改：

technical_analyst.md — claims 示例改为：

```json
    {
      "claim_type": "numerical",
      "source_type": "data",
      "field_ref": "technical_indicators.MA.5.-1",
      "stated_value": 13.0,
      "interpretation": "MA5 为 13.0",
      "metric_name": "MA",
      "period": "2026-08-28"
    }
```

「要求」追加：

```markdown
6. data 型 claim 必填 metric_name 与 period：metric_name 取指标词表规范名（MA/MACD/DIF/DEA/RSI/BOLL/KDJ/max_drawdown/volatility/beta/var_95），须与 field_ref 的指标段一致；period 填该值对应的实际交易日（YYYY-MM-DD，见 context 序列语义头的最新期标注）
7. 覆盖纪律：markdown 正文中每个关键数值（百分比/金额/倍数）都必须与某条 claim 的 stated_value 一致——未被 claim 认领的数字会被覆盖率审计计为黑数字
8. context 中每个序列块开头的「# 序列语义」声明了排序方向与最新期位置，引用数值前先核对该声明
```

macro_analyst.md — 示例 `"metric_name": "CPI", "period": "2026-07"`；要求追加同构条款（词表：CPI/PMI/M2/LPR；period 填 YYYY-MM 月份，见序列语义头）。

fundamental_analyst.md — 示例 `"metric_name": "ROE", "period": "2025"`；词表：ROE/ROA/ROIC/毛利率/净利率/资产负债率/流动比率/速动比率/利息覆盖倍数/存货周转率/应收账款周转率/应付账款周转率/总资产周转率/经营现金流\/净利润/FCF/权益乘数 等；period 填年份（2024）或报告日（20251231）或季度（2025Q4）。

sentiment_analyst.md — 示例 claims 追加 `"metric_name": null, "period": null` 并说明「entity/event 型 claim 可置 null」。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_contracts.py src/finance_agent/prompts/
git commit -m "docs(prompts): 分析师 prompt 声明 metric_name/period + 覆盖纪律（T9；deploy_prompts 发布为 live 步骤）"
```

---

### Task 10: 基准集 v1.1 生成器（near_miss 四档双向 + semantic_mismatch 子集）

**Files:**
- Create: `evals/claim_benchmark/build_v11.py`
- Test: `tests/evals/claim_benchmark/test_build_v11.py`

**Interfaces:**
- Consumes: `evals/claim_benchmark/data/benchmark_v1_labeled.jsonl`（clean 基样本含 label/gt）；T1 metric_vocab
- Produces:
  - `build_v11(input_path, out_prefix, near_miss_n, semantic_n, seed) -> int`（CLI 同 build_benchmark.py 风格）
  - 输出 `benchmark_v11.jsonl/.csv`；entry schema 继承 v1 + `should_pass: bool | None`（near_miss 行）+ `tamper_amp: float | None`；label 由规则确定（should_pass→PASS 否则 FAIL；semantic 错配→FAIL，对照→原 label），不经 LLM 标注（披露）

构造规则：
- near_miss：从 label==PASS 且 gt/claim 数值可用的 clean 行取基样；篡改幅度四档 {0.003, 0.005, 0.007, 0.01} 轮转，方向 ± 交替；`tampered = round(gt*(1±amp), 2)`；篡改后按数值型容差公式 `abs(gt-tampered) < max(0.01, abs(gt)*0.005)` 重算 `should_pass`；配额 steering 使 should_pass 占比 ≈50%（先全量生成候选再按 50/50 配额抽取）；delta 重算写入。
- semantic_mismatch：从 field_ref 可解析出指标段的 clean 行取基样；term 风味：填入词表中不同的规范键（取 `(canonical_index+1) % len(vocab)` 确定性错位）；period 风味（仅 field_ref 有显式期次段的行）：claim.period = 相邻不同期（年份 ±1）；对照组：填正确 metric_name/period（label 沿用原 label）。三小组各 ≈semantic_n/3。
- subsets 标记：near_miss / semantic_mismatch+semantic_term / semantic_mismatch+semantic_period / semantic_mismatch+semantic_control。

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/claim_benchmark/test_build_v11.py
"""TDD tests for build_v11.py — 基准集 v1.1 构造规则。"""

import json
from pathlib import Path

from evals.claim_benchmark.build_v11 import build_v11


def _base_rows() -> list[dict]:
    rows = []
    for i in range(30):
        rows.append(
            {
                "entry_id": f"benchmark_v1_{i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "stated_value": 45.2,
                    "interpretation": "毛利率 45.2%",
                },
                "ground_truth": 45.2,
                "delta": 0.0,
                "verifier_status": "PASS",
                "rejudged_status": "PASS",
                "trace_id": f"t{i % 3}",
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "trace_timestamp": "2026-08-30",
                "trace_version": "post_fix",
                "coverage_gap": False,
                "subsets": ["clean"],
                "disease": None,
                "label": "PASS",
            }
        )
    return rows


def _write_pool(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "pool.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def _load(out_prefix: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in out_prefix.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestNearMissV11:
    def test_four_tier_amplitudes_present(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        amps = {
            e["tamper_amp"]
            for e in _load(out)
            if "near_miss" in e["subsets"]
        }
        assert amps == {0.003, 0.005, 0.007, 0.01}

    def test_half_should_pass(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        nm = [e for e in _load(out) if "near_miss" in e["subsets"]]
        should_pass = sum(1 for e in nm if e["should_pass"])
        assert should_pass == len(nm) / 2

    def test_label_matches_should_pass(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        for e in _load(out):
            if "near_miss" in e["subsets"]:
                assert e["label"] == ("PASS" if e["should_pass"] else "FAIL")
                # 篡改值确实落在声明幅度上（容差重算后与 should_pass 自洽）
                gt = float(e["ground_truth"])
                stated = float(e["claim"]["stated_value"])
                delta = abs(gt - stated)
                tol = max(0.01, abs(gt) * 0.005)
                assert (delta < tol) == e["should_pass"]


class TestSemanticMismatchSubset:
    def test_term_mismatch_labeled_fail(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        terms = [e for e in _load(out) if "semantic_term" in e["subsets"]]
        assert terms, "应生成 semantic_term 风味样本"
        for e in terms:
            assert e["label"] == "FAIL"
            assert e["claim"]["metric_name"] not in (None, "毛利率")

    def test_period_mismatch_labeled_fail(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        periods = [e for e in _load(out) if "semantic_period" in e["subsets"]]
        assert periods
        for e in periods:
            assert e["label"] == "FAIL"
            assert e["claim"]["period"] not in (None, "2024")

    def test_control_keeps_original_label(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        controls = [e for e in _load(out) if "semantic_control" in e["subsets"]]
        assert controls
        for e in controls:
            assert e["label"] == "PASS"
            assert e["claim"]["metric_name"] == "毛利率"
            assert e["claim"]["period"] == "2024"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/claim_benchmark/test_build_v11.py -v`
Expected: FAIL（module 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python
"""基准集 v1.1 生成（harden-citation-semantic-coverage）：

- near_miss 重构：篡改幅度 ±{0.3%, 0.5%, 0.7%, 1%} 四档探容差边界，
  50% should_pass（容差内，标签 PASS）→ 同时测量漏检与误报；
- 新增 semantic_mismatch 子集：数值/field_ref 正确但术语或期次张冠李戴
  （标签 FAIL），配对照组（正确申报，沿用原 label）测误报；
- 标签由规则确定（篡改后按数值型容差公式重算 should_pass；语义错配构造
  即 FAIL），不经 LLM 标注——合成样本标签确定性，披露于输出统计。

用法:
    uv run python evals/claim_benchmark/build_v11.py \
        --input evals/claim_benchmark/data/benchmark_v1_labeled.jsonl \
        --near-miss 40 --semantic 30 --seed 42 \
        --out-prefix evals/claim_benchmark/data/benchmark_v11
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from finance_agent.metric_vocab import (  # noqa: E402
    _METRIC_ALIASES,
    canonical_metric,
    field_ref_metric_segments,
    field_ref_period_segment,
)

TAMPER_AMPS = (0.003, 0.005, 0.007, 0.01)


def _tol_pass(stated: float, gt: float) -> bool:
    """数值型容差公式镜像（与 citation.py 数值型一致）。"""
    return abs(gt - stated) < max(0.01, abs(gt) * 0.005)


def _eligible_clean(rows: list[dict]) -> list[dict]:
    """label==PASS、gt 数值可用、clean 子集的基样。"""
    out = []
    for r in rows:
        if r.get("label") != "PASS" or "clean" not in (r.get("subsets") or []):
            continue
        try:
            float(r["ground_truth"])
        except (TypeError, ValueError):
            continue
        out.append(r)
    return out


def _make_near_miss(base: list[dict], n: int, rng: random.Random) -> list[dict]:
    """四档篡改 + 50/50 should_pass 配额（候选生成后按配额抽取）。"""
    candidates: list[dict] = []
    for i, row in enumerate(base):
        gt = float(row["ground_truth"])
        amp = TAMPER_AMPS[i % len(TAMPER_AMPS)]
        sign = 1.0 if i % 2 == 0 else -1.0
        tampered = round(gt * (1 + sign * amp), 2)
        should_pass = _tol_pass(tampered, gt)
        entry = {
            **row,
            "claim": {**row["claim"], "stated_value": tampered},
            "delta": abs(gt - tampered),
            "subsets": ["near_miss"],
            "should_pass": should_pass,
            "tamper_amp": amp,
            "label": "PASS" if should_pass else "FAIL",
        }
        candidates.append(entry)
    pass_pool = [c for c in candidates if c["should_pass"]]
    fail_pool = [c for c in candidates if not c["should_pass"]]
    rng.shuffle(pass_pool)
    rng.shuffle(fail_pool)
    half = n // 2
    picked = pass_pool[:half] + fail_pool[: n - half]
    # 池不足时如实披露：用余量互补，占比偏离 50% 由输出统计呈现
    if len(picked) < n:
        rest = [c for c in candidates if c not in picked]
        rng.shuffle(rest)
        picked.extend(rest[: n - len(picked)])
    return picked[:n]


def _semantic_bases(base: list[dict]) -> list[dict]:
    """可注入语义字段的基样：field_ref 有指标段且首个指标段可 canonical 化。"""
    return [
        r
        for r in base
        if field_ref_metric_segments(r["claim"]["field_ref"])
        and canonical_metric(field_ref_metric_segments(r["claim"]["field_ref"])[0])
    ]


def _make_semantic(base: list[dict], n: int, rng: random.Random) -> list[dict]:
    """term / period / control 三小组各 ≈n/3。"""
    vocab = sorted(_METRIC_ALIASES)
    rng.shuffle(base)
    third = n // 3
    out: list[dict] = []
    term_pool = [r for r in base if field_ref_metric_segments(r["claim"]["field_ref"])]
    for row in term_pool[:third]:
        segs = field_ref_metric_segments(row["claim"]["field_ref"])
        correct = canonical_metric(segs[0]) or segs[0]
        wrong = vocab[(vocab.index(correct) + 1) % len(vocab)] if correct in vocab else "净利率"
        if wrong == correct:
            wrong = vocab[(vocab.index(correct) + 2) % len(vocab)]
        out.append(
            {
                **row,
                "claim": {**row["claim"], "metric_name": wrong},
                "subsets": ["semantic_mismatch", "semantic_term"],
                "should_pass": None,
                "tamper_amp": None,
                "label": "FAIL",
            }
        )
    period_pool = [r for r in base if field_ref_period_segment(r["claim"]["field_ref"])]
    for row in period_pool[:third]:
        seg = field_ref_period_segment(row["claim"]["field_ref"]) or ""
        wrong_period = str(int(seg[:4]) - 1) if seg[:4].isdigit() else "1999"
        out.append(
            {
                **row,
                "claim": {
                    **row["claim"],
                    "metric_name": canonical_metric(
                        field_ref_metric_segments(row["claim"]["field_ref"])[0]
                    ),
                    "period": wrong_period,
                },
                "subsets": ["semantic_mismatch", "semantic_period"],
                "should_pass": None,
                "tamper_amp": None,
                "label": "FAIL",
            }
        )
    for row in base[: n - len(out)]:
        segs = field_ref_metric_segments(row["claim"]["field_ref"])
        seg_period = field_ref_period_segment(row["claim"]["field_ref"])
        out.append(
            {
                **row,
                "claim": {
                    **row["claim"],
                    "metric_name": canonical_metric(segs[0]) if segs else None,
                    "period": seg_period,
                },
                "subsets": ["semantic_mismatch", "semantic_control"],
                "should_pass": None,
                "tamper_amp": None,
            }
        )
    return out


def build_v11(
    input_path: Path,
    out_prefix: Path,
    near_miss_n: int,
    semantic_n: int,
    seed: int,
) -> int:
    with input_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rng = random.Random(seed)  # noqa: S311 - 可复现抽样
    base = _eligible_clean(rows)
    print(f"基样池: {len(base)} 条（label=PASS ∧ clean ∧ gt 数值可用）")

    entries = _make_near_miss(base, near_miss_n, rng) + _make_semantic(
        _semantic_bases(base), semantic_n, rng
    )
    for i, e in enumerate(entries):
        e["entry_id"] = f"benchmark_v11_{i:04d}"
        e["verifier_status"] = None
        e["rejudged_status"] = None

    nm = [e for e in entries if "near_miss" in e["subsets"]]
    sp = sum(1 for e in nm if e["should_pass"])
    print(f"near_miss {len(nm)} 条（should_pass {sp} = {sp / max(len(nm), 1):.0%}）")
    print(f"semantic_mismatch {sum(1 for e in entries if 'semantic_mismatch' in e['subsets'])} 条")
    print("[披露] v1.1 标签规则确定（容差公式重算 / 构造即 FAIL），不经 LLM 标注")

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    with out_prefix.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with out_prefix.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["entry_id", "subsets", "label", "should_pass", "tamper_amp",
                        "field_ref", "stated_value", "ground_truth", "delta",
                        "metric_name", "period"],
            extrasaction="ignore",
        )
        w.writeheader()
        for e in entries:
            w.writerow(
                {
                    "entry_id": e["entry_id"],
                    "subsets": "+".join(e["subsets"]),
                    "label": e["label"],
                    "should_pass": e.get("should_pass"),
                    "tamper_amp": e.get("tamper_amp"),
                    "field_ref": e["claim"].get("field_ref"),
                    "stated_value": e["claim"].get("stated_value"),
                    "ground_truth": e.get("ground_truth"),
                    "delta": e.get("delta"),
                    "metric_name": e["claim"].get("metric_name"),
                    "period": e["claim"].get("period"),
                }
            )
    print(f"已写: {out_prefix.with_suffix('.jsonl')} / {out_prefix.with_suffix('.csv')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="基准集 v1.1 生成")
    ap.add_argument("--input", required=True)
    ap.add_argument("--near-miss", type=int, default=40)
    ap.add_argument("--semantic", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-prefix", required=True)
    args = ap.parse_args()
    return build_v11(
        Path(args.input), Path(args.out_prefix), args.near_miss, args.semantic, args.seed
    )


if __name__ == "__main__":
    sys.exit(main())
```

注意 `_make_semantic` 中 control 组标签沿用原 label（PASS）；`_semantic_bases` 池保证 term/control 组首指标段可 canonical 化。若 `_METRIC_ALIASES` 私有导入触发 ruff 偏好，可在 metric_vocab 增加公开别名 `METRIC_VOCAB = _METRIC_ALIASES` 并改导入（二选一，以 ruff 结果为准）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/claim_benchmark/test_build_v11.py -v`
Expected: PASS（6 项）

- [ ] **Step 5: Commit**

```bash
git add tests/evals/claim_benchmark/test_build_v11.py evals/claim_benchmark/build_v11.py
git commit -m "feat(evals): 基准集 v1.1 生成器（near_miss 四档双向 + semantic_mismatch 子集）（T10）"
```

---

### Task 11: rejudge/measure v1.1（语义复判 + 子集分列披露 + 90% 检出门禁）

**Files:**
- Modify: `evals/claim_benchmark/rejudge.py`（语义前置检查）
- Modify: `evals/claim_benchmark/measure.py`（near_miss 分列 + semantic_mismatch 检出门禁行）
- Test: `tests/evals/claim_benchmark/test_rejudge.py`（追加）、`tests/evals/claim_benchmark/test_measure.py`（追加）

**Interfaces:**
- Consumes: T3 语义检查逻辑（离线镜像）、T10 v1.1 entry schema
- Produces:
  - `rejudge_claim` 新前置：claim 含 metric_name/period 时先跑离线语义检查（term 纯字符串；period 仅显式期次段可比，索引锚定跳过），FAIL 直接返回 "FAIL"
  - `measure()` 输出新增 `near_miss_over_line_recall`、`near_miss_in_line_fp_rate`、`semantic_mismatch_detection` 与门禁 `semantic_gate: {"gate": 0.9, "passed": ...}`

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/claim_benchmark/test_rejudge.py 追加：

from evals.claim_benchmark.rejudge import rejudge_claim


class TestRejudgeSemantic:
    def test_term_mismatch_rejudged_fail(self):
        """metric_name 与 field_ref 指标段不一致 → 离线复判 FAIL（数值正确也拦）。"""
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "profitability_metrics.毛利率.2024",
            "stated_value": 45.2,
            "interpretation": "净利率 45.2%",
            "metric_name": "净利率",
            "period": None,
        }
        assert rejudge_claim(claim, 45.2, 0.0) == "FAIL"

    def test_period_mismatch_rejudged_fail(self):
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "profitability_metrics.毛利率.2024",
            "stated_value": 45.2,
            "interpretation": "2023 年毛利率 45.2%",
            "metric_name": "毛利率",
            "period": "2023",
        }
        assert rejudge_claim(claim, 45.2, 0.0) == "FAIL"

    def test_semantic_control_rejudged_pass(self):
        """正确申报的 term/period → 语义检查通过，回落到容差复判 PASS。"""
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "profitability_metrics.毛利率.2024",
            "stated_value": 45.2,
            "interpretation": "2024 年毛利率 45.2%",
            "metric_name": "毛利率",
            "period": "2024",
        }
        assert rejudge_claim(claim, 45.2, 0.0) == "PASS"

    def test_legacy_claim_without_semantic_fields_unchanged(self):
        """v1 旧行（无新字段）复判行为不回归。"""
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": 40.0,
            "interpretation": "资产负债率 40%",
        }
        assert rejudge_claim(claim, 40.0, 0.0) == "PASS"
```

```python
# tests/evals/claim_benchmark/test_measure.py 追加：


class TestMeasureV11Subsets:
    def _entries(self) -> list[dict]:
        def near_miss(label: str, stated: float, gt: float, i: int) -> dict:
            return {
                "entry_id": f"benchmark_v11_{i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "stated_value": stated,
                    "interpretation": "x",
                },
                "ground_truth": gt,
                "delta": abs(gt - stated),
                "subsets": ["near_miss"],
                "should_pass": label == "PASS",
                "label": label,
            }

        def semantic(metric_name: str, label: str, i: int) -> dict:
            return {
                "entry_id": f"benchmark_v11_{100 + i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "stated_value": 45.2,
                    "interpretation": "x",
                    "metric_name": metric_name,
                },
                "ground_truth": 45.2,
                "delta": 0.0,
                "subsets": ["semantic_mismatch", "semantic_term"],
                "label": label,
            }

        entries = [
            near_miss("PASS", 45.2 * 1.003, 45.2, 0),  # 容差内 → 复判 PASS
            near_miss("FAIL", 45.2 * 1.01, 45.2, 1),  # 过线 → 复判 FAIL
            semantic("净利率", "FAIL", 0),  # 术语错配 → 复判 FAIL（检出）
        ]
        return entries

    def test_near_miss_split_disclosed(self):
        from evals.claim_benchmark.measure import measure

        rep = measure(self._entries())
        assert rep["near_miss_over_line_recall"] == 1.0  # 过线 1/1 检出
        assert rep["near_miss_in_line_fp_rate"] == 0.0  # 线内 0 误报

    def test_semantic_detection_gate(self):
        from evals.claim_benchmark.measure import measure

        rep = measure(self._entries())
        assert rep["semantic_mismatch_detection"] == 1.0
        assert rep["semantic_gate"] == {"gate": 0.9, "passed": True}

    def test_semantic_gate_fails_below_90(self):
        from evals.claim_benchmark.measure import measure

        entries = self._entries()
        # 再加 9 条术语正确但 label=FAIL 的构造（复判 PASS → 未检出）
        for i in range(9):
            entries.append(
                {
                    "entry_id": f"benchmark_v11_{200 + i:04d}",
                    "claim": {
                        "claim_type": "numerical",
                        "source_type": "data",
                        "field_ref": "profitability_metrics.毛利率.2024",
                        "stated_value": 45.2,
                        "interpretation": "x",
                        "metric_name": "毛利率",
                    },
                    "ground_truth": 45.2,
                    "delta": 0.0,
                    "subsets": ["semantic_mismatch", "semantic_term"],
                    "label": "FAIL",
                }
            )
        rep = measure(entries)
        assert rep["semantic_mismatch_detection"] == 0.1
        assert rep["semantic_gate"]["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/claim_benchmark/test_rejudge.py tests/evals/claim_benchmark/test_measure.py -v`
Expected: FAIL（语义复判/新键未实现）

- [ ] **Step 3: Write minimal implementation**

`evals/claim_benchmark/rejudge.py` 追加（`rejudge_claim` 开头接入前置）：

```python
def _rejudge_semantic(claim: dict) -> Status | None:
    """语义层离线复判（harden-citation-semantic-coverage 镜像 citation.py）：

    term 检查纯字符串（metric_name 规范键 vs field_ref 指标段）；
    period 检查仅显式期次段可比（索引锚定离线无从解析 → None 跳过，与
    管线「计缺口不 FAIL」对齐——baseline 的索引锚定样本期次维度不计检出）。
    返回 "FAIL" 或 None（通过/不适用）。
    """
    from finance_agent.metric_vocab import (
        canonical_metric,
        field_ref_metric_segments,
        field_ref_period_segment,
        period_matches,
    )

    field_ref = str(claim.get("field_ref") or "")
    metric_name = (claim.get("metric_name") or "").strip()
    if metric_name:
        canonical = canonical_metric(metric_name)
        seg_keys = {(canonical_metric(s) or s) for s in field_ref_metric_segments(field_ref)}
        if canonical is None or canonical not in seg_keys:
            return "FAIL"
    period = (claim.get("period") or "").strip()
    if period:
        actual = field_ref_period_segment(field_ref)
        if actual is not None and not period_matches(period, actual):
            return "FAIL"
    return None
```

`rejudge_claim` 在现有逻辑最前（`source_type == "llm_inference"` 判断之后）插入：

```python
    semantic = _rejudge_semantic(claim)
    if semantic is not None:
        return semantic
```

`evals/claim_benchmark/measure.py` `measure()` 追加子集指标（在既有 `nm_recall` 计算后）：

```python
    def _near_miss_split() -> tuple[float | None, float | None]:
        """v1.1 分列：过线检出率（should_fail 召回）与线内误报率（should_pass 误判）。"""
        sub = [r for r in core if "near_miss" in r["subsets"]]
        over = [r for r in sub if r["label"] == "FAIL"]
        inline = [r for r in sub if r["label"] == "PASS"]
        over_recall = (
            sum(1 for r in over if r["rejudged"] == "FAIL") / len(over) if over else None
        )
        inline_fp = (
            sum(1 for r in inline if r["rejudged"] == "FAIL") / len(inline) if inline else None
        )
        return over_recall, inline_fp

    def _semantic_detection() -> float | None:
        """semantic_mismatch 子集检出率（label=FAIL 中复判 FAIL 占比）。"""
        sub = [
            r
            for r in rows
            if "semantic_mismatch" in r["subsets"] and r["label"] == "FAIL"
        ]
        if not sub:
            return None
        return sum(1 for r in sub if r["rejudged"] == "FAIL") / len(sub)

    over_recall, inline_fp = _near_miss_split()
    semantic_det = _semantic_detection()
```

返回 dict 追加：

```python
        "near_miss_over_line_recall": None if over_recall is None else round(over_recall, 4),
        "near_miss_in_line_fp_rate": None if inline_fp is None else round(inline_fp, 4),
        "semantic_mismatch_detection": None if semantic_det is None else round(semantic_det, 4),
        "semantic_gate": {
            "gate": 0.9,
            "passed": semantic_det is not None and semantic_det >= 0.9,
        },
```

`_print_report` 追加两行：

```python
    print(f"near_miss 过线检出率: {rep['near_miss_over_line_recall']}  线内误报率: {rep['near_miss_in_line_fp_rate']}")
    print(f"semantic_mismatch 检出率: {rep['semantic_mismatch_detection']}（门禁 ≥ 0.9: {'✅' if rep['semantic_gate']['passed'] else '❌/不适用'}）")
```

`main()` 退出码：`return 0 if rep["gate"]["passed"] and rep["semantic_gate"]["passed"] else 1`——注意 v1 基线无 semantic_mismatch 子集时 `semantic_det is None` → `passed=False` 会误伤 v1 重放；调整 passed 语义为 `semantic_det is None or semantic_det >= 0.9`（无子集不适用不拦截），测试 `test_semantic_gate_fails_below_90` 断言的 `passed is False` 仅在有子集且 <0.9 时成立。相应地返回 dict 用 `"passed": semantic_det is None or semantic_det >= 0.9`，测试里 1.0 → True、0.1 → False 均成立。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/claim_benchmark/ -v`
Expected: PASS（存量钉死测试不回归 + 新增 7 项）

- [ ] **Step 5: Commit**

```bash
git add evals/claim_benchmark/rejudge.py evals/claim_benchmark/measure.py tests/evals/claim_benchmark/
git commit -m "feat(evals): rejudge 语义离线复判 + measure near_miss 分列/semantic 90% 门禁（T11）"
```

---

### Task 12: run_experiment 增加 citation_pass / citation_coverage 指标

**Files:**
- Modify: `evals/task.py`（_run_deep 输出两指标）
- Modify: `evals/run.py`（两个确定性 evaluator + 报告 CI 块）
- Test: `tests/evals/test_task.py`（追加）、`tests/evals/test_run.py`（追加）

**Interfaces:**
- Consumes: T6 state.citation_coverage；既有 make_evaluation / _mean_rows
- Produces:
  - task 输出键 `citation_pass: float | None`、`citation_coverage: float | None`（quick/skipped → None）
  - `eval_citation_pass`、`eval_citation_coverage`（output 无值 → None 不计入）
  - 报告 `means` 旁新增 `citation_ci: {metric: [lo, hi]}`（均值 bootstrap 95% CI，B=10000，seed=42）

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_run.py 追加：

from evals.run import _citation_ci, eval_citation_coverage, eval_citation_pass


class TestCitationMetricEvaluators:
    def test_pass_evaluator_reads_output(self):
        ev = eval_citation_pass(
            input={}, output={"citation_pass": 1.0}, expected_output={}, metadata={}
        )
        assert ev.name == "citation_pass"
        assert ev.value == 1.0

    def test_coverage_evaluator_reads_output(self):
        ev = eval_citation_coverage(
            input={}, output={"citation_coverage": 0.85}, expected_output={}, metadata={}
        )
        assert ev.name == "citation_coverage"
        assert ev.value == 0.85

    def test_missing_output_returns_none(self):
        """quick/无 citation 数据 → None 不计入（与 expected 缺省跳过同口径）。"""
        assert (
            eval_citation_pass(input={}, output={"mode": "quick"}, expected_output={}, metadata={})
            is None
        )
        assert (
            eval_citation_coverage(input={}, output=None, expected_output={}, metadata={}) is None
        )

    def test_citation_ci_deterministic(self):
        lo, hi = _citation_ci([0.8, 0.9, 1.0, 0.7])
        assert lo <= 0.875 <= hi
        assert _citation_ci([0.8, 0.9, 1.0, 0.7]) == (lo, hi)  # seed 固定可复现
        assert _citation_ci([]) == (0.0, 0.0)
```

```python
# tests/evals/test_task.py 追加：


class TestTaskCitationOutputs:
    def test_deep_output_includes_citation_metrics(self, monkeypatch):
        """deep task 输出携带 citation_pass/citation_coverage（来自管线 state）。"""
        import evals.task as task_mod

        class _FakeGraph:
            def invoke(self, state, config=None):
                return {"final_report": "r", "citation_pass": True, "citation_coverage": 0.92}

        monkeypatch.setattr(task_mod, "build_5layer_graph", lambda: _FakeGraph())
        monkeypatch.setattr(task_mod, "extract_judge_vars", lambda state, query="": {})
        monkeypatch.setattr(task_mod, "get_callback_handler", lambda: None)
        out = task_mod._run_deep({"stock_code": "600519", "query": "q"})
        assert out["citation_pass"] == 1.0
        assert out["citation_coverage"] == 0.92
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_run.py tests/evals/test_task.py -v`
Expected: FAIL（`_citation_ci` / evaluator 不存在）

- [ ] **Step 3: Write minimal implementation**

`evals/task.py` `_run_deep` 返回 dict 追加两键：

```python
    return {
        "report": state.get("final_report"),
        "ticker": inp["stock_code"],
        "judge_vars": extract_judge_vars(state, query=inp.get("query", "")),
        "mode": "deep",
        "skipped": None,
        # harden-citation-semantic-coverage：引用指标进实验报告（citation_pass
        # 布尔转 0/1；citation_coverage 缺失→None 不计入）
        "citation_pass": (
            float(state["citation_pass"]) if state.get("citation_pass") is not None else None
        ),
        "citation_coverage": (
            float(state["citation_coverage"]) if state.get("citation_coverage") is not None else None
        ),
    }
```

`evals/run.py`：

```python
def eval_citation_pass(*, input, output, expected_output, metadata):
    """citation_pass（管线 trace 级布尔）经 output 透传为实验 Score。"""
    value = (output or {}).get("citation_pass")
    if value is None:
        return None
    return make_evaluation({"name": "citation_pass", "value": float(value), "comment": None})


def eval_citation_coverage(*, input, output, expected_output, metadata):
    """citation_coverage（正文数字普查覆盖率，harden-citation-semantic-coverage）。"""
    value = (output or {}).get("citation_coverage")
    if value is None:
        return None
    return make_evaluation({"name": "citation_coverage", "value": float(value), "comment": None})


def _citation_ci(vals: list[float], B: int = 10_000, seed: int = 42) -> tuple[float, float]:
    """均值的 bootstrap 95% CI（非配对；配对显著性由 compare.py 契约承担）。"""
    import numpy as np

    if not vals:
        return (0.0, 0.0)
    arr = np.asarray(vals, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(B, len(arr)))
    means = arr[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
```

`all_evaluators()` 列表追加 `eval_citation_pass, eval_citation_coverage`。`_write_report` 调用前计算并写入：

```python
    # citation 指标均值 CI（harden-citation-semantic-coverage spec：均值与 95% CI）
    citation_ci = {}
    for metric in ("citation_pass", "citation_coverage"):
        vals = [
            float(row["scores"][metric])
            for row in rows
            if (row.get("scores") or {}).get(metric) is not None
        ]
        if vals:
            lo, hi = _citation_ci(vals)
            citation_ci[metric] = [round(lo, 4), round(hi, 4)]
```

`_write_report` 签名加 `citation_ci: dict` 参数并写入 JSON `"citation_ci": citation_ci`；`main()` 调用点同步更新。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_run.py tests/evals/test_task.py tests/evals/test_compare.py -v`
Expected: PASS（compare 存量不回归——metric_names 泛化自动覆盖新指标）

- [ ] **Step 5: Commit**

```bash
git add evals/task.py evals/run.py tests/evals/test_run.py tests/evals/test_task.py
git commit -m "feat(evals): run_experiment 增加 citation_pass/citation_coverage 指标 + 均值 CI（T12）"
```

---

### Task 13: decision_grounding rubric v3（语义核对扩展）

**Files:**
- Modify: `evals/judges.py:38-99`（RUBRIC_VERSIONS + decision_grounding rubric 扩展）
- Test: `tests/evals/test_judges.py`（追加）

**Interfaces:**
- Produces: `RUBRIC_VERSIONS: dict[str, int]`（decision_grounding=3，其余=1）；rubric 新增语义核对条款

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_judges.py 追加：

from evals.judges import RUBRICS, RUBRIC_VERSIONS


class TestDecisionGroundingRubricV3:
    def test_version_incremented(self):
        """rubric 变更递增版本号（evidence_refs 版为 v2，语义核对版为 v3）。"""
        assert RUBRIC_VERSIONS["decision_grounding"] == 3

    def test_other_rubrics_version_pinned(self):
        assert RUBRIC_VERSIONS["report_relevance"] == 1
        assert RUBRIC_VERSIONS["debate_quality"] == 1
        assert RUBRIC_VERSIONS["consistency"] == 1

    def test_rubric_includes_semantic_check(self):
        """语义核对条款：术语/期次/方向与所引数值一致；解读失当扣分。"""
        rubric = RUBRICS["decision_grounding"]
        assert "语义一致" in rubric
        assert "期次" in rubric
        assert "行业领先" in rubric  # 反例锚点（垫底表述为领先）
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_judges.py -v`
Expected: FAIL（RUBRIC_VERSIONS 不存在）

- [ ] **Step 3: Write minimal implementation**

`evals/judges.py` 在 `RUBRICS` 定义前加：

```python
# rubric 版本（变更递增，校准门禁按版本重校准；decision_grounding：
# v1 初版 → v2 evidence_refs 结构化核对 → v3 interpretation 语义核对）
RUBRIC_VERSIONS: dict[str, int] = {
    "report_relevance": 1,
    "debate_quality": 1,
    "decision_grounding": 3,
    "consistency": 1,
}
```

`decision_grounding` rubric 的 evidence_refs 分支（「→ 4-5 分；」之前）插入语义核对条款：

```python
若交易决策含 evidence_refs（结构化论据引用，每项含 claim 与 source），逐条核对：
- claim 的数值/事实能在对应 source（technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager）的结论中找到出处，
  且 reasoning 的主要论据都能在 evidence_refs 中找到对应项 → 4-5 分；
- 语义一致性核对：论据表述的指标术语、期次、方向须与所引数值语义一致——
  数值有出处但术语张冠李戴（毛利率写成净利率）、期次错位（年报值说成季度值）、
  方向失当（数值下降表述为「改善」、行业垫底表述为「行业领先」）属解读失当，
  不得仅因数值有出处给高分 → 降至 2-3 分；
- source 与论据对不上、claim 数值在来源中不存在（无中生有）、或 evidence_refs 缺失
  reasoning 中大量论据的引用 → 1-2 分。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_judges.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/judges.py tests/evals/test_judges.py
git commit -m "feat(evals): decision_grounding rubric v3 语义核对扩展（重校准为人工门禁）（T13）"
```

---

## Live follow-ups（非本计划代码任务，archive 前置的人工/live 门禁）

1. **人工 ADR**（tasks.md 前置 1）：重试路由按桶分流属行为变更 + `citation_coverage` 阈值 0.8 默认值 → 人工落 `docs/adr/0018-*.md`（agent 不得新建 ADR）。
2. **prompt 发布**：T9 后执行 `uv run python scripts/deploy_prompts.py`（否则 eval 门禁拒绝运行）。
3. **三标的冒烟**（汉森制药/贵州茅台/中际旭创）：FAIL 率 <10%、coverage ≥0.8、无格式类重试触发；中际旭创技术类期次错位 FAIL 13→0（tasks.md 验收项）。
4. **覆盖率抽查**：首批产出人工抽查 20 条确认普查口径（tasks.md）。
5. **基准集冻结**：生成 v1.1（`build_v11.py`）→ 重跑 `measure.py --labeled data/benchmark_v11.jsonl` → 冻结 verifier-baseline-v1.1（results/v1.1.md 披露 near_miss 分列 + semantic_mismatch 检出率）。
6. **judge 重校准**：rubric v3 按「Judge 校准门禁」契约重校准（人工一致性 ≥80%）后上线。

## Self-Review 记录

- **spec 覆盖**：citation-verification delta 5 个 Requirement → T8（语义头）/ T2+T3（术语期次）/ T4（内部一致性）/ T5+T6（覆盖率）/ T6+T7（分桶重试）；evaluation delta 3 个 Requirement → T10（v1.1 构造）/ T11+冻结 follow-up（测量披露）/ T12（实验指标）/ T13（rubric）。tasks.md「通用」验收项 → 执行后 verification 步骤统一跑。
- **既有契约不触碰**：容差公式、负索引解析、DataFrame 两段解析、单一词表（resolver 无中文映射）均不改；rejudge 钉死测试锁定镜像。
- **类型一致性**：`_verify_data_claim(claim, state, value_fn)`、`_series_semantic_header(direction, latest_label, count)`、`compute_coverage(markdown, stated_values)`、`build_v11(input_path, out_prefix, near_miss_n, semantic_n, seed)` 在任务间引用一致。
