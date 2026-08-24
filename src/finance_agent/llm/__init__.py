# src/finance_agent/llm/__init__.py
"""LLM Provider Gateway 包（delta add-llm-provider-gateway）。

migrate-off-legacy-llm-shim（Task 3）：legacy 薄壳（call_llm /
call_llm_stream / call_llm_with_tools / legacy.py）已删除，生产 LLM 调用
统一经 ``finance_agent.llm.gateway``（complete_text / complete_stream /
complete_stream_async / complete_with_tools）。``LLMConfig`` 类型独立在
``finance_agent.llm.config``（api 契约层依赖），此处保留 re-export 兼容旧
import 路径（``from finance_agent.llm import LLMConfig``）。

新代码应使用 gateway/resolver/contracts/types，不再有第二个 LLM 入口。
"""

from finance_agent.llm.config import LLMConfig  # noqa: F401
from finance_agent.llm.registry import get_profile_preset, list_presets  # noqa: F401
from finance_agent.llm.resolver import resolve_profile  # noqa: F401
from finance_agent.llm.types import (  # noqa: F401
    CanonicalEvent,
    CanonicalRequest,
    Capability,
    ModelProfile,
)
