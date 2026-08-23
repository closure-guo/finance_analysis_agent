"""gateway 截断续写（llm-output-resume delta Task 1-4）。

mock adapter raw_* 返回「前段 length + 续写 stop」双段流，验证续写
触发、拼接、预算派生、进度标注注入、再截断上抛。
"""

from __future__ import annotations

from finance_agent.llm.adapters.litellm_adapter import build_resume_kwargs
from finance_agent.llm.contracts import partial_json_progress
from finance_agent.llm.gateway import _build_progress_annotation, _maybe_resume_text


def _estimate_tokens(text: str) -> int:
    # 与实现同源的估算：默认按 4 字符/token
    return max(1, len(text) // 4)


def test_build_resume_kwargs_appends_instruction_and_shrinks_budget():
    base = {
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 16384,
    }
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


def test_build_resume_kwargs_injects_prior_tail_not_head():
    """续写消息注入 prior_text 尾部 4000 字符而非全文（design D1 尾部注入基线）。

    头部/尾部用可区分字符：prior_text > 4000 字符，断言只出现尾部子串、
    头部不出现，证明注入的是截取的尾部而非整段 prior_text。
    """
    head = "HEAD_MARKER:" * 40
    tail = "TAIL_MARKER:" * 1200
    prior_text = head + tail
    assert len(prior_text) > 4000
    base = {"model": "glm-5.2", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8192}
    out = build_resume_kwargs(base, prior_text=prior_text)
    content = out["messages"][-1]["content"]
    assert out["messages"][-1]["role"] == "user"
    assert "已生成内容尾部" in content
    assert prior_text[-4000:] in content
    assert head not in content


def test_build_resume_kwargs_tail_injection_composes_single_message():
    """尾部 + 指令合成 1 条 user 消息：messages 数 = 原 messages + 1。"""
    base = {
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "part"}],
        "max_tokens": 8192,
    }
    out = build_resume_kwargs(base, prior_text="x" * 5000)
    assert len(out["messages"]) == len(base["messages"]) + 1
    assert out["messages"][-1]["role"] == "user"


def test_build_resume_kwargs_tail_injection_layout_order():
    """消息 content 布局：进度标注在前 → 已生成内容尾部 → 续写指令在后。"""
    prior_text = "A" * 6000
    ann = "- key_findings: ⏳ 已闭合 3 条"
    base = {"model": "glm-5.2", "messages": [], "max_tokens": 8192}
    out = build_resume_kwargs(base, prior_text=prior_text, progress_annotation=ann)
    content = out["messages"][-1]["content"]
    assert content.index(ann) < content.index("已生成内容尾部") < content.index("续写")


# ---- Task 2: partial_json_progress ----

FIELDS = ["agent_name", "summary", "key_findings", "claims", "markdown"]


def test_partial_progress_field_midway():
    """标量字段已闭合 → done；数组字段断在半路 → in_progress；未出现 → pending。"""
    text = '{"agent_name": "technical", "summary": "ok", "key_findings": ["a", "b'
    prog = partial_json_progress(text, FIELDS)
    assert prog["agent_name"] == "done"
    assert prog["summary"] == "done"
    assert prog["key_findings"] == "in_progress"
    assert prog["claims"] == "pending"
    assert prog["markdown"] == "pending"


def test_partial_progress_array_element_midway():
    """数组断在元素中间（元素字符串未闭合）→ 数组字段 in_progress。"""
    text = '{"agent_name": "macro", "summary": "s", "key_findings": ["a", "b'
    prog = partial_json_progress(text, FIELDS)
    assert prog["key_findings"] == "in_progress"


def test_partial_progress_unrecoverable_returns_none():
    """找不到 { 开始（纯文本 / 空文本）→ None，调用方降级仅尾部注入。"""
    assert partial_json_progress("分析完成，非 JSON", FIELDS) is None
    assert partial_json_progress("", FIELDS) is None


def test_partial_progress_complete_json_all_done():
    """完整 JSON → 所有字段 done。"""
    text = '{"agent_name": "x", "summary": "s", "key_findings": [], "claims": [], "markdown": "m"}'
    prog = partial_json_progress(text, FIELDS)
    assert set(prog.values()) == {"done"}


# ---- Task 3: _maybe_resume_text + _build_progress_annotation ----


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
