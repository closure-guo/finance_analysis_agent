# src/finance_agent/llm/__init__.py
"""LLM Provider Gateway 包（delta add-llm-provider-gateway）。

兼容薄壳：旧 ``finance_agent.llm`` 模块的公共 API 经 ``legacy`` re-export，
既有 import 路径（``from finance_agent.llm import call_llm`` 等）与
mock.patch 字符串目标不变；新代码应使用 gateway/resolver/contracts。
"""

from finance_agent.llm.legacy import (  # noqa: F401
    LLMConfig,
    call_llm,
    call_llm_stream,
    call_llm_with_tools,
)
from finance_agent.llm.registry import get_profile_preset, list_presets  # noqa: F401
from finance_agent.llm.resolver import resolve_profile  # noqa: F401
from finance_agent.llm.types import (  # noqa: F401
    CanonicalEvent,
    CanonicalRequest,
    Capability,
    ModelProfile,
)
