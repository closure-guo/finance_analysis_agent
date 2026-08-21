# src/finance_agent/llm/adapters/litellm_adapter.py
"""litellm adapter：唯一允许 import/配置 litellm 的地方（delta Task 1.4）。

运行时防护收口（design 决策 4）：
- ``disable_streaming_logging``：incident 016 —— litellm 流式每个 chunk 向
  全局 100 线程池提交 logging，worker 内 asyncio.run 新建 ProactorEventLoop，
  Windows/Py3.14 ``_fallback_socketpair`` 并发竞态令线程永久卡在 accept()
  （100 worker 全灭、退出 join 挂死）。项目 Langfuse 走自研 SDK，零损失。
- ``drop_params``：Task 8 起移除全局静默 drop（设计档案 §8：关键参数不静默
  丢弃）。未知/白名单外参数由 litellm 原生报错（显式失败）；白名单内非关键
  参数仅在 capability 明确不支持时由 ``_drop_unsupported`` 剔除。回滚保险：
  环境变量 ``LLM_DROP_PARAMS_STRICT=1`` 可临时恢复旧全局 drop 行为。
- litellm-langfuse 兼容补丁：1.85.x 与 langfuse 4.x 深度不兼容
  （version 属性、sdk_integration 参数等多处不匹配），noop 其 logger。

业务模块（llm.py / harness/litellm_client.py）经 ``ensure_litellm_runtime``
触发初始化，不各自设置 —— 防止防护配置漂移。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from finance_agent.llm.errors import LLMError
    from finance_agent.llm.types import Capability, ModelProfile

logger = logging.getLogger(__name__)

_INIT_LOCK = threading.Lock()
_initialized = False


def _apply_langfuse_compat_patch() -> None:
    """litellm-langfuse 兼容补丁（自 finance_agent/llm.py 迁入，行为不变）。"""
    try:
        import importlib.metadata

        import langfuse

        if not hasattr(langfuse, "version"):
            _lf_ver = importlib.metadata.version("langfuse")
            langfuse.version = type("version", (), {"__version__": _lf_ver})()  # type: ignore[attr-defined]
    except Exception:  # noqa: S110 -- 补丁失败不阻断初始化
        pass

    def _lf_noop(self, *a, **kw):  # noqa: ARG001
        pass

    def _lf_noop_init(self, *a, **kw):  # noqa: ARG001
        self.langfuse_sdk_version = "4.13.0"
        self.Langfuse = None
        self.langfuse_client = None

    for _cls_path in (
        "litellm.integrations.langfuse.langfuse.LangFuseLogger",
        "litellm.integrations.langfuse.langfuse_prompt_management.LangfusePromptManagement",
    ):
        try:
            _parts = _cls_path.rsplit(".", 1)
            _mod = __import__(_parts[0], fromlist=[_parts[1]])
            _cls = getattr(_mod, _parts[1])
            _cls.__init__ = _lf_noop_init
            for _method in ("log_event_on_langfuse", "_log_langfuse_v2", "_log_langfuse_v1"):
                if hasattr(_cls, _method):
                    setattr(_cls, _method, _lf_noop)
        except Exception:  # noqa: S110
            pass


def ensure_litellm_runtime() -> None:
    """幂等初始化 litellm 运行时防护（线程安全，可并发首次调用）。"""
    global _initialized
    if _initialized:
        return
    with _INIT_LOCK:
        if _initialized:
            return
        import litellm

        # Task 8：移除全局静默 drop（设计档案 §8）；回滚开关：线上出现
        # 端点拒收非关键参数的事故时，设 LLM_DROP_PARAMS_STRICT=1 临时恢复旧行为
        if os.environ.get("LLM_DROP_PARAMS_STRICT") == "1":
            litellm.drop_params = True
        else:
            litellm.drop_params = False
        # incident 016 死锁防护（NOT RECOMMENDED 标记仅影响 litellm 自身
        # 用量回调——项目未注册任何 litellm callback，零功能损失）
        litellm.disable_streaming_logging = True
        _apply_langfuse_compat_patch()
        _initialized = True


# ── 消息序列化收口（delta Task 2.1）─────────────────────────────────


def capability_for_model(model: str) -> Capability:
    """按 model 名推断 Capability（基于 registry preset，不猜行为细节）。

    存量调用方（harness LiteLLMClient）只有 model 字符串；新代码应经
    resolver.resolve_profile 拿完整 ModelProfile。推断规则保守：
    已知 glm/deepseek 映射对应 preset，其余按 openai-compatible 中性假设。
    """
    from finance_agent.llm.registry import get_profile_preset

    lower = model.lower()
    if "glm" in lower:
        return get_profile_preset("ark-glm").capability
    if "deepseek" in lower:
        return get_profile_preset("deepseek-official").capability
    return get_profile_preset("openai-compatible").capability


def _normalize_arguments_str(raw: object) -> object:
    """tool_calls.arguments 规范化为合法 JSON 字符串。

    GLM 等模型偶发输出单引号 Python 字面量（"{'q': 'x'}"），严格端点
    回传 400。合法 JSON 原样返回；Python 字面量经 literal_eval 重 dumps；
    解析失败保留原值（不因清洗破坏请求）。
    """
    import ast
    import json

    if not isinstance(raw, str):
        return raw
    try:
        json.loads(raw)
        return raw
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return json.dumps(ast.literal_eval(raw), ensure_ascii=False)
    except (ValueError, SyntaxError):
        return raw


def sanitize_messages_for_profile(messages: list[dict], capability: Capability) -> list[dict]:
    """按 capability 清洗回传消息。

    - reasoning 字段：``reasoning_must_echo_on_tool`` 为 False 时剥除
      （方舟拒收该字段 400）；为 True 时保留（DeepSeek 官方要求回传）。
    - arguments 规范化对全部 provider 生效（合法 JSON 是通用要求，
      已合法的值原样返回，无副作用）。
    """
    cleaned: list[dict] = []
    for m in messages:
        m = dict(m)
        if not capability.reasoning_must_echo_on_tool:
            m.pop("reasoning_content", None)
        if m.get("tool_calls"):
            m["tool_calls"] = [
                {
                    **tc,
                    "function": {
                        **tc.get("function", {}),
                        "arguments": _normalize_arguments_str(
                            tc.get("function", {}).get("arguments")
                        ),
                    },
                }
                for tc in m["tool_calls"]
            ]
        cleaned.append(m)
    return cleaned


def sanitize_request_messages(messages: list[dict], capability: Capability) -> list[dict]:
    """gateway 各入口复用命名的薄包装（delta Task 5.1-C.1）。

    逻辑唯一实现仍是 ``sanitize_messages_for_profile``，此处仅提供
    gateway 语义命名（请求前消息清洗），不复制实现。
    """
    return sanitize_messages_for_profile(messages, capability)


# ── 工具增量合并收口（delta Task 5.1-C.1，设计 §8 职责 3）─────────────


class ToolCallAccumulator:
    """流式 tool_calls 增量按 index 聚合（自 harness/litellm_client.py:270-287 移植）。

    litellm 流式 delta 的 tool_calls 片段形如
    ``{id, function: {name, arguments}, index}``（attrs，测试可用同构 dict）；
    arguments 片段跨 chunk 拼接，id/name 首次出现即固定。
    """

    def __init__(self) -> None:
        self._calls: dict[int, dict] = {}

    def add(self, delta: Any) -> None:
        """聚合单个 tool_call 增量片段。"""
        if isinstance(delta, dict):
            idx = delta.get("index", 0)
            tc_id = delta.get("id") or ""
            func = delta.get("function") or {}
        else:
            idx = getattr(delta, "index", 0)
            tc_id = getattr(delta, "id", None) or ""
            func = getattr(delta, "function", None) or {}
        if isinstance(func, dict):
            name = func.get("name", "")
            args = func.get("arguments", "")
        else:
            name = getattr(func, "name", None) or ""
            args = getattr(func, "arguments", None) or ""

        if idx not in self._calls:
            self._calls[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
        call = self._calls[idx]
        if tc_id:
            call["id"] = tc_id
        if name:
            call["function"]["name"] = name
        if args:
            call["function"]["arguments"] += args

    @property
    def calls(self) -> dict[int, dict]:
        """已聚合的 tool_call dict（按 index 键控）。"""
        return self._calls


def finalize_tool_calls(acc: ToolCallAccumulator) -> list[dict]:
    """聚合结果 → 标准 tool_calls 列表（自 harness :46-57 / :411-430 移植）。

    按 index 排序输出 ``{id, function: {name, arguments: <json str>}}``；
    arguments 先经 ``_normalize_arguments_str``（单引号字面量重序列化），
    再做嵌套 ``{"arguments": X}`` 解包（X 为 dict 直接用、为 str 保留），
    空值归为 ``{}``，非法 JSON 不因清洗破坏请求。
    """
    import json

    results: list[dict] = []
    for idx in sorted(acc.calls.keys()):
        raw = acc.calls[idx]
        args_raw = raw["function"]["arguments"] or ""
        normalized = _normalize_arguments_str(args_raw)
        args_str: str = str(normalized) if normalized else "{}"
        try:
            parsed = json.loads(args_str) if args_str else {}
        except (json.JSONDecodeError, ValueError):
            parsed = {}
        # 嵌套 {"arguments": X} 解包（模型偶发格式，_normalize_tool_args 语义）
        if isinstance(parsed, dict) and len(parsed) == 1 and "arguments" in parsed:
            inner = parsed["arguments"]
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except (json.JSONDecodeError, ValueError):
                    inner = None
            if isinstance(inner, dict):
                parsed = inner
            elif isinstance(inner, str):
                args_str = inner
                parsed = None
        if parsed is not None:
            args_str = json.dumps(parsed, ensure_ascii=False)
        results.append(
            {
                "id": raw.get("id") or f"call_{idx}",
                "function": {"name": raw["function"]["name"], "arguments": args_str},
            }
        )
    return results


def classify_outcome(finish_reason: str | None, *, saw_text_delta: bool) -> None:
    """finish_reason 归一化分型（delta Task 2.2）。

    正常（stop/tool_calls 或有正文 delta 的缺失 reason）返回 None；
    异常分类抛 typed error：length → OutputTruncated（预算复核/repair）、
    content_filter → ContentFiltered（不重试）、无 reason 且无正文 →
    EmptyLLMOutput（重试）——截断/空输出不再伪装成下游 JSONDecodeError。
    """
    from finance_agent.llm.errors import ContentFiltered, EmptyLLMOutput, OutputTruncated

    if finish_reason == "length":
        raise OutputTruncated("finish_reason=length：输出被截断（复核 max_tokens 或 repair）")
    if finish_reason == "content_filter":
        raise ContentFiltered("finish_reason=content_filter：内容被端点过滤，不重试")
    if not saw_text_delta and finish_reason not in ("tool_calls",):
        raise EmptyLLMOutput(
            f"无正文 delta 且 finish_reason={finish_reason!r}：模型思考后即止（incident 017），建议重试"
        )
    return None


def derive_output_budget(capability: Capability, requested: int | None = None) -> int:
    """输出预算派生（delta Task 2.3）：替换 16384 硬编码。

    显式 requested 优先（调用方明确意图）；否则用 capability.max_output
    （preset 已编码：方舟 GLM 因 reasoning_forced 共享配额给 16384，
    其余默认 8192）。reasoning 与正文共享配额的端点预算必须覆盖
    reasoning 峰值（incident 017：4096 下正文被挤空/截断）。
    """
    if requested is not None:
        return requested
    return capability.max_output


def normalize_exception(exc: Exception) -> LLMError:
    """litellm 异常 → typed error 归一化（delta Task 2.4）。

    调用方只见 LLMError 家族：retryable 标志驱动重试策略
    （ContentFiltered/AuthError 等不重试，RateLimit/Timeout 重试）。
    未知异常包装为 UnknownLLMError 保留上下文，不静默吞掉。
    """
    import litellm as _litellm

    from finance_agent.llm.errors import (
        AuthError,
        ContentFiltered,
        ContextOverflow,
        LLMError,
        LLMTimeoutError,
        ModelNotFound,
        RateLimitError,
        UnknownLLMError,
    )

    ex = _litellm.exceptions
    if isinstance(exc, ex.AuthenticationError):
        return AuthError(f"鉴权失败（检查 api_key）：{exc}")
    if isinstance(exc, ex.RateLimitError):
        return RateLimitError(f"限流：{exc}")
    if isinstance(exc, (ex.Timeout, ex.APIConnectionError)):
        return LLMTimeoutError(f"请求超时/连接失败：{exc}")
    if isinstance(exc, ex.NotFoundError):
        return ModelNotFound(f"模型/端点不存在：{exc}")
    if isinstance(exc, ex.ContextWindowExceededError):
        return ContextOverflow(f"上下文超窗：{exc}")
    if isinstance(exc, ex.ContentPolicyViolationError):
        return ContentFiltered(f"内容被端点过滤：{exc}")
    if isinstance(exc, LLMError):
        return exc
    return UnknownLLMError(f"{type(exc).__name__}: {exc}")


def guard_params_supported(
    capability: Capability,
    *,
    tools: list | None = None,
    tool_choice: str = "auto",
    response_format: str | None = None,
) -> None:
    """关键参数能力守卫（delta Task 2.5）：不支持显式抛错，不静默 drop。

    覆盖 tools / tool_choice=required / response_format=json_schema。
    （全局 drop_params 白名单化收口在 Task 5.1，此处先建立显式守卫。）
    """
    from finance_agent.llm.errors import UnsupportedCapabilityError

    if tools and capability.tools == "none":
        raise UnsupportedCapabilityError(
            f"provider 不支持工具调用（capability.tools=none），请求携带 {len(tools)} 个工具；"
            "请降级 action 文本协议或更换 profile"
        )
    if tool_choice == "required" and not capability.tool_choice_required:
        raise UnsupportedCapabilityError("provider 不支持 tool_choice=required")
    if response_format == "json_schema" and capability.json_schema != "strict_schema":
        raise UnsupportedCapabilityError(
            f"provider 不支持 strict schema（capability.json_schema={capability.json_schema}）"
        )


def apply_provider_options(profile: ModelProfile) -> dict[str, Any]:
    """provider_options 唯一消费点：校验并转为请求 kwargs（设计档案 §7.1）。

    registry schema 校验（非法值/未知 key → pydantic ValidationError）。
    provider=="deepseek" 且 capability.extra_body_allowed 时产出：
    - ``extra_body.thinking.type``：thinking 显式设置时携带
    - ``reasoning_effort``：显式设置时携带
    - ``suppress_temperature: True``：thinking=="enabled" 时携带 —— 内部
      契约标志（非 litellm 参数），gateway 据此不发送 temperature
      （deepseek thinking 模式拒收 temperature，对齐 legacy deep 分支）。
    其他 provider / 空 provider_options → ``{}``。
    """
    options = dict(getattr(profile, "provider_options", None) or {})
    if not options:
        return {}
    from finance_agent.llm.registry import PROVIDER_OPTIONS_SCHEMAS

    schema = PROVIDER_OPTIONS_SCHEMAS.get(profile.provider)
    if schema is None:
        return {}
    validated = schema.model_validate(options)
    if profile.provider != "deepseek" or not profile.capability.extra_body_allowed:
        return {}
    out: dict[str, Any] = {}
    thinking = getattr(validated, "thinking", None)
    effort = getattr(validated, "reasoning_effort", None)
    if thinking is not None:
        out["extra_body"] = {"thinking": {"type": thinking}}
    if effort is not None:
        out["reasoning_effort"] = effort
    # 内部契约标志：告知 gateway 不发送 temperature（非 litellm 参数）
    if thinking == "enabled":
        out["suppress_temperature"] = True
    return out


# API 形式 → litellm completion 的 ``api`` 参数（add-llm-api-form）：
# chat_completion→/chat/completions、messages→/v1/messages、responses→/responses。
# 仅在显式设置时返回 kwargs；空/未知 → {}（litellm 按 model 前缀自动路由）。
_API_FORM_TO_LITELLM_API = {
    "chat_completion": "chat",
    "messages": "messages",
    "responses": "responses",
}


def apply_api_form_kwargs(profile: ModelProfile) -> dict[str, Any]:
    api_form = getattr(profile, "api_form", None)
    if not api_form:
        return {}
    litellm_api = _API_FORM_TO_LITELLM_API.get(api_form)
    if litellm_api is None:
        return {}  # 上游已校验，防御性兜底
    return {"api": litellm_api}


# 非关键参数白名单（Task 8）：仅这些参数允许按 capability 剔除；
# 白名单外未知参数一律透传，由 litellm/端点原生报错（显式失败）。
_SOFT_DROP_WHITELIST = {"temperature", "top_p", "frequency_penalty", "presence_penalty"}


def _drop_unsupported(kwargs: dict[str, Any]) -> dict[str, Any]:
    """白名单内且 capability 明确不支持的非关键参数 → 剔除 + warning。

    YAGNI：当前唯一 capability 信号是 ``reasoning_forced``（方舟 GLM 类
    thinking 强制端点拒收 temperature）→ 仅据此剔除 temperature；
    top_p/frequency_penalty/presence_penalty 暂无 capability 信号，透传。
    """
    model = kwargs.get("model")
    if not isinstance(model, str):
        return kwargs
    if "temperature" in kwargs and capability_for_model(model).reasoning_forced:
        logger.warning("参数 temperature 被 adapter 白名单剔除(端点不支持)：model=%s", model)
        kwargs.pop("temperature")
    return kwargs


def _with_default_timeout(kwargs: dict[str, Any]) -> dict[str, Any]:
    """调用方未传 timeout 时注入默认值（incident 016/017 卡死防护）。

    请求无超时会令流式 chunk 停滞时调用永久挂起（016 线程死锁、
    017 思考后即止两类事故均表现为主管线卡死）。显式 timeout 不覆盖。
    """
    if "timeout" not in kwargs:
        kwargs["timeout"] = float(os.environ.get("LLM_TIMEOUT_SECONDS", "300"))
    return kwargs


def raw_completion(**kwargs: Any) -> Any:
    """adapter 内暴露 litellm.completion（gateway/probes 唯一入口）。

    确保 litellm 的 import 与运行时防护只存在于 adapter；业务/gateway/
    probe 经本函数调用，保证门禁（adapters 外禁 import litellm）可执行。
    """
    import litellm

    ensure_litellm_runtime()
    return litellm.completion(**_with_default_timeout(_drop_unsupported(dict(kwargs))))


def raw_stream(**kwargs: Any) -> Any:
    import litellm

    ensure_litellm_runtime()
    return litellm.completion(**_with_default_timeout(_drop_unsupported(dict(kwargs))), stream=True)


async def raw_acompletion(**kwargs: Any) -> Any:
    """adapter 内暴露异步 litellm.acompletion（harness 唯一入口）。"""
    import litellm

    ensure_litellm_runtime()
    return await litellm.acompletion(**_with_default_timeout(_drop_unsupported(dict(kwargs))))
