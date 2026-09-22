# tests/nodes/test_llm_utils_fallback.py
"""结构化节点路径的 fallback 链执行（spec llm-policy-router Requirement 2）。

缺口（本轮修复前）：`gateway.complete_text_with_fallback` 只服务非流式入口且零生产调用方，
节点路径（call_llm_for_json → call_llm_streaming → gateway.complete_stream）在
「输出合同 repair 耗尽」与四类不可重试 typed error（ContentFiltered/AuthError/
ModelNotFound/UnsupportedCapability）下直接上抛，从不按 fallback_chain 切换 profile。

钉住的合同：
- repair 耗尽（JSON 解析失败 / 字段校验失败）→ 切链中下一 profile 重试；
- 触发类 typed error 不在本 profile 空转重试，直接交给链切换；
- 每次切换落该次尝试的 trace（fallback_from + fallback_path，含完整路径）；
- 链长上限 3；链耗尽上抛最后一个错误（不静默降级）；
- 非触发错误（如 RuntimeError）不切换；无 fallback 配置 → 单 profile 行为不变；
- 首次尝试沿用请求级配置透传（preset=None），链仅在首次失败后解析（懒）。
"""

from __future__ import annotations

import dataclasses
import json
from unittest.mock import patch

import pytest

from finance_agent.llm.errors import AuthError, ContentFilteredError
from finance_agent.llm.registry import get_profile_preset
from finance_agent.llm.resolver import IncompleteLLMConfigError
from finance_agent.nodes._llm_utils import call_llm_for_json


def _pin_primary(fallback: tuple[str, ...] = ("openai-official",)):
    """固定 primary=deepseek-official（隔离 env / probe 缓存对解析结果的影响）。"""
    return patch(
        "finance_agent.llm.gateway.resolve_profile",
        return_value=dataclasses.replace(
            get_profile_preset("deepseek-official"), fallback=fallback
        ),
    )


def _fake_streamer(handler):
    """按 handler(第几次调用, kwargs) 产出文本或异常的 call_llm_streaming mock。"""
    calls: list[dict] = []

    def fake(prompt: str, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return handler(len(calls), kwargs)

    return fake, calls


def _presets(calls: list[dict]) -> list[str | None]:
    return [c.get("preset") for c in calls]


class TestRepairExhaustedSwitchesProfile:
    def test_json_repair_exhausted_switches_to_fallback(self):
        """坏 JSON 两次（首答 + 强化指令重试）仍失败 → 换链中下一 profile 成功。"""

        def handler(n, kw):
            if kw.get("preset") == "openai-official":
                return '{"decision": "hold"}'
            return "我认为风险可控。"  # 无 JSON → 强化重试 → 仍失败 → 切换

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
        ):
            result = call_llm_for_json("审批", node_name="risk_judge")

        assert result == {"decision": "hold"}
        # 首次尝试（含同 profile repair 重试）沿用请求级配置透传 → preset=None；
        # 切换后的成员按 preset 名选中
        assert _presets(calls) == [None, None, "openai-official"]
        # fallback 成员用 preset 名（不带请求级配置）
        assert calls[2]["llm_config"] is None
        # 每次切换落该次尝试的 trace
        assert calls[2]["fallback_from"] == "deepseek-official"
        assert calls[2]["fallback_path"] == ["deepseek-official", "openai-official"]
        # 首次尝试（primary）不携带切换事实
        assert not calls[0].get("fallback_from")

    def test_validation_exhausted_switches_to_fallback(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            action: str

        def handler(n, kw):
            if kw.get("preset") == "openai-official":
                return '{"action": "watch"}'
            return '{"x": 1}'  # JSON 合法但缺必填 → validate 失败 → 重试 → 仍失败 → 切换

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
        ):
            result = call_llm_for_json("审批", validate=Out.model_validate)

        assert result == {"action": "watch"}
        # 首次尝试（含同 profile repair 重试）沿用请求级配置透传 → preset=None；
        # 切换后的成员按 preset 名选中
        assert _presets(calls) == [None, None, "openai-official"]

    def test_no_fallback_config_keeps_single_profile_behavior(self):
        """无 fallback 配置（fallback=()）→ 与原语义一致：同 profile 重试后上抛。"""

        def handler(n, kw):
            return "坏输出"

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(fallback=()),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(json.JSONDecodeError),
        ):
            call_llm_for_json("x")
        assert _presets(calls) == [None, None]


class TestLazyChainResolution:
    def test_happy_path_never_resolves_chain(self):
        """happy path 不解析链：stub 模式与半套请求级配置不被提前打回。"""

        def handler(n, kw):
            return '{"ok": true}'

        fake, calls = _fake_streamer(handler)
        with (
            patch("finance_agent.llm.gateway.fallback_attempt_plan") as plan_mock,
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
        ):
            assert call_llm_for_json("x") == {"ok": True}
        assert plan_mock.call_count == 0
        assert len(calls) == 1

    def test_chain_resolution_failure_does_not_mask_original_error(self):
        """链解析失败（配置半套等）→ 上抛原错误，不换错误面。"""

        def handler(n, kw):
            return "坏输出"

        fake, _ = _fake_streamer(handler)
        with (
            patch(
                "finance_agent.llm.gateway.fallback_attempt_plan",
                side_effect=IncompleteLLMConfigError("请求级 llm_config 不完整"),
            ),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(json.JSONDecodeError),
        ):
            call_llm_for_json("x")


class TestTypedErrorSwitchesProfile:
    def test_content_filtered_switches_without_same_profile_retry(self):
        """ContentFiltered 不可经同 profile 重试解决：一次尝试即切链（不空转复读）。"""

        def handler(n, kw):
            if kw.get("preset") == "openai-official":
                return '{"ok": true}'
            raise ContentFilteredError("blocked by provider")

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
        ):
            result = call_llm_for_json("x")

        assert result == {"ok": True}
        assert _presets(calls) == [None, "openai-official"]
        assert calls[1]["fallback_from"] == "deepseek-official"

    def test_chain_exhausted_raises_last_typed_error(self):
        """链耗尽上抛最后一个 typed error（不静默降级、不无限重试）。"""

        def handler(n, kw):
            raise AuthError("bad key")

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(AuthError),
        ):
            call_llm_for_json("x")
        assert _presets(calls) == [None, "openai-official"]

    def test_attempts_capped_at_three(self):
        """链长上限 3：三成员链全失败 → 每成员一次，不再多试。"""

        def handler(n, kw):
            raise AuthError("bad key")

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(fallback=("openai-official", "anthropic")),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(AuthError),
        ):
            call_llm_for_json("x")
        assert _presets(calls) == [None, "openai-official", "anthropic"]

    def test_non_trigger_error_does_not_switch(self):
        """非触发错误（服务瞬时故障类）沿既有同 profile 重试语义，不换 profile。"""

        def handler(n, kw):
            raise RuntimeError("boom")

        fake, calls = _fake_streamer(handler)
        with (
            _pin_primary(),
            patch("finance_agent.nodes._llm_utils.call_llm_streaming", side_effect=fake),
            pytest.raises(RuntimeError),
        ):
            call_llm_for_json("x")
        assert _presets(calls) == [None, None]
