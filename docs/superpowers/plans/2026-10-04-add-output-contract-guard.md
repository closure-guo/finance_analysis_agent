# add-output-contract-guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯文本交付物（研究聚焦摘要等）嵌入前过确定性输出校验——泄露独白/截断/空正文不得进交付物；verdict 进 Langfuse 观测。

**Architecture:** 三层分工——`output_guard.py` 纯函数校验器（判定）；`complete_text` 增加 opt-in `output_guard` 参数（把 verdict + finish_reason/resume_count 写进观测 metadata，遥测层）；`report.py._build_focus_summary` 调用侧决策（违约定向重试 1 次 → 结构化兜底），并删除 raw_reasoning 交付回退。网关请求路径与 resume 机制不动。

**Tech Stack:** Python 3.12 / pytest / monkeypatch（`litellm_adapter.raw_completion` / `langfuse_tracing.get_langfuse`）/ ruff / mypy

## Global Constraints

- 工作目录：`.worktrees/add-output-contract-guard`（分支 `add-output-contract-guard`）。**禁止在主检出切分支**（主检出被并发会话使用）
- commit 格式：`feat(<scope>): <中文描述> (add-output-contract-guard)`；禁止 merge commit
- 每个任务收尾 `uv run ruff check` 与 `uv run mypy` 必须绿
- 测试不触网：gateway 测试 monkeypatch `finance_agent.llm.adapters.litellm_adapter.raw_completion`，报告节点测试 `patch.object(report_mod, "complete_text")`
- 不改 `src/finance_agent/prompts/`（重试强化指令是代码内 system 拼接，非 Langfuse prompt，无需 deploy_prompts）
- 注释风格对齐现有代码（中文、说明契约来源），不做计划外的"顺手改"
- 校验基准样本：泄露样本=incident 036 实测（`reports/拓荆科技_688072_20261004_171013_report.md` 研究聚焦段）；干净反例=`reports/中远海能_600026_20261004_144914_report.md` 研究聚焦段

---

### Task 1: output_guard 校验器

**Files:**
- Create: `src/finance_agent/llm/output_guard.py`
- Test: `tests/llm/test_output_guard.py`

**Interfaces:**
- Consumes: 无（纯函数，零依赖）
- Produces: `GuardVerdict`（dataclass：`ok: bool`、`reason: str | None`、`hits: list[str]`）；`validate_deliverable_text(text: str | None, *, target_lang: str = "zh", finish_reason: str | None = None) -> GuardVerdict`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_output_guard.py
"""纯文本交付物输出合同校验器（delta add-output-contract-guard / incident 036）。"""

from __future__ import annotations

from finance_agent.llm.output_guard import validate_deliverable_text

# incident 036 实测泄露样本（拓荆 171013 报告研究聚焦段，节选）
_LEAKED_036 = (
    "The user wants a 150-200 character (Chinese characters) research focus summary "
    "for 拓荆科技 (Piotech), synthesizing the analysis outputs. Key points to weave in:\n\n"
    "- Rating: 中性 (0.50 confidence), watch decision\n\n"
    "Important constraint: cite financial data with latest disclosed period.\n\n"
    "Draft:\n\n"
    "“综合裁决为中性（置信度0.50），交易决策维持watch观望。多空优势错位于时间维度……PE_ttm 85."
)

# 干净反例（中远海能 2026-10-04 14:49 报告研究聚焦段，节选）
_CLEAN_ZH = (
    "中远海能多空证据大体均衡，给予中性评级（置信度0.55-0.6），维持观望。核心支撑在于："
    "油运高景气推动2026H1归母净利同比+143%，中期技术趋势完好（MA20较MA60高15%），"
    "PE_ttm约16.76倍估值不算贵。业绩利好已兑现后进入催化真空期，建议等待数据确认后再择向。"
)


def test_leaked_036_sample_rejected():
    v = validate_deliverable_text(_LEAKED_036)
    assert v.ok is False
    assert "leak:the_user_wants" in v.hits
    assert "leak:draft_marker" in v.hits
    assert "truncated:tail" in v.hits  # 「PE_ttm 85.」句中悬空


def test_clean_zh_sample_passes():
    v = validate_deliverable_text(_CLEAN_ZH)
    assert v.ok is True, f"干净样本被误伤: hits={v.hits}"
    assert v.hits == []


