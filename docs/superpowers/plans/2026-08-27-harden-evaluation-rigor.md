# Harden Evaluation Rigor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `openspec/changes/harden-evaluation-rigor/` delta 实现：citation 重算注册表全覆盖 + UNVERIFIABLE 监控、claim 基准集 + 校验器准度门禁 + 配对 bootstrap + 消融协议、decision-backtest 离线回放评估。

**Architecture:** 评估设施全部新增在 `evals/`（业务代码唯一允许改动：`src/finance_agent/citation.py` 注册表扩展与 `nodes/citation_node.py` 新增 Score 上报）。统计方法（配对/block bootstrap、Cohen's κ）落在 `evals/stats.py` 单一模块供各处复用。回测复用 `outcome/settle.py` 结算语义与 `metrics/technical.py` 基线指标。

**Tech Stack:** Python 3.12+ / pydantic / pandas / numpy / pytest（numpy 已是既有依赖，勿新增依赖）。

## Global Constraints

- delta spec：`openspec/changes/harden-evaluation-rigor/specs/{citation-verification,evaluation,decision-backtest}/spec.md`
- 容差语义不变：绝对 0.01 / 相对 0.5%；三态裁决 PASS/FAIL/UNVERIFIABLE 不变
- 评估设施全部位于 `evals/`；业务代码零侵入（仅 citation.py 注册表 + citation_node.py Score 上报）
- 结算语义复用 `outcome/settle.py` 的 `evaluate_decision`，不另造一套
- `uv run pytest` 全过、`uv run ruff check` 无错误、`uv run mypy` 无错误
- 禁止占位符：每步给完整代码；mypy 对 `evals/` 同样生效（mypy_path=src 已配）
- Windows Git Bash 环境；测试命令用 `uv run pytest <path> -v`
- 不新建 ADR；不动 `decision_log` 在线结算语义

---

### Task 1: citation 注册表全覆盖 + 覆盖缺口计数

**Files:**
- Modify: `src/finance_agent/citation.py:94-143`
- Test: `tests/test_citation.py`（追加）

**Interfaces:**
- Consumes: `finance_agent.metrics.{solvency,profitability,efficiency,cashflow,technical,risk}` 的 calc_* 纯函数
- Produces: `_COMPUTATIONAL_RECALC` 含 7 根键：`dupont_tree` / `solvency_metrics` / `profitability_metrics` / `efficiency_metrics` / `cashflow_metrics` / `technical_indicators` / `risk_metrics`；`CitationResult.coverage_gap: bool`；`CitationReport.coverage_gaps: int`

- [ ] **Step 1: Write the failing test**

在 `tests/test_citation.py` 末尾追加（文件顶部 import 区补 `import pandas as pd` 与 metrics 导入；`balance_sheet` / `income_statement` / `cash_flow` / `indicators` 来自 `tests/conftest.py`）：

```python
class TestComputationalRegistryCoverage:
    """注册表全覆盖：metrics/ 全部纯函数指标族可重算（spec 计算型声明重算注册表全覆盖）。"""

    def _state(self, balance_sheet, income_statement, cash_flow, indicators):
        kline = pd.DataFrame(
            {
                "日期": pd.date_range("2025-01-01", periods=80, freq="D").strftime("%Y-%m-%d"),
                "开盘": [10.0] * 80,
                "收盘": [10.0 + i * 0.1 for i in range(80)],
                "最高": [10.5 + i * 0.1 for i in range(80)],
                "最低": [9.5 + i * 0.1 for i in range(80)],
                "成交量": [1000.0] * 80,
            }
        )
        bench = kline.copy()
        return {
            "balance_sheet": balance_sheet,
            "income_statement": income_statement,
            "cash_flow_statement": cash_flow,
            "financial_indicators": indicators,
            "kline": kline,
            "benchmark_kline": bench,
        }

    def test_registry_covers_all_metric_families(self):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        expected = {
            "dupont_tree",
            "solvency_metrics",
            "profitability_metrics",
            "efficiency_metrics",
            "cashflow_metrics",
            "technical_indicators",
            "risk_metrics",
        }
        assert expected <= set(_COMPUTATIONAL_RECALC)

    def test_solvency_recalc_pass_and_fail(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC
        from finance_agent.metrics.solvency import calc_solvency

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["solvency_metrics"](state)
        assert truth["资产负债率"]["2024"] == calc_solvency(
            balance_sheet, income_statement, indicators
        )["资产负债率"]["2024"]
        ok = Claim(
            claim_type="computational", source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=float(truth["资产负债率"]["2024"]), interpretation="",
        )
        bad = Claim(
            claim_type="computational", source_type="data",
            field_ref="solvency_metrics.资产负债率.2024",
            stated_value=float(truth["资产负债率"]["2024"]) * 2, interpretation="",
        )
        results = verify_claims([ok, bad], state)
        assert results[0].status == "PASS"
        assert results[1].status == "FAIL"

    def test_profitability_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["profitability_metrics"](state)
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref="profitability_metrics.净利率.2024",
            stated_value=float(truth["净利率"]["2024"]), interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_efficiency_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["efficiency_metrics"](state)
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref="efficiency_metrics.总资产周转率.2024",
            stated_value=float(truth["总资产周转率"]["2024"]), interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_cashflow_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["cashflow_metrics"](state)
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref="cashflow_metrics.经营现金流/净利润.2024",
            stated_value=float(truth["经营现金流/净利润"]["2024"]), interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_technical_recalc_with_list_index(self, balance_sheet, income_statement, cash_flow, indicators):
        """technical_indicators 值为等长 list，子路径须支持 list index。"""
        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        from finance_agent.metrics.technical import calc_technical

        truth = calc_technical(state["kline"])
        ma5_last = truth["MA"]["5"][-1]
        assert ma5_last is not None
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref=f"technical_indicators.MA.5.{len(truth['MA']['5']) - 1}",
            stated_value=float(ma5_last), interpretation="",
        )
        result = verify_claims([claim], state)[0]
        assert result.status == "PASS"
        assert result.ground_truth == pytest.approx(ma5_last)

    def test_risk_recalc(self, balance_sheet, income_statement, cash_flow, indicators):
        from finance_agent.citation import _COMPUTATIONAL_RECALC

        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        truth = _COMPUTATIONAL_RECALC["risk_metrics"](state)
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref="risk_metrics.max_drawdown",
            stated_value=float(truth["max_drawdown"]), interpretation="",
        )
        assert verify_claims([claim], state)[0].status == "PASS"

    def test_unregistered_root_counts_coverage_gap(self):
        state = {"balance_sheet": pd.DataFrame(), "income_statement": pd.DataFrame()}
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref="unknown_metrics.某指标.2024", stated_value=1.0, interpretation="",
        )
        results = verify_claims([claim], state)
        report = CitationReport.from_results(results)
        assert results[0].status == "UNVERIFIABLE"
        assert report.coverage_gaps == 1

    def test_registered_root_no_coverage_gap(self, balance_sheet, income_statement, cash_flow, indicators):
        state = self._state(balance_sheet, income_statement, cash_flow, indicators)
        claim = Claim(
            claim_type="computational", source_type="data",
            field_ref="dupont_tree.L1.2024.ROE", stated_value=0.28, interpretation="",
        )
        report = CitationReport.from_results(verify_claims([claim], state))
        assert report.coverage_gaps == 0
```

文件顶部补：`import pytest`（若未导入）。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citation.py::TestComputationalRegistryCoverage -v`
Expected: FAIL — `KeyError: 'solvency_metrics'`（注册表缺键）与 `coverage_gaps` 属性不存在

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/citation.py`：import 区替换为

```python
from finance_agent.metrics.cashflow import calc_cashflow
from finance_agent.metrics.dupont import calc_dupont
from finance_agent.metrics.efficiency import calc_efficiency
from finance_agent.metrics.profitability import calc_profitability
from finance_agent.metrics.risk import calc_risk
from finance_agent.metrics.solvency import calc_solvency
from finance_agent.metrics.technical import calc_technical
```

注册表与 `CitationResult` / `CitationReport` 扩展：

```python
class CitationResult(BaseModel):
    """单条 Claim 的校验结果。"""

    status: Literal["PASS", "FAIL", "UNVERIFIABLE"]
    claim: Claim
    ground_truth: float | str | None = None
    delta: float | None = None
    coverage_gap: bool = False  # 计算型 claim 根键未注册 → True（覆盖缺口指标）
```

```python
class CitationReport(BaseModel):
    """批量校验汇总报告。"""

    results: list[CitationResult]
    total: int = 0
    passed: int = 0
    failed: int = 0
    unverifiable: int = 0
    coverage_gaps: int = 0
    all_passed: bool = False

    @classmethod
    def from_results(cls, results: list[CitationResult]) -> CitationReport:
        """从校验结果列表构建汇总报告。"""
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        unverifiable = sum(1 for r in results if r.status == "UNVERIFIABLE")
        return cls(
            results=results,
            total=len(results),
            passed=passed,
            failed=failed,
            unverifiable=unverifiable,
            coverage_gaps=sum(1 for r in results if r.coverage_gap),
            all_passed=failed == 0,
        )
```

```python
# ── 计算型 claim 重算注册表 ──
# field_ref 根键 → 从 state 原始数据重算的函数。
# 覆盖 metrics/ 全部纯函数指标族；未注册根键 → UNVERIFIABLE + coverage_gap 计数。
_COMPUTATIONAL_RECALC: dict[str, Callable[[dict], dict]] = {
    "dupont_tree": lambda s: calc_dupont(s["balance_sheet"], s["income_statement"]),
    "solvency_metrics": lambda s: calc_solvency(
        s["balance_sheet"], s["income_statement"], s.get("financial_indicators")
    ),
    "profitability_metrics": lambda s: calc_profitability(
        s["balance_sheet"], s["income_statement"], s.get("financial_indicators")
    ),
    "efficiency_metrics": lambda s: calc_efficiency(
        s["balance_sheet"], s["income_statement"], s.get("financial_indicators")
    ),
    "cashflow_metrics": lambda s: calc_cashflow(
        s["balance_sheet"], s["income_statement"], s["cash_flow_statement"]
    ),
    "technical_indicators": lambda s: calc_technical(s["kline"]),
    "risk_metrics": lambda s: calc_risk(s["kline"], s.get("benchmark_kline")),
}
```

`_verify_computational` 未注册分支与子路径导航（支持 list index，technical_indicators 值为等长 list）：

```python
    recalc_fn = _COMPUTATIONAL_RECALC.get(root)
    if recalc_fn is None:
        return CitationResult(status="UNVERIFIABLE", claim=claim, coverage_gap=True)
```

```python
    # 从重算结果中按 sub_path 取值（dict 键 + list 序号，与 _resolve_field_ref 语义一致）
    current: object = recalculated
    for part in sub_path:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return CitationResult(status="UNVERIFIABLE", claim=claim)
        else:
            return CitationResult(status="UNVERIFIABLE", claim=claim)
        if current is None:
            return CitationResult(status="FAIL", claim=claim, ground_truth=None, delta=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citation.py tests/nodes/test_citation_node.py -v`
Expected: PASS（含既有容差/三态回归用例全绿）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/citation.py tests/test_citation.py
git commit -m "feat(citation): 计算型重算注册表覆盖 metrics 全指标族 + 覆盖缺口计数 (harden-evaluation-rigor)"
```

---

### Task 2: citation_unverifiable_ratio Score 上报

**Files:**
- Modify: `src/finance_agent/nodes/citation_node.py:44-65`
- Test: `tests/nodes/test_citation_node.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `CitationReport.coverage_gaps`
- Produces: Langfuse Score `citation_unverifiable_ratio`（NUMERIC，0-1，0-claim 时 0.0）；失败记 WARN 不阻断

- [ ] **Step 1: Write the failing test**

`tests/nodes/test_citation_node.py` 追加（沿用该文件既有的 langfuse mock 方式；先读文件确认 mock target 名，若既有测试用 `@patch("finance_agent.nodes.citation_node.get_langfuse")` 则照抄该模式）：

```python
class TestUnverifiableRatioScore:
    """spec「UNVERIFIABLE 占比监控」Scenario「占比上报」。"""

    def _run_node(self, claims_payload, state):
        report_dict = {
            "claims": claims_payload,
        }
        state = {**state, "analyst_reports": {"fundamental": report_dict}}
        return verify_citations(state)

    def test_ratio_score_reported(self, monkeypatch):
        from finance_agent import citation_node

        captured = {}

        class _Client:
            def score_current_trace(self, **kwargs):
                captured[kwargs["name"]] = kwargs

            def update_current_span(self, **kwargs):
                pass

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: _Client())
        claims = [
            {"claim_type": "numerical", "source_type": "data",
             "field_ref": "solvency_metrics.资产负债率.2024",
             "stated_value": 40.0, "interpretation": ""},
            {"claim_type": "numerical", "source_type": "llm_inference",
             "field_ref": "x", "stated_value": 1.0, "interpretation": ""},
        ]
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}}}
        self._run_node(claims, state)
        assert "citation_unverifiable_ratio" in captured
        assert captured["citation_unverifiable_ratio"]["value"] == 0.5
        assert captured["citation_pass"]["value"] == 1.0

    def test_zero_claims_ratio_is_zero(self, monkeypatch):
        from finance_agent import citation_node

        captured = {}

        class _Client:
            def score_current_trace(self, **kwargs):
                captured[kwargs["name"]] = kwargs

            def update_current_span(self, **kwargs):
                pass

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: _Client())
        verify_citations({"analyst_reports": {}})
        assert captured["citation_unverifiable_ratio"]["value"] == 0.0

    def test_langfuse_failure_warns_not_raises(self, monkeypatch, caplog):
        from finance_agent import citation_node

        class _Boom:
            def score_current_trace(self, **kwargs):
                raise RuntimeError("langfuse down")

            def update_current_span(self, **kwargs):
                raise RuntimeError("langfuse down")

        monkeypatch.setattr(citation_node, "get_langfuse", lambda: _Boom())
        state = {"solvency_metrics": {"资产负债率": {"2024": 40.0}},
                 "analyst_reports": {"a": {"claims": [
                     {"claim_type": "numerical", "source_type": "data",
                      "field_ref": "solvency_metrics.资产负债率.2024",
                      "stated_value": 40.0, "interpretation": ""}]}}}
        result = verify_citations(state)  # 不抛异常
        assert result["citation_pass"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_citation_node.py::TestUnverifiableRatioScore -v`
