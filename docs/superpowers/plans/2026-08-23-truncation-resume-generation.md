# 截断续写（llm-output-resume）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 gateway 三个 complete 入口实现「finish_reason=length 时发起断点续写（尾部+进度标注），续写仍截断则按 OutputTruncatedError 上抛」，消除 deep 长 JSON 节点全文重试浪费与 quick 异步路径静默截断。

**Architecture:** 续写是「新请求 + 已生成正文尾部/进度标注为上下文 + 剩余预算」而非「切分重排」。三个公共入口（`complete_text` / `complete_stream` / `complete_stream_async`）各自的 length 分支调共享 helper 构造续写请求；续写正文直接拼接前段，`finish_reason` 以续写段为准；观测 metadata 记 `resume_count`/`truncated`。

**Tech Stack:** Python 3.12+（`from __future__ import annotations`）、pydantic v2、litellm、pytest（monkeypatch mock raw_completion/raw_stream/raw_acompletion）、OpenSpec delta `truncation-resume-generation`。

## Global Constraints

- 测试统一放 `tests/llm/`，按 TDD「先红后绿」，mock 目标是 adapter 的 `raw_completion`/`raw_stream`/`raw_acompletion`（LLM 第三方可 stub，AGENTS.md 允许）。
- 不引入新依赖；续写 helper 放 `src/finance_agent/llm/adapters/litellm_adapter.py` 与 `src/finance_agent/llm/contracts.py`（与既有 `extract_json` 同族）。
- 续写预算 = `max(1, 原预算 - prior_text 估算消耗)`（D2），**不翻倍**；仅 1 轮续写，再截断即抛 `OutputTruncatedError`（D3）。
- 拼接 = 字符串**直接连接**，不插入分隔符、不裁剪任何一侧、不去重（spec 拼接契约）。
- 未截断路径零行为变化、零额外调用（gateway 现有 GeneratorExit 修复等未提交改动是本计划的基线，保留不动）。
- 续写指令统一一句话（design.md Open Q1 已决策），结构信息由进度标注承担。
- 进度标注只报「已闭合 N 条」，**不报目标总数**（`/5` 是模型预期，解析器无法得知，编造会污染续写）。
- 现有 `_llm_utils.py:266` 的 32768 翻倍重试**保留为 fallback**（design.md Migration Plan），本计划不改 `_llm_utils.py`。
- 提交规范：`feat(resume): ...` 小步提交；仅在用户要求时 push。

---

### Task 1: 续写请求构造器 `build_resume_kwargs`（litellm_adapter.py）

**Files:**
- Modify: `src/finance_agent/llm/adapters/litellm_adapter.py`（新增函数，放在 `derive_output_budget` 之后）
- Test: `tests/llm/test_gateway_resume.py`（新建）

**Interfaces:**
- Consumes: 无（纯函数，基于传入 request_kwargs 克隆）
- Produces: `build_resume_kwargs(request_kwargs: dict, prior_text: str, progress_annotation: str | None = None) -> dict` — Task 2/3/4 的续写请求构造入口；`progress_annotation` 非 None 时拼入续写指令段

- [ ] **Step 1: 写失败测试**

```python
# tests/llm/test_gateway_resume.py
"""gateway 截断续写（llm-output-resume delta Task 1-4）。

mock adapter raw_* 返回「前段 length + 续写 stop」双段流，验证续写
触发、拼接、预算派生、进度标注注入、再截断上抛。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.adapters.litellm_adapter import build_resume_kwargs
from finance_agent.llm.errors import OutputTruncatedError


def _estimate_tokens(text: str) -> int:
    # 与实现同源的估算：默认按 4 字符/token
    return max(1, len(text) // 4)


def test_build_resume_kwargs_appends_instruction_and_shrinks_budget():
    base = {"model": "glm-5.2", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 16384}
    out = build_resume_kwargs(base, prior_text="x" * 8000)
    assert out["model"] == "glm-5.2"
    assert out["messages"][-1]["role"] == "user"
    assert "续写" in out["messages"][-1]["content"]
    # 剩余配额：16384 - 8000/4 = 16384 - 2000 = 14384
    assert out["max_tokens"] == 16384 - _estimate_tokens("x" * 8000)
    # 其余 kwargs 保留
    assert out["messages"][0] == {"role": "user", "content": "hi"}


def test_build_resume_kwargs_floor_budget_at_1():
    base = {"model": "glm-5.2", "messages": [], "max_tokens": 10}
    out = build_resume_kwargs(base, prior_text="x" * 100000)
    assert out["max_tokens"] == 1


def test_build_resume_kwargs_injects_progress_annotation():
    base = {"model": "glm-5.2", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8192}
    ann = "- agent_name: ✅ 已完成\n- key_findings: ⏳ 已闭合 3 条"
    out = build_resume_kwargs(base, prior_text="x", progress_annotation=ann)
    assert ann in out["messages"][-1]["content"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`（build_resume_kwargs 不存在）

