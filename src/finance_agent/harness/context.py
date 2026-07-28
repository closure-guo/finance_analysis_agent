"""
Mini Harness - Context Manager
上下文管理：对话历史、Token 预算、渐进式压缩

设计原则（来自 Claude Code 的五级压缩 Pipeline）：
- Token 是零和预算：花在历史上的每个 token 都是当前推理的代价
- 渐进压缩：最便宜的策略优先，最昂贵的最后
- 追加式：压缩不修改历史，只追加摘要消息
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from finance_agent.harness.types import Message, Role

logger = logging.getLogger("finance_agent.harness.context")


# ───────────────────────────────────────────────
# Token 估算（快速且无需外部依赖）
# ───────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """
    快速估算 token 数量。
    使用经验法则：中文 ≈ 1 token/字，英文 ≈ 0.25 token/字
    实际生产环境应使用 tiktoken，但这里保持零依赖。
    """
    if not text:
        return 0
    # 简单启发式：按字符分类统计
    cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - cn_chars
    return int(cn_chars * 1.0 + other_chars * 0.25 + 0.5)


# ───────────────────────────────────────────────
# Context Manager
# ───────────────────────────────────────────────


@dataclass
class ContextBudget:
    """
    Token 预算配置

    Claude Code 的设计洞察：上下文不是无限资源，
    而是需要预算管理的有限资源。预留系统提示和输出的空间。
    """

    max_context_tokens: int = 120000  # 总上下文预算
    system_reserve: int = 4000  # 系统提示预留
    output_reserve: int = 8000  # 模型输出预留
    tool_result_budget: int = 50000  # 单个工具结果超过此值则截断
    compact_threshold_ratio: float = 0.85  # 达到总预算的 85% 时触发压缩

    @property
    def available_for_history(self) -> int:
        """可用于历史消息的 token 数"""
        return self.max_context_tokens - self.system_reserve - self.output_reserve

    @property
    def compact_threshold(self) -> int:
        """触发压缩的阈值"""
        return int(self.max_context_tokens * self.compact_threshold_ratio)


@dataclass
class CompactBoundary:
    """压缩边界标记 -- 事件溯源风格，追加到历史中"""

    boundary_id: str
    original_message_count: int
    compacted_message_count: int
    timestamp: float = field(default_factory=time.time)
    summary: str = ""


class ContextManager:
    """
    上下文管理器

    职责：
    1. 维护消息历史（追加式，不删除）
    2. 追踪 token 使用量
    3. 在预算接近上限时执行渐进式压缩
    4. 生成 LLM API 可用的消息列表

    渐进式压缩策略（简化自 Claude Code 的 L1-L5）：
    - L1: 工具结果截断（超长输出截断到预览）
    - L2: 过期思考删除（移除历史 think 消息）
    - L3: 摘要替换（使用 LLM 摘要替换旧消息）
    """

    def __init__(self, budget: ContextBudget | None = None):
        self.budget = budget or ContextBudget()
        self.messages: list[Message] = []
        self.system_message: Message | None = None
        self.boundaries: list[CompactBoundary] = []
        self._current_tokens: int = 0
        self._compacts_done: int = 0

    # ── 消息操作 ──

    def set_system(self, content: str) -> None:
        """设置系统提示"""
        self.system_message = Message(role=Role.SYSTEM, content=content)
        self._recalc_tokens()

    def append(self, message: Message) -> None:
        """追加消息（追加式，从不删除）"""
        self.messages.append(message)
        self._current_tokens += estimate_tokens(message.content)

    def append_user(self, content: str) -> None:
        """追加用户消息"""
        self.append(Message(role=Role.USER, content=content))

    def append_assistant(
        self,
        content: str,
        tool_calls: list[dict] | None = None,
        reasoning_content: str | None = None,
    ) -> None:
        """追加助手消息

        Args:
            content: 最终回答文本（content）
            tool_calls: 工具调用记录
            reasoning_content: DeepSeek 原生思维链，工具调用轮次需回传 API
        """
        self.append(
            Message(
                role=Role.ASSISTANT,
                content=content,
                tool_calls=tool_calls,
                reasoning_content=reasoning_content,
            )
        )

    def append_system(self, content: str) -> None:
        """追加系统提示消息"""
        self.append(Message(role=Role.SYSTEM, content=content))

    def append_tool_result(self, tool_call_id: str, output: str, is_error: bool = False) -> None:
        """追加工具结果消息"""
        # L1: 工具结果预算检查
        if len(output) > self.budget.tool_result_budget:
            truncated = output[: self.budget.tool_result_budget]
            truncated += f"\n\n[输出已截断 - 原始长度 {len(output)} 字符]"
            output = truncated
        self.append(
            Message(
                role=Role.TOOL,
                content=output,
                tool_call_id=tool_call_id,
            )
        )

    # ── Token 追踪 ──

    def get_token_count(self) -> int:
        """获取当前总 token 估算"""
        return self._current_tokens + estimate_tokens(
            self.system_message.content if self.system_message else ""
        )

    def is_near_limit(self) -> bool:
        """是否接近上下文上限"""
        return self.get_token_count() >= self.budget.compact_threshold

    def is_over_limit(self) -> bool:
        """是否超过可用于历史的 token 上限"""
        return self.get_token_count() >= self.budget.available_for_history

    # ── 压缩 Pipeline（渐进式） ──

    async def maybe_compact(
        self, llm_summarizer: Callable[[list[Message]], str] | None = None
    ) -> bool:
        """
        检查是否需要压缩，如需要则执行。

        返回 True 表示执行了压缩。

        压缩策略优先级：
        1. L1: 工具结果截断（已在 append_tool_result 中执行）
        2. L2: 删除过期的 think 消息
        3. L3: 对旧消息进行摘要
        """
        if not self.is_near_limit():
            return False

        logger.info(
            f"Token 使用量 {self.get_token_count()} 接近阈值 {self.budget.compact_threshold}，启动压缩"
        )

        # L2: 清理 think 消息（零成本）
        removed = self._strip_think_messages()
        if removed > 0:
            logger.info(f"L2 压缩：移除了 {removed} 条 think 消息")
            if not self.is_near_limit():
                return True

        # L3: 摘要旧消息（需要 LLM）
        if llm_summarizer and len(self.messages) > 6:
            await self._summarize_old_messages(llm_summarizer)
            return True

        # 兜底：硬截断最旧的消息
        self._hard_truncate()
        return True

    def _strip_think_messages(self) -> int:
        """
        L2: 移除 think 消息 -- 这些内部推理不需要保留在历史中。
        Claude Code 的洞察：think 消息对当前轮次有用，但很快过期。
        """
        removed = 0
        # 保留最近一轮的 think，删除更早的
        # 找到最后一条 user 消息的索引
        last_user_idx = -1
        for i, m in enumerate(self.messages):
            if m.role == Role.USER:
                last_user_idx = i

        # 删除 last_user_idx 之前的所有旧式 think（以 <thinking> 标记，遗留机制）
        # 清理非工具调用轮次的 reasoning_content 节省 token（DeepSeek 思考模式：
        # 非工具调用轮次的 reasoning_content 可不回传，API 忽略；工具调用轮次必须保留）
        to_remove = []
        for i, m in enumerate(self.messages):
            if i < last_user_idx and m.role == Role.ASSISTANT:
                # 旧式 <thinking> 标记消息：整体删除
                if m.content.startswith("<thinking>"):
                    to_remove.append(i)
                # 原生思考：非工具调用轮次的 reasoning_content 清理（工具调用轮次保留）
                elif m.reasoning_content and not m.tool_calls:
                    self._current_tokens -= estimate_tokens(m.reasoning_content)
                    m.reasoning_content = None
                    removed += 1

        for i in reversed(to_remove):
            removed += 1
            self._current_tokens -= estimate_tokens(self.messages[i].content)
            del self.messages[i]

        return removed

    async def _summarize_old_messages(self, summarizer: Callable[[list[Message]], str]) -> None:
        """
        L3: 将旧消息摘要为一条消息。
        保留最近 N 条消息完整，摘要更早的内容。
        """
        keep_recent = 4  # 保留最近 4 条消息
        if len(self.messages) <= keep_recent + 2:
            return

        old_messages = self.messages[:-keep_recent]
        recent_messages = self.messages[-keep_recent:]

        summary_text = summarizer(old_messages)
        boundary = CompactBoundary(
            boundary_id=f"compact_{self._compacts_done}",
            original_message_count=len(old_messages),
            compacted_message_count=1,
            summary=summary_text,
        )
        self.boundaries.append(boundary)
        self._compacts_done += 1

        # 替换为摘要消息
        summary_msg = Message(
            role=Role.SYSTEM,
            content=f"[上下文摘要 #{self._compacts_done}]\n{summary_text}",
        )
        self.messages = [summary_msg] + recent_messages
        self._recalc_tokens()
        logger.info(
            f"L3 压缩：{len(old_messages)} 条消息 -> 摘要，保留 {len(recent_messages)} 条完整"
        )

    def _hard_truncate(self) -> None:
        """兜底：硬截断最旧的消息（保留最近的）"""
        keep = 6
        if len(self.messages) > keep:
            removed = len(self.messages) - keep
            self.messages = self.messages[-keep:]
            self._recalc_tokens()
            logger.warning(f"兜底截断：删除了 {removed} 条旧消息")

    # ── 构建 API 消息列表 ──

    def build_messages_for_api(self) -> list[dict[str, Any]]:
        """
        构建发送给 LLM API 的消息列表。
        格式：[system, msg1, msg2, ...]
        """
        result: list[dict[str, Any]] = []
        if self.system_message:
            result.append(self.system_message.to_api_dict())
        for m in self.messages:
            result.append(m.to_api_dict())
        return result

    def get_last_user_message(self) -> str | None:
        """获取最近一条用户消息的内容"""
        for m in reversed(self.messages):
            if m.role == Role.USER:
                return m.content
        return None

    def _recalc_tokens(self) -> None:
        """重新计算 token 数"""
        total = 0
        if self.system_message:
            total += estimate_tokens(self.system_message.content)
        for m in self.messages:
            total += estimate_tokens(m.content)
        self._current_tokens = total

    def __repr__(self) -> str:
        return f"ContextManager(tokens={self.get_token_count()}/{self.budget.max_context_tokens}, messages={len(self.messages)})"
