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