- [ ] **Step 3: 最小实现**

```python
# src/finance_agent/llm/adapters/litellm_adapter.py —— derive_output_budget 之后新增

_RESUME_INSTRUCTION = (
    "你正在续写一份分析报告，直接无缝继续输出剩余部分，"
    "不要重复以上已输出的内容。"
)


def _estimate_tokens(text: str) -> int:
    """正文 token 估算（续写预算派生用）：仅需近似值。"""
    return max(1, len(text) // 4)


def build_resume_kwargs(
    request_kwargs: dict[str, Any],
    prior_text: str,
    progress_annotation: str | None = None,
) -> dict[str, Any]:
    """构造断点续写请求 kwargs（delta Task 1.1，design D1/D2）。

    基于原 request_kwargs 深拷贝：messages 追加续写指令段（明确
    「不重复已给内容、无缝继续」，progress_annotation 非 None 时拼入
    进度标注），max_tokens 取剩余配额 max(1, 原预算 - prior_text 估算)。
    其余 key（model/api_key/endpoint/超时）原样保留。
    """
    out = dict(request_kwargs)
    out["messages"] = list(request_kwargs.get("messages", []))
    instruction = _RESUME_INSTRUCTION
    if progress_annotation:
        instruction = f"{progress_annotation}\n\n{instruction}"
    out["messages"] = out["messages"] + [{"role": "user", "content": instruction}]
    base_budget = int(request_kwargs.get("max_tokens") or 4096)
    out["max_tokens"] = max(1, base_budget - _estimate_tokens(prior_text))
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/llm/adapters/litellm_adapter.py tests/llm/test_gateway_resume.py
git commit -m "feat(resume): 续写请求构造器 build_resume_kwargs（尾部+进度标注+剩余预算）"
```

---

### Task 2: 部分解析器 `partial_json_progress`（contracts.py）

**Files:**
- Modify: `src/finance_agent/llm/contracts.py`（新增，放在 `extract_json` 同族）
- Test: `tests/llm/test_gateway_resume.py`（追加）

**Interfaces:**
- Consumes: 无
- Produces: `partial_json_progress(text: str, top_fields: list[str]) -> dict[str, str] | None` — 返回「字段名 → 状态」映射，状态 ∈ `{"done", "in_progress", "pending"}`，或 None（无法解析/非 JSON）。Task 3/4 用它生成 `progress_annotation` 字符串

- [ ] **Step 1: 写失败测试**

```python
# tests/llm/test_gateway_resume.py 追加

from finance_agent.llm.contracts import partial_json_progress

FIELDS = ["agent_name", "summary", "key_findings", "claims", "markdown"]


def test_partial_progress_field_midway():
    text = '{"agent_name": "technical", "summary": "ok", "key_findings": ["a", "b'
    prog = partial_json_progress(text, FIELDS)
    assert prog["agent_name"] == "done"
    assert prog["summary"] == "done"
    assert prog["key_findings"] == "in_progress"
    assert prog["claims"] == "pending"
    assert prog["markdown"] == "pending"


def test_partial_progress_array_element_midway():
    text = '{"agent_name": "macro", "summary": "s", "key_findings": ["a", "b',  # 同上但字段序
    # 数组断在元素中间 → key_findings in_progress
    prog = partial_json_progress(text, FIELDS)
    assert prog["key_findings"] == "in_progress"


def test_partial_progress_unrecoverable_returns_none():
    # 找不到 { 开始（纯文本）→ None
    assert partial_json_progress("分析完成，非 JSON", FIELDS) is None
    # 空文本 → None
    assert partial_json_progress("", FIELDS) is None


def test_partial_progress_complete_json_all_done():
    text = '{"agent_name": "x", "summary": "s", "key_findings": [], "claims": [], "markdown": "m"}'
    prog = partial_json_progress(text, FIELDS)
    assert set(prog.values()) == {"done"}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: FAIL with `ImportError`（partial_json_progress 不存在）

- [ ] **Step 3: 最小实现**

```python
# src/finance_agent/llm/contracts.py —— extract_json 附近新增

