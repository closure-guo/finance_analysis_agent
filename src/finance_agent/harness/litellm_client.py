"""LiteLLM 适配的 LLM 客户端。

用 litellm 替换 harness 默认的 httpx LLMClient，
支持 DeepSeek/Kimi 等 OpenAI 兼容 API，包括 thinking mode 和 tool calling。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC
from typing import Any

from finance_agent.harness.llm_client import LLMResponse
from finance_agent.harness.types import ToolCallRequest
from finance_agent.langfuse_tracing import truncate_for_trace

logger = logging.getLogger("finance_agent.harness.litellm_client")


def _resolve_key(api_key: str | None) -> str:
    """Resolve API key from explicit param or environment."""
    if api_key:
        return api_key
    env_key = os.environ.get("LLM_API_KEY", "")
    if env_key:
        return env_key
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _is_deepseek(model: str) -> bool:
    return "deepseek" in model.lower()


def _prompt_metadata(prompt_name: str | None, prompt_version: str | int | None) -> dict:
    """构造 generation metadata：仅在显式提供 prompt_name/version 时写入对应键。

    ADR-0015 Task 4：prompt 元数据可追溯。未传入时返回空 dict（与历史
    Langfuse 调用向后兼容）。与 llm.py 中同名 helper 对称，避免跨模块依赖。
    """
    md: dict = {}
    if prompt_name:
        md["prompt_name"] = prompt_name
    if prompt_version is not None:
        md["prompt_version"] = prompt_version
    return md


def _generation_metadata(
    prompt_name: str | None,
    prompt_version: str | int | None,
    agent: str | None = None,
) -> dict:
    """构造 generation metadata：prompt 元数据 + agent 过滤字段。

    agent 仅在显式提供时写入（与 _prompt_metadata 相同的向后兼容约定，
    不污染 metadata 命名空间）。与 llm.py 中同名 helper 同构，避免跨模块依赖。
    """
    md = _prompt_metadata(prompt_name, prompt_version)
    if agent:
        md["agent"] = agent
    return md


class LiteLLMClient:
    """用 litellm 实现的 LLM 客户端，接口与 harness LLMClient 一致。"""

    def __init__(
        self,
        model: str = "deepseek/deepseek-chat",
        api_key: str | None = None,
        base_url: str | None = None,
        thinking: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        prompt_name: str | None = None,
        prompt_version: str | int | None = None,
        agent: str | None = None,
    ):
        self.model = model
        self.api_key = _resolve_key(api_key)
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "")

        # 自动补 litellm provider 前缀：
        # 用户填了自定义 base_url（OpenAI 兼容端点）但模型名缺少 provider 前缀时，
        # litellm 无法识别调用协议。自定义 OpenAI 兼容端点统一用 openai/ 前缀路由。
        if self.base_url and self.model and "/" not in self.model:
            self.model = f"openai/{self.model}"
        # thinking 模式：None 时默认 "enabled"（向后兼容），由 build_agent 从 llm_config 注入
        self.thinking = thinking
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # prompt 元数据（ADR-0015 Task 4）：ReAct 链路的 system_prompt 来自单一
        # mode prompt（quick_mode / deep_mode / follow_up_mode），整个 agent 生命周期
        # 固定，故作为 client 实例字段；chat_stream 每次都挂到 generation metadata。
        # prompt_version 来自 Langfuse BasePrompt.version（int），本地兜底 "local"。
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        # agent 标签（Task 4）：harness 侧 generation observation 用 agent 名命名
        # （如 react_agent），使其在 Langfuse trace 中可按 agent 归属/过滤。
        self.agent = agent

        # Langfuse 可观测性（可选，ADR-0015）- 复用统一单例
        self._langfuse = None
        if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
            from finance_agent.langfuse_tracing import get_langfuse

            self._langfuse = get_langfuse()

    def _build_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        """构建 litellm 参数，处理 DeepSeek 特有配置。"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "timeout": 120,  # 整体请求超时（秒），防止 streaming 响应卡死
        }

        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["api_base"] = self.base_url

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        # DeepSeek: 开启原生思考模式（reasoning_content 与 content 分离下发）
        # 官方文档（2025-12 起更新）：思考模式支持工具调用，仅要求工具调用轮次
        # 在后续请求中回传 reasoning_content 字段（见 Message.to_api_dict / ContextManager）。
        # 思考模式不支持 temperature/top_p 等参数（设置不报错但不生效）。
        # thinking 由构造时传入（build_agent 从 llm_config 解析），None 时默认 "enabled"（向后兼容）。
        is_ds = _is_deepseek(self.model)
        effectiveThinking = self.thinking or "enabled"

        if is_ds:
            kwargs["extra_body"] = {"thinking": {"type": effectiveThinking}}
        else:
            kwargs["temperature"] = temperature

        return kwargs

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> AsyncIterator[LLMResponse]:
        """流式聊天请求，yield LLMResponse 对象。"""
        from datetime import datetime

        import litellm

        kwargs = self._build_kwargs(messages, tools, temperature, tool_choice)
        _start_time = datetime.now(UTC)
        _accumulated_text = ""
        _accumulated_reasoning = ""  # 累加 DeepSeek reasoning_content（原生思考增量）

        # Langfuse 追踪（ADR-0015）- start_as_current_observation 建立父子上下文，
        # 使本 generation 挂到 CallbackHandler 已建好的 react_loop span 下。
        # 保留 CM 引用以便 __exit__ 恢复 OTel 上下文（否则下次 chat_stream 会误挂父级）。
        # prompt_name/prompt_version（Task 4）：来自 client 实例字段，每次都挂到 metadata。
        # agent 标签（Task 4）：设 agent 时 observation 以 agent 命名（如 react_agent），
        # 否则回退 litellm:{model}。
        _lf_cm = None
        _lf_obs = None
        if self._langfuse:
            try:
                _lf_cm = self._langfuse.start_as_current_observation(
                    name=self.agent or f"litellm:{self.model}",
                    as_type="generation",
                    input={"messages": messages},
                    model=self.model,
                    metadata=_generation_metadata(
                        self.prompt_name, self.prompt_version, self.agent
                    ),
                )
                _lf_obs = _lf_cm.__enter__()
            except Exception as e:
                logger.warning("Langfuse 观测创建失败: %s", e)
                _lf_cm = None
                _lf_obs = None

        for attempt in range(self.max_retries):
            try:
                current_tool_calls: dict[int, dict[str, Any]] = {}

                response = await litellm.acompletion(**kwargs)

                # per-chunk 超时保护：单个 chunk 超过 60 秒未到达则终止流
                _chunk_iter = response.__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(_chunk_iter.__anext__(), timeout=60.0)
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        logger.warning("LLM streaming chunk 超时（60s 无数据），终止当前流")
                        break

                    choices = chunk.choices
                    if not choices:
                        continue

                    delta = choices[0].delta
                    finish_reason = choices[0].finish_reason

                    # 原生思考增量（DeepSeek reasoning_content）-- 先于 content 输出
                    reasoning = getattr(delta, "reasoning_content", None) or ""
                    if reasoning:
                        _accumulated_reasoning += reasoning  # 累加供 Langfuse 落 trace
                        yield LLMResponse(reasoning_delta=reasoning)

                    # 文本增量（content，最终回答）
                    text = getattr(delta, "content", None) or ""
                    if text:
                        _accumulated_text += text
                        yield LLMResponse(text_delta=text)

                    # Tool call 增量
                    tool_delta = getattr(delta, "tool_calls", None) or []
                    for t in tool_delta:
                        idx = t.index if hasattr(t, "index") else 0
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": "",
                                "function": {"name": "", "arguments": ""},
                            }

                        call = current_tool_calls[idx]
                        if t.id:
                            call["id"] = t.id
                        func = t.function
                        if func and func.name:
                            call["function"]["name"] = func.name
                        if func and func.arguments:
                            call["function"]["arguments"] += func.arguments

                    # 检查 finish_reason
                    if finish_reason == "tool_calls" and current_tool_calls:
                        parsed = self._parse_tool_calls(current_tool_calls)
                        self._finish_langfuse(
                            _lf_cm,
                            _lf_obs,
                            _accumulated_text,
                            chunk,
                            reasoning=_accumulated_reasoning,
                            tool_calls=parsed,
                        )
                        yield LLMResponse(tool_calls=parsed, is_finished=True)
                        return

                    if finish_reason == "stop":
                        if current_tool_calls:
                            parsed = self._parse_tool_calls(current_tool_calls)
                            self._finish_langfuse(
                                _lf_cm,
                                _lf_obs,
                                _accumulated_text,
                                chunk,
                                reasoning=_accumulated_reasoning,
                                tool_calls=parsed,
                            )
                            yield LLMResponse(tool_calls=parsed, is_finished=True)
                        else:
                            self._finish_langfuse(
                                _lf_cm,
                                _lf_obs,
                                _accumulated_text,
                                chunk,
                                reasoning=_accumulated_reasoning,
                            )
                            yield LLMResponse(is_finished=True)
                        return

                # 流结束但没有明确的 finish_reason
                if current_tool_calls:
                    parsed = self._parse_tool_calls(current_tool_calls)
                    self._finish_langfuse(
                        _lf_cm,
                        _lf_obs,
                        _accumulated_text,
                        None,
                        reasoning=_accumulated_reasoning,
                        tool_calls=parsed,
                    )
                    yield LLMResponse(tool_calls=parsed, is_finished=True)
                else:
                    self._finish_langfuse(
                        _lf_cm, _lf_obs, _accumulated_text, None, reasoning=_accumulated_reasoning
                    )
                    yield LLMResponse(is_finished=True)
                return

            except Exception as e:
                logger.warning(f"LLM 请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                else:
                    if _lf_cm and _lf_obs:
                        try:
                            _lf_obs.update(output={"error": str(e)}, level="ERROR")
                            _lf_cm.__exit__(None, None, None)
                            if self._langfuse:
                                self._langfuse.flush()
                        except Exception as e2:  # noqa: S110
                            logger.debug("Langfuse 错误观测收尾失败: %s", e2)
                    # 重试耗尽：raise 异常而非 yield 错误文本，使 Agent 主循环能正确捕获
                    raise

    def _finish_langfuse(
        self,
        cm,
        obs,
        text: str,
        last_chunk,
        reasoning: str = "",
        tool_calls: list[ToolCallRequest] | None = None,
    ) -> None:
        """流结束后更新 Langfuse 观测并退出上下文（恢复 OTel 父级）。

        tool_calls 仅在工具调用分支传入（list[ToolCallRequest]），纯文本分支传 None。
        output 结构：{answer, reasoning, [tool_calls]}；无 tool_calls 时不写该字段，
        保持 Task 2 已落地的 {answer, reasoning} 结构向后兼容。
        """
        if not cm or not obs:
            return
        try:
            usage = {}
            if last_chunk and hasattr(last_chunk, "usage") and last_chunk.usage:
                u = last_chunk.usage
                usage = {
                    "input": getattr(u, "prompt_tokens", 0),
                    "output": getattr(u, "completion_tokens", 0),
                    "total": getattr(u, "total_tokens", 0),
                }
            # output 结构化：answer + reasoning（裁剪防撑爆 Langfuse span）
            output_obj: dict[str, Any] = {
                "answer": truncate_for_trace(text),
                "reasoning": truncate_for_trace(reasoning),
            }
            # 仅有工具调用时才写入 tool_calls 字段（保持纯文本分支 output 结构不变）
            if tool_calls:
                output_obj["tool_calls"] = [
                    {
                        "name": tc.name,
                        # ToolCallRequest.arguments 是 dict，序列化为紧凑 JSON 字符串保留语义
                        "arguments": truncate_for_trace(
                            json.dumps(tc.arguments, ensure_ascii=False, separators=(",", ":"))
                        ),
                    }
                    for tc in tool_calls
                ]
            obs.update(output=output_obj, usage_details=usage)
            cm.__exit__(None, None, None)
            if self._langfuse:
                self._langfuse.flush()
        except Exception as e:
            logger.warning("Langfuse 观测更新失败: %s", e)

    def _parse_tool_calls(self, raw_calls: dict[int, dict[str, Any]]) -> list[ToolCallRequest]:
        """解析累积的 tool_call 数据。"""
        results = []
        for idx in sorted(raw_calls.keys()):
            raw = raw_calls[idx]
            try:
                args = (
                    json.loads(raw["function"]["arguments"]) if raw["function"]["arguments"] else {}
                )
            except json.JSONDecodeError:
                args = {}
            results.append(
                ToolCallRequest(
                    id=raw.get("id", f"call_{idx}"),
                    name=raw["function"]["name"],
                    arguments=args,
                )
            )
        return results

    def __repr__(self) -> str:
        return f"LiteLLMClient(model={self.model})"
