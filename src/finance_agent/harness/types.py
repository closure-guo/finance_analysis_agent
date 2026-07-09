"""
Mini Harness - Core Types
基于 Claude Code 设计的简化版 Agent Harness 类型系统

核心设计原则：
- 模型负责推理，基础设施负责控制
- 所有状态变更都通过事件驱动
- Token 是零和预算，每处设计都考虑上下文经济性
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Protocol,
    TypedDict,
)

# ───────────────────────────────────────────────
# 基础枚举
# ───────────────────────────────────────────────


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ActionType(str, Enum):
    """ReAct 循环中 Agent 的单步动作类型"""

    THINK = "think"  # 内部思考（Claude Code 的 <thinking>）
    TOOL_CALL = "tool_call"  # 请求调用工具
    TOOL_RESULT = "tool_result"  # 工具执行结果
    ANSWER = "answer"  # 最终回答
    ERROR = "error"  # 执行错误
    PROGRESS = "progress"  # 流式工具的中间进度
    TOOL_METADATA = "tool_metadata"  # 工具的结构化元数据（不进入 LLM 上下文）


class PermissionMode(str, Enum):
    """权限模式：从完全手动到完全自动的光谱"""

    ASK = "ask"  # 所有操作都询问（最保守）
    NORMAL = "normal"  # 写操作需确认，读操作自动
    AUTO_EDIT = "auto_edit"  # 自动批准文件编辑，其他需确认
    AUTO = "auto"  # AI 判断哪些需要审批
    YOLO = "yolo"  # 跳过所有确认（危险模式）


class HookPoint(str, Enum):
    """生命周期钩子挂载点（精简自 Claude Code 的 27 种）"""

    ON_SESSION_START = "on_session_start"
    ON_SESSION_END = "on_session_end"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    ON_PERMISSION_REQUIRED = "on_permission_required"
    ON_ERROR = "on_error"


# ───────────────────────────────────────────────
# 核心数据结构
# ───────────────────────────────────────────────


@dataclass
class Message:
    """
    对话消息 -- 兼容 OpenAI/Claude API 格式

    Claude Code 的设计洞察：消息不只是 (role, content) 元组，
    而是包含完整元数据的上下文单元。tool_calls 和 tool_call_id
    使消息自描述，无需外部状态就能重建对话历史。
    """

    role: Role
    content: str
    tool_calls: list[ToolCallDict] | None = None
    tool_call_id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_api_dict(self) -> dict[str, Any]:
        """转换为 LLM API 请求格式"""
        result: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    def __repr__(self) -> str:
        preview = self.content[:60].replace("\n", " ") if self.content else ""
        if len(self.content) > 60:
            preview += "..."
        return f"Message({self.role.value}: {preview})"


@dataclass
class ToolCallRequest:
    """LLM 发起的工具调用请求"""

    id: str
    name: str
    arguments: dict[str, Any]  # 已 JSON parse 后的参数

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> ToolCallRequest:
        """从 API response 中解析 tool_call 块"""
        return cls(
            id=raw.get("id", ""),
            name=raw.get("function", {}).get("name", ""),
            arguments=raw.get("function", {}).get("arguments", {}),
        )


@dataclass
class ToolResult:
    """
    工具执行结果

    Claude Code 的设计：tool_result 需要包含足够元数据
    用于权限审计、错误恢复、性能分析，而不仅是 output 字符串。
    """

    tool_call_id: str
    name: str
    output: str
    is_error: bool = False
    duration_ms: int | None = None
    permission_granted: bool = True  # 权限是否被批准
    metadata: dict[str, Any] | None = None  # 新增：结构化数据，不进入 LLM 上下文

    def to_message(self) -> Message:
        """转换为 tool 角色消息，供下一轮 LLM 消费"""
        return Message(
            role=Role.TOOL,
            content=self.output,
            tool_call_id=self.tool_call_id,
        )


@dataclass
class ToolSchema:
    """工具的 JSON Schema 描述，用于注册到 LLM function calling"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object

    def to_function_dict(self) -> dict[str, Any]:
        """转换为 OpenAI function 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class PermissionRequest:
    """权限请求 -- 需要用户/系统决策的操作拦截"""

    tool_name: str
    arguments: dict[str, Any]
    risk_level: RiskLevel
    reason: str  # 为什么需要权限

    def describe(self) -> str:
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"[{self.risk_level.value}] {self.tool_name}({args_str}) - {self.reason}"


class RiskLevel(str, Enum):
    """操作风险等级"""

    READ = "read"  # 只读，无风险
    LOW = "low"  # 低风险（如读取非敏感文件）
    MEDIUM = "medium"  # 中风险（如编辑已有文件）
    HIGH = "high"  # 高风险（如执行 shell 命令）
    CRITICAL = "critical"  # 极高风险（如删除文件、网络请求）


# ───────────────────────────────────────────────
# ReAct 循环事件（流式输出给消费者）
# ───────────────────────────────────────────────


@dataclass
class StreamEvent:
    """流式事件 -- ReAct 循环向外部消费者发送的增量更新"""

    event_type: ActionType
    content: str
    tool_call: ToolCallRequest | None = None
    tool_result: ToolResult | None = None
    permission_request: PermissionRequest | None = None
    metadata: dict[str, Any] | None = None  # 新增

    @classmethod
    def think(cls, content: str) -> StreamEvent:
        return cls(event_type=ActionType.THINK, content=content)

    @classmethod
    def for_tool_call(cls, call: ToolCallRequest) -> StreamEvent:
        return cls(event_type=ActionType.TOOL_CALL, content=f"调用 {call.name}", tool_call=call)

    @classmethod
    def for_tool_result(cls, result: ToolResult) -> StreamEvent:
        return cls(
            event_type=ActionType.TOOL_RESULT, content=result.output[:200], tool_result=result
        )

    @classmethod
    def answer(cls, content: str) -> StreamEvent:
        return cls(event_type=ActionType.ANSWER, content=content)

    @classmethod
    def error(cls, content: str) -> StreamEvent:
        return cls(event_type=ActionType.ERROR, content=content)

    @classmethod
    def permission_required(cls, req: PermissionRequest) -> StreamEvent:
        return cls(event_type=ActionType.TOOL_CALL, content=req.describe(), permission_request=req)

    @classmethod
    def progress(cls, content: str, metadata: dict[str, Any] | None = None) -> StreamEvent:
        return cls(event_type=ActionType.PROGRESS, content=content, metadata=metadata)

    @classmethod
    def tool_metadata(cls, metadata: dict[str, Any]) -> StreamEvent:
        return cls(event_type=ActionType.TOOL_METADATA, content="", metadata=metadata)


# ───────────────────────────────────────────────
# 运行结果
# ───────────────────────────────────────────────


@dataclass
class AgentRunResult:
    """Agent 单次运行的完整结果"""

    final_answer: str = ""
    messages: list[Message] = field(default_factory=list)
    iterations: int = 0
    total_tokens_used: int = 0
    is_truncated: bool = False  # 是否因达到 max_iterations 而截断
    errors: list[str] = field(default_factory=list)
    duration_ms: int | None = None


# ────────────────────────────────────────────
# TypedDict（用于 API 兼容性）
# ────────────────────────────────────────────


class ToolCallDict(TypedDict, total=False):
    """OpenAI API 格式的 tool_call 字典"""

    id: str
    type: str
    function: dict[str, Any]


class FunctionSchema(TypedDict, total=False):
    """JSON Schema 的 function 定义部分"""

    name: str
    description: str
    parameters: dict[str, Any]


# ────────────────────────────────────────────
# 协议（接口定义）
# ────────────────────────────────────────────


class ToolCallable(Protocol):
    """工具函数协议 -- 任何匹配此签名的函数都可注册为工具"""

    __name__: str
    __doc__: str | None

    async def __call__(self, **kwargs: Any) -> str: ...


class PermissionHandler(Protocol):
    """权限决策器协议 -- 决定操作是否被允许"""

    async def check(self, request: PermissionRequest) -> bool:
        """返回 True 表示允许，False 表示拒绝"""
        ...


class HookCallable(Protocol):
    """钩子回调协议"""

    async def __call__(self, context: dict[str, Any]) -> None: ...
