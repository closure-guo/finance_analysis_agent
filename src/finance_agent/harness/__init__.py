"""
Mini Harness - 基于 Claude Code 设计的简化版 Agent Harness

核心模块：
- loop.Agent: ReAct 主循环 Agent
- tool_manager: 工具注册与内置工具 (@tool 装饰器)
- context.ContextManager: 上下文与 Token 预算管理
- permissions.PermissionChecker: Deny-first 权限系统
- llm_client.LLMClient: 流式 LLM 客户端
- hooks.HookManager: 生命周期事件系统
- types: 所有核心类型定义

快速开始：
    from finance_agent.harness import create_agent

    agent = create_agent(model="gpt-4o-mini")
    async for event in agent.run("帮我读取 main.py 的内容"):
        print(event.content)
"""

__version__ = "0.1.0"

# 核心入口
# 主要子系统（按需导入）
from finance_agent.harness.context import ContextBudget, ContextManager
from finance_agent.harness.hooks import HookManager, HookPoint
from finance_agent.harness.llm_client import LLMClient
from finance_agent.harness.loop import Agent, create_agent
from finance_agent.harness.permissions import PermissionChecker, PermissionMode
from finance_agent.harness.tool_manager import ToolManager, clear_registry, register_tool, tool

# 类型
from finance_agent.harness.types import (
    ActionType,
    AgentRunResult,
    Message,
    PermissionRequest,
    RiskLevel,
    Role,
    StreamEvent,
    ToolCallRequest,
    ToolResult,
    ToolSchema,
)

__all__ = [
    # 核心
    "Agent",
    "create_agent",
    # 子系统
    "ContextManager",
    "ContextBudget",
    "PermissionChecker",
    "PermissionMode",
    "ToolManager",
    "tool",
    "register_tool",
    "clear_registry",
    "LLMClient",
    "HookManager",
    "HookPoint",
]
