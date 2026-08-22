"""gateway 截断续写（llm-output-resume delta Task 1-4）。

mock adapter raw_* 返回「前段 length + 续写 stop」双段流，验证续写
触发、拼接、预算派生、进度标注注入、再截断上抛。
"""

from __future__ import annotations

from finance_agent.llm.adapters.litellm_adapter import build_resume_kwargs


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