def partial_json_progress(text: str, top_fields: list[str]) -> dict[str, str] | None:
    """尽力部分解析已生成正文，标注各顶层字段进度（llm-output-resume Task 1.3）。

    返回 {字段名: "done" | "in_progress" | "pending"}：
    - done：对应顶层字段的值在文本中已完整闭合；
    - in_progress：正在书写但未闭合（括号栈顶所在字段）；
    - pending：schema 顶层字段中尚未出现（出现过的字段集合的补集）。
    文本不含 "{"（非 JSON/纯文本）或为空 → None（调用方降级仅尾部）。
    只报告已闭合数量级事实，不编造目标总数（"/5" 之类交付给续写指令）。
    """
    start = text.find("{")
    if start < 0:
        return None

    # 括号栈扫描：depth 记录嵌套深度，cur_field 记录当前值所属顶层字段
    stack: list[tuple[str, int]] = []      # (括号字符, 对应起始深度)
    done: set[str] = set()
    seen: set[str] = set()
    cur_field: str | None = None
    in_str = False
    escaped = False
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            # 粗略识别顶层 key："xxx": 且当前只在根对象一层
            # （简化：记录最近出现在 ":" 前的 token，交给下方判断）
            continue
        if ch in "{[":
            stack.append((ch, len(stack)))
            if len(stack) == 1 and cur_field:
                seen.add(cur_field)
        elif ch in "}]":
            if stack:
                stack.pop()
            if len(stack) == 0 and cur_field:
                # 根对象闭合 → 该字段值完整
                done.add(cur_field)
                cur_field = None
        elif ch == ":" and len(stack) == 1:
            # 扫描到顶层 key：往前取引号内 token
            key = _extract_key_around(text, i)
            if key:
                cur_field = key
                seen.add(key)

    # 兜底：栈非空 → 栈顶所在字段 in_progress
    in_prog: str | None = None
    if stack:
        in_prog = cur_field if cur_field is not None else (top_fields[0] if top_fields else None)

    result: dict[str, str] = {}
    for f in top_fields:
        if f in done:
            result[f] = "done"
        elif f == in_prog or (in_prog is None and f in seen and f not in done):
            result[f] = "in_progress"
        else:
            result[f] = "pending"
    return result


def _extract_key_around(text: str, colon_idx: int) -> str | None:
    """在 colon 前找最近一个闭合引号包裹的 token（即 JSON key）。"""
    end = text.rfind('"', 0, colon_idx)
    if end < 0:
        return None
    start = text.rfind('"', 0, end)
    if start < 0:
        return None
    return text[start + 1 : end]
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: PASS (全部通过)

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/llm/contracts.py tests/llm/test_gateway_resume.py
git commit -m "feat(resume): 部分 JSON 解析器 partial_json_progress（done/in_progress/pending）"
```

---

### Task 3: 进度标注字符串生成 + `_maybe_resume_text` 判定（gateway.py）

**Files:**
- Modify: `src/finance_agent/llm/gateway.py`（新增 `_maybe_resume_text`、`_build_progress_annotation`）
- Test: `tests/llm/test_gateway_resume.py`（追加）

**Interfaces:**
- Consumes: `build_resume_kwargs`（Task 1）、`partial_json_progress`（Task 2）
- Produces: `_maybe_resume_text(finish: str, answer: str) -> bool`（Task 4/5 判定续写）；`_build_progress_annotation(answer: str, top_fields: list[str] | None) -> str | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/llm/test_gateway_resume.py 追加

from finance_agent.llm.gateway import _build_progress_annotation, _maybe_resume_text