Expected: FAIL — `KeyError: 'citation_unverifiable_ratio'`

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/nodes/citation_node.py` 的 `_report_to_langfuse` 改为：

```python
def _report_to_langfuse(report: CitationReport) -> None:
    """上报 citation 校验结果到 Langfuse（trace 级 boolean score + span 明细）。

    citation_unverifiable_ratio（spec「UNVERIFIABLE 占比监控」）是数据层退化的
    先行指标；上报失败记 WARN（spec：Langfuse 不可用 SHALL 记 WARN 且不阻断）。
    """
    try:
        from finance_agent.langfuse_tracing import get_langfuse

        client = get_langfuse()
        if client is None:
            return
        fail_count = sum(1 for r in report.results if r.status == "FAIL")
        total = len(report.results)
        client.score_current_trace(
            name="citation_pass",
            value=1.0 if report.all_passed else 0.0,
            data_type="BOOLEAN",
            comment=f"{'PASS' if report.all_passed else 'FAIL'}: {fail_count}/{total} claims failed",
            metadata={"all_passed": report.all_passed, "fail_count": fail_count, "total": total},
        )
        ratio = (report.unverifiable / total) if total else 0.0
        client.score_current_trace(
            name="citation_unverifiable_ratio",
            value=round(ratio, 4),
            data_type="NUMERIC",
            comment=f"UNVERIFIABLE {report.unverifiable}/{total}; coverage_gaps={report.coverage_gaps}",
        )
        client.update_current_span(
            metadata={"citation_report": report.model_dump()},
        )
    except Exception as e:
        logger.warning("Langfuse citation score 上报失败: %s", e)
```

注意：函数内 import 的 `get_langfuse` 需提升可 patch 性——monkeypatch 打在 `citation_node.get_langfuse` 上要求符号在模块命名空间。将 import 改为模块级 `from finance_agent.langfuse_tracing import get_langfuse`（与既有函数内 import 等价，零行为差异），并同步更新既有测试若其 patch 的是旧 target。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_citation_node.py -v`
Expected: PASS（新 3 例 + 既有全绿）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/citation_node.py tests/nodes/test_citation_node.py
git commit -m "feat(observability): citation_unverifiable_ratio 上报 Langfuse,失败记 WARN (harden-evaluation-rigor)"
```

---

### Task 3: UNVERIFIABLE 占比突升监控

**Files:**
- Create: `evals/unverifiable_monitor.py`
- Create: `scripts/monitor_unverifiable_ratio.py`
- Test: `tests/evals/test_unverifiable_monitor.py`

**Interfaces:**
- Consumes: 无（纯逻辑 + Langfuse REST）
- Produces: `detect_rise(recent: Sequence[float], baseline: Sequence[float], threshold_pp: float = 0.10) -> dict | None`；`evaluate_history(scores: list[tuple[str, float]], *, baseline_window: int = 30, recent_window: int = 5, threshold_pp: float = 0.10) -> dict | None`；CLI `uv run python scripts/monitor_unverifiable_ratio.py`

- [ ] **Step 1: Write the failing test**

```python
"""突升检测纯逻辑测试（spec「UNVERIFIABLE 占比监控」Scenario「占比突升告警」）。"""

from evals.unverifiable_monitor import detect_rise, evaluate_history


class TestDetectRise:
    def test_no_rise_within_threshold(self):
        assert detect_rise([0.10, 0.12], [0.08, 0.10, 0.09]) is None

    def test_rise_over_threshold_alerts(self):
        alert = detect_rise([0.25, 0.26], [0.10, 0.12, 0.11])
        assert alert is not None
        assert alert["level"] == "warning"
        assert alert["baseline_mean"] == 0.11
        assert alert["recent_mean"] == 0.255
        assert alert["rise_pp"] > 0.10

    def test_empty_inputs_return_none(self):
        assert detect_rise([], []) is None
        assert detect_rise([0.5], []) is None


class TestEvaluateHistory:
    def test_history_sorted_and_evaluated(self):
        history = [("2026-08-01", 0.10), ("2026-08-02", 0.11), ("2026-08-03", 0.12),
                   ("2026-08-04", 0.30), ("2026-08-05", 0.32)]
        alert = evaluate_history(history, baseline_window=3, recent_window=2)
        assert alert is not None
        assert alert["recent_mean"] == 0.31

    def test_insufficient_history_none(self):
        assert evaluate_history([("d1", 0.5)], baseline_window=3, recent_window=2) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_unverifiable_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.unverifiable_monitor'`

- [ ] **Step 3: Write minimal implementation**

`evals/unverifiable_monitor.py`：

```python
"""citation_unverifiable_ratio 突升监控（spec citation-verification「UNVERIFIABLE 占比监控」）。

占比突升 = 数据层退化先行信号（数据源接口变更/事件管线降级/注册表覆盖缺口扩大）。
纯逻辑（detect_rise / evaluate_history）可测；CLI 从 Langfuse 拉取 Score 序列检测。
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

SCORE_NAME = "citation_unverifiable_ratio"
DEFAULT_BASELINE_WINDOW = 30
DEFAULT_RECENT_WINDOW = 5
DEFAULT_THRESHOLD_PP = 0.10  # +10pp


def detect_rise(
    recent: Sequence[float],
    baseline: Sequence[float],
    threshold_pp: float = DEFAULT_THRESHOLD_PP,
) -> dict | None:
    """recent 均值较 baseline 均值上升超过 threshold_pp → 告警 dict；否则 None。"""
    if not recent or not baseline:
        return None
    recent_mean = sum(recent) / len(recent)
    baseline_mean = sum(baseline) / len(baseline)
    rise_pp = recent_mean - baseline_mean
    if rise_pp <= threshold_pp:
        return None
    return {
        "level": "warning",
        "score": SCORE_NAME,
        "recent_mean": round(recent_mean, 4),
        "baseline_mean": round(baseline_mean, 4),
        "rise_pp": round(rise_pp, 4),
        "threshold_pp": threshold_pp,
        "hint": "排查数据层（数据源接口/事件管线）或 citation 注册表覆盖缺口",
    }


def evaluate_history(
    history: list[tuple[str, float]],
    *,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
    recent_window: int = DEFAULT_RECENT_WINDOW,
    threshold_pp: float = DEFAULT_THRESHOLD_PP,
) -> dict | None:
    """history: [(timestamp, ratio)]，按时间升序取 recent_window 为近期、
    其前 baseline_window 为基线，做突升检测。样本不足返回 None。"""
    ordered = sorted(history, key=lambda t: t[0])
    if len(ordered) < recent_window + baseline_window:
        return None
    recent = [v for _, v in ordered[-recent_window:]]
    baseline = [v for _, v in ordered[-(recent_window + baseline_window) : -recent_window]]
    return detect_rise(recent, baseline, threshold_pp)


def fetch_scores(host: str, limit: int = 200) -> list[tuple[str, float]]:
    """从 Langfuse REST API 拉取该 Score 最近记录（timestamp, value），升序返回。"""
    public = os.environ["LANGFUSE_PUBLIC_KEY"]
    secret = os.environ["LANGFUSE_SECRET_KEY"]
    token = base64.b64encode(f"{public}:{secret}".encode()).decode()
    url = f"{host.rstrip('/')}/api/public/scores?name={SCORE_NAME}&limit={limit}"
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - 内网 Langfuse
        data = json.loads(resp.read().decode())
    rows = [(item["timestamp"], float(item["value"])) for item in data.get("data", [])]
    return sorted(rows, key=lambda t: t[0])


def main() -> None:
    load_dotenv()
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    history = fetch_scores(host)
    alert = evaluate_history(history)
    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "score": SCORE_NAME,
        "n_scores": len(history),
        "alert": alert,
    }
    out_dir = Path("reports/monitoring")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"unverifiable-ratio-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    print(f"监控记录已写入 {path}")


if __name__ == "__main__":
    main()
```

`scripts/monitor_unverifiable_ratio.py`：

```python
#!/usr/bin/env python
"""定时监控 citation_unverifiable_ratio 突升（告警记录落 reports/monitoring/）。"""
from evals.unverifiable_monitor import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_unverifiable_monitor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/unverifiable_monitor.py scripts/monitor_unverifiable_ratio.py tests/evals/test_unverifiable_monitor.py
git commit -m "feat(evals): unverifiable 占比突升监控与告警记录 (harden-evaluation-rigor)"
```

---

### Task 4: 统计核心（配对/block bootstrap + Cohen's κ）

**Files:**
- Create: `evals/stats.py`
- Test: `tests/evals/test_stats.py`

**Interfaces:**
- Produces（后续任务依赖，签名精确）:
  - `paired_bootstrap_ci(a: Sequence[float], b: Sequence[float], *, B: int = 10_000, seed: int = 42, alpha: float = 0.05) -> tuple[float, float]` — 逐 item 配对重采样 `mean(a)-mean(b)` 的 `(lo, hi)`
  - `block_bootstrap_stat(series: Sequence[float], stat_fn: Callable[[Sequence[float]], float], *, block_size: int = 20, B: int = 1_000, seed: int = 42, alpha: float = 0.05) -> tuple[float, float]` — 循环块 bootstrap，对时序保留自相关
  - `paired_block_bootstrap_diff(a: Sequence[float], b: Sequence[float], *, block_size: int = 20, B: int = 1_000, seed: int = 42, alpha: float = 0.05) -> tuple[float, float]` — 同步块重采样两条对齐时序的 `stat(a)-stat(b)` CI（stat 固定为 `sharpe`）
  - `sharpe(returns: Sequence[float]) -> float` — 年化夏普（rf=0，252 交易日，ddof=1）
  - `cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float`

- [ ] **Step 1: Write the failing test**

```python
"""统计核心测试：确定性 seed 下 CI 数值可复现。"""

import math

from evals.stats import (
    block_bootstrap_stat,
    cohen_kappa,
    paired_block_bootstrap_diff,
    paired_bootstrap_ci,
    sharpe,
)


class TestPairedBootstrap:
    def test_ci_excludes_zero_for_clear_gap(self):
        a = [0.9, 0.91, 0.89, 0.92, 0.9]
        b = [0.5, 0.49, 0.51, 0.5, 0.5]
        lo, hi = paired_bootstrap_ci(a, b, B=2_000, seed=7)
        assert lo > 0

    def test_ci_contains_zero_for_identical(self):
        a = [0.5, 0.6, 0.4]
        lo, hi = paired_bootstrap_ci(a, a, B=500, seed=7)
        assert lo <= 0.0 <= hi

    def test_deterministic_with_seed(self):
        a = [1.0, 2.0, 3.0, 4.0]
        b = [1.5, 1.0, 2.5, 2.0]
        assert paired_bootstrap_ci(a, b, B=500, seed=11) == paired_bootstrap_ci(a, b, B=500, seed=11)


class TestSharpe:
    def test_constant_returns_zero_vol_defined(self):
        # 恒定收益 std=0：返回 0.0 而非除零
        assert sharpe([0.01] * 10) == 0.0

    def test_positive_skew_positive_sharpe(self):
        r = [0.02] * 8 + [0.0, 0.0]
        assert sharpe(r) > 0


class TestBlockBootstrap:
    def test_stat_ci_brackets_point_estimate(self):
        series = [0.001 * ((i % 7) - 3) + 0.002 for i in range(200)]
        lo, hi = block_bootstrap_stat(series, sharpe, block_size=20, B=500, seed=3)
        assert lo <= sharpe(series) <= hi

    def test_paired_diff_ci(self):
        a = [0.002 + 0.0005 * ((i % 5) - 2) for i in range(120)]
        b = [0.0 for _ in range(120)]
        lo, hi = paired_block_bootstrap_diff(a, b, block_size=20, B=500, seed=3)
        assert lo <= hi


class TestCohenKappa:
    def test_perfect_agreement(self):
        labels = ["PASS", "FAIL", "UNVERIFIABLE", "PASS"]
        assert cohen_kappa(labels, labels) == 1.0

    def test_chance_agreement_near_zero(self):
        a = ["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"]
        b = ["PASS", "PASS", "PASS", "PASS", "FAIL", "FAIL"]
        kappa = cohen_kappa(a, b)
        assert -0.2 < kappa < 0.2

    def test_length_mismatch_raises(self):
        import pytest

        with pytest.raises(ValueError):
            cohen_kappa(["PASS"], ["PASS", "FAIL"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/stats.py`：

