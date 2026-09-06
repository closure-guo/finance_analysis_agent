"""
Mini Harness - Tool Manager
工具管理器：注册、分发、执行工具

设计原则（来自 Claude Code）：
- 装饰器注册：@tool 标记任何函数为 Agent 可用工具
- Schema 自动生成：从函数签名推导 JSON Schema，无需手写
- 统一执行入口：所有工具调用经过相同的生命周期（权限检查 -> Hook -> 执行 -> 结果处理）
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from finance_agent.harness.llm_client import build_schema_from_function
from finance_agent.harness.permissions import PermissionChecker
from finance_agent.harness.types import (
    PermissionMode,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger("finance_agent.harness.tools")


# ───────────────────────────────────────────────
# 工具装饰器
# ───────────────────────────────────────────────

# 全局工具注册表
_TOOL_REGISTRY: dict[str, Callable] = {}
_TOOL_SCHEMAS: dict[str, ToolSchema] = {}


def tool(name: str | None = None, description: str | None = None):
    """
    工具装饰器 -- 将函数注册为 Agent 可用工具。

    用法：
        @tool()
        async def read_file(path: str, limit: int = 100) -> str:
            '''读取文件内容

            Args:
                path: 文件路径
                limit: 最大读取行数
            '''
            ...

    自动推导：
    - 工具名称（函数名或指定 name）
    - 描述（docstring 或指定 description）
    - 参数 Schema（函数签名）
    """

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        schema = build_schema_from_function(func, name=tool_name, description=description)

        # 包装函数：统一异常处理
        async def wrapper(**kwargs) -> str:
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(**kwargs)
                else:
                    result = func(**kwargs)
                return str(result) if result is not None else ""
            except Exception as e:
                return f"[错误] {type(e).__name__}: {e}"

        # 保留元数据
        wrapper.__name__ = tool_name
        wrapper.__doc__ = func.__doc__
        wrapper._is_tool = True  # type: ignore
        wrapper._schema = schema  # type: ignore

        _TOOL_REGISTRY[tool_name] = wrapper
        _TOOL_SCHEMAS[tool_name] = schema

        return func  # 返回原函数，不影响正常使用

    return decorator


def register_tool(func: Callable, name: str | None = None, description: str | None = None) -> None:
    """函数式注册工具（不使用装饰器时）"""
    tool(name=name, description=description)(func)


def clear_registry() -> None:
    """清空注册表（测试用）"""
    _TOOL_REGISTRY.clear()
    _TOOL_SCHEMAS.clear()


# ───────────────────────────────────────────────
# 工具管理器
# ───────────────────────────────────────────────


class ToolManager:
    """
    工具管理器 -- 工具注册、分发、执行

    职责：
    1. 维护工具注册表
    2. 提供工具 schema 列表（供 LLM function calling 使用）
    3. 执行工具调用（经过权限检查和生命周期钩子）
    4. 收集执行统计
    """

    def __init__(self, permission_checker: PermissionChecker | None = None):
        self.checker = permission_checker or PermissionChecker(mode=PermissionMode.NORMAL)
        self.tools: dict[str, Callable] = dict(_TOOL_REGISTRY)
        self.schemas: dict[str, ToolSchema] = dict(_TOOL_SCHEMAS)
        self.stats: dict[str, dict[str, Any]] = {}

    # ── 注册 ──

    def register(self, func: Callable, name: str | None = None) -> None:
        """注册单个工具"""
        n = name or func.__name__
        schema = build_schema_from_function(func, name=n)
        self.tools[n] = func
        self.schemas[n] = schema
        logger.debug(f"注册工具: {n}")

    def register_all_builtins(self) -> None:
        """注册所有内置工具（本包不提供内置工具，此方法为 no-op）"""
        pass

    def get_schemas_for_llm(self) -> list[dict[str, Any]]:
        """获取 LLM function calling 格式的工具列表"""
        return [s.to_function_dict() for s in self.schemas.values()]

    def get_tool_names(self) -> list[str]:
        return list(self.tools.keys())

    def is_streaming(self, name: str) -> bool:
        """检查工具是否为流式工具（async generator）。

        经 functools.unwrap 透传 __wrapped__：add-toolcall-evaluation 的工具调用
        埋点（agent_factory._trace_tool）用 wraps 包装异步生成器后，裸
        inspect.isasyncgenfunction 会误判为非流式（执行路径退化、THINK 丢弃），
        必须穿透包装器判定。未包装的注册行为不变。
        """
        import inspect

        func = self.tools.get(name)
        if func is None:
            return False
        # functools.wraps 包装器以 __wrapped__ 指向原函数（Py3.14 stdlib 无
        # functools.unwrap，直接用属性穿透）；未包装时取自身
        return inspect.isasyncgenfunction(getattr(func, "__wrapped__", func))

    # ── 执行 ──

    async def execute(
        self,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """
        执行工具调用 -- 统一入口

        执行流程：
        1. 检查工具是否存在
        2. 权限检查（Deny-first）
        3. 执行工具函数
        4. 包装结果
        """
        start = time.time()

        # 1. 检查工具是否存在
        if name not in self.tools:
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"[错误] 工具 '{name}' 不存在。可用工具: {', '.join(self.tools.keys())}",
                is_error=True,
                duration_ms=0,
            )

        # 2. 权限检查
        permitted = await self.checker.check(name, arguments)
        if not permitted:
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"[已拒绝] 工具 '{name}' 的权限请求被拒绝。",
                is_error=True,
                duration_ms=0,
                permission_granted=False,
            )

        # 3. 执行
        try:
            func = self.tools[name]
            if asyncio.iscoroutinefunction(func):
                output = await func(**arguments)
            else:
                output = func(**arguments)

            duration = int((time.time() - start) * 1000)

            # 统计
            if name not in self.stats:
                self.stats[name] = {"calls": 0, "errors": 0, "total_ms": 0}
            self.stats[name]["calls"] += 1
            self.stats[name]["total_ms"] += duration

            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=str(output) if output is not None else "",
                duration_ms=duration,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            if name in self.stats:
                self.stats[name]["errors"] += 1

            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"[错误] {type(e).__name__}: {e}",
                is_error=True,
                duration_ms=duration,
            )

    async def execute_stream(
        self,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ):
        """
        执行流式工具（async generator） -- yield StreamEvent，返回最终 ToolResult。

        流式工具 yield StreamEvent（PROGRESS / TOOL_RESULT），
        本方法透传 PROGRESS 事件，提取最终 TOOL_RESULT 返回。
        """
        from finance_agent.harness.types import ActionType

        start = time.time()

        # 1. 检查工具是否存在
        if name not in self.tools:
            yield self._error_result(tool_call_id, name, f"工具 '{name}' 不存在")
            return

        # 2. 权限检查
        permitted = await self.checker.check(name, arguments)
        if not permitted:
            yield self._error_result(
                tool_call_id, name, f"工具 '{name}' 的权限请求被拒绝", permission_granted=False
            )
            return

        # 3. 执行流式工具
        try:
            func = self.tools[name]
            gen = func(**arguments)

            final_result: ToolResult | None = None

            async for event in gen:
                if event.event_type == ActionType.PROGRESS:
                    yield event
                elif event.event_type == ActionType.THINK:
                    # 透传管线节点思考（含 node metadata），供 SSE 按 agent 分组
                    # （与 loop.py 同步：此前只透传 PROGRESS/TOOL_RESULT，丢 THINK）
                    yield event
                elif event.event_type == ActionType.TOOL_RESULT:
                    # 流式工具的最终结果
                    if event.tool_result:
                        final_result = event.tool_result
                    yield event

            # 统计
            duration = int((time.time() - start) * 1000)
            if name not in self.stats:
                self.stats[name] = {"calls": 0, "errors": 0, "total_ms": 0}
            self.stats[name]["calls"] += 1
            self.stats[name]["total_ms"] += duration

            if final_result is None:
                # 流式工具未返回 TOOL_RESULT，构建一个
                final_result = ToolResult(
                    tool_call_id=tool_call_id,
                    name=name,
                    output="",
                    duration_ms=duration,
                )

            yield final_result

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            if name in self.stats:
                self.stats[name]["errors"] += 1
            yield self._error_result(tool_call_id, name, f"{type(e).__name__}: {e}", duration)

    def _error_result(
        self,
        tool_call_id: str,
        name: str,
        message: str,
        duration_ms: int = 0,
        permission_granted: bool = True,
    ) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call_id,
            name=name,
            output=f"[错误] {message}",
            is_error=True,
            duration_ms=duration_ms,
            permission_granted=permission_granted,
        )

    def __repr__(self) -> str:
        return f"ToolManager(tools={len(self.tools)}, schemas={len(self.schemas)})"
