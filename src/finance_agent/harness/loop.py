"""
Mini Harness - ReAct Loop
ReAct 主循环：Agent 的心脏

设计来源：Claude Code 的 query.ts -- "5 行骨架 + 1695 行基础设施"

骨架代码（Claude Code 原始伪代码）：
    while (true) {
      // 1. Reason + Act: 调用模型
      for await (const msg of callModel({...})) {
        if (msg has tool_use blocks) needsFollowUp = true
      }
      // 2. Observe: 无工具调用 -> 完成
      if (!needsFollowUp) return { reason: 'completed' }
      // 3. 执行工具，追加结果，继续循环
      for await (const update of runTools(...)) { ... }
      state = { messages: [...old, ...assistant, ...toolResults] }
    }

我们的实现保留了相同的骨架结构，但增加了：
- 流式事件输出（async generator）
- Token 预算管理
- 权限检查
- 生命周期钩子
- 最大迭代限制（防止无限循环）
- 错误恢复
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from finance_agent.harness.context import ContextBudget, ContextManager
from finance_agent.harness.hooks import HookManager
from finance_agent.harness.llm_client import LLMClient
from finance_agent.harness.permissions import PermissionChecker
from finance_agent.harness.tool_manager import ToolManager
from finance_agent.harness.types import (
    ActionType,
    HookPoint,
    PermissionMode,
    PermissionRequest,
    StreamEvent,
    ToolCallRequest,
    ToolResult,
)

logger = logging.getLogger("finance_agent.harness.loop")


# ───────────────────────────────────────────────
# 默认系统提示
# ───────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """你是一个智能助手，可以通过工具解决复杂问题。

工作方式：
1. 分析用户需求，决定是否需要使用工具
2. 如需工具，调用合适的工具获取信息
3. 根据工具结果继续推理或给出最终回答
4. 你可以多次调用工具，直到获得足够信息

