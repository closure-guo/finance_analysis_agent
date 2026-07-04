"""Agent 间通信的结构化输出模型。

参考 ADR-0011 和 TradingAgents (arXiv:2412.20138)。
结构化输出解决"电话效应"：agent 间传递 Pydantic 对象而非自由 Markdown。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from finance_agent.citation import Claim


class AnalystReport(BaseModel):
    """Layer I 分析师 Agent 的结构化输出。

    每个 analyst agent（宏观/基本面/技术面/舆情）输出此对象，
    供下游辩论 agent 和引用校验器使用。
    """

    agent_name: str  # "macro" | "fundamental" | "technical" | "sentiment"
    summary: str
    key_findings: list[str]
    claims: list[Claim]  # 用于确定性引用校验
    markdown: str  # 完整章节 Markdown，用于最终报告渲染


class DebateMessage(BaseModel):
    """Layer II/IV 辩论消息。

    Bull/Bear 辩论（Layer II）和 Risk Management 辩论（Layer IV）的消息单元。
    每轮辩论中各角色用 Send 并行产出，收集到 debate_history。
    """

    role: str  # "bull" | "bear" | "aggressive" | "conservative" | "neutral" | "research_manager" | "risk_judge"
    round: int
    content: str
    key_arguments: list[str]


class TradeDecision(BaseModel):
    """Layer III (Trader) / Layer IV (Risk Judge) 的交易决策。

    action 受 Literal 约束，仅允许 buy/sell/hold/watch。
    confidence 为 0-1 的置信度。
    """

    action: Literal["buy", "sell", "hold", "watch"]
    confidence: float
    reasoning: str
    position_size: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