def test_maybe_resume_length_with_text():
    assert _maybe_resume_text("length", "已有正文") is True


def test_maybe_resume_length_empty_text():
    assert _maybe_resume_text("length", "") is False
    assert _maybe_resume_text("length", None) is False


def test_maybe_resume_stop_never():
    assert _maybe_resume_text("stop", "正文") is False
    assert _maybe_resume_text("tool_calls", "正文") is False


def test_build_progress_annotation_formats_markdown():
    ann = _build_progress_annotation(
        '{"agent_name": "technical", "key_findings": ["a"',
        ["agent_name", "summary", "key_findings"],
    )
    assert ann is not None
    assert "agent_name: ✅ 已完成" in ann
    assert "key_findings: ⏳" in ann
    assert "summary: ⬜ 未开始" in ann


def test_build_progress_annotation_none_for_plain_text():
    assert _build_progress_annotation("纯文本", ["agent_name"]) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 最小实现**

```python
# src/finance_agent/llm/gateway.py —— 模块级，build_trace_metadata 附近新增

def _maybe_resume_text(finish: str | None, answer: str | None) -> bool:
    """判定是否触发续写（llm-output-resume Task 1.2）：仅 finish=length 且正文非空。"""
    return finish == "length" and bool(answer)


_STATUS_ICON = {"done": "✅ 已完成", "in_progress": "⏳", "pending": "⬜ 未开始"}


def _build_progress_annotation(
    answer: str | None, top_fields: list[str] | None
) -> str | None:
    """从已生成正文 + 顶层字段清单生成进度标注文本；不可解析返回 None。

    只报「已闭合数量级」事实（in_progress 字段不附目标总数），
    交付给 build_resume_kwargs 的 progress_annotation。
    """
    from finance_agent.llm.contracts import partial_json_progress

    if not answer or not top_fields:
        return None
    prog = partial_json_progress(answer, top_fields)
    if prog is None:
        return None
    lines = ["当前输出进度："]
    for f in top_fields:
        state = prog.get(f, "pending")
        icon = _STATUS_ICON[state]
        if state == "in_progress":
            # 只报已闭合事实，不编造目标数量（"/5" 解析器无法得知）
            lines.append(f"- {f}: {icon} 断点位于已输出尾部")
        else:
            lines.append(f"- {f}: {icon}")
    return "\n".join(lines)
```

> 实现说明：in_progress 字段不附元素计数（只报「断点位于已输出尾部」），避免编造目标总数。TDD 断言只依赖图标与字段名，不依赖具体计数文本。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/llm/gateway.py tests/llm/test_gateway_resume.py
git commit -m "feat(resume): 续写判定 _maybe_resume_text + 进度标注生成 _build_progress_annotation"
```

---

### Task 4: `complete_stream`（同步流式）续写

**Files:**
- Modify: `src/finance_agent/llm/gateway.py:575-582`（length 分支拦截）
- Test: `tests/llm/test_gateway_resume.py`（追加）

**Interfaces:**
- Consumes: `_maybe_resume_text`、`_build_progress_annotation`、`build_resume_kwargs`、`raw_stream`
- Produces: 续写后事件流 `text…text…finished`（无 error 前插），再截断时 `error(OutputTruncatedError)` + `_gen.update(truncated=true)`

接线参数：`complete_stream` 与 `complete_stream_async` 各新增可选参数 `top_fields: list[str] | None = None`（调用方节点传入其 schema 顶层字段；None 则不做进度标注，仅尾部续写）。

- [ ] **Step 1: 写失败测试**

```python
# tests/llm/test_gateway_resume.py 追加

from finance_agent.llm.gateway import complete_stream


def _make_raw_stream(items):
    """把 chunk 列表包成可迭代的 raw_stream 返回值。"""
    from types import SimpleNamespace

    class _It:
        def __init__(self, items):
            self._items = list(items)

        def __iter__(self):
            return self

        def __next__(self):
            if self._items:
                return self._items.pop(0)
            raise StopIteration

    return _It(items)


def _chunk_sync(*, text="", reasoning="", finish=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(reasoning_content=reasoning or None, content=text or None),
                finish_reason=finish,
            )
        ]
    )