规则：
- 优先使用工具获取实时信息，不要依赖训练数据的过时知识
- 每次只调用一个工具，等待结果后再决定下一步
- 如果任务复杂，先制定计划再执行
- 最终回答使用用户使用的语言
- 工具调用之间用 <thinking> 标签展示推理过程
"""


# ───────────────────────────────────────────────
# Agent 主类
# ───────────────────────────────────────────────


class Agent:
    """
    Mini Harness Agent -- 简化版 ReAct 循环实现

    架构组成：
    - ContextManager: 对话历史 + Token 预算
    - ToolManager: 工具注册 + 执行
    - PermissionChecker: 权限决策
    - LLMClient: 模型调用
    - HookManager: 生命周期事件

    使用方法：
        agent = Agent(model="gpt-4o-mini")
        agent.tools.register_all_builtins()

        async for event in agent.run("帮我读取 main.py 的内容"):
            print(event.content)
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        permission_mode: PermissionMode = PermissionMode.YOLO,
        max_iterations: int = 15,
        context_budget: ContextBudget | None = None,
        interactive_permission: Callable[[PermissionRequest], Any] | None = None,
        llm: LLMClient | None = None,
    ):
        # 初始化各子系统
        self.context = ContextManager(budget=context_budget or ContextBudget())
        self.llm = llm or LLMClient(model=model, api_key=api_key, base_url=base_url)
        self.tools = ToolManager()
        self.hooks = HookManager()

        # 权限系统
        self.permission_callback = interactive_permission
        self.permissions = PermissionChecker(
            mode=permission_mode,
            interactive_callback=self._default_permission_handler,
        )
        self.tools.checker = self.permissions

        # 配置
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.context.set_system(self.system_prompt)

        # 运行时状态
        self.session_id: str = str(uuid.uuid4())[:8]
        self._running = False

    # ── 权限处理 ──

    async def _default_permission_handler(self, request: PermissionRequest) -> bool:
        """
        默认权限处理器。

        优先级：
        1. 外部传入的交互式回调
        2. 自动拒绝（安全默认）

        建议：在生产环境中传入交互式回调（如 CLI 确认、WebSocket 请求等）
        """
        if self.permission_callback:
            return await self.permission_callback(request)

        # 无交互能力时：读取操作自动允许，写入操作拒绝
        if request.risk_level in (
            PermissionChecker.RiskLevel.READ if hasattr(PermissionChecker, "RiskLevel") else []
        ):
            return True

        logger.warning(f"权限请求（无交互回调，默认拒绝）: {request.describe()}")
        return False

    # ── 核心运行入口 ──

    async def run(self, user_input: str) -> AsyncIterator[StreamEvent]:
        """
        运行 Agent -- 核心入口

        参数：
            user_input: 用户输入文本

        返回：
            异步生成器，yield StreamEvent

        使用示例：
            async for event in agent.run("帮我分析一下这个文件"):
                if event.event_type == ActionType.THINK:
                    print(f"思考: {event.content}")
                elif event.event_type == ActionType.TOOL_CALL:
                    print(f"调用工具: {event.tool_call.name}")
                elif event.event_type == ActionType.ANSWER:
                    print(f"回答: {event.content}")
        """
        if self._running:
            yield StreamEvent.error("Agent 正在运行中，请等待当前任务完成")
            return

        self._running = True
        start_time = time.time()
        iterations = 0

        # 1. 触发会话开始钩子
        await self.hooks.emit(
            HookPoint.ON_SESSION_START,
            {
                "session_id": self.session_id,
                "user_input": user_input,
            },
        )

        # 2. 追加用户消息到上下文
        self.context.append_user(user_input)

        try:
            # ═══════════════════════════════════
            # ReAct 主循环 -- Claude Code 的核心
            # ═══════════════════════════════════
            while iterations < self.max_iterations:
                iterations += 1
                logger.debug(f"=== ReAct 循环第 {iterations} 轮 ===")

                # ── 检查 token 预算，如需则压缩 ──
                compacted = await self.context.maybe_compact()
                if compacted:
                    await self.hooks.emit(
                        HookPoint.PRE_COMPACT,
                        {
                            "session_id": self.session_id,
                            "context": self.context,
                        },
                    )

                # ── 获取工具 schemas ──
                tool_schemas = self.tools.get_schemas_for_llm()

                # ── 构建 API 消息 ──
                api_messages = self.context.build_messages_for_api()

                # ── 调用 LLM（流式）──
                assistant_text = ""
                pending_tool_calls: list[ToolCallRequest] = []

                async for chunk in self.llm.chat_stream(
                    messages=api_messages,
                    tools=tool_schemas if tool_schemas else None,
                ):
                    if chunk.text_delta:
                        # 流式文本增量
                        assistant_text += chunk.text_delta

                        # 提取 <thinking> 标签内容作为 think 事件
                        think_content = self._extract_thinking(assistant_text)
                        if think_content:
                            yield StreamEvent.think(think_content)

                        # 普通文本作为增量输出
                        yield StreamEvent(
                            event_type=ActionType.ANSWER,
                            content=chunk.text_delta,
                        )

                    if chunk.tool_calls:
                        pending_tool_calls = chunk.tool_calls
                        for tc in pending_tool_calls:
                            yield StreamEvent.for_tool_call(tc)

                    if chunk.is_finished:
                        break

                # ── 追加助手消息到上下文 ──
                tool_calls_raw = []
                for tc in pending_tool_calls:
                    tool_calls_raw.append(
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": str(tc.arguments)},
                        }
                    )
                self.context.append_assistant(
                    assistant_text, tool_calls_raw if tool_calls_raw else None
                )

                # ── 检查是否有工具调用 ──
                if not pending_tool_calls:
                    # 无工具调用 -> 任务完成
                    logger.debug("无工具调用，循环结束")
                    break

                # ── 执行工具调用 ──
                for tc in pending_tool_calls:
                    # 发送权限请求事件（消费者可展示确认 UI）
                    risk = self.permissions._assess_risk(tc.name, tc.arguments)
                    perm_req = PermissionRequest(
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        risk_level=risk,
                        reason=f"工具 '{tc.name}' 需要权限",
                    )
                    yield StreamEvent.permission_required(perm_req)

                    # 权限检查
                    permitted = await self.permissions.check(tc.name, tc.arguments)
                    if not permitted:
                        result = ToolResult(
                            tool_call_id=tc.id,
                            name=tc.name,
                            output=f"权限被拒绝：工具 '{tc.name}' 的执行未获授权。",
                            is_error=True,
                            permission_granted=False,
                        )
                        self.context.append_tool_result(tc.id, result.output, is_error=True)
                        yield StreamEvent.for_tool_result(result)
                        continue

                    # 触发 pre_tool_use 钩子
                    await self.hooks.emit(
                        HookPoint.PRE_TOOL_USE,
                        {
                            "session_id": self.session_id,
                            "tool_name": tc.name,
                            "arguments": tc.arguments,
                            "tool_call_id": tc.id,
                        },
                    )

                    # 执行工具
                    result = await self.tools.execute(tc.id, tc.name, tc.arguments)

                    # 追加工具结果到上下文
                    self.context.append_tool_result(tc.id, result.output, result.is_error)

                    # 触发 post_tool_use 钩子
                    await self.hooks.emit(
                        HookPoint.POST_TOOL_USE,
                        {
                            "session_id": self.session_id,
                            "tool_name": tc.name,
                            "arguments": tc.arguments,
                            "result": result,
                        },
                    )

                    yield StreamEvent.for_tool_result(result)

            # 循环结束
            if iterations >= self.max_iterations:
                yield StreamEvent.error(f"达到最大迭代次数 ({self.max_iterations})，任务被截断")

        except Exception as e:
            logger.exception("Agent 运行时错误")
            await self.hooks.emit(
                HookPoint.ON_ERROR,
                {
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            yield StreamEvent.error(f"运行时错误: {e}")

        finally:
            # 会话结束钩子
            duration_ms = int((time.time() - start_time) * 1000)
            await self.hooks.emit(
                HookPoint.ON_SESSION_END,
                {
                    "session_id": self.session_id,
                    "iterations": iterations,
                    "duration_ms": duration_ms,
                },
            )
            self._running = False

    # ── 便捷方法 ──

    async def run_sync(self, user_input: str) -> str:
        """
        同步风格运行 -- 收集所有事件，返回最终回答

        用于不需要流式处理的场景。
        """
        final_answer_parts = []
        async for event in self.run(user_input):
            if event.event_type == ActionType.ANSWER:
                final_answer_parts.append(event.content)
        return "".join(final_answer_parts)

    def add_tool(self, func: Callable, name: str | None = None) -> None:
        """注册自定义工具"""
        self.tools.register(func, name=name)

    def on(self, hook_point: HookPoint, callback: Callable) -> None:
        """订阅生命周期事件"""
        self.hooks.on(hook_point, callback)

    # ── 内部工具 ──

    @staticmethod
    def _extract_thinking(text: str) -> str | None:
        """从助手输出中提取 <thinking> 标签内容"""
        if "<thinking>" in text and "</thinking>" in text:
            start = text.index("<thinking>") + len("<thinking>")
            end = text.index("</thinking>")
            return text[start:end].strip()
        return None

    def __repr__(self) -> str:
        return (
            f"Agent(model={self.llm.model}, "
            f"tools={len(self.tools.tools)}, "
            f"mode={self.permissions.mode.value}, "
            f"session={self.session_id})"
        )


# ───────────────────────────────────────────────
# 快速构建函数
# ───────────────────────────────────────────────


def create_agent(
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    system_prompt: str | None = None,
    permission_mode: str = "normal",
    with_builtins: bool = True,
    **kwargs: Any,
) -> Agent:
    """
    快速创建 Agent 实例

    参数：
        model: LLM 模型名称
        api_key: API 密钥（默认从环境变量读取）
        system_prompt: 自定义系统提示
        permission_mode: 权限模式 (ask/normal/auto_edit/auto/yolo)
        with_builtins: 是否注册内置工具
        **kwargs: 传递给 Agent 的其他参数

    示例：
        agent = create_agent(model="gpt-4o", permission_mode="auto_edit")
        result = await agent.run_sync("帮我读取 README.md")
    """
    mode = PermissionMode(permission_mode)

    agent = Agent(
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
        permission_mode=mode,
        **kwargs,
    )

    if with_builtins:
        agent.tools.register_all_builtins()

    return agent