def test_finish_reason_length_forces_truncated():
    v = validate_deliverable_text(_CLEAN_ZH, finish_reason="length")
    assert v.ok is False
    assert "truncated:length" in v.hits


def test_tail_heuristic_catches_mid_sentence_cut():
    v = validate_deliverable_text("拓荆科技维持观望，现价对应PE_ttm 85.")
    assert v.ok is False
    assert "truncated:tail" in v.hits


def test_english_only_rejected_by_lang_ratio():
    v = validate_deliverable_text("Piotech is a semiconductor equipment company with strong growth.")
    assert v.ok is False
    assert "leak:lang_ratio" in v.hits


def test_empty_text_rejected():
    v = validate_deliverable_text("")
    assert v.ok is False
    assert v.reason == "empty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_output_guard.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'finance_agent.llm.output_guard'`）

- [ ] **Step 3: Write minimal implementation**

```python
# src/finance_agent/llm/output_guard.py
"""纯文本交付物输出合同校验器（delta add-output-contract-guard）。

凡 LLM 文本直接进入用户可见交付物（报告章节、研究聚焦摘要等）的路径，
嵌入前 MUST 经本校验：泄露检测（任务独白标记、非目标语言占比）、
截断检测（finish_reason=length 或句中悬空收尾）。
判定违约由调用方定向重试，重试仍违约回退结构化兜底（spec «纯文本交付物输出合同»）。
规则以 incident 036 实测泄露样本为基准、中远海能 2026-10-04 14:49 干净样本
为反例双向校准（误伤干净输出视为校验器缺陷）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 任务独白泄露模式（incident 036 实测；锚定行首/固定短语，降低误伤）
_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    ("leak:the_user_wants", re.compile(r"The user wants", re.IGNORECASE)),
    ("leak:draft_marker", re.compile(r"^\s*Draft\s*:", re.MULTILINE)),
    ("leak:key_points_marker", re.compile(r"Key points to weave in", re.IGNORECASE)),
    ("leak:important_constraint", re.compile(r"Important constraint\s*:", re.IGNORECASE)),
    ("leak:let_me", re.compile(r"^\s*(?:Let me|I'll|I will|I need to)\b", re.MULTILINE)),
)

# 句中悬空收尾（截断启发式；finish_reason 缺失时的兜底信号）
_TRUNCATED_TAIL = re.compile(r"(?:[0-9]+\.$|[,，、；;：:（(]$)")

# 中文交付物最低中文字符占比（对 CJK+拉丁字母总数；容忍 PE_ttm/MACD 等术语）
_ZH_RATIO_MIN = 0.6

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass
class GuardVerdict:
    """校验判定（进 trace metadata，spec «判定结果可观测»）。"""

    ok: bool
    reason: str | None = None
    hits: list[str] = field(default_factory=list)


def validate_deliverable_text(
    text: str | None,
    *,
    target_lang: str = "zh",
    finish_reason: str | None = None,
) -> GuardVerdict:
    """校验 LLM 文本能否直接嵌入交付物。不抛错，返回判定由调用方处置。"""
    if not text or not text.strip():
        return GuardVerdict(ok=False, reason="empty", hits=["empty"])

    hits: list[str] = []
    if finish_reason == "length":
        hits.append("truncated:length")

    for name, pat in _LEAK_PATTERNS:
        if pat.search(text):
            hits.append(name)

    if target_lang == "zh":
        cjk = len(_CJK.findall(text))
        latin = len(_LATIN.findall(text))
        if cjk + latin > 0 and cjk / (cjk + latin) < _ZH_RATIO_MIN:
            hits.append("leak:lang_ratio")

    if "truncated:length" not in hits and _TRUNCATED_TAIL.search(text.rstrip()):
        hits.append("truncated:tail")

    if not hits:
        return GuardVerdict(ok=True)
    return GuardVerdict(ok=False, reason=hits[0], hits=hits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_output_guard.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Lint + 类型检查 + Commit**

```bash
uv run ruff check && uv run mypy
git add src/finance_agent/llm/output_guard.py tests/llm/test_output_guard.py
git commit -m "feat(llm): 纯文本交付物输出合同校验器 output_guard (add-output-contract-guard)"
```

---

### Task 2: complete_text guard 观测通道

**Files:**
- Modify: `src/finance_agent/llm/gateway.py:220-376`（`complete_text` 签名与返回路径）
- Test: `tests/llm/test_gateway_guard.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `validate_deliverable_text(text, *, target_lang, finish_reason) -> GuardVerdict`
- Produces: `complete_text(..., output_guard: dict[str, Any] | None = None)`；当传 `output_guard` 时返回 metadata 附 `guard: {"ok": bool, "reason": str|None, "hits": list[str]}`；Langfuse 观测 metadata 携带 `finish_reason` / `resume_count` / `guard`。注意：**决策不依赖 metadata["guard"]**（Task 3 调用侧自行校验），gateway 侧 guard 仅承担遥测职责

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_gateway_guard.py
"""complete_text 纯文本交付物 guard 契约（delta add-output-contract-guard）。"""

