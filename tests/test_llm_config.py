"""LLMConfig 数据结构与 LLMConfigRequest 反序列化单元测试。

覆盖 tasks.md 1.3：默认值、JSON 反序列化、字段可选性。
"""

from __future__ import annotations

from finance_agent.api import LLMConfigRequest
from finance_agent.llm import LLMConfig

# ── LLMConfig dataclass ──


def test_llm_config_defaults_all_none():
    """LLMConfig 无参构造时所有字段应为 None（回退环境变量）。"""
    cfg = LLMConfig()
    assert cfg.model is None
    assert cfg.baseUrl is None
    assert cfg.apiKey is None
    assert cfg.thinking is None


def test_llm_config_field_names_camel_case():
    """LLMConfig 字段名须用 camelCase（baseUrl / apiKey），对齐前端 JSON 契约。"""
    cfg = LLMConfig(model="m", baseUrl="u", apiKey="k", thinking="disabled")
    assert cfg.model == "m"
    assert cfg.baseUrl == "u"
    assert cfg.apiKey == "k"
    assert cfg.thinking == "disabled"


def test_llm_config_partial_construction():
    """LLMConfig 支持仅指定部分字段，其余保持 None。"""
    cfg = LLMConfig(model="deepseek/deepseek-chat")
    assert cfg.model == "deepseek/deepseek-chat"
    assert cfg.baseUrl is None
    assert cfg.apiKey is None
    assert cfg.thinking is None


def test_llm_config_is_frozen_mutable_default():
    """LLMConfig 是普通 dataclass，字段可独立修改（非 frozen）。"""
    cfg = LLMConfig()
    cfg.model = "openai/gpt-4o"
    assert cfg.model == "openai/gpt-4o"


# ── LLMConfigRequest Pydantic 模型 ──


def test_llm_config_request_defaults_all_none():
    """LLMConfigRequest 无参构造时所有字段应为 None。"""
    req = LLMConfigRequest()
    assert req.model is None
    assert req.baseUrl is None
    assert req.apiKey is None
    assert req.thinking is None


def test_llm_config_request_from_json_full():
    """LLMConfigRequest 从完整 JSON 反序列化，字段值正确。"""
    req = LLMConfigRequest.model_validate(
        {
            "model": "deepseek/deepseek-chat",
            "baseUrl": "https://api.deepseek.com/v1",
            "apiKey": "sk-xxx",
            "thinking": "enabled",
        }
    )
    assert req.model == "deepseek/deepseek-chat"
    assert req.baseUrl == "https://api.deepseek.com/v1"
    assert req.apiKey == "sk-xxx"
    assert req.thinking == "enabled"


def test_llm_config_request_from_empty_json():
    """空 JSON 对象反序列化为全 None 字段（字段全部可选）。"""
    req = LLMConfigRequest.model_validate({})
    assert req.model is None
    assert req.baseUrl is None
    assert req.apiKey is None
    assert req.thinking is None


def test_llm_config_request_partial_json():
    """部分字段 JSON 反序列化，缺失字段保持 None。"""
    req = LLMConfigRequest.model_validate({"model": "openai/gpt-4o"})
    assert req.model == "openai/gpt-4o"
    assert req.baseUrl is None
    assert req.apiKey is None
    assert req.thinking is None


def test_llm_config_request_to_llm_config_mapping():
    """LLMConfigRequest 字段可手动映射到 LLMConfig（API 端点的转换逻辑基础）。"""
    req = LLMConfigRequest(
        model="deepseek/deepseek-chat",
        baseUrl="https://api.deepseek.com/v1",
        apiKey="sk-xxx",
        thinking="disabled",
    )
    cfg = LLMConfig(
        model=req.model,
        baseUrl=req.baseUrl,
        apiKey=req.apiKey,
        thinking=req.thinking,
    )
    assert cfg.model == "deepseek/deepseek-chat"
    assert cfg.baseUrl == "https://api.deepseek.com/v1"
    assert cfg.apiKey == "sk-xxx"
    assert cfg.thinking == "disabled"
