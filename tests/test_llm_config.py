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


# ── apiForm（add-llm-api-form）──


def test_llm_config_request_accepts_valid_api_form():
    """合法 apiForm 三个取值都能通过校验。"""
    for value in ("chat_completion", "messages", "responses"):
        req = LLMConfigRequest.model_validate({"apiForm": value})
        assert req.apiForm == value


def test_llm_config_request_null_api_form_allowed():
    """apiForm 为 null/缺省 → None（未设置，自动路由）。"""
    assert LLMConfigRequest().apiForm is None
    assert LLMConfigRequest.model_validate({"apiForm": None}).apiForm is None


def test_llm_config_request_rejects_invalid_api_form():
    """非法 apiForm → ValidationError（HTTP 422），不静默忽略。"""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LLMConfigRequest.model_validate({"apiForm": "bogus"})


# ── contextLength（add-context-length-config）──


def test_llm_config_request_accepts_positive_context_length():
    """合法正整数 contextLength 通过校验。"""
    req = LLMConfigRequest.model_validate({"contextLength": 200000})
    assert req.contextLength == 200000


def test_llm_config_request_null_context_length_allowed():
    """contextLength 缺省/null → None（跟随 registry 静态默认）。"""
    assert LLMConfigRequest().contextLength is None
    assert LLMConfigRequest.model_validate({"contextLength": None}).contextLength is None


def test_llm_config_request_rejects_non_positive_context_length():
    """contextLength 为 0 / 负数 / 非整数 → ValidationError（HTTP 422），不静默忽略。"""
    import pytest
    from pydantic import ValidationError

    for bad in (0, -5, 1.5, "abc"):
        with pytest.raises(ValidationError):
            LLMConfigRequest.model_validate({"contextLength": bad})


def test_llm_config_dataclass_carries_context_length():
    """LLMConfig dataclass 携带 contextLength，_to_llm_config 透传。"""
    from finance_agent.api import _to_llm_config

    req = LLMConfigRequest(
        model="openai/gpt-4o",
        baseUrl="https://api.openai.com/v1",
        apiKey="sk-x",
        contextLength=200000,
    )
    cfg = _to_llm_config(req)
    assert cfg is not None
    assert cfg.contextLength == 200000