def test_complete_stream_resumes_after_length(monkeypatch):
    calls = []

    def fake_raw_stream(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            # 前段：length 截断
            return _make_raw_stream(
                [_chunk_sync(text="前半"), _chunk_sync(finish="length")]
            )
        # 续写段：stop 正常结束（断言带上尾部上下文）
        msgs = kwargs["messages"]
        assert msgs[-1]["role"] == "user"
        assert "续写" in msgs[-1]["content"]
        assert calls[0]["messages"][-1]["content"] not in msgs[-1]["content"]
        return _make_raw_stream([_chunk_sync(text="后半"), _chunk_sync(finish="stop")])

    monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_raw_stream)
    events = list(complete_stream([{"role": "user", "content": "hi"}]))
    texts = "".join(e.text for e in events if e.kind == "text")
    assert texts == "前半后半"
    assert events[-1].kind == "finished"
    assert events[-1].finish_reason == "stop"
    assert len(calls) == 2


def test_complete_stream_resume_sends_progress_annotation(monkeypatch):
    calls = []

    def fake_raw_stream(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _make_raw_stream([_chunk_sync(text="a"), _chunk_sync(finish="length")])
        assert "进度" in kwargs["messages"][-1]["content"] or "✅" in kwargs["messages"][-1]["content"]
        return _make_raw_stream([_chunk_sync(text="b"), _chunk_sync(finish="stop")])

    monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_raw_stream)
    events = list(
        complete_stream(
            [{"role": "user", "content": "hi"}],
            top_fields=["agent_name", "summary"],
        )
    )
    assert "".join(e.text for e in events if e.kind == "text") == "ab"


def test_complete_stream_resume_internal_error_when_truncated_again(monkeypatch):
    calls = []

    def fake_raw_stream(**kwargs):
        calls.append(kwargs)
        return _make_raw_stream([_chunk_sync(text="x"), _chunk_sync(finish="length")])

    monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_raw_stream)
    events = list(complete_stream([{"role": "user", "content": "hi"}]))
    assert events[-1].kind == "error"
    assert "OutputTruncated" in events[-1].finish_reason
    assert len(calls) == 2  # 精确：1 次原始 + 1 次续写，之后停止
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/llm/test_gateway_resume.py::test_complete_stream_resumes_after_length -v`
Expected: FAIL（当前 complete_stream 对 length 抛 error 事件，无续写）

- [ ] **Step 3: 最小实现**

修改 `complete_stream`：签名加 `top_fields`；在 `classify_outcome` 调用前插入续写分支。

```python
# gateway.py complete_stream —— 签名新增：
#     top_fields: list[str] | None = None,

# 在 finishing 循环结束后的 finish 分型处（原 try: classify_outcome(...) 附近）：
        _finish = finish
        if _maybe_resume_text(_finish, _answer):
            # 续写：构造新请求（尾部+进度标注），二次流式，事件直接续发
            from finance_agent.llm.adapters.litellm_adapter import build_resume_kwargs
            from finance_agent.llm.contracts import partial_json_progress
            from finance_agent.llm.errors import OutputTruncatedError

            ann = None
            if top_fields:
                prog = partial_json_progress(_answer, top_fields)
                if prog is not None:
                    ann = _build_progress_annotation(_answer, top_fields)
            resume_kwargs = build_resume_kwargs(
                request_kwargs, prior_text=_answer, progress_annotation=ann
            )
            try:
                stream2 = raw_stream(**resume_kwargs)
                _finish = None
                for chunk2 in stream2:
                    choice2 = chunk2.choices[0]
                    d2 = choice2.delta
                    if (
                        getattr(choice2, "finish_reason", None)
                        and getattr(choice2, "finish_reason", None) != _finish
                    ):
                        _finish = getattr(choice2, "finish_reason", None) or _finish
                    if d2 and getattr(d2, "reasoning_content", None):
                        _reasoning += str(d2.reasoning_content)
                    if d2 and getattr(d2, "content", None):
                        ct = str(d2.content)
                        _answer += ct
                        yield CanonicalEvent(kind="text", text=ct)
            except Exception as exc2:  # noqa: BLE001
                _finalize_observation(
                    _gen, _answer, _reasoning, _last_usage,
                    metadata=(trace or {}).get("metadata"),
                )
                err2 = normalize_exception(exc2)
                if _gen is not None:
                    from contextlib import suppress
                    with suppress(Exception):
                        _gen.update(
                            metadata={**((trace or {}).get("metadata") or {}),
                                      "truncated": True},
                            level="ERROR",
                        )
                yield CanonicalEvent(
                    kind="error", finish_reason=type(err2).__name__, raw={"error": str(err2)}
                )
                return
            # 续写段观测与收口
            if _gen is not None:
                from contextlib import suppress
                with suppress(Exception):
                    _gen.update(
                        metadata={**((trace or {}).get("metadata") or {}), "resume_count": 1}
                    )
            if _maybe_resume_text(_finish, _answer):
                # 续写仍截断：上抛（保留原错误类型），标记 truncated
                exc3 = OutputTruncatedError(
                    "续写仍 finish_reason=length：输出被截断（resume 上限 1）"
                )
                if _gen is not None:
                    with suppress(Exception):
                        _gen.update(
                            metadata={**((trace or {}).get("metadata") or {}),
                                      "resume_count": 1, "truncated": True},
                            level="ERROR",
                        )
                yield CanonicalEvent(
                    kind="error", finish_reason=type(exc3).__name__, raw={"error": str(exc3)}
                )
                return
            finish = _finish
        try:
            classify_outcome(finish, saw_text_delta=True if _answer else False)
        except Exception as exc:  # noqa: BLE001
            yield CanonicalEvent(
                kind="error", finish_reason=type(exc).__name__, raw={"error": str(exc)}
            )
            return
        yield CanonicalEvent(kind="finished", finish_reason=finish)
