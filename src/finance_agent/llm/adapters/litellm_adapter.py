# src/finance_agent/llm/adapters/litellm_adapter.py
"""litellm adapter：唯一允许 import/配置 litellm 的地方（delta Task 1.4）。

运行时防护收口（design 决策 4）：
- ``disable_streaming_logging``：incident 016 —— litellm 流式每个 chunk 向
  全局 100 线程池提交 logging，worker 内 asyncio.run 新建 ProactorEventLoop，
  Windows/Py3.14 ``_fallback_socketpair`` 并发竞态令线程永久卡在 accept()
  （100 worker 全灭、退出 join 挂死）。项目 Langfuse 走自研 SDK，零损失。
- ``drop_params``：历史行为保留（阶段二 Task 2.5 白名单化后收紧）。
- litellm-langfuse 兼容补丁：1.85.x 与 langfuse 4.x 深度不兼容
  （version 属性、sdk_integration 参数等多处不匹配），noop 其 logger。

业务模块（llm.py / harness/litellm_client.py）经 ``ensure_litellm_runtime``
触发初始化，不各自设置 —— 防止防护配置漂移。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from finance_agent.llm.errors import LLMError
    from finance_agent.llm.types import Capability

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

        litellm.drop_params = True
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


def raw_completion(**kwargs: Any) -> Any:
    """adapter 内暴露 litellm.completion（gateway/probes 唯一入口）。

    确保 litellm 的 import 与运行时防护只存在于 adapter；业务/gateway/
    probe 经本函数调用，保证门禁（adapters 外禁 import litellm）可执行。
    """
    import litellm

    ensure_litellm_runtime()
    return litellm.completion(**kwargs)


def raw_stream(**kwargs: Any) -> Any:
    import litellm

    ensure_litellm_runtime()
    return litellm.completion(**kwargs, stream=True)
