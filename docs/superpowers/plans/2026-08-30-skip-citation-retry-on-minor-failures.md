# Skip Citation Retry on Minor Failures — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单轮引用校验失败轻微（FAIL ≤ 1 且失败率 ≤ 5%）时直接放行渲染，不触发分析师全量重跑（消 incident 020 遗留 #1；验证数据：汉森/茅台 1/46=2.2% FAIL 仍重跑 1-2 轮空转）。

**Architecture:** `citation_node.py` 计算 `citation_minor_fail` 布尔并落 trace 标记（复用既有 `update_current_span` 降级通道）；`routing.py::after_citation` 新增分支在轻微失败时直接 `render`。校验器与既有停滞降级/轮数上限（<3）语义不变。

**Tech Stack:** Python / LangGraph 路由纯函数 + 图节点。

## Global Constraints

- 校验器 `citation.py` 零改动；既有停滞降级（`citation_retry_stagnated`，失败率 ≥ 上轮 80%）与轮数上限（iteration_count < 3）行为不回归。
- FAIL 判定语义不变：`citation_pass=False` 仍算失败，仅「是否重试」路由变化；放行渲染不删改 claim。
- 降级/放行决策 SHALL 在 trace 观测留下可判读标记（spec citation-retry-policy）。
- 全量验证：`uv run pytest -m "not live"` / `uv run ruff check` / `uv run mypy`（本 delta 文件范围）。

---

### Task 1: after_citation 轻微失败放行（TDD）

**Files:**
- Modify: `src/finance_agent/routing.py`（`after_citation`，约 41-53 行）
- Test: `tests/test_routing.py`（TestAfterCitationDeescalation 类内新增）

**Interfaces:**
- Consumes: `state["citation_pass"]`、`state["citation_minor_fail"]`（Task 2 由 citation_node 写入）
- Produces: `after_citation(state) -> str`，轻微失败返回 `"render"`

- [ ] **Step 1: Write the failing test**

在 `tests/test_routing.py` 的 `TestAfterCitationDeescalation` 类内末尾追加：

```python
class TestAfterCitationMinorFail:
    """skip-citation-retry-on-minor-failures：FAIL≤1 且失败率≤5% 免重试。"""

    def test_minor_fail_returns_render(self):
        state = {
            "citation_pass": False,
            "citation_minor_fail": True,
            "iteration_count": 1,
            "citation_fail_rates": [0.022],
        }
        assert after_citation(state) == "render"

    def test_non_minor_fail_still_retries(self):
        state = {
            "citation_pass": False,
            "citation_minor_fail": False,
            "iteration_count": 1,
            "citation_fail_rates": [0.542],
        }
        assert after_citation(state) == "retry"

    def test_cap_still_enforced_with_minor_flag(self):
        """轮数上限优先：即使轻微失败标记为假但已达 3 轮仍渲染。"""
        state = {"citation_pass": False, "citation_minor_fail": False, "iteration_count": 3}
        assert after_citation(state) == "render"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_routing.py::TestAfterCitationMinorFail -v`
Expected: FAIL（`after_citation` 未识别 `citation_minor_fail`）

- [ ] **Step 3: Implement the routing branch**

`src/finance_agent/routing.py::after_citation` 首行判定改为：

```python
def after_citation(state: dict) -> str:
    """引用校验路由：PASS → 渲染，轻微失败（≤1 条且 ≤5%）→ 渲染，FAIL → 重试（最多 3 次）。"""
    if state.get("citation_pass", False) or state.get("citation_minor_fail", False):
        return "render"
    if state.get("iteration_count", 0) < 3:
        if citation_retry_stagnated(state.get("citation_fail_rates") or []):
            return "render"
        return "retry"
    return "render"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_routing.py -v`
