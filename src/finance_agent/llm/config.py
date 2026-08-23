"""请求级 LLM 配置类型（migrate-off-legacy-llm-shim：自 legacy 独立迁出）。

``LLMConfig`` 是 API 层（``LLMConfigRequest``）到下游管线节点的转换对象：
api.``_to_llm_config`` Pydantic→dataclass，``agent_factory``/``api``
各入口作类型标注，节点经 ``_request_config_dict`` 转为 gateway 请求级 dict
（``{"model","baseUrl","apiKey","thinking","apiForm"}``）。

字段用 camelCase（baseUrl / apiKey），与前端 JSON 契约及项目命名约定一致。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMConfig:
    """请求级 LLM 配置，字段为 None 时回退环境变量。

    字段用 camelCase 命名（baseUrl / apiKey），与前端 JSON 契约及项目命名约定一致。
    """

    model: str | None = None
    baseUrl: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    apiKey: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    thinking: str | None = None
    apiForm: str | None = None  # noqa: N815  # API 形式：chat_completion / messages / responses，None 自动路由