```python
"""评估统计核心（spec evaluation「实验对比统计显著性」/ decision-backtest「统计显著性与不确定性报告」）。

- 配对 bootstrap：分数对比按 dataset item 重采样，B=10,000（FinGround 规格）
- block bootstrap：回测时序按交易日块重采样（默认块长 20），保留自相关
- Cohen's κ：标注者一致性
全部函数接受 seed，保证 CI 数值可复现（测试与报告可回归）。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np


def sharpe(returns: Sequence[float]) -> float:
    """年化夏普（rf=0，252 交易日，ddof=1）；std=0 时返回 0.0。"""
    arr = np.asarray(returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    std = float(arr.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float(arr.mean() / std * math.sqrt(252))


def _percentile_ci(samples: np.ndarray, alpha: float) -> tuple[float, float]:
    lo = float(np.percentile(samples, 100 * alpha / 2))
    hi = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    return lo, hi


def paired_bootstrap_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    B: int = 10_000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """逐 item 配对重采样 mean(a)-mean(b) 的 95% 百分位 CI（a/b 等长对齐）。"""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if len(arr_a) != len(arr_b) or len(arr_a) == 0:
        raise ValueError("paired bootstrap 要求 a/b 等长且非空")
    rng = np.random.default_rng(seed)
    n = len(arr_a)
    idx = rng.integers(0, n, size=(B, n))
    diffs = arr_a[idx].mean(axis=1) - arr_b[idx].mean(axis=1)
    return _percentile_ci(diffs, alpha)


def _block_indices(n: int, block_size: int, rng: np.random.Generator, n_paths: int) -> list[np.ndarray]:
    """循环块 bootstrap：随机起点、取 ceil(n/block) 个环形块拼接后截断到 n。"""
    n_blocks = math.ceil(n / block_size)
    starts = rng.integers(0, n, size=(n_paths, n_blocks))
    offsets = np.arange(block_size)
    flat = ((starts[:, :, None] + offsets[None, None, :]) % n).reshape(n_paths, -1)
    return [row[:n] for row in flat]


def block_bootstrap_stat(
    series: Sequence[float],
    stat_fn: Callable[[Sequence[float]], float],
    *,
    block_size: int = 20,
    B: int = 1_000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """对时序做循环块 bootstrap，返回 stat_fn 的 95% CI。"""
    arr = np.asarray(series, dtype=float)
    if len(arr) == 0:
        raise ValueError("series 不能为空")
    rng = np.random.default_rng(seed)
    stats = np.array([stat_fn(arr[idx]) for idx in _block_indices(len(arr), block_size, rng, B)])
    return _percentile_ci(stats, alpha)


def paired_block_bootstrap_diff(
    a: Sequence[float],
    b: Sequence[float],
    *,
    block_size: int = 20,
    B: int = 1_000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """两条对齐日收益时序的 Sharpe 差 CI：同一组块索引同步重采样（配对）。"""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if len(arr_a) != len(arr_b) or len(arr_a) == 0:
        raise ValueError("paired block bootstrap 要求 a/b 等长且非空")
    rng = np.random.default_rng(seed)
    stats = np.array(
        [sharpe(arr_a[idx]) - sharpe(arr_b[idx]) for idx in _block_indices(len(arr_a), block_size, rng, B)]
    )
    return _percentile_ci(stats, alpha)


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    """Cohen's κ（无权重）；完全不一致/边界情形安全返回。"""
    if len(labels_a) != len(labels_b):
        raise ValueError("标注序列等长")
    n = len(labels_a)
    if n == 0:
        return 0.0
    categories = sorted(set(labels_a) | set(labels_b))
    idx = {c: i for i, c in enumerate(categories)}
    matrix = np.zeros((len(categories), len(categories)), dtype=int)
    for la, lb in zip(labels_a, labels_b, strict=True):
        matrix[idx[la], idx[lb]] += 1
    po = float(np.trace(matrix)) / n
    pe = float(sum(matrix[i].sum() * matrix[:, i].sum() for i in range(len(categories)))) / (n * n)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_stats.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/stats.py tests/evals/test_stats.py
git commit -m "feat(evals): 统计核心 — 配对/block bootstrap 与 Cohen's κ (harden-evaluation-rigor)"
```

---

### Task 5: claim 基准集（schema + fixture state + 种子集 + κ 元信息）

**Files:**
- Create: `evals/claim_benchmark/__init__.py`（空文件）
- Create: `evals/claim_benchmark/schema.py`
- Create: `evals/claim_benchmark/fixtures.py`
- Create: `evals/claim_benchmark/seed.jsonl`（由脚本确定性生成后提交）
- Create: `evals/claim_benchmark/meta.json`
- Test: `tests/evals/claim_benchmark/test_schema.py`

**Interfaces:**
- Consumes: `finance_agent.citation.Claim / verify_claims`；Task 4 `cohen_kappa`
- Produces:
  - `BenchmarkEntry`（pydantic）: `entry_id: str`、`state_key: str`、`claim: dict`、`label_final: Literal["PASS","FAIL","UNVERIFIABLE"]`、`label_a: str | None`、`label_b: str | None`、`annotator_a: str`、`annotator_b: str`、`subsets: list[str]`（取值 `"borderline"` / `"hedged"`）
  - `BenchmarkMeta`: `version: str`、`n_reports: int`、`n_claims: int`、`kappa: float | None`、`notes: str`
  - `fixtures.build_state(state_key: str) -> dict`（当前唯一 key `"state_v1"`）
  - `load_entries() -> list[BenchmarkEntry]`、`load_meta() -> BenchmarkMeta`、`compute_kappa(entries) -> float | None`

- [ ] **Step 1: Write the failing test**

```python
"""claim 基准集 schema 与加载测试。"""

from evals.claim_benchmark.fixtures import build_state
from evals.claim_benchmark.schema import (
    BenchmarkEntry,
    BenchmarkMeta,
    compute_kappa,
    load_entries,
    load_meta,
)


class TestSchema:
    def test_entry_roundtrip(self):
        entry = BenchmarkEntry(
            entry_id="e1", state_key="state_v1",
            claim={"claim_type": "numerical", "source_type": "data",
                   "field_ref": "solvency_metrics.资产负债率.2024",
                   "stated_value": 40.0, "interpretation": ""},
            label_final="PASS", label_a="PASS", label_b="PASS",
            annotator_a="a", annotator_b="b", subsets=[],
        )
        dumped = entry.model_dump()
        assert BenchmarkEntry.model_validate(dumped) == entry

    def test_meta_requires_version(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BenchmarkMeta(n_reports=1, n_claims=1, notes="")


class TestFixture:
    def test_state_v1_deterministic(self):
        s1, s2 = build_state("state_v1"), build_state("state_v1")
        assert list(s1.keys()) == list(s2.keys())
        assert s1["balance_sheet"].equals(s2["balance_sheet"])
        # 各注册表根键的原始输入齐备
        for key in ("balance_sheet", "income_statement", "cash_flow_statement",
                    "financial_indicators", "kline", "benchmark_kline"):
            assert key in s1


class TestSeed:
    def test_seed_loads_and_wellformed(self):
        entries = load_entries()
        assert 30 <= len(entries) <= 60  # 种子集规模（30 份报告起点，随 bad case 扩充）
        meta = load_meta()
        assert meta.version
        assert meta.n_claims == len(entries)
        for e in entries:
            assert e.label_final in {"PASS", "FAIL", "UNVERIFIABLE"}
            assert build_state(e.state_key) is not None

    def test_seed_contains_adversarial_subsets(self):
        entries = load_entries()
        assert any("borderline" in e.subsets for e in entries)
        assert any("hedged" in e.subsets for e in entries)

    def test_compute_kappa_dual_labels(self):
        entries = load_entries()
        kappa = compute_kappa(entries)
        # 种子集 label_a/label_b 同源（synthetic-seed）→ kappa=1.0；人工双标后为真实值
        assert kappa is None or 0.0 <= kappa <= 1.0
```

注意：种子集 label_a/label_b 若为同源 synthetic，`compute_kappa` 返回 `None` 并由 meta.notes 说明；当存在真实双人标注（annotator 含 `"human"`）时才计算 κ。测试按此断言。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/claim_benchmark/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/claim_benchmark/schema.py`：

```python
"""断言级校验基准集 schema（spec evaluation「断言级校验基准集」）。

数据文件：seed.jsonl（每行一条 BenchmarkEntry）+ meta.json（版本/规模/κ）。
种子集为合成确定性数据（annotator=synthetic-seed），标注语义待人工双人标注
替换/扩充（meta.notes 说明）；滚动补库 = 追加行 + version 递增。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from evals.stats import cohen_kappa

_DIR = Path(__file__).resolve().parent


class BenchmarkEntry(BaseModel):
    entry_id: str
    state_key: str  # fixtures.build_state 的 key
    claim: dict  # Claim.model_dump()
    label_final: Literal["PASS", "FAIL", "UNVERIFIABLE"]
    label_a: str | None = None
    label_b: str | None = None
    annotator_a: str = "synthetic-seed"
    annotator_b: str = "synthetic-seed"
    subsets: list[str] = Field(default_factory=list)  # borderline / hedged


class BenchmarkMeta(BaseModel):
    version: str
    n_reports: int
    n_claims: int
    kappa: float | None = None
    notes: str = ""


def load_entries() -> list[BenchmarkEntry]:
    lines = (_DIR / "seed.jsonl").read_text(encoding="utf-8").splitlines()
    return [BenchmarkEntry.model_validate(json.loads(line)) for line in lines if line.strip()]


def load_meta() -> BenchmarkMeta:
    return BenchmarkMeta.model_validate(
        json.loads((_DIR / "meta.json").read_text(encoding="utf-8"))
    )


def compute_kappa(entries: list[BenchmarkEntry]) -> float | None:
    """存在真实双人标注（双方 annotator 非 synthetic）时计算 κ；否则 None。"""
    dual = [e for e in entries if e.label_a and e.label_b
            and "synthetic" not in e.annotator_a and "synthetic" not in e.annotator_b]
    if not dual:
        return None
    return cohen_kappa([e.label_a or "" for e in dual], [e.label_b or "" for e in dual])
```

`evals/claim_benchmark/fixtures.py`：

```python
"""基准集确定性 state fixture：代码内构建 DataFrame（非二进制存储，可 diff、可审计）。

state_v1 与 tests/conftest.py 同源风格：3 年圆整财务数据 + 80 日合成 K 线。
"""

from __future__ import annotations

import pandas as pd

_BALANCE = pd.DataFrame(
    {
        "报告日": ["20241231", "20231231", "20221231"],
        "货币资金": [200.0, 180.0, 150.0],
        "存货": [100.0, 90.0, 80.0],
        "流动资产合计": [500.0, 450.0, 400.0],
        "固定资产净值": [300.0, 280.0, 260.0],
        "累计折旧": [120.0, 100.0, 80.0],
        "非流动资产合计": [500.0, 450.0, 400.0],
        "资产总计": [1000.0, 900.0, 800.0],
        "短期借款": [80.0, 70.0, 60.0],
        "应付账款": [60.0, 50.0, 45.0],
        "应收账款": [40.0, 35.0, 30.0],
        "一年内到期的非流动负债": [20.0, 15.0, 10.0],
        "流动负债合计": [300.0, 280.0, 260.0],
        "长期借款": [50.0, 40.0, 30.0],
        "应付债券": [30.0, 20.0, 20.0],
        "非流动负债合计": [100.0, 70.0, 60.0],
        "负债合计": [400.0, 350.0, 320.0],
        "所有者权益(或股东权益)合计": [600.0, 550.0, 480.0],
        "实收资本(或股本)": [125.0, 125.0, 125.0],
        "未分配利润": [200.0, 170.0, 140.0],
    }
)

_INCOME = pd.DataFrame(
    {
        "报告日": ["20241231", "20231231", "20221231"],
        "营业收入": [1000.0, 900.0, 800.0],
        "营业成本": [600.0, 550.0, 500.0],
        "销售费用": [50.0, 45.0, 40.0],
        "管理费用": [60.0, 55.0, 50.0],
        "研发费用": [30.0, 25.0, 20.0],
        "财务费用": [22.0, 20.0, 18.0],
        "利息费用": [20.0, 18.0, 16.0],
        "营业利润": [200.0, 180.0, 160.0],
        "利润总额": [200.0, 180.0, 160.0],
        "所得税费用": [30.0, 27.0, 24.0],
        "净利润": [170.0, 153.0, 136.0],
        "归属于母公司所有者的净利润": [168.0, 151.0, 134.0],
    }
)

_CASH = pd.DataFrame(
    {
        "报告日": ["20241231", "20231231", "20221231"],
        "经营活动产生的现金流量净额": [250.0, 220.0, 200.0],
        "购建固定资产、无形资产和其他长期资产所支付的现金": [80.0, 70.0, 60.0],
        "投资活动产生的现金流量净额": [-100.0, -90.0, -80.0],
        "分配股利、利润或偿付利息所支付的现金": [50.0, 45.0, 40.0],
        "筹资活动产生的现金流量净额": [-30.0, -20.0, -10.0],
    }
)


def _kline(n: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": [10.0] * n,
            "收盘": [10.0 + i * 0.1 for i in range(n)],
            "最高": [10.5 + i * 0.1 for i in range(n)],
            "最低": [9.5 + i * 0.1 for i in range(n)],
            "成交量": [1000.0] * n,
        }
    )


def build_state(state_key: str) -> dict:
    if state_key != "state_v1":
        raise KeyError(f"未知 state fixture: {state_key}")
    from finance_agent.metrics.solvency import calc_solvency

    base = {
        "balance_sheet": _BALANCE.copy(),
        "income_statement": _INCOME.copy(),
        "cash_flow_statement": _CASH.copy(),
        "financial_indicators": None,
        "kline": _kline(),
        "benchmark_kline": _kline(),
    }
    # 数值型 claim 直接读值的派生指标须在 state 中可得（与真实管线 compute 后一致）
    base["solvency_metrics"] = calc_solvency(
        base["balance_sheet"], base["income_statement"], base["financial_indicators"]
    )
    return base
```

种子集生成：实现内联在 `evals/claim_benchmark/__init__.py` 不需要。写一次性生成逻辑为模块 `evals/claim_benchmark/_seed_gen.py`（git 提交，保证可重生成）：

```python
"""确定性生成 seed.jsonl（不调 LLM；真值由 citation 契约从 fixture 重算得出）。