from __future__ import annotations

from types import SimpleNamespace

from finance_agent.llm.gateway import complete_text

_LEAKED = (
    "The user wants a 150-200 character research focus summary for 拓荆科技.\n\n"
    "Key points to weave in:\n\nDraft:\n\n“综合裁决为中性……PE_ttm 85."
)
_LLM_CFG = {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"}


def _fake_completion(content: str, finish_reason: str = "stop"):
    def fake(**kwargs):  # noqa: ARG001
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, reasoning_content=None),
                    finish_reason=finish_reason,
                )
            ],
            usage=None,
        )

    return fake


def test_guard_pass_clean_text(monkeypatch):
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("中远海能多空证据大体均衡，给予中性评级，维持观望。"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
    )
    assert meta["guard"]["ok"] is True
    assert meta["finish_reason"] == "stop"


def test_guard_flags_leak(monkeypatch):
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion(_LEAKED),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
    )
    assert meta["guard"]["ok"] is False
    assert "leak:the_user_wants" in meta["guard"]["hits"]


def test_guard_flags_length_finish(monkeypatch):
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("完全合规的中文摘要，以句号收尾。", finish_reason="length"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
    )
    assert meta["guard"]["ok"] is False
    assert "truncated:length" in meta["guard"]["hits"]


def test_no_guard_param_no_guard_key(monkeypatch):
    """向后兼容：不传 output_guard 时返回 metadata 无 guard 键。"""
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("干净的中文摘要。"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}], purpose="quick", llm_config=_LLM_CFG
    )
    assert "guard" not in meta