```

> 实现说明：续写分支插入在 `classify_outcome` 之前；正常路径（非 length）完全不变。续写内层循环与主循环共享 `_answer`/`_reasoning`/`_last_usage` 累积；续写结束的 `finished` 事件携带续写段的 finish_reason。观测：续写成功 `resume_count=1`，再截断补 `truncated=true`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/llm/test_gateway_resume.py -v`
Expected: PASS（含同步流 3 个新用例）

- [ ] **Step 5: 运行既有流式测试确认无回归**

Run: `uv run pytest tests/llm/test_gateway_stream.py tests/llm/test_gateway_stream_async.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/finance_agent/llm/gateway.py tests/llm/test_gateway_resume.py
git commit -m "feat(resume): complete_stream 同步流式断点续写（尾部+进度标注+再截断上抛）"
```

---

### Task 5: `complete_text`（非流式）与 `complete_stream_async`（异步流式）续写

**Files:**
- Modify: `src/finance_agent/llm/gateway.py:166-260`（complete_text length 分支）、`gateway.py:656-871`（complete_stream_async length 分支）
- Test: `tests/llm/test_gateway_resume.py`（追加）

**Interfaces:**
- Consumes: Task 1-4 的 helper
- Produces: 两入口相同的续写语义：length+非空正文 → 续写拼接；续写仍 length → 抛 `OutputTruncatedError`（`complete_text` 直接抛，`complete_stream_async` 以 error 事件 + 抛错）；异步路径同时修复「length 被静默当正常结束」缺陷

- [ ] **Step 1: 写失败测试**