Expected: PASS（新增用例 + 既有重试/停滞/上限用例不回归）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/routing.py tests/test_routing.py
git commit -m "feat(routing): citation 轻微失败（≤1 条且 ≤5%）直接放行渲染 — incident 020 遗留 #1"
```

### Task 2: citation_node 计算 minor_fail 标志并落 trace 标记（TDD）

**Files:**
- Modify: `src/finance_agent/nodes/citation_node.py`（`verify_citations`，约 37-60 行 + 返回值）
- Test: `tests/nodes/test_citation_node.py`（TestVerifyCitations 类内新增）

**Interfaces:**
- Consumes: `results`（list[CitationResult]）、`report`（CitationReport）、`fail_rates`（list[float]）
- Produces: state 返回字典新增 `"citation_minor_fail": bool`；轻微失败时 span 标记 `citation_minor_fail_deescalated`

- [ ] **Step 1: Write the failing test**

在 `tests/nodes/test_citation_node.py` 的 `TestVerifyCitations` 类内追加：

```python
    def test_minor_fail_sets_flag_and_marks_span(self, monkeypatch):
        """40 条中 1 条 FAIL（2.5% ≤ 5%）：设置 citation_minor_fail 并落 span 标记。"""
        from finance_agent.nodes import citation_node

        marks: list[dict] = []

        def fake_update_span(**kwargs):
            marks.append(kwargs)

        monkeypatch.setattr(citation_node, "update_current_span", fake_update_span)

        # 39 条与 gt 一致（PASS）+ 1 条 mismatch（FAIL）→ fail_count=1, rate=2.5%
        claims = [
            {
                "claim_type": "numerical",
                "source_type": "data",
                "field_ref": "macro_indicators.m2.0.货币和准货币(M2)-同比增长",
                "stated_value": 17.37 if i < 39 else 16.19,
                "interpretation": "",
            }
            for i in range(40)
        ]
        state = {
            "analyst_reports": {"technical": {
                "agent_name": "technical", "summary": "", "key_findings": [],
                "claims": claims, "markdown": "",
            }},
            "macro_indicators": {"m2": [{"货币和准货币(M2)-同比增长": 17.37}]},
        }
        result = citation_node.verify_citations(state)
        assert result["citation_minor_fail"] is True
        marked = [m for m in marks if m.get("metadata", {}).get("citation_minor_fail_deescalated")]
        assert marked, f"轻微失败须落 span 标记，实际 marks: {marks}"

    def test_many_fails_no_minor_flag(self, monkeypatch):
        """失败数/失败率超阈值（13 条全 FAIL，100%）不设 minor_fail。"""
        from finance_agent.nodes import citation_node

        monkeypatch.setattr(citation_node, "update_current_span", lambda **kw: None)
        claims = [
            {
                "claim_type": "numerical",
                "source_type": "data",
                "field_ref": "macro_indicators.m2.0.货币和准货币(M2)-同比增长",
                "stated_value": 16.19,
                "interpretation": "",
            }
            for _ in range(13)
        ]
        state = {
            "analyst_reports": {"technical": {
                "agent_name": "technical", "summary": "", "key_findings": [],
                "claims": claims, "markdown": "",
            }},
            "macro_indicators": {"m2": [{"货币和准货币(M2)-同比增长": 17.37}]},
        }
        result = citation_node.verify_citations(state)
        assert result["citation_minor_fail"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_citation_node.py::TestVerifyCitations -v`
Expected: FAIL（`citation_minor_fail` 键不存在）

- [ ] **Step 3: Implement the node flag**

`src/finance_agent/nodes/citation_node.py` 在既有 fail_rate/fail_rates 计算之后（约 42-53 行区域）插入：

```python
    minor_fail = (not report.all_passed) and fail_count <= 1 and fail_rate <= 0.05
    if minor_fail:
        # skip-citation-retry-on-minor-failures：单点/近零失败直接放行渲染，
        # 不重跑分析师（校验器确定性，同 claim 重跑必复现——incident 022 实测）
        update_current_span(
            metadata={
                "citation_minor_fail_deescalated": True,
                "fail_rates": fail_rates,
            },
            level="WARNING",
        )
```

并在 return 字典追加：

```python
    return {
        "citation_report": report.model_dump(),
        "citation_pass": report.all_passed,
        "iteration_count": iteration_count + 1,
        "citation_fail_rates": fail_rates,
        "citation_minor_fail": minor_fail,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_citation_node.py -v`
Expected: PASS（新增 2 用例 + 存量 14 用例不回归）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/citation_node.py tests/nodes/test_citation_node.py
git commit -m "feat(citation_node): minor_fail 标志 + trace 标记 — skip-citation-retry-on-minor-failures"
```

### Task 3: 全量门禁

**Files:**
- 无新代码；验证 + 回填 delta tasks.md

- [ ] **Step 1: 全量验证**

Run: `uv run pytest -m "not live" -q`
Expected: 全绿（存量 1511 基线 + 新增 5 用例）
Run: `uv run ruff check src/finance_agent/routing.py src/finance_agent/nodes/citation_node.py tests/test_routing.py tests/nodes/test_citation_node.py`
Expected: 全绿
Run: `uv run mypy src/finance_agent/routing.py src/finance_agent/nodes/citation_node.py`
Expected: 零错误

- [ ] **Step 2: 冒烟回归（live，可选人工）**

深跑 ≥1 只标的（如汉森制药），确认轻微失败场景 `citation_minor_fail=True` 且 iteration_count 保持 1（无重试轮）；验收数据回填 delta tasks.md（机器不可复现时标人工待办）。