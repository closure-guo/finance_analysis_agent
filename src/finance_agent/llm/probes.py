# src/finance_agent/llm/probes.py
"""capability probe 判定层（delta 4.1，设计档案 §16/§11）。

五项探测判定为纯函数（发送编排在 api 层）；probe 运行时事实覆盖静态能力表
（design 决策 7）。目标：区分「能聊天」与「能跑 Agent」的假可用 profile。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from finance_agent.llm.types import Capability, ModelProfile


@dataclass
class ProbeReport:
    """五项探测结果 + 有效配置 + warnings。"""

    non_stream: bool
    stream: bool
    tool_call: bool
    tool_followup: bool
    json_output: bool
    latency_ms: int
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _latency_tier(ms: int) -> str:
    if ms < 200:
        return "fast"
    if ms < 1500:
        return "medium"
    return "slow"


def build_probe_report(
    *,
    non_stream: bool,
    stream: bool,
    tool_call: bool,
    tool_followup: bool,
    json_output: bool,
    latency_ms: int,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> ProbeReport:
    """组装 ProbeReport（判定由各探测函数产出，本函数保证一致性/DTO）。"""
    return ProbeReport(
        non_stream=non_stream,
        stream=stream,
        tool_call=tool_call,
        tool_followup=tool_followup,
        json_output=json_output,
        latency_ms=latency_ms,
        warnings=list(warnings or []) + [f"latency={_latency_tier(latency_ms)}"],
        error=error,
    )


def judge_capability_from_probe(report: ProbeReport) -> Capability:
    """由 probe 事实推导 Capability（覆盖静态默认）。

    tools：tool_call+tool_followup 都过 → single；否则 none。
    json：json_output 过 → json_mode；否则 none。
    """
    tools: str = "single" if report.tool_call and report.tool_followup else "none"
    json_schema: str = "json_mode" if report.json_output else "none"
    return Capability(
        tools=tools,  # type: ignore[arg-type]
        tool_choice_required=False,
        streaming=True,
        streaming_tool_calls=report.tool_call,
        json_schema=json_schema,  # type: ignore[arg-type]
        supports_system_role=True,
        reasoning_field=None,
        reasoning_must_echo_on_tool=False,
        reasoning_forced=False,
        max_context=128000,
        max_output=8192,
        extra_body_allowed=True,
    )


def merge_probe_into_profile(profile: ModelProfile, report: ProbeReport) -> ModelProfile:
    """probe 运行时事实覆盖静态 profile 的能力表（以 probe 为准）。

    probe 只验证「factual」能力（tools/json/streaming 类），不测量上下文/
    输出窗口，也不测 reasoning 行为——`judge_capability_from_probe` 硬编码的
    max_context/max_output 是保守默认值，直接采用会回退 capability 特化配置
    （如 ark-glm 的 max_output=16384、reasoning_forced 的预算策略）。因此
    保留原 capability 的 max_context/max_output/reasoning_* 等 provider 静态
    事实，只覆盖 probe 实测字段；与静态表不一致的字段名记入 probe_warnings。
    其余 profile 字段（api_key/provider_options/default_params 等）原样保留。
    """
    import dataclasses

    probed = judge_capability_from_probe(report)
    orig = profile.capability
    merged_cap = dataclasses.replace(
        probed,
        max_context=orig.max_context,
        max_output=orig.max_output,
        reasoning_field=orig.reasoning_field,
        reasoning_must_echo_on_tool=orig.reasoning_must_echo_on_tool,
        reasoning_forced=orig.reasoning_forced,
    )
    warnings: list[str] = []
    for field_name in (
        "tools",
        "json_schema",
        "streaming",
        "streaming_tool_calls",
        "tool_choice_required",
        "supports_system_role",
        "extra_body_allowed",
    ):
        old, new = getattr(orig, field_name), getattr(merged_cap, field_name)
        if old != new:
            warnings.append(f"{field_name}: {old}→{new}")
    return dataclasses.replace(
        profile,
        capability=merged_cap,
        probe_required=False,
        probe_warnings=tuple(warnings),
    )


def run_live_probes(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    max_tokens: int = 500,
) -> ProbeReport:
    """实际执行五项探测（真实 LLM 调用），返回 ProbeReport。

    - non_stream：非流式 completion
    - json_output：response_format=json_object（或退化为 json_mode）
    - stream：stream=True 首 chunk
    - tool_call：带 tools 请求，期望返回结构化 tool_calls
    - tool_followup：模拟工具结果回传（native 或 action 协议），期望继续
    """
    import time
    from typing import Any

    from finance_agent.llm.adapters.litellm_adapter import raw_completion, raw_stream

    base: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "messages": [{"role": "user", "content": "说你好"}],
        "max_tokens": max_tokens,
        "timeout": 60,
    }
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "probe_echo",
                "description": "回显",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]
    report: dict = {
        "non_stream": False,
        "stream": False,
        "tool_call": False,
        "tool_followup": False,
        "json_output": False,
        "latency_ms": 0,
    }
    warnings: list[str] = []

    # non_stream + json_output
    start = time.perf_counter()
    try:
        raw_completion(**base)
        report["non_stream"] = True
        try:
            raw_completion(**base, response_format={"type": "json_object"})
            report["json_output"] = True
        except Exception:  # noqa: S110 -- json_mode 可选能力，失败记 warning
            warnings.append("json_mode_unsupported")
    except Exception as exc:  # noqa: BLE001
        latency = int((time.perf_counter() - start) * 1000)
        return ProbeReport(
            non_stream=False,
            stream=False,
            tool_call=False,
            tool_followup=False,
            json_output=False,
            latency_ms=latency,
            warnings=warnings,
            error=f"{type(exc).__name__}: {str(exc)[:120]}",
        )

    # stream
    try:
        sr = raw_stream(**base)
        _ = next(iter(sr))
        report["stream"] = True
    except Exception:  # noqa: S110
        warnings.append("stream_unsupported")

    # tool_call
    try:
        tr = raw_completion(**base, tools=TOOLS, tool_choice="auto")
        msg = tr.choices[0].message
        report["tool_call"] = bool(getattr(msg, "tool_calls", None))

        # tool_followup：构造工具结果回传
        if report["tool_call"]:
            tc = msg.tool_calls[0]
            followup_msgs: list = list(base["messages"]) + [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": tc.id, "content": "probe-ok"},
            ]
            fr = raw_completion(**{**base, "messages": followup_msgs, "tools": TOOLS})
            report["tool_followup"] = fr.choices[0].message.content is not None
    except Exception:  # noqa: S110
        warnings.append("tool_call_probe_error")

    latency = int((time.perf_counter() - start) * 1000)
    return build_probe_report(
        non_stream=report["non_stream"],
        stream=report["stream"],
        tool_call=report["tool_call"],
        tool_followup=report["tool_followup"],
        json_output=report["json_output"],
        latency_ms=latency,
        warnings=warnings,
    )