def test_observation_metadata_carries_finish_reason_and_guard(monkeypatch):
    """spec «判定结果可观测»：观测 metadata 落 finish_reason/resume_count/guard。"""
    updates = []

    class _FakeObs:
        def update(self, **kw):
            updates.append(kw)

    class _FakeCM:
        def __enter__(self):
            return _FakeObs()

        def __exit__(self, *a):
            return False

    class _FakeLF:
        def start_as_current_observation(self, **kw):  # noqa: ARG002
            return _FakeCM()

    monkeypatch.setattr("finance_agent.langfuse_tracing.get_langfuse", lambda: _FakeLF())
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion(_LEAKED),
    )
    complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
        trace={"name": "report", "metadata": {"agent": "report"}},
    )
    metas = [u["metadata"] for u in updates if "metadata" in u]
    last = metas[-1]
    assert last["finish_reason"] == "stop"
    assert last["resume_count"] == 0
    assert last["guard"]["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_gateway_guard.py -v`
Expected: FAIL（`TypeError: complete_text() got an unexpected keyword argument 'output_guard'`）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/llm/gateway.py` 三处改动：

3a. 签名（`trace` 参数后新增）：

```python
    trace: dict[str, Any] | None = None,
    output_guard: dict[str, Any] | None = None,
    timeout_seconds: float = 300.0,
```

3b. docstring 补一句（放在断点续写说明之后）：

```
    ``output_guard``（可选）：纯文本交付物输出合同（delta add-output-contract-guard）。
    传 ``{"target_lang": "zh"}`` 时对 content 执行泄露/截断校验，判定落返回
    metadata ``guard`` 与观测 metadata（仅遥测；处置决策在调用侧）。
```

3c. 返回路径（`_finalize_observation` 调用前插入 verdict 计算，替换原调用与 return 段，约 gateway.py:352-376）：

```python
    guard_verdict: dict[str, Any] | None = None
    if output_guard is not None:
        from finance_agent.llm.output_guard import validate_deliverable_text

        _v = validate_deliverable_text(
            raw_content,
            target_lang=output_guard.get("target_lang", "zh"),
            finish_reason=resp.choices[0].finish_reason,
        )
        guard_verdict = {"ok": _v.ok, "reason": _v.reason, "hits": _v.hits}
    # 观测 metadata 补 finish_reason/resume_count/guard（incident 036 遥测缺口：
    # 此前仅调用方 trace metadata 入观测，截断归因无从查起）
    _obs_meta: dict[str, Any] = dict((trace or {}).get("metadata") or {})
    _obs_meta["finish_reason"] = resp.choices[0].finish_reason
    _obs_meta["resume_count"] = 1 if _resumed else 0
    if guard_verdict is not None:
        _obs_meta["guard"] = guard_verdict
    # Langfuse output.answer 与 legacy call_llm 对齐：content 为空时用
    # reasoning 作为 answer（legacy trace 行为），但返回 text 不做回退。
    _finalize_observation(
        _gen,
        raw_content or raw_reasoning,
        raw_reasoning,
        getattr(resp, "usage", None),
        metadata=_obs_meta,
    )
    _close_observation(_gen_cm)
    text = raw_content
    metadata = build_trace_metadata(
        profile,
        purpose=purpose,
        finish_reason=resp.choices[0].finish_reason,
        max_tokens_source="requested" if max_tokens is not None else "capability",
        # usage 真值存在时非估算（设计档案 §12：估算必须标 usage_estimated=true）
        usage_estimated=getattr(resp, "usage", None) is None,
    )
    metadata["raw_content"] = raw_content
    metadata["raw_reasoning"] = raw_reasoning
    if _resumed:
        # 续写成功可追溯：resume_count=1 落返回 metadata（与观测侧一致）
        metadata["resume_count"] = 1
    if guard_verdict is not None:
        metadata["guard"] = guard_verdict
    return text, metadata
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_gateway_guard.py tests/llm/test_gateway.py tests/llm/test_gateway_resume.py -v`
Expected: PASS（新 5 + 存量全绿——resume 分支的 `_gen.update` 被最终 `_finalize_observation` 覆盖，metadata 幂等）

- [ ] **Step 5: Lint + 类型检查 + Commit**

```bash
uv run ruff check && uv run mypy
git add src/finance_agent/llm/gateway.py tests/llm/test_gateway_guard.py
git commit -m "feat(llm): complete_text guard 观测通道——verdict/finish_reason/resume_count 进 trace (add-output-contract-guard)"
```

---

### Task 3: report.py 研究聚焦接入合同

**Files:**
- Modify: `src/finance_agent/nodes/report.py:284-347`（`_build_focus_summary`）
- Test: `tests/nodes/test_report_focus_guard.py`（新建）

**Interfaces:**
- Consumes: Task 1 `validate_deliverable_text`；既有 `complete_text`（现带 `output_guard` 参数）
- Produces: `_build_focus_summary(state, focus, focus_tags) -> str` 行为变更——违约重试 1 次、不再回退 raw_reasoning；签名不变（调用方 `report.py:406` 无感）

- [ ] **Step 1: Write the failing test**

```python
# tests/nodes/test_report_focus_guard.py
"""_build_focus_summary 输出合同集成（delta add-output-contract-guard）。"""

from __future__ import annotations

from unittest.mock import patch

from finance_agent.nodes import report as report_mod
from finance_agent.nodes.report import _build_focus_summary

_LEAKED = (
    "The user wants a 150-200 character research focus summary.\n\n"
    "Key points to weave in:\n\nDraft:\n\n“综合裁决为中性……PE_ttm 85."
)
_CLEAN = "拓荆科技多空证据均衡，给予中性评级（置信度0.50），维持观望，等待扣非口径验证后择向。"

_STATE = {
    "api_key": None,
    "stock_name": "拓荆科技",
    "analyst_reports": {"fundamental": {"summary": "基本面摘要"}},
    "research_manager_conclusion": "研究结论：中性",
    "final_trade_decision": {"action": "watch", "reasoning": "观望"},
    "llm_config": None,
}


def test_clean_first_call_passes_through():
    calls = []

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        calls.append(messages)
        return _CLEAN, {"finish_reason": "stop"}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert out == _CLEAN
    assert len(calls) == 1


def test_leak_triggers_retry_with_strengthened_instruction():
    calls = []

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        calls.append(messages)
        if len(calls) == 1:
            return _LEAKED, {"finish_reason": "stop"}
        return _CLEAN, {"finish_reason": "stop"}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert out == _CLEAN
    assert len(calls) == 2
    assert "禁止" in calls[1][0]["content"]  # 强化指令落在第二次的 system


def test_double_leak_falls_back_to_structured_join():
    calls = []

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        calls.append(messages)
        return _LEAKED, {"finish_reason": "stop"}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert out == "[fundamental] 基本面摘要"[:200]
    assert len(calls) == 2


def test_empty_content_with_reasoning_not_delivered():
    """raw_reasoning 回退坑关闭：content 空时不得把 reasoning 当交付文本。"""
    reasoning_text = "Let me think about the summary. I will write it now."

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        return "", {"finish_reason": "stop", "raw_reasoning": reasoning_text}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert reasoning_text not in out
    assert out == "[fundamental] 基本面摘要"[:200]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_report_focus_guard.py -v`
Expected: FAIL（泄露文本被直接返回 / raw_reasoning 被当交付 / 无重试）

- [ ] **Step 3: Write minimal implementation**

替换 `src/finance_agent/nodes/report.py:330-347`（`with contextlib.suppress(Exception):` 起到函数尾）：

```python
    def _call(system_extra: str = "") -> tuple[str, dict]:
        text, meta = complete_text(
            [
                {"role": "system", "content": system + system_extra},
                {"role": "user", "content": prompt},
            ],
            purpose="quick",
            max_tokens=400,
            temperature=0.3,
            llm_config=_request_config_dict(state.get("llm_config"), api_key),
            trace={"name": "report", "metadata": {"agent": "report"}},
            output_guard={"target_lang": "zh"},
        )
        return (text or "").strip(), meta

    from finance_agent.llm.output_guard import validate_deliverable_text

    with contextlib.suppress(Exception):
        resp, meta = _call()
        # 调用侧判定（gateway 侧 output_guard 仅承担观测遥测；决策语义在本层）
        if resp and validate_deliverable_text(
            resp, finish_reason=meta.get("finish_reason")
        ).ok:
            return resp
        # 违约（泄露/截断/空）→ 定向重试 1 次（incident 036：glm-5.3 间歇性
        # 把任务独白写进正文；强化指令禁止思考输出）
        retry_resp, retry_meta = _call(
            "\n\n重要：直接输出最终摘要文本。禁止输出任务理解、要点清单、"
            "约束重述、Draft 标记或任何思考过程；只输出面向读者的 150-200 字中文摘要。"
        )
        if retry_resp and validate_deliverable_text(
            retry_resp, finish_reason=retry_meta.get("finish_reason")
        ).ok:
            return retry_resp

    # 兜底：取首个分析师 summary 截断
    fallback = materials[0] if materials else ""
    return fallback[:200]
```

注意：**删除原 `resp = text or meta.get("raw_reasoning") or ""` 行**——raw_reasoning 回退坑（incident 036 根因 4）就此关闭；`from finance_agent.llm.output_guard import ...` 按本文件既有 import 风格可上移到模块头，实现者按 ruff 意见放置。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_report_focus_guard.py tests/nodes/test_report.py -v`
Expected: PASS（新 4 + 存量 test_report.py 全绿——既有 `test_focus_summary_from_llm_landed_in_state` 的 clean mock 走直通路径）

- [ ] **Step 5: Lint + 类型检查 + Commit**

```bash
uv run ruff check && uv run mypy
git add src/finance_agent/nodes/report.py tests/nodes/test_report_focus_guard.py
git commit -m "feat(report): 研究聚焦接入输出合同——泄露重试+结构化兜底, 关 raw_reasoning 回退 (add-output-contract-guard)"
```

---

### Task 4: 全量验证（verification-before-completion）

**Files:** 无新改动（纯验证）

- [ ] **Step 1: 定向回归**

Run: `uv run pytest tests/llm/ tests/nodes/test_report.py tests/nodes/test_report_focus_guard.py -q`
Expected: 全绿，0 failed

- [ ] **Step 2: Lint + 类型**

Run: `uv run ruff check && uv run mypy`
Expected: 双绿

- [ ] **Step 3: 汇报**

汇报真实输出（通过数/失败数），不做无证据的完成声称。人工验证（真实跑拓荆分析核对研究聚焦段）+ sync + archive 由 owner 决策后进行，不在本计划范围。