```python
# tests/llm/test_gateway_resume.py 追加

from finance_agent.llm.gateway import complete_stream_async, complete_text


def test_complete_text_resumes_after_length(monkeypatch):
    from types import SimpleNamespace

    calls = []

    def fake_raw_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            msg = SimpleNamespace(content="前半", reasoning_content="")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg, finish_reason="length")],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )
        assert "续写" in kwargs["messages"][-1]["content"]
        msg = SimpleNamespace(content="后半", reasoning_content="")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion", fake_raw_completion
    )
    text, meta = complete_text([{"role": "user", "content": "hi"}])
    assert text == "前半后半"
    assert meta["resume_count"] == 1
    assert len(calls) == 2


def test_complete_text_resume_truncated_again_raises(monkeypatch):
    from types import SimpleNamespace

    def fake_raw_completion(**kwargs):
        msg = SimpleNamespace(content="x", reasoning_content="")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="length")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion", fake_raw_completion
    )
    with pytest.raises(OutputTruncatedError):
        complete_text([{"role": "user", "content": "hi"}], trace={"name": "t"})


def test_complete_stream_async_resumes_after_length(monkeypatch):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _AsyncIter(
                [_chunk(text="异步前", finish=None), _chunk(finish="length")]
            )
        assert "续写" in kwargs["messages"][-1]["content"]
        return _AsyncIter([_chunk(text="异步后", finish=None), _chunk(finish="stop")])

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    events = []
    async for ev in complete_stream_async([{"role": "user", "content": "hi"}]):
        events.append(ev)
    texts = "".join(e.text for e in events if e.kind == "text")
    assert texts == "异步前异步后"
    assert events[-1].kind == "finished"
    assert events[-1].finish_reason == "stop"
    assert len(calls) == 2


def test_complete_stream_async_empty_length_raises_not_silent(monkeypatch):
    """修复静默缺陷：异步 length + 空正文必须抛 OutputTruncatedError，而非 finished(None)。"""
    async def fake_acompletion(**kwargs):
        return _AsyncIter([_chunk(finish="length")])

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    with pytest.raises(OutputTruncatedError):
        async for ev in complete_stream_async([{"role": "user", "content": "hi"}]):
            pass
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/llm/test_gateway_resume.py -k "complete_text or complete_stream_async" -v`
Expected: FAIL（complete_text 不续写只返回前段；async 把 length 静默当 finished）

- [ ] **Step 3: 最小实现**

`complete_text` 在 `resp` 返回后、`text = raw_content` 前插入：

```python
        # 续写（llm-output-resume）：length 且非空正文 → 续写拼接，再截断上抛
        if _maybe_resume_text(resp.choices[0].finish_reason, raw_content):
            top_fields = kwargs.get("top_fields")  # 由调用方经参数传入（见签名）
            ann = None
            if top_fields:
                from finance_agent.llm.contracts import partial_json_progress
                prog = partial_json_progress(raw_content, top_fields)
                if prog is not None:
                    ann = _build_progress_annotation(raw_content, top_fields)
            resume_kwargs = build_resume_kwargs(
                request_kwargs, prior_text=raw_content, progress_annotation=ann
            )
            try:
                resp2 = _raw_completion_with_timeout(resume_kwargs, timeout_seconds)
                raw_content += resp2.choices[0].message.content or ""
                raw_reasoning = raw_content  # 完成后统一按 content 处理
                if _gen is not None:
                    from contextlib import suppress
                    with suppress(Exception):
                        _gen.update(
                            metadata={
                                **((trace or {}).get("metadata") or {}),
                                "resume_count": 1,
                            }
                        )
                if resp2.choices[0].finish_reason == "length":
                    raise OutputTruncatedError(
                        "续写仍 finish_reason=length：输出被截断（resume 上限 1）"
                    )
                resp = resp2
            except OutputTruncatedError:
                if _gen is not None:
                    from contextlib import suppress
                    with suppress(Exception):
                        _gen.update(
                            metadata={
                                **((trace or {}).get("metadata") or {}),
                                "resume_count": 1,
                                "truncated": True,
                            },
                            level="ERROR",
                        )
                raise
```

`complete_text` 签名新增 `top_fields: list[str] | None = None`，并在函数体里把 `top_fields` 供续写分支使用（直接引用局部变量，不经 kwargs）。

`complete_stream_async` 在 `finish == "stop"` 分支前插入（当前为流结束无明确 reason 时 `finished(None)` 的静默路径）：

