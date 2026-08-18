# tests/llm/test_errors.py
"""finish_reason 归一化与 typed errors 测试（delta Task 2.2）。

截断不再表现为下游偶发 JSONDecodeError 的前提：adapter 层分型
（incident 017 教训——length 截断/空正文未被识别）。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.adapters.litellm_adapter import classify_outcome
from finance_agent.llm.errors import (
    ContentFiltered,
    EmptyLLMOutput,
    OutputTruncated,
)


class TestClassifyOutcome:
    def test_stop_normal(self):
        assert classify_outcome("stop", saw_text_delta=True) is None

    def test_tool_calls_normal(self):
        assert classify_outcome("tool_calls", saw_text_delta=False) is None

    def test_length_raises_truncated(self):
        with pytest.raises(OutputTruncated):
            classify_outcome("length", saw_text_delta=True)

    def test_content_filter_raises(self):
        with pytest.raises(ContentFiltered):
            classify_outcome("content_filter", saw_text_delta=True)

    def test_unknown_without_delta_raises_empty(self):
        """finish_reason 缺失/unknown 且无任何正文 delta → 空输出（GLM 思考后即止）。"""
        with pytest.raises(EmptyLLMOutput):
            classify_outcome(None, saw_text_delta=False)
        with pytest.raises(EmptyLLMOutput):
            classify_outcome("unknown", saw_text_delta=False)

    def test_unknown_with_delta_normal(self):
        """无 finish_reason 但正文有内容（连接中断前的部分输出）不判空。"""
        assert classify_outcome(None, saw_text_delta=True) is None

    def test_empty_reasoning_only_still_empty(self):
        """reasoning 有 delta 不算正文——只有 saw_text_delta 才算。"""
        with pytest.raises(EmptyLLMOutput):
            classify_outcome("stop", saw_text_delta=False)


class TestOutputBudget:
    def test_budget_from_capability(self):
        """预算从 capability 派生：方舟 GLM（reasoning_forced）16384，普通 8192。"""
        from finance_agent.llm.adapters.litellm_adapter import (
            capability_for_model,
            derive_output_budget,
        )

        assert derive_output_budget(capability_for_model("openai/glm-5.2")) == 16384
        assert derive_output_budget(capability_for_model("openai/gpt-4o")) == 8192

    def test_explicit_request_wins(self):
        from finance_agent.llm.adapters.litellm_adapter import (
            capability_for_model,
            derive_output_budget,
        )

        assert derive_output_budget(capability_for_model("openai/glm-5.2"), requested=400) == 400
