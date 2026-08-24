# tests/llm/test_registry.py
"""registry 静态能力表测试（Task 1.2）。

静态表是默认值，probe 是运行时事实；冲突以 probe 为准（design 决策 7）。
覆盖设计档案 §11 五类 preset + 方舟 GLM 实测行为。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.registry import (
    get_profile_preset,
    list_presets,
)


class TestPresets:
    def test_deepseek_official(self):
        p = get_profile_preset("deepseek-official")
        assert p.model.startswith("deepseek/")
        assert p.capability.reasoning_must_echo_on_tool is True
        assert p.capability.reasoning_forced is False

    def test_openai_compatible_custom(self):
        """自定义 OpenAI 兼容端点（方舟/Ollama/vLLM/中转）：无 reasoning 契约假设。"""
        p = get_profile_preset("openai-compatible")
        assert p.model.startswith("openai/")
        assert p.capability.reasoning_must_echo_on_tool is False

    def test_ark_glm_forced_reasoning(self):
        """方舟 GLM preset：思考强制开启不可关（incident 017 实测）。"""
        p = get_profile_preset("ark-glm")
        assert p.capability.reasoning_forced is True
        assert p.capability.reasoning_must_echo_on_tool is False

    def test_ark_glm_max_tokens_aligned_official_default(self):
        """方舟 GLM-5.3 max_tokens 对齐官方默认 65536（docs.bigmodel.cn）。"""
        p = get_profile_preset("ark-glm")
        assert p.capability.max_output == 65536
        assert p.default_params == {"max_tokens": 65536}

    def test_unknown_preset_raises(self):
        with pytest.raises(KeyError):
            get_profile_preset("no-such-preset")

    def test_list_presets_nonempty_and_named(self):
        names = list_presets()
        assert "deepseek-official" in names
        assert "ark-glm" in names
        assert all(isinstance(n, str) for n in names)