覆盖：numerical PASS/FAIL、computational 7 根键 PASS/FAIL、borderline（真值
±2%~-1% 与 +1%~+4.9% 的对抗 FAIL claim）、hedged 措辞、llm_inference
UNVERIFIABLE、comparative、event。
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.claim_benchmark.fixtures import build_state
from evals.claim_benchmark.schema import BenchmarkEntry
from finance_agent.citation import _COMPUTATIONAL_RECALC

_DIR = Path(__file__).resolve().parent


def _claims_for_root(state: dict, root: str) -> list[tuple[dict, str, list[str]]]:
    """返回 (claim, label, subsets) 列表：PASS 一条 + 对抗 FAIL 一条（含 borderline/hedged 变体）。"""
    truth = _COMPUTATIONAL_RECALC[root](state)
    out: list[tuple[dict, str, list[str]]] = []
    leaf = _first_leaf(truth)
    if leaf is None:
        return out
    path, gt = leaf
    ref = ".".join([root, *path])
    out.append((
        {"claim_type": "computational", "source_type": "data", "field_ref": ref,
         "stated_value": round(gt, 6), "interpretation": ""},
        "PASS", [],
    ))
    out.append((
        {"claim_type": "computational", "source_type": "data", "field_ref": ref,
         "stated_value": round(gt * 1.5, 6), "interpretation": ""},
        "FAIL", [],
    ))
    # borderline：真值 +2%（容差 0.5% 之外、±5% 之内）→ 应判 FAIL 的对抗样本
    out.append((
        {"claim_type": "computational", "source_type": "data", "field_ref": ref,
         "stated_value": round(gt * 1.02, 6), "interpretation": ""},
        "FAIL", ["borderline"],
    ))
    # hedged：模糊措辞包装的准确值 → PASS；措辞不改变数值语义（点值+容差，design 默认）
    out.append((
        {"claim_type": "computational", "source_type": "data", "field_ref": ref,
         "stated_value": round(gt, 6), "interpretation": f"约 {round(gt, 2)}，可能存在小幅波动"},
        "PASS", ["hedged"],
    ))
    return out


def _first_leaf(tree: object, path: list[str] | None = None) -> tuple[list[str], float] | None:
    path = path or []
    if isinstance(tree, dict):
        for key, value in tree.items():
            found = _first_leaf(value, [*path, str(key)])
            if found is not None:
                return found
        return None
    if isinstance(tree, list):
        for i, value in enumerate(tree):
            if isinstance(value, (int, float)) and value is not None and float(value) != 0.0:
                return [*path, str(i)], float(value)
        return None
    if isinstance(tree, (int, float)) and tree is not None and float(tree) != 0.0:
        return path, float(tree)
    return None


def generate() -> list[BenchmarkEntry]:
    state = build_state("state_v1")
    entries: list[BenchmarkEntry] = []
    n_report = 0

    def add(claim: dict, label: str, subsets: list[str]) -> None:
        nonlocal n_report
        n_report += 1
        entries.append(
            BenchmarkEntry(
                entry_id=f"seed-{n_report:04d}",
                state_key="state_v1",
                claim=claim,
                label_final=label,
                label_a=label,
                label_b=label,
                annotator_a="synthetic-seed",
                annotator_b="synthetic-seed",
                subsets=subsets,
            )
        )

    # 每个注册根键 4 条（PASS/FAIL/borderline/hedged）
    for root in _COMPUTATIONAL_RECALC:
        for claim, label, subsets in _claims_for_root(state, root):
            add(claim, label, subsets)

    # 数值型：build_state 的 solvency_metrics 已由 calc_solvency 计算，直接读值
    debt = state["solvency_metrics"]["资产负债率"]["2024"]
    add({"claim_type": "numerical", "source_type": "data",
         "field_ref": "solvency_metrics.资产负债率.2024",
         "stated_value": float(debt), "interpretation": "资产负债率处于适中水平"}, "PASS", [])
    add({"claim_type": "numerical", "source_type": "data",
         "field_ref": "solvency_metrics.资产负债率.2024",
         "stated_value": float(debt) * 1.5, "interpretation": ""}, "FAIL", [])
    add({"claim_type": "numerical", "source_type": "data",
         "field_ref": "solvency_metrics.资产负债率.2023",
         "stated_value": float(state["solvency_metrics"]["资产负债率"]["2023"]) * 1.03,
         "interpretation": "负债率较上年约上升"}, "FAIL", ["borderline", "hedged"])

    # llm_inference → UNVERIFIABLE
    add({"claim_type": "numerical", "source_type": "llm_inference",
         "field_ref": "solvency_metrics.资产负债率.2024",
         "stated_value": 40.0, "interpretation": "行业惯例约 40%"}, "UNVERIFIABLE", ["hedged"])
    # 未注册根键 → UNVERIFIABLE（覆盖缺口）
    add({"claim_type": "computational", "source_type": "data",
         "field_ref": "not_registered.指标.2024", "stated_value": 1.0, "interpretation": ""},
        "UNVERIFIABLE", [])

    return entries