```python
                # 续写（llm-output-resume）：length 且非空正文 → 二次流式续发
                if _maybe_resume_text(finish, answer):
                    from finance_agent.llm.errors import OutputTruncatedError

                    ann = None
                    if top_fields:
                        from finance_agent.llm.contracts import partial_json_progress
                        prog = partial_json_progress(answer, top_fields)
                        if prog is not None:
                            ann = _build_progress_annotation(answer, top_fields)
                    resume_kwargs = build_resume_kwargs(
                        request_kwargs, prior_text=answer, progress_annotation=ann
                    )
                    resp2 = await raw_acompletion(**resume_kwargs)
                    _iter2 = resp2.__aiter__()
                    _finish2 = None
                    while True:
                        try:
                            chunk2 = await asyncio.wait_for(
                                _iter2.__anext__(), timeout=chunk_timeout
                            )
                        except StopAsyncIteration:
                            break
                        except TimeoutError:
                            raise _ChunkTimeoutError("续写段 chunk 超时") from None
                        if getattr(chunk2, "usage", None):
                            last_usage = chunk2.usage
                        choices2 = getattr(chunk2, "choices", None) or []
                        if not choices2:
                            continue
                        c2 = choices2[0]
                        d2 = c2.delta
                        _finish2 = getattr(c2, "finish_reason", None) or _finish2
                        if d2 and getattr(d2, "reasoning_content", None):
                            reasoning_acc += str(d2.reasoning_content)
                            yield CanonicalEvent(kind="reasoning", reasoning=str(d2.reasoning_content))
                        if d2 and getattr(d2, "content", None):
                            ct2 = str(d2.content)
                            answer += ct2
                            yield CanonicalEvent(kind="text", text=ct2)
                    if _gen is not None:
                        from contextlib import suppress
                        with suppress(Exception):
                            _gen.update(
                                metadata={
                                    **((trace or {}).get("metadata") or {}),
                                    "resume_count": 1,
                                }
                            )
                    if _finish2 == "length":
                        _finalize_observation(
                            _gen, answer, reasoning_acc, last_usage,
                            metadata=(trace or {}).get("metadata"),
                        )
                        if _gen is not None:
                            with suppress(Exception):
                                _gen.update(
                                    metadata={
                                        **((trace or {}).get("metadata") or {}),
                                        "resume_count": 1,
                                        "truncated": True,
                                    },
                                    level="ERROR",
                                )
                        raise OutputTruncatedError(
                            "续写仍 finish_reason=length：输出被截断（resume 上限 1）"
                        )
                    finish = _finish2
                    # 落入下方 stop/tool_calls 正常收口分支
```

`complete_stream_async` 签名新增 `top_fields: list[str] | None = None`；并把流结束无明确 reason 时的 `finished(None)` 静默路径改为：`finish == "length"` 时（正文为空，未触发续写）抛 `OutputTruncatedError` 而非 `finished(None)`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/llm/test_gateway_resume.py -k "complete_text or complete_stream_async" -v`
Expected: PASS

- [ ] **Step 5: 全量 llm 测试回归**

Run: `uv run pytest tests/llm/ -v`
Expected: PASS（含既有 test_gateway.py / test_gateway_stream.py / test_gateway_stream_async.py 等）

- [ ] **Step 6: 提交**

```bash
git add src/finance_agent/llm/gateway.py tests/llm/test_gateway_resume.py
git commit -m "feat(resume): complete_text/complete_stream_async 断点续写 + 异步 length 不再静默"
```

---

### Task 6: 集成回归与收尾

**Files:**
- Modify: 无
- Test: `tests/llm/test_gateway_resume.py`（如有断言不严则修正）

- [ ] **Step 1: 全量后端测试**

Run: `uv run pytest tests/ -m "not live"`
Expected: 0 failures

- [ ] **Step 2: Lint 与类型检查**

Run: `uv run ruff check && uv run mypy`
Expected: 0 errors（新增模块零告警）

- [ ] **Step 3: delta 契约校验**

Run: `openspec validate truncation-resume-generation --strict`
Expected: valid

- [ ] **Step 4: 自检 spec 覆盖**

对照 `openspec/changes/truncation-resume-generation/specs/llm-output-resume/spec.md` 逐条核对：
- 截断时发起断点续写 → Task 4/5
- 续写请求携带结构进度标注 → Task 2/3/4
- 续写上限与终止（1 轮再截断上抛）→ Task 4/5
- 续写可追溯（resume_count/truncated）→ Task 4/5
- 续写拼接契约（直接连接、事件顺序）→ Task 4/5

- [ ] **Step 5: 更新 tasks.md 勾选**

将 `openspec/changes/truncation-resume-generation/tasks.md` 中已完成的 1.1-5.2 全部勾选 `[x]`

- [ ] **Step 6: 提交**

```bash
git add openspec/changes/truncation-resume-generation/tasks.md
git commit -m "docs(resume): 实施完成，tasks.md 全勾"
```