def main() -> None:
    entries = generate()
    lines = [e.model_dump_json() for e in entries]
    (_DIR / "seed.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (_DIR / "meta.json").write_text(
        json.dumps(
            {
                "version": "0.1.0-seed",
                "n_reports": len(entries),
                "n_claims": len(entries),
                "kappa": None,
                "notes": (
                    "种子集为合成确定性数据（synthetic-seed），用于准度测量管线端到端验证；"
                    "生产基准集（30-50 份历史报告 × 20-30 claim，双人背对背标注 + 仲裁，"
                    "κ 上报）在此基础上滚动补库替换——补库时追加行并递增 version。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"生成 {len(entries)} 条 → seed.jsonl / meta.json")


if __name__ == "__main__":
    main()
```

执行 `uv run python -m evals.claim_benchmark._seed_gen` 生成 `seed.jsonl` + `meta.json` 后一并提交。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/claim_benchmark/test_schema.py -v`
Expected: PASS（28+ 条种子、含 borderline/hedged 子集）

- [ ] **Step 5: Commit**

```bash
git add evals/claim_benchmark tests/evals/claim_benchmark
git commit -m "feat(evals): 断言级校验基准集 schema/fixture/种子集 (harden-evaluation-rigor)"
```

---

### Task 6: 校验器准度测量与门禁

**Files:**
- Create: `evals/claim_benchmark/accuracy.py`
- Test: `tests/evals/claim_benchmark/test_accuracy.py`

**Interfaces:**
- Consumes: Task 5 `load_entries/load_meta/build_state`；`finance_agent.citation.verify_claims/Claim`；Task 4 `paired_bootstrap_ci`
- Produces: `measure(entries: list[BenchmarkEntry]) -> AccuracyReport`（pydantic：`precision/recall/f1: float`、`f1_ci: tuple[float,float]`、`accuracy: float`、`borderline_recall: float | None`、`hedged_recall: float | None`、`gate_passed: bool`、`n: int`）；CLI `uv run python -m evals.claim_benchmark.accuracy`（报告落 `reports/claim_benchmark/`）

- [ ] **Step 1: Write the failing test**

```python
"""准度测量测试：FAIL 为正类；门禁 F1 ≥ 0.90；擦边/模糊子集分项召回显式披露。"""

from evals.claim_benchmark.accuracy import measure
from evals.claim_benchmark.schema import BenchmarkEntry


def _entry(label: str, predicted: str, subsets: list[str] | None = None) -> BenchmarkEntry:
    return BenchmarkEntry(
        entry_id="x", state_key="state_v1",
        claim={"claim_type": "numerical", "source_type": "data",
               "field_ref": "f", "stated_value": 1.0, "interpretation": ""},
        label_final=label, annotator_a="synthetic-seed", annotator_b="synthetic-seed",
        subsets=subsets or [],
    )


class TestMeasure:
    def test_perfect_verifier_passes_gate(self):
        report = measure([_entry("PASS", "PASS"), _entry("FAIL", "FAIL")])
        assert report.precision == 1.0
        assert report.f1 == 1.0
        assert report.gate_passed

    def test_missed_fail_lowers_recall(self):
        report = measure([
            _entry("FAIL", "PASS"), _entry("FAIL", "FAIL"),
            _entry("FAIL", "FAIL"), _entry("FAIL", "FAIL"),
        ])
        assert report.recall == 0.75
        assert report.f1 < 0.90  # 3/4 召回仍过不了 0.90 门禁（P=1 时 F1≈0.857）

    def test_subsets_recall_reported(self):
        report = measure([
            _entry("FAIL", "FAIL", ["borderline"]),
            _entry("FAIL", "PASS", ["borderline"]),
            _entry("PASS", "PASS", ["hedged"]),
        ])
        assert report.borderline_recall == 0.5
        assert report.hedged_recall == 1.0

    def test_empty_subset_recall_is_none(self):
        report = measure([_entry("PASS", "PASS")])
        assert report.borderline_recall is None
        assert report.hedged_recall is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/claim_benchmark/test_accuracy.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/claim_benchmark/accuracy.py`：

```python
"""校验器准度测量与门禁（spec evaluation「校验器准度测量与门禁」）。

FAIL 为正类（校验器的可执行产出就是拦截错误 claim）。门禁：整体 F1 ≥ 0.90
方可宣称校验结果可信；擦边（±5%）与 hedged 子集召回单独披露，不设硬门禁。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from evals.claim_benchmark.fixtures import build_state
from evals.claim_benchmark.schema import BenchmarkEntry, load_entries, load_meta
from finance_agent.citation import Claim, verify_claims

F1_GATE = 0.90


class AccuracyReport(BaseModel):
    n: int
    precision: float
    recall: float
    f1: float
    f1_ci: tuple[float, float]
    accuracy: float
    borderline_recall: float | None = None
    hedged_recall: float | None = None
    gate_passed: bool
    gate_note: str


def _predicted(entry: BenchmarkEntry, state: dict) -> str:
    claim = Claim.model_validate(entry.claim)
    return verify_claims([claim], state)[0].status


def measure(entries: list[BenchmarkEntry], *, seed: int = 42) -> AccuracyReport:
    states: dict[str, dict] = {}
    rows: list[tuple[str, str, list[str]]] = []  # (label, predicted, subsets)
    for e in entries:
        if e.state_key not in states:
            states[e.state_key] = build_state(e.state_key)
        rows.append((e.label_final, _predicted(e, states[e.state_key]), e.subsets))

    tp = sum(1 for lab, pr, _ in rows if lab == "FAIL" and pr == "FAIL")
    fp = sum(1 for lab, pr, _ in rows if lab != "FAIL" and pr == "FAIL")
    fn = sum(1 for lab, pr, _ in rows if lab == "FAIL" and pr != "FAIL")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = sum(1 for lab, pr, _ in rows if lab == pr) / len(rows) if rows else 0.0

    # F1 的 bootstrap CI：按 entry 重采样 0/1 指标（spec：P/R/F1 带 95% CI）
    if rows:
        fail_labels = [1.0 if lab == "FAIL" else 0.0 for lab, _, _ in rows]
        fail_preds = [1.0 if pr == "FAIL" else 0.0 for _, pr, _ in rows]
        # 复用 paired bootstrap：TP/FP/FN 逐次重算
        import numpy as np

        rng = np.random.default_rng(seed)
        n = len(rows)
        f1_samples: list[float] = []
        for _ in range(2_000):
            idx = rng.integers(0, n, size=n)
            lab_s = [fail_labels[i] for i in idx]
            pr_s = [fail_preds[i] for i in idx]
            tp_s = sum(1 for l, p in zip(lab_s, pr_s, strict=True) if l == 1 and p == 1)
            fp_s = sum(1 for l, p in zip(lab_s, pr_s, strict=True) if l == 0 and p == 1)
            fn_s = sum(1 for l, p in zip(lab_s, pr_s, strict=True) if l == 1 and p == 0)
            p_s = tp_s / (tp_s + fp_s) if tp_s + fp_s else 0.0
            r_s = tp_s / (tp_s + fn_s) if tp_s + fn_s else 0.0
            f1_samples.append(2 * p_s * r_s / (p_s + r_s) if p_s + r_s else 0.0)
        lo = float(np.percentile(f1_samples, 2.5))
        hi = float(np.percentile(f1_samples, 97.5))
    else:
        lo = hi = 0.0

    def _subset_recall(name: str) -> float | None:
        sub = [(lab, pr) for lab, pr, ss in rows if name in ss]
        if not sub:
            return None
        return sum(1 for lab, pr in sub if lab == pr) / len(sub)

    gate_passed = f1 >= F1_GATE
    return AccuracyReport(
        n=len(rows),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        f1_ci=(round(lo, 4), round(hi, 4)),
        accuracy=round(accuracy, 4),
        borderline_recall=None if _subset_recall("borderline") is None
        else round(_subset_recall("borderline"), 4),
        hedged_recall=None if _subset_recall("hedged") is None
        else round(_subset_recall("hedged"), 4),
        gate_passed=gate_passed,
        gate_note=(
            "校验器准度可信（F1 ≥ 0.90）"
            if gate_passed
            else "校验器自身准度未达标：下游 FAIL 判定须在评估报告中标注此状态"
        ),
    )


def main() -> None:
    meta = load_meta()
    entries = load_entries()
    report = measure(entries)
    payload = {
        "benchmark_version": meta.version,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **report.model_dump(),
        "disclosure": (
            "擦边子集（stated_value 真值 ±5% 内对抗 claim）召回单独披露，不设硬门禁；"
            "hedged 子集（约/可能/接近措辞）召回单独披露。"
        ),
    }
    out_dir = Path("reports/claim_benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"accuracy-v{meta.version}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"准度报告已写入 {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes + 跑一次真实准度测量**

Run: `uv run pytest tests/evals/claim_benchmark/ -v && uv run python -m evals.claim_benchmark.accuracy`
Expected: 测试 PASS；CLI 输出种子集 F1（预期 =1.0，种子由契约生成；若 <0.90 说明校验器对某族 claim 判定与契约预期不一致——这是真实发现，须以失败测试方式记录并修复校验器或修正种子标签，禁止为了让门禁变绿改弱断言）

- [ ] **Step 5: Commit**

```bash
git add evals/claim_benchmark/accuracy.py tests/evals/claim_benchmark/test_accuracy.py
git commit -m "feat(evals): 校验器准度测量 P/R/F1+CI 与 0.90 门禁、擦边/hedged 分项披露 (harden-evaluation-rigor)"
```

---

### Task 7: 实验对比配对 bootstrap CLI

**Files:**
- Create: `evals/compare.py`
- Test: `tests/evals/test_compare.py`

**Interfaces:**
- Consumes: `evals/run.py` 落盘的 `reports/evals/<name>-<ts>.json`（结构：`{experiment, rows: [{item, mode, scores: {metric: value}}]}`）；Task 4 `paired_bootstrap_ci`
- Produces: `compare_reports(path_a: Path, path_b: Path, *, B: int = 10_000, seed: int = 42) -> CompareReport`；CLI `uv run python -m evals.compare reports/evals/a.json reports/evals/b.json`；结论字符串仅三种：`"显著改进"` / `"显著退步"` / `"无显著差异"`

- [ ] **Step 1: Write the failing test**

```python
"""实验对比测试：配对 bootstrap + 结论措辞约束（CI 含 0 → 只能写无显著差异）。"""

import json

from evals.compare import compare_reports


def _write(tmp_path, name: str, scores: list[float]) -> object:
    path = tmp_path / f"{name}.json"
    rows = [
        {"item": f"q{i}", "mode": "deep", "scores": {"report_relevance": s}}
        for i, s in enumerate(scores)
    ]
    path.write_text(json.dumps({"experiment": name, "rows": rows}), encoding="utf-8")
    return path


class TestCompareReports:
    def test_significant_improvement(self, tmp_path):
        a = _write(tmp_path, "a", [0.9, 0.91, 0.89, 0.92, 0.9, 0.91])
        b = _write(tmp_path, "b", [0.5, 0.48, 0.52, 0.5, 0.49, 0.51])
        report = compare_reports(a, b, B=2_000, seed=7)
        m = report.metrics["report_relevance"]
        assert m.conclusion == "显著改进"
        assert m.ci[0] > 0

    def test_no_significant_difference(self, tmp_path):
        a = _write(tmp_path, "a", [0.6, 0.5, 0.55, 0.52])
        b = _write(tmp_path, "b", [0.51, 0.49, 0.5, 0.53])
        report = compare_reports(a, b, B=2_000, seed=7)
        m = report.metrics["report_relevance"]
        assert m.conclusion == "无显著差异"

    def test_unpaired_items_rejected(self, tmp_path):
        a = _write(tmp_path, "a", [0.6, 0.5])
        b = _write(tmp_path, "b", [0.5])  # 缺 q1
        import pytest

        with pytest.raises(ValueError, match="item 不对齐"):
            compare_reports(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_compare.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/compare.py`：

```python
"""实验基线对比：配对 bootstrap 95% CI（spec evaluation「实验对比统计显著性」）。

输入两份 evals/run.py 报告 JSON，按 dataset item 配对；CI 含 0 → 结论只能是
「无显著差异」，禁止「略有提升」等无统计支撑措辞。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from evals.stats import paired_bootstrap_ci


class MetricComparison(BaseModel):
    mean_a: float
    mean_b: float
    diff: float
    ci: tuple[float, float]
    conclusion: str  # 显著改进 / 显著退步 / 无显著差异


class CompareReport(BaseModel):
    experiment_a: str
    experiment_b: str
    B: int
    metrics: dict[str, MetricComparison]


def _load_rows(path: Path) -> tuple[str, dict[str, dict[str, float]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, dict[str, float]] = {}
    for row in data.get("rows", []):
        if row.get("skipped"):
            continue
        rows[str(row["item"])] = {
            k: float(v) for k, v in (row.get("scores") or {}).items() if v is not None
        }
    return str(data.get("experiment", path.stem)), rows


def compare_reports(path_a: Path, path_b: Path, *, B: int = 10_000, seed: int = 42) -> CompareReport:
    name_a, rows_a = _load_rows(path_a)
    name_b, rows_b = _load_rows(path_b)
    if set(rows_a) != set(rows_b):
        only_a = sorted(set(rows_a) - set(rows_b))[:3]
        only_b = sorted(set(rows_b) - set(rows_a))[:3]
        raise ValueError(
            f"item 不对齐（配对 bootstrap 要求同一 dataset 全量跑完）: "
            f"仅A有{only_a} 仅B有{only_b}"
        )
    metric_names = sorted({m for scores in rows_a.values() for m in scores})
    comparisons: dict[str, MetricComparison] = {}
    for metric in metric_names:
        pairs = [
            (rows_a[item].get(metric), rows_b[item].get(metric))
            for item in sorted(rows_a)
        ]
        valid = [(a, b) for a, b in pairs if a is not None and b is not None]
        if not valid:
            continue
        seq_a = [a for a, _ in valid]
        seq_b = [b for _, b in valid]
        mean_a = sum(seq_a) / len(seq_a)
        mean_b = sum(seq_b) / len(seq_b)
        lo, hi = paired_bootstrap_ci(seq_a, seq_b, B=B, seed=seed)
        if lo > 0:
            conclusion = "显著改进"
        elif hi < 0:
            conclusion = "显著退步"
        else:
            conclusion = "无显著差异"
        comparisons[metric] = MetricComparison(
            mean_a=round(mean_a, 4),
            mean_b=round(mean_b, 4),
            diff=round(mean_a - mean_b, 4),
            ci=(round(lo, 4), round(hi, 4)),
            conclusion=conclusion,
        )
    return CompareReport(experiment_a=name_a, experiment_b=name_b, B=B, metrics=comparisons)


def main() -> None:
    parser = argparse.ArgumentParser(description="实验对比（配对 bootstrap 95% CI）")
    parser.add_argument("report_a")
    parser.add_argument("report_b")
    parser.add_argument("--B", type=int, default=10_000)
    args = parser.parse_args()
    report = compare_reports(Path(args.report_a), Path(args.report_b), B=args.B)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    out_dir = Path("reports/evals")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"compare-{report.experiment_a}-vs-{report.experiment_b}-{ts}.json"
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"对比报告已写入 {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_compare.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/compare.py tests/evals/test_compare.py
git commit -m "feat(evals): 实验对比配对 bootstrap CI 与结论措辞约束 (harden-evaluation-rigor)"
```

---

### Task 8: 数据对齐消融实验编排

**Files:**
- Create: `evals/ablation.py`
- Test: `tests/evals/test_ablation.py`

**Interfaces:**
- Consumes: `finance_agent.nodes.*` 各节点函数（模块级导入便于 patch）；`evals.extract.extract_judge_vars`；`evals.judges.run_judge`；Task 4 `paired_bootstrap_ci`；`evals.run._collect_prompt_versions`
- Produces:
  - `build_variant_graph(variant: Literal["analysts","plus_debate","full"]) -> CompiledStateGraph` — 三变体共用同一 state 快照起点（compute_metrics 之后），仅编排不同
  - `run_ablation(tickers: Sequence[str], *, repeats: int = 3, snapshot_builder=None) -> dict` — 返回报告 dict（含 per-variant citation_pass 率、judge 分中位数、层间增量 CI）
  - 报告落 `reports/ablation/`

- [ ] **Step 1: Write the failing test**

```python
"""消融编排测试：变体输入对齐（同一快照）、聚合与结论措辞。全部 mock 节点，不调 LLM。"""

from evals.ablation import aggregate_results, build_variant_graph, conclusion_for_layer


class TestVariantGraph:
    def test_three_variants_buildable(self):
        for variant in ("analysts", "plus_debate", "full"):
            graph = build_variant_graph(variant)
            assert graph is not None

    def test_unknown_variant_raises(self):
        import pytest

        with pytest.raises(ValueError):
            build_variant_graph("nope")


class TestAggregate:
    def _runs(self, variant: str, citation: list[bool], judge: list[float]) -> list[dict]:
        return [
            {"variant": variant, "ticker": f"t{i % 3}", "citation_pass": c,
             "judge": {"report_relevance": j}}
            for i, (c, j) in enumerate(zip(citation, judge, strict=True))
        ]

    def test_layer_increment_with_ci_support(self):
        runs = (
            self._runs("analysts", [False] * 6, [2.0] * 6)
            + self._runs("plus_debate", [True] * 6, [4.0] * 6)
            + self._runs("full", [True] * 6, [4.5] * 6)
        )
        report = aggregate_results(runs)
        debate = report["layers"]["debate"]
        assert debate["judge_report_relevance"]["conclusion"] == "显著改进"
        full = report["layers"]["full"]
        assert full["judge_report_relevance"]["ci"][0] > 0

    def test_layer_without_support_flagged(self):
        runs = (
            self._runs("analysts", [True, False], [3.0, 3.1])
            + self._runs("plus_debate", [True, False], [3.05, 3.0])
        )
        report = aggregate_results(runs)
        assert (
            report["layers"]["debate"]["judge_report_relevance"]["conclusion"]
            == "该层价值未获统计支持"
        )


class TestConclusionWording:
    def test_ci_contains_zero_wording(self):
        c = conclusion_for_layer((-.01, .02))
        assert c == "该层价值未获统计支持"

    def test_ci_positive_wording(self):
        assert conclusion_for_layer((0.05, 0.4)) == "显著改进"

    def test_ci_negative_wording(self):
        assert conclusion_for_layer((-0.4, -0.05)) == "显著退步"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_ablation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/ablation.py`（节点全部模块级导入，测试可 patch；`_collect_prompt_versions` 从 `evals.run` 复用）：

```python
"""数据对齐消融实验（spec evaluation「数据对齐消融实验」；design D4）。

三变体（spec 原文「单分析师直出」按「仅分析师层直出」实现：4 分析师 →
citation → 报告；(b) + Bull/Bear 辩论 + research_manager；(c) 完整 5 层）：
所有变体接收完全相同的 fetch_data+compute_metrics state 快照（重放，不重取数），
差异只可归因于编排架构。每标的先构建一次快照，三变体 × 3 次重复共用。
"""

from __future__ import annotations

import json
import pickle
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from evals.extract import extract_judge_vars
from evals.judges import run_judge
from evals.stats import paired_bootstrap_ci
from finance_agent.nodes.analysts import (
    fundamental_analyst,
    macro_analyst,
    sentiment_analyst,
    technical_analyst,
)
from finance_agent.nodes.citation_node import verify_citations
from finance_agent.nodes.compute import compute_metrics
from finance_agent.nodes.debate import bear_debater, bull_debater
from finance_agent.nodes.fetch import fetch_data
from finance_agent.nodes.fund_manager import fund_manager
from finance_agent.nodes.report import generate_report
from finance_agent.nodes.research_manager import research_manager
from finance_agent.nodes.risk import (
    aggressive_debater,
    conservative_debater,
    neutral_debater,
    risk_judge,
)
from finance_agent.nodes.trader import trader

Variant = Literal["analysts", "plus_debate", "full"]
JUDGE_DIMS = ["report_relevance", "debate_quality", "decision_grounding", "consistency"]


def build_variant_graph(variant: Variant) -> CompiledStateGraph:
    """三变体共用「analysts → verify_citations」前段，按层级递增编排。"""
    if variant not in ("analysts", "plus_debate", "full"):
        raise ValueError(f"未知变体: {variant}")
    g: StateGraph = StateGraph(dict)
    g.add_node("technical_analyst", technical_analyst)
    g.add_node("macro_analyst", macro_analyst)
    g.add_node("fundamental_analyst", fundamental_analyst)
    g.add_node("sentiment_analyst", sentiment_analyst)
    g.add_node("verify_citations", verify_citations)

    g.add_edge(START, "technical_analyst")
    g.add_edge(START, "macro_analyst")
    g.add_edge(START, "fundamental_analyst")
    g.add_edge(START, "sentiment_analyst")
    for n in ("technical_analyst", "macro_analyst", "fundamental_analyst", "sentiment_analyst"):
        g.add_edge(n, "verify_citations")
    tail = "verify_citations"

    if variant in ("plus_debate", "full"):
        g.add_node("bull_r1", bull_debater)
        g.add_node("bear_r1", bear_debater)
        g.add_node("bull_r2", bull_debater)
        g.add_node("bear_r2", bear_debater)
        g.add_node("research_manager", research_manager)
        g.add_edge(tail, "bull_r1")
        g.add_edge(tail, "bear_r1")
        g.add_edge("bull_r1", "bull_r2")
        g.add_edge("bear_r1", "bear_r2")
        g.add_edge("bull_r2", "research_manager")
        g.add_edge("bear_r2", "research_manager")
        tail = "research_manager"

    if variant == "full":
        g.add_node("trader", trader)
        g.add_node("aggressive_r1", aggressive_debater)
        g.add_node("conservative_r1", conservative_debater)
        g.add_node("neutral_r1", neutral_debater)
        g.add_node("risk_judge", risk_judge)
        g.add_node("fund_manager", fund_manager)
        g.add_edge(tail, "trader")
        g.add_edge("trader", "aggressive_r1")
        g.add_edge("trader", "conservative_r1")
        g.add_edge("trader", "neutral_r1")
        for n in ("aggressive_r1", "conservative_r1", "neutral_r1"):
            g.add_edge(n, "risk_judge")
        g.add_edge("risk_judge", "fund_manager")
        tail = "fund_manager"

    g.add_node("generate_report", generate_report)
    g.add_edge(tail, "generate_report")
    g.add_edge("generate_report", END)
    return g.compile()


def build_snapshot(ticker: str, *, client: Any = None, cache: Any = None) -> dict:
    """fetch_data + compute_metrics 一次，输出可重放的 state 快照（含 DataFrame）。"""
    base = {"stock_code": ticker, "enable_web_search": False}
    state: dict = {**base, **fetch_data(base, client=client, cache=cache)}
    state.update(compute_metrics(state))  # type: ignore[arg-type]
    return state


def snapshot_digest(state: dict) -> str:
    """快照摘要（审计用）：各 DataFrame shape + 哈希，证明三变体输入一致。"""
    import hashlib

    parts: list[str] = []
    for key in sorted(state):
        value = state[key]
        if hasattr(value, "shape"):
            parts.append(f"{key}:{value.shape}:{hashlib.md5(str(value.values.tobytes()).encode()).hexdigest()[:8]}")
        elif isinstance(value, (str, int, float, bool)) or value is None:
            parts.append(f"{key}:{value!r}")
        else:
            parts.append(f"{key}:type={type(value).__name__}")
    return "|".join(parts)


def run_variant_once(variant: Variant, snapshot: dict, query: str) -> dict:
    """单次变体运行：快照重放 + citation_pass + judge 变量提取。"""
    graph = build_variant_graph(variant)
    state = graph.invoke({**snapshot, "focus": query})
    judge_vars = extract_judge_vars(state, query=query)
    return {
        "final_report": state.get("final_report"),
        "citation_pass": bool(state.get("citation_pass")),
        "judge_vars": judge_vars,
        "decision": state.get("final_trade_decision"),
    }


def conclusion_for_layer(ci: tuple[float, float]) -> str:
    if ci[0] > 0:
        return "显著改进"
    if ci[1] < 0:
        return "显著退步"
    return "该层价值未获统计支持"


def aggregate_results(runs: list[dict], *, B: int = 10_000, seed: int = 42) -> dict:
    """runs: [{variant, ticker, citation_pass, judge: {dim: score}}]。

    层级增量 = 上一变体 → 本变体的配对 bootstrap CI（按 ticker 中位数配对）。
    """
    variants = ["analysts", "plus_debate", "full"]
    layer_names = {"plus_debate": "debate", "full": "full"}
    report: dict[str, Any] = {"variants": {}, "layers": {}}
    for variant in variants:
        v_runs = [r for r in runs if r["variant"] == variant]
        report["variants"][variant] = {
            "n_runs": len(v_runs),
            "citation_pass_rate": (
                sum(1 for r in v_runs if r["citation_pass"]) / len(v_runs) if v_runs else None
            ),
            "judge_medians": {
                dim: _median([r["judge"][dim] for r in v_runs if r["judge"].get(dim) is not None])
                for dim in JUDGE_DIMS
            },
        }
    for variant in ("plus_debate", "full"):
        prev = "analysts" if variant == "plus_debate" else "plus_debate"
        layer: dict[str, Any] = {}
        prev_by_ticker = _by_ticker_median(runs, prev)
        cur_by_ticker = _by_ticker_median(runs, variant)
        common = sorted(set(prev_by_ticker) & set(cur_by_ticker))
        for dim in JUDGE_DIMS:
            seq_prev = [prev_by_ticker[t][dim] for t in common if prev_by_ticker[t].get(dim) is not None]
            seq_cur = [cur_by_ticker[t][dim] for t in common if cur_by_ticker[t].get(dim) is not None]
            if not seq_prev or not seq_cur:
                continue
            lo, hi = paired_bootstrap_ci(seq_cur, seq_prev, B=B, seed=seed)
            layer[f"judge_{dim}"] = {
                "diff_median": round(sum(seq_cur) / len(seq_cur) - sum(seq_prev) / len(seq_prev), 4),
                "ci": (round(lo, 4), round(hi, 4)),
                "conclusion": conclusion_for_layer((lo, hi)),
            }
        # citation_pass 率差值（点估计披露，不设 CI 门禁）
        layer["citation_pass_rate"] = {
            "prev": report["variants"][prev]["citation_pass_rate"],
            "current": report["variants"][variant]["citation_pass_rate"],
        }
        report["layers"][layer_names[variant]] = layer
    return report


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _by_ticker_median(runs: list[dict], variant: str) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    tickers = {r["ticker"] for r in runs if r["variant"] == variant}
    for t in tickers:
        t_runs = [r for r in runs if r["variant"] == variant and r["ticker"] == t]
        out[t] = {dim: _median([r["judge"][dim] for r in t_runs if r["judge"].get(dim) is not None])
                  for dim in JUDGE_DIMS}
    return out


def run_ablation(
    tickers: Sequence[str],
    *,
    repeats: int = 3,
    snapshot_builder: Callable[[str], dict] | None = None,
    query: str = "综合评估投资价值",
) -> dict:
    """消融主流程：每标的一次快照 → 3 变体 × repeats 次 → 聚合报告。

    实际跑批消耗 LLM token（10 标的 × 3 变体 × 3 次 ≈ 90 次深度分析），
    属人工触发的评估动作；本函数不做静默降级。
    """
    builder = snapshot_builder or build_snapshot
    runs: list[dict] = []
    snapshots: dict[str, str] = {}
    for ticker in tickers:
        snapshot = builder(ticker)
        snapshots[ticker] = snapshot_digest(snapshot)
        for variant in ("analysts", "plus_debate", "full"):
            for _ in range(repeats):
                out = run_variant_once(variant, snapshot, query)
                judge_scores: dict[str, float | None] = {}
                for dim in JUDGE_DIMS:
                    if variant == "analysts" and dim != "report_relevance":
                        judge_scores[dim] = None  # 无辩论/决策层维度不适用
                        continue
                    result = run_judge(dim, out["judge_vars"])
                    judge_scores[dim] = (
                        float(result["score"]) if result["score"] is not None else None
                    )
                runs.append({
                    "variant": variant, "ticker": ticker,
                    "citation_pass": out["citation_pass"], "judge": judge_scores,
                })
    report = aggregate_results(runs)
    report["snapshot_digests"] = snapshots  # 三变体共用同一 digest = 输入对齐证据
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def main() -> None:
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="数据对齐消融实验")
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    report = run_ablation(args.tickers, repeats=args.repeats)
    out_dir = Path("reports/ablation")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ablation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"消融报告已写入 {path}")


if __name__ == "__main__":
    main()
```

注意：实现时先读 `src/finance_agent/graph.py` 的 analyst Send/汇聚边与 `verify_citations` 前置条件，确保变体图节点连线与主图语义一致（analysts 并行 → verify_citations 汇聚）；`pickle` 导入若未用则删除。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_ablation.py -v`
Expected: PASS（图可编译、聚合措辞正确；不调 LLM）

- [ ] **Step 5: Commit**

```bash
git add evals/ablation.py tests/evals/test_ablation.py
git commit -m "feat(evals): 数据对齐消融三变体编排与层间增量 CI 报告 (harden-evaluation-rigor)"
```

---

### Task 9: 回测数据快照（时点截断）+ 回放 + 决策一致性

**Files:**
- Create: `evals/backtest/__init__.py`（空）
- Create: `evals/backtest/data_snapshot.py`
- Create: `evals/backtest/replay.py`
- Test: `tests/evals/backtest/test_data_snapshot.py`
- Test: `tests/evals/backtest/test_replay.py`

**Interfaces:**
- Consumes: `AKShareClient`（可选注入）；`outcome.settle.evaluate_decision`；`evals.ablation.build_variant_graph("full")`（回放复用完整编排，快照由 data_snapshot 提供）
- Produces:
  - `disclosure_deadline(period_end: str) -> str`（"20241231"→"20250430"；Q1→0430 / H1→0831 / Q3→1031）
  - `truncate_state(full_state: dict, decision_date: str) -> dict`（行情/财报/事件按可得性截断；`stock_quote`/`industry_pe` 剔除——当下时点数据无法回放）
  - `build_snapshot(code: str, decision_date: str, *, client=None) -> SnapshotResult`（`SnapshotResult.state: dict`、`SnapshotResult.metadata: dict`：`decision_date/data_cutoff/disclosure_rule/excluded_fields/fetched_at`）
  - `replay_decision(code, decision_date, *, snapshot=None, client=None) -> dict`（`decision/final_report/settlement/consistency 字段无`）
  - `replay_with_consistency(code, decision_date, n=3, ...) -> dict`（`decisions: list[str]`、`agreement: float`（多数方向占比）、`settlement`（首次回放的结算））

- [ ] **Step 1: Write the failing test**

`tests/evals/backtest/test_data_snapshot.py`：

```python
"""时点截断测试（spec decision-backtest「历史离线回放」Scenario「时点截断」）。"""

import pandas as pd

from evals.backtest.data_snapshot import disclosure_deadline, truncate_state


class TestDisclosureDeadline:
    def test_annual_report_next_year_april(self):
        assert disclosure_deadline("20241231") == "20250430"

    def test_quarters(self):
        assert disclosure_deadline("20240331") == "20240430"
        assert disclosure_deadline("20240630") == "20240831"
        assert disclosure_deadline("20240930") == "20241031"


class TestTruncateState:
    def _kline(self) -> pd.DataFrame:
        dates = [f"2025-01-{d:02d}" for d in range(1, 29)]
        return pd.DataFrame({"日期": dates, "开盘": 10.0, "收盘": 10.5,
                             "最高": 11.0, "最低": 9.5, "成交量": 100.0})

    def test_kline_truncated_to_decision_date(self):
        state = {"kline": self._kline()}
        out = truncate_state(state, "2025-01-14")
        assert out["kline"]["日期"].max() == "2025-01-14"

    def test_financials_by_disclosure_not_period(self):
        bs = pd.DataFrame({"报告日": ["20241231", "20231231"], "资产总计": [1000.0, 900.0]})
        state = {"balance_sheet": bs}
        # 2024 年报披露截止 2025-04-30 → 决策日 2025-03-01 不可得，须剔除
        out = truncate_state(state, "2025-03-01")
        assert list(out["balance_sheet"]["报告日"]) == ["20231231"]
        out2 = truncate_state(state, "2025-05-01")
        assert list(out2["balance_sheet"]["报告日"]) == ["20241231", "20231231"]

    def test_point_in_time_fields_excluded(self):
        state = {"kline": self._kline(), "stock_quote": {"price": 10.0}, "industry_pe": {"pe": 20}}
        out = truncate_state(state, "2025-01-14")
        assert "stock_quote" not in out
        assert "industry_pe" not in out

    def test_news_events_filtered_by_date(self):
        state = {
            "news_list": [{"date": "2025-01-10", "title": "a"}, {"date": "2025-01-20", "title": "b"}],
            "key_events": [{"date": "2025-01-12", "title": "e1"}, {"date": "2025-02-01", "title": "e2"}],
        }
        out = truncate_state(state, "2025-01-14")
        assert [n["title"] for n in out["news_list"]] == ["a"]
        assert [e["title"] for e in out["key_events"]] == ["e1"]
```

`tests/evals/backtest/test_replay.py`：

```python
"""回放与决策一致性测试：mock 编排图，不调 LLM。"""

from evals.backtest.replay import build_decision_record, direction_agreement


class TestDecisionRecord:
    def test_record_shape_matches_settle_contract(self):
        kline_close_on_t = 12.5
        decision = {"action": "buy", "entry_price": None, "stop_loss": 11.0,
                    "target_price": 14.0, "confidence": 0.7}
        record = build_decision_record(decision, entry_price=kline_close_on_t,
                                       decision_date="2025-01-14", code="600519")
        assert record["entry_price"] == 12.5
        assert record["action"] == "buy"
        assert record["timestamp"] == "2025-01-14"
        # 与 outcome.settle.evaluate_decision 契约兼容：直接跑通结算
        import pandas as pd

        from finance_agent.outcome.settle import evaluate_decision

        kline = pd.DataFrame({
            "日期": ["2025-01-15", "2025-01-16"],
            "开盘": [12.6, 13.8], "收盘": [12.8, 14.2],
            "最高": [12.9, 14.5], "最低": [12.5, 13.5],
        })
        settlement = evaluate_decision(record, kline, None)
        assert settlement is not None
        assert settlement.status == "hit_target"


class TestConsistency:
    def test_full_agreement(self):
        assert direction_agreement(["buy", "buy", "buy"]) == 1.0

    def test_two_of_three(self):
        assert direction_agreement(["buy", "buy", "sell"]) == 2 / 3

    def test_flag_below_threshold(self):
        assert direction_agreement(["buy", "sell", "hold"]) < 2 / 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/backtest -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/backtest/data_snapshot.py`：

```python
"""回测数据快照：时点截断 + 可审计元信息（spec decision-backtest「历史离线回放」；design D5）。

前视偏差防控：行情按日期 ≤ T；财报按披露截止日（法定期限近似：Q1→04-30、
H1→08-31、Q3→10-31、年报→次年 04-30）而非报告期；新闻/事件按日期 ≤ T；
stock_quote / industry_pe 等纯当下数据剔除并在 metadata.excluded_fields 记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

_EXCLUDED_POINT_IN_TIME = ("stock_quote", "industry_pe")


@dataclass
class SnapshotResult:
    state: dict
    metadata: dict = field(default_factory=dict)


def disclosure_deadline(period_end: str) -> str:
    """A 股法定披露截止日近似（报告期期末 → 最晚披露日）。"""
    year, month = int(period_end[:4]), int(period_end[4:6])
    deadline = {(3,): "0430", (6,): "0831", (9,): "1031", (12,): "0430"}[(month,)]
    if month == 12:
        return f"{year + 1}{deadline}"
    return f"{year}{deadline}"


def _truncate_kline(df: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    dates = df["日期"].astype(str).str[:10]
    return df[dates <= decision_date].copy()


def _truncate_reports(df: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    deadlines = df["报告日"].astype(str).map(lambda d: disclosure_deadline(d))
    keep = deadlines <= decision_date.replace("-", "")
    return df[keep].copy()


def _truncate_dated_list(items: Any, decision_date: str) -> list:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, dict):
            date = str(item.get("date") or item.get("发布时间") or "")[:10]
            if not date or date <= decision_date:
                out.append(item)
        else:
            out.append(item)
    return out


def truncate_state(full_state: dict, decision_date: str) -> dict:
    """所有可得性截断的入口；不改调用方对象。"""
    out: dict = {}
    for key, value in full_state.items():
        if key in _EXCLUDED_POINT_IN_TIME:
            continue
        if key in ("kline", "benchmark_kline") and isinstance(value, pd.DataFrame):
            out[key] = _truncate_kline(value, decision_date)
        elif key in ("balance_sheet", "income_statement", "cash_flow_statement",
                     "financial_indicators", "quarterly_income") and isinstance(value, pd.DataFrame):
            if "报告日" in value.columns:
                out[key] = _truncate_reports(value, decision_date)
            else:
                out[key] = value.copy()
        elif key in ("news_list", "key_events"):
            out[key] = _truncate_dated_list(value, decision_date)
        else:
            out[key] = value
    return out


def build_snapshot(code: str, decision_date: str, *, client: Any = None) -> SnapshotResult:
    """拉全量数据 → 截断 → 快照 + 审计元信息。"""
    from finance_agent.nodes.fetch import fetch_data

    base = {"stock_code": code, "enable_web_search": False}
    full = {**base, **fetch_data(base, client=client)}
    state = truncate_state(full, decision_date)
    metadata = {
        "code": code,
        "decision_date": decision_date,
        "data_cutoff": decision_date,
        "disclosure_rule": "legal-deadline-approx(Q1:0430,H1:0831,Q3:1031,FY:next-0430)",
        "excluded_fields": list(_EXCLUDED_POINT_IN_TIME),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    return SnapshotResult(state=state, metadata=metadata)
```

`evals/backtest/replay.py`：

```python
"""离线回放：截断快照 → 完整编排 → TradeDecision → 复用 outcome.settle 结算。

结算语义（涨跌停递延/停牌顺延/跳空穿越/方向符号化）全部复用
outcome.settle.evaluate_decision，不另造一套（spec「绩效指标与基线对比」）。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from evals.ablation import build_variant_graph
from evals.backtest.data_snapshot import SnapshotResult, build_snapshot
from finance_agent.nodes.compute import compute_metrics
from finance_agent.outcome.settle import evaluate_decision


def build_decision_record(
    decision: dict, *, entry_price: float, decision_date: str, code: str
) -> dict:
    """TradeDecision 序列化 dict → evaluate_decision 契约的 decision record。

    entry_price 统一取决策日收盘（回测无实时盘口；结算从 T+1 行起评）。
    """
    return {
        "decision_id": f"backtest-{code}-{decision_date}",
        "action": decision.get("action", "hold"),
        "entry_price": float(entry_price),
        "stop_loss": decision.get("stop_loss"),
        "target_price": decision.get("target_price"),
        "timestamp": decision_date,
    }


def direction_agreement(actions: list[str]) -> float:
    """n 次重复的多数方向占比（spec：一致率 < 2/3 剔除或单独标注）。"""
    if not actions:
        return 0.0
    top = Counter(actions).most_common(1)[0][1]
    return top / len(actions)


def replay_decision(
    code: str,
    decision_date: str,
    *,
    snapshot: SnapshotResult | None = None,
    client: Any = None,
    full_kline: pd.DataFrame | None = None,
) -> dict:
    """单次回放：快照（截断）→ compute_metrics → 完整 5 层 → 结算（全量 K 线）。"""
    snap = snapshot or build_snapshot(code, decision_date, client=client)
    state = {**snap.state}
    state.update(compute_metrics(state))  # type: ignore[arg-type]
    graph = build_variant_graph("full")
    final = graph.invoke({**state, "focus": f"{code} 综合评估投资价值"})
    decision = final.get("final_trade_decision") or {}
    kline = full_kline if full_kline is not None else state.get("kline")
    entry_price = _close_on_or_before(kline, decision_date)
    action = str(decision.get("action", ""))
    if entry_price is None or not action:
        return {"decision": decision, "settlement": None, "entry_price": None,
                "action": action, "decision_date": decision_date,
                "snapshot_metadata": snap.metadata, "final_report": final.get("final_report")}
    record = build_decision_record(
        decision, entry_price=entry_price, decision_date=decision_date, code=code
    )
    settlement = evaluate_decision(record, kline, state.get("benchmark_kline"))
    return {
        "decision": decision,
        "settlement": settlement.__dict__ if settlement else None,
        "entry_price": entry_price,
        "action": action,
        "decision_date": decision_date,
        "snapshot_metadata": snap.metadata,
        "final_report": final.get("final_report"),
    }


def replay_with_consistency(
    code: str,
    decision_date: str,
    *,
    n: int = 3,
    snapshot: SnapshotResult | None = None,
    client: Any = None,
    full_kline: pd.DataFrame | None = None,
) -> dict:
    """同一快照重复回放 n 次：决策方向一致率 + 首次结算结果（一致性独立维度披露）。"""
    snap = snapshot or build_snapshot(code, decision_date, client=client)
    actions: list[str] = []
    first: dict | None = None
    for _ in range(n):
        result = replay_decision(
            code, decision_date, snapshot=snap, full_kline=full_kline
        )
        actions.append(str((result.get("decision") or {}).get("action", "hold")))
        if first is None:
            first = result
    return {
        "code": code,
        "decision_date": decision_date,
        "actions": actions,
        "agreement": round(direction_agreement(actions), 4),
        "settlement": (first or {}).get("settlement"),
        "snapshot_metadata": snap.metadata,
    }


def _close_on_or_before(kline: pd.DataFrame | None, date: str) -> float | None:
    if kline is None or kline.empty:
        return None
    dates = kline["日期"].astype(str).str[:10]
    eligible = kline[dates <= date]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["收盘"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/backtest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/backtest tests/evals/backtest
git commit -m "feat(evals): 回测时点截断快照/回放/决策一致性,结算复用 outcome.settle (harden-evaluation-rigor)"
```

---

### Task 10: 回测绩效四指标 + 规则基线 + 分层抽样 + block bootstrap 显著性 + 编排

**Files:**
- Create: `evals/backtest/performance.py`
- Create: `evals/backtest/baselines.py`
- Create: `evals/backtest/sampling.py`
- Create: `evals/backtest/significance.py`
- Create: `evals/backtest/run_backtest.py`
- Test: `tests/evals/backtest/test_performance.py`
- Test: `tests/evals/backtest/test_baselines.py`
- Test: `tests/evals/backtest/test_sampling.py`
- Test: `tests/evals/backtest/test_significance.py`

**Interfaces:**
- Consumes: `metrics/technical.py calc_technical`；Task 4 `sharpe/block_bootstrap_stat/paired_block_bootstrap_diff`；Task 9 `replay_with_consistency/build_snapshot`
- Produces:
  - `perf_metrics(daily_returns: Sequence[float]) -> dict` — `{"CR": float, "ARR": float, "Sharpe": float, "MDD": float}`
  - `baseline_positions(kline: pd.DataFrame, strategy: Literal["buy_hold","macd","kdj","rsi"]) -> pd.Series`；`strategy_returns(kline, positions) -> list[float]`
  - `classify_regime(window_kline: pd.DataFrame, *, up_threshold=0.10, down_threshold=-0.10) -> Literal["bull","bear","sideways"]`；`stratified_sample(index_kline, stock_pool, *, per_regime=10, window_days=120, seed=42) -> list[dict]`（`{"code","regime","decision_date"}`）
  - `validate_sanity(sharpe_value: float, sanity_note: str | None) -> Literal["valid","invalid"]`；`block_length_sensitivity(returns, *, blocks=(10,20,40), B=1000, seed=42) -> dict`
  - 编排 CLI：`uv run python -m evals.backtest.run_backtest --codes 600519 000858 --per-regime 10 --repeats 3 [--sanity-note "..."]`

- [ ] **Step 1: Write the failing test**

`tests/evals/backtest/test_performance.py`：

```python
from evals.backtest.performance import perf_metrics


class TestPerfMetrics:
    def test_known_values(self):
        # 100 日每日 +1%：CR = 1.01^100 - 1 ≈ 1.7048；MDD = 0
        returns = [0.01] * 100
        m = perf_metrics(returns)
        assert abs(m["CR"] - (1.01 ** 100 - 1)) < 1e-9
        assert m["MDD"] == 0.0
        assert m["Sharpe"] > 0
        assert m["ARR"] > m["CR"]

    def test_drawdown_from_peak(self):
        returns = [0.1, -0.2, 0.0]
        m = perf_metrics(returns)
        # 峰值 1.1 → 谷 0.88 → MDD = 0.2/1.1
        assert abs(m["MDD"] - 0.2 / 1.1) < 1e-9

    def test_empty_returns_zeroed(self):
        m = perf_metrics([])
        assert m == {"CR": 0.0, "ARR": 0.0, "Sharpe": 0.0, "MDD": 0.0}
```

`tests/evals/backtest/test_baselines.py`：

```python
import pandas as pd

from evals.backtest.baselines import baseline_positions, strategy_returns


def _kline(n: int = 120, drift: float = 0.05) -> pd.DataFrame:
    close = [10.0 * (1 + drift) ** i for i in range(n)]
    return pd.DataFrame({
        "日期": [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)],
        "开盘": close, "收盘": close, "最高": [c * 1.01 for c in close],
        "最低": [c * 0.99 for c in close], "成交量": [100.0] * n,
    })


class TestBaselines:
    def test_buy_hold_always_long(self):
        pos = baseline_positions(_kline(), "buy_hold")
        assert (pos == 1).all()

    def test_macd_trend_following(self):
        # 单边上涨 → MACD DIF>DEA → 大部分时间持仓
        pos = baseline_positions(_kline(), "macd")
        assert pos.iloc[-1] == 1
        assert pos.mean() > 0.5

    def test_strategy_returns_length_matches(self):
        kline = _kline()
        pos = baseline_positions(kline, "rsi")
        rets = strategy_returns(kline, pos)
        assert len(rets) == len(kline) - 1  # 首日无前仓收益

    def test_unknown_strategy_raises(self):
        import pytest

        with pytest.raises(ValueError):
            baseline_positions(_kline(), "nope")
```

`tests/evals/backtest/test_sampling.py`：

```python
import pandas as pd

from evals.backtest.sampling import classify_regime, stratified_sample


def _index(total: float) -> pd.DataFrame:
    n = 60
    start = 100.0
    end = start * (1 + total)
    closes = [start + (end - start) * i / (n - 1) for i in range(n)]
    return pd.DataFrame({
        "日期": [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)],
        "收盘": closes,
    })


class TestRegime:
    def test_bull_bear_sideways(self):
        assert classify_regime(_index(0.30)) == "bull"
        assert classify_regime(_index(-0.30)) == "bear"
        assert classify_regime(_index(0.02)) == "sideways"


class TestStratifiedSample:
    def test_three_regimes_ten_stocks(self):
        # 三段拼接的指数历史：上涨 + 下跌 + 震荡
        kline = pd.concat([_index(0.3), _index(-0.3), _index(0.0)], ignore_index=True)
        pool = [f"{600000 + i}" for i in range(40)]
        sample = stratified_sample(kline, pool, per_regime=10, window_days=55)
        regimes = {s["regime"] for s in sample}
        assert regimes == {"bull", "bear", "sideways"}
        for regime in regimes:
            assert sum(1 for s in sample if s["regime"] == regime) >= 10

    def test_missing_regime_raises(self):
        import pytest

        pool = [f"{600000 + i}" for i in range(40)]
        with pytest.raises(ValueError, match="regime"):
            stratified_sample(_index(0.3), pool, per_regime=10, window_days=55)
```

`tests/evals/backtest/test_significance.py`：

```python
from evals.backtest.significance import block_length_sensitivity, validate_sanity


class TestSanityGate:
    def test_high_sharpe_without_note_invalid(self):
        assert validate_sanity(3.5, None) == "invalid"

    def test_high_sharpe_with_note_valid(self):
        assert validate_sanity(3.5, "样本期 2019-2024 横跨牛熊；MDD 18%；月度换手") == "valid"

    def test_normal_sharpe_valid_without_note(self):
        assert validate_sanity(1.2, None) == "valid"


class TestSensitivity:
    def test_reports_multiple_block_lengths(self):
        returns = [0.001 * ((i % 9) - 4) + 0.0015 for i in range(200)]
        out = block_length_sensitivity(returns, B=300, seed=1)
        assert set(out) == {"10", "20", "40"}
        for ci in out.values():
            assert ci[0] <= ci[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/backtest -v`
Expected: FAIL — 新模块 `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`evals/backtest/performance.py`：

```python
"""绩效四指标：CR / ARR / Sharpe / MDD（TradingAgents 指标选型）。rf=0、252 交易日。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from evals.stats import sharpe as _sharpe


def perf_metrics(daily_returns: Sequence[float]) -> dict[str, float]:
    if not daily_returns:
        return {"CR": 0.0, "ARR": 0.0, "Sharpe": 0.0, "MDD": 0.0}
    wealth = 1.0
    peak = 1.0
    mdd = 0.0
    for r in daily_returns:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        mdd = max(mdd, (peak - wealth) / peak)
    cr = wealth - 1.0
    n = len(daily_returns)
    arr = (wealth) ** (252 / n) - 1 if wealth > 0 else -1.0
    return {
        "CR": round(cr, 6),
        "ARR": round(arr, 6),
        "Sharpe": round(_sharpe(daily_returns), 4),
        "MDD": round(mdd, 6),
    }
```

`evals/backtest/baselines.py`：

```python
"""规则基线：Buy-and-Hold / MACD / KDJ / RSI（复用 metrics/technical.py，不另造指标）。"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from finance_agent.metrics.technical import calc_technical

Strategy = Literal["buy_hold", "macd", "kdj", "rsi"]


def baseline_positions(kline: pd.DataFrame, strategy: Strategy) -> pd.Series:
    """返回逐日仓位（1=持仓, 0=空仓），长度与 kline 相同。"""
    n = len(kline)
    if strategy == "buy_hold":
        return pd.Series(1, index=kline.index)
    tech = calc_technical(kline)
    if strategy == "macd":
        dif = pd.Series(tech["MACD"]["DIF"], dtype=float)
        dea = pd.Series(tech["MACD"]["DEA"], dtype=float)
        raw = (dif > dea).astype(float)
    elif strategy == "kdj":
        k = pd.Series(tech["KDJ"]["K"], dtype=float)
        d = pd.Series(tech["KDJ"]["D"], dtype=float)
        raw = (k > d).astype(float)
    elif strategy == "rsi":
        rsi = pd.Series(tech["RSI"]["6"], dtype=float)
        raw = pd.Series(np.nan, index=range(n))
        position = 0.0
        values: list[float] = []
        for v in rsi:
            if pd.notna(v):
                if v < 30:
                    position = 1.0
                elif v > 70:
                    position = 0.0
            values.append(position)
        raw = pd.Series(values, dtype=float)
    else:
        raise ValueError(f"未知基线策略: {strategy}")
    positions = raw.fillna(0.0)
    return positions.reset_index(drop=True)


def strategy_returns(kline: pd.DataFrame, positions: pd.Series) -> list[float]:
    """日收益 = 前一日仓位 × 当日涨跌（T-1 信号 T 生效，无前视）。"""
    close = kline["收盘"].astype(float).reset_index(drop=True)
    pct = close.pct_change().fillna(0.0)
    prev_pos = positions.shift(1).fillna(0.0)
    return list((prev_pos * pct)[1:])
```

`evals/backtest/sampling.py`：

```python
"""分层市场状态抽样（spec decision-backtest「分层市场状态抽样」）。

regime 判定：窗口内基准指数总涨跌幅（> +10% bull / < -10% bear / 其间 sideways）。
每 regime ≥ per_regime 只标的；缺 regime 直接抛错（禁止单边行情汇报）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

UP_THRESHOLD = 0.10
DOWN_THRESHOLD = -0.10


def classify_regime(
    window_kline: pd.DataFrame,
    *,
    up_threshold: float = UP_THRESHOLD,
    down_threshold: float = DOWN_THRESHOLD,
) -> str:
    close = window_kline["收盘"].astype(float)
    if close.empty:
        raise ValueError("空窗口")
    total = close.iloc[-1] / close.iloc[0] - 1.0
    if total > up_threshold:
        return "bull"
    if total < down_threshold:
        return "bear"
    return "sideways"


def stratified_sample(
    index_kline: pd.DataFrame,
    stock_pool: list[str],
    *,
    per_regime: int = 10,
    window_days: int = 120,
    seed: int = 42,
) -> list[dict]:
    """滑窗扫描指数历史找三种 regime 窗口；每 regime 抽 per_regime 只标的 +
    决策日（窗口末日）。样本不足抛 ValueError。"""
    dates = index_kline["日期"].astype(str).str[:10]
    n = len(index_kline)
    rng = np.random.default_rng(seed)
    found: dict[str, dict] = {}  # regime → {"end_idx", "decision_date"}
    step = max(1, window_days // 4)
    for end in range(window_days, n + 1, step):
        window = index_kline.iloc[end - window_days : end]
        regime = classify_regime(window)
        if regime not in found:
            found[regime] = {"end_idx": end, "decision_date": str(dates.iloc[end - 1])}
        if len(found) == 3:
            break
    missing = {"bull", "bear", "sideways"} - set(found)
    if missing:
        raise ValueError(f"指数历史未覆盖 regime: {sorted(missing)}（禁止只在单边行情上汇报）")
    sample: list[dict] = []
    for regime, info in found.items():
        if len(stock_pool) < per_regime:
            raise ValueError(f"regime {regime} 标的池不足 {per_regime}")
        chosen = list(rng.choice(stock_pool, size=per_regime, replace=False))
        for code in chosen:
            sample.append({"code": str(code), "regime": regime, "decision_date": info["decision_date"]})
    return sample
```

`evals/backtest/significance.py`：

```python
"""block bootstrap 显著性 + 夏普异常拦截（spec「统计显著性与不确定性报告」）。"""

from __future__ import annotations

from collections.abc import Sequence

from evals.stats import block_bootstrap_stat, sharpe

SANITY_SHARPE_LIMIT = 3.0


def validate_sanity(sharpe_value: float, sanity_note: str | None) -> str:
    """Sharpe > 3 的批次必须附 sanity check 说明（样本期/回撤/换手），否则无效。"""
    if sharpe_value > SANITY_SHARPE_LIMIT and not (sanity_note and sanity_note.strip()):
        return "invalid"
    return "valid"


def block_length_sensitivity(
    returns: Sequence[float],
    *,
    blocks: tuple[int, ...] = (10, 20, 40),
    B: int = 1_000,
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """块长敏感性：多块长下 Sharpe CI 并排披露（契约要求附说明）。"""
    return {
        str(b): block_bootstrap_stat(returns, sharpe, block_size=b, B=B, seed=seed)
        for b in blocks
    }
```

`evals/backtest/run_backtest.py`：

```python
"""回测编排 CLI（人工触发；LLM 消耗 ≈ 股数 × 3 次回放）。

流程：分层抽样 → 逐样本 replay_with_consistency（n=3）→ 结算收益序列 →
绩效四指标 + 基线对照 + block bootstrap Sharpe CI + 一致性披露 →
reports/backtest/<name>.json。一致率 < 2/3 的标的不进绩效汇总，单独披露。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from evals.backtest.baselines import baseline_positions, strategy_returns
from evals.backtest.performance import perf_metrics
from evals.backtest.replay import replay_with_consistency
from evals.backtest.sampling import stratified_sample
from evals.backtest.significance import block_length_sensitivity, validate_sanity
from evals.stats import paired_block_bootstrap_diff

CONSISTENCY_FLOOR = 2 / 3


def _trade_daily_returns(result: dict, kline: pd.DataFrame) -> list[float]:
    """单笔回放结果（Task 9 replay 返回：settlement + entry_price + action +
    decision_date）→ 持有期日收益序列（entry=决策日收盘，exit=结算价）。

    近似：持有期内按逐日收盘 pct_change，末日修正到结算价；
    方法在报告 metadata.methodology 披露。
    """
    settlement = result.get("settlement") or {}
    entry = float(result.get("entry_price") or 0.0)
    if not settlement or entry <= 0:
        return []
    dates = kline["日期"].astype(str).str[:10]
    start = str(result.get("decision_date", ""))[:10]
    end = str(settlement.get("settle_date", ""))[:10]
    window = kline[(dates > start) & (dates <= end)]
    if window.empty:
        return []
    closes = [entry, *window["收盘"].astype(float).tolist()]
    if settlement.get("settle_price") is not None:
        closes[-1] = float(settlement["settle_price"])
    sign = 1.0 if result.get("action") == "buy" else -1.0
    return [sign * (closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes))]


def run_backtest(
    sample: list[dict],
    klines: dict[str, pd.DataFrame],
    benchmark_kline: pd.DataFrame | None = None,
    *,
    repeats: int = 3,
    sanity_note: str | None = None,
    replay_fn=replay_with_consistency,
) -> dict:
    results: list[dict] = []
    for item in sample:
        code, decision_date = item["code"], item["decision_date"]
        outcome = replay_fn(code, decision_date, n=repeats,
                            full_kline=klines.get(code))
        results.append({**item, **outcome})
    consistent = [r for r in results if r["agreement"] >= CONSISTENCY_FLOOR]
    excluded = [
        {"code": r["code"], "regime": r["regime"], "agreement": r["agreement"], "actions": r["actions"]}
        for r in results if r["agreement"] < CONSISTENCY_FLOOR
    ]
    system_returns: list[float] = []
    baseline_returns: dict[str, list[float]] = {s: [] for s in ("buy_hold", "macd", "kdj", "rsi")}
    for r in consistent:
        kline = klines.get(r["code"])
        if kline is None:
            continue
        system_returns.extend(_trade_daily_returns(r, kline))
        for strat in baseline_returns:
            baseline_returns[strat].extend(
                strategy_returns(kline, baseline_positions(kline, strat))  # type: ignore[arg-type]
            )
    system_perf = perf_metrics(system_returns)
    sanity = validate_sanity(system_perf["Sharpe"], sanity_note)

    table: dict[str, Any] = {"system": system_perf}
    for strat, rets in baseline_returns.items():
        table[strat] = perf_metrics(rets)
    best_baseline = max(
        ("buy_hold", "macd", "kdj", "rsi"),
        key=lambda s: table[s]["Sharpe"],
    )
    base_returns = baseline_returns[best_baseline]
    sharpe_ci = None
    if system_returns and base_returns:
        # 两条序列按前 min 长度截齐（起点对齐：均为样本期首日起的日收益序列）
        m = min(len(system_returns), len(base_returns))
        sharpe_ci = paired_block_bootstrap_diff(
            system_returns[:m], base_returns[:m], B=1_000, seed=42
        )
    by_regime: dict[str, Any] = {}
    for regime in {r["regime"] for r in consistent}:
        regime_returns = [
            ret for r in consistent if r["regime"] == regime
            for ret in _trade_daily_returns(r, klines[r["code"]])
        ]
        by_regime[regime] = perf_metrics(regime_returns)

    conclusion = (
        "无显著差异" if sharpe_ci and sharpe_ci[0] <= 0 <= sharpe_ci[1]
        else ("显著优于基线" if sharpe_ci and sharpe_ci[0] > 0 else "样本不足，无法判定")
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_sample": len(sample),
        "n_consistent": len(consistent),
        "consistency": {
            "mean_agreement": round(sum(r["agreement"] for r in results) / len(results), 4) if results else None,
            "excluded_low_consistency": excluded,
        },
        "perf_table": table,
        "best_baseline": best_baseline,
        "sharpe_excess_ci": sharpe_ci and (round(sharpe_ci[0], 4), round(sharpe_ci[1], 4)),
        "conclusion": conclusion if sanity == "valid" else "invalid: Sharpe>3 未附 sanity check 说明",
        "sanity": sanity,
        "block_length_sensitivity": (
            block_length_sensitivity(system_returns, B=1_000, seed=42) if system_returns else None
        ),
        "perf_by_regime": by_regime,
        "methodology": {
            "entry": "决策日收盘；结算自 T+1 行起评（复用 outcome.settle 语义）",
            "daily_returns": "单笔结算收益摊到持有期逐日；基线为 T-1 信号 T 生效的逐日仓位收益",
            "benchmark": "BENCHMARK_CODE 默认 000300（沿 decision-outcome 默认，待 ADR 确认）",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="decision-backtest 离线回放")
    parser.add_argument("--codes", nargs="+", required=True, help="标的池（分层抽样输入）")
    parser.add_argument("--per-regime", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--sanity-note", default=None)
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()
    from finance_agent.data.akshare_client import AKShareClient

    client = AKShareClient()
    index_kline = client.fetch_index_kline("000300", days=1500)
    sample = stratified_sample(index_kline, args.codes, per_regime=args.per_regime)
    klines = {code: client.fetch_kline(code, days=1500) for code in args.codes}
    report = run_backtest(sample, klines, repeats=args.repeats, sanity_note=args.sanity_note)
    out_dir = Path("reports/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"backtest-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"回测报告已写入 {path}")


if __name__ == "__main__":
    main()
```

实现时注意：`_trade_daily_returns` 消费 Task 9 `replay_with_consistency` 返回 dict（含 `settlement` / `entry_price` / `action` / `decision_date`）；`paired_block_bootstrap_diff` 要求系统与基线收益序列等长——实现时对两者取 `min(len)` 截齐并在报告 metadata 记录截断，避免长度不等时静默跳过 CI。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/backtest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/backtest tests/evals/backtest
git commit -m "feat(evals): 回测绩效四指标/规则基线/分层抽样/block bootstrap 显著性与编排 (harden-evaluation-rigor)"
```

---

### Task 11: 全量验证 + tasks.md 回填

**Files:**
- Modify: `openspec/changes/harden-evaluation-rigor/tasks.md`
- Create: `tests/validation/2026-08-27-harden-evaluation-rigor-verification.md`

**Interfaces:** 无代码；验证 + 回填。

- [ ] **Step 1: 全量门禁**

```bash
uv run pytest
uv run ruff check
uv run mypy
```
Expected: 三个命令全绿（0 failed / 无 error）。任何失败 → 修复后重跑，禁止跳过。

- [ ] **Step 2: 契约对照自查**

逐条对照 delta spec 三个 spec.md 的 Requirement/Scenario 与实现：
- citation-verification：注册表 7 根键 fixture 测试、未注册→UNVERIFIABLE+缺口计数、ratio Score、突升告警
- evaluation：基准集 schema/κ、准度 P/R/F1+CI+门禁+子集披露、对比 bootstrap+措辞约束、消融三变体对齐
- decision-backtest：时点截断、快照审计、四指标+基线、分层抽样、block bootstrap+敏感性、Sharpe>3 拦截、一致性、结算复用

- [ ] **Step 3: 回填 tasks.md**

勾选已完成验收项（人工 ADR、人工双人标注等前置项保持未勾，注明待人工）。

- [ ] **Step 4: 写验证记录并提交**

`tests/validation/2026-08-27-harden-evaluation-rigor-verification.md`（记录三条门禁命令输出摘要 + 契约对照结论 + 待人工事项）。

```bash
git add openspec/changes/harden-evaluation-rigor/tasks.md tests/validation/2026-08-27-harden-evaluation-rigor-verification.md
git commit -m "docs(harden-evaluation-rigor): tasks 回填 + 验证记录"
```
