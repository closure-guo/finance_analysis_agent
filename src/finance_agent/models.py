"""Agent 间通信的结构化输出模型。

参考 ADR-0011 和 TradingAgents (arXiv:2412.20138)。
结构化输出解决"电话效应"：agent 间传递 Pydantic 对象而非自由 Markdown。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    # 解析降级标记：LLM 输出解析失败时为 True，使下游能区分
    # 「解析失败导致的零 claim」与「LLM 正常输出的零 claim」
    # （零 claim 会使引用校验 all_passed=True，见 citation.py 的 failed == 0）
    parse_degraded: bool = False


class DebateMessage(BaseModel):
    """Layer II/IV 辩论消息。

    Bull/Bear 辩论（Layer II）和 Risk Management 辩论（Layer IV）的消息单元。
    每轮辩论中各角色用 Send 并行产出，收集到 debate_history。
    """

    role: Literal[
        "bull",
        "bear",
        "aggressive",
        "conservative",
        "neutral",
        "research_manager",
        "risk_judge",
    ]
    round: int = Field(ge=1)
    content: str
    key_arguments: list[str]


# TradeDecision.evidence_refs 的 source 规范枚举（improve-decision-grounding）
TRADE_EVIDENCE_SOURCES = frozenset(
    {
        "technical",
        "macro",
        "fundamental",
        "sentiment",
        "debate_bull",
        "debate_bear",
        "research_manager",
    }
)

# LLM 输出常见别名 → 规范 source（归一不拒绝，见 TradeEvidenceRef validator）
_SOURCE_ALIASES = {
    "technical_analyst": "technical",
    "macro_analyst": "macro",
    "fundamental_analyst": "fundamental",
    "sentiment_analyst": "sentiment",
    "bull": "debate_bull",
    "bear": "debate_bear",
    "research_manager_conclusion": "research_manager",
}


class TradeEvidenceRef(BaseModel):
    """交易决策的论据引用 — 决策论据到来源的可核对映射。

    source 宽松接收：仅做大小写/别名归一，未知值原样保留（LLM 抖动
    不炸管线——judge 自会因无法核对而判低分；与 action/confidence 的
    硬校验相反，此处是「降级不中断」路线）。
    """

    claim: str
    source: str

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        norm = value.strip().lower()
        return _SOURCE_ALIASES.get(norm, norm)


class TradeDecision(BaseModel):
    """Layer III (Trader) / Layer IV (Risk Judge) 的交易决策。

    action 受 Literal 约束，仅允许 buy/sell/hold/watch。
    confidence 为 0-1 的置信度。
    """

    action: Literal["buy", "sell", "hold", "watch"]
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    position_size: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
    # toolize-price-levels：sanity 校验二次未通过时由工具参考带修正（可观测标注）
    price_level_corrected: bool = False
    price_level_correction_reason: str | None = None
    evidence_refs: list[TradeEvidenceRef] = Field(default_factory=list)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _scrub_evidence_refs(cls, value: object) -> object:
        """宽松清洗证据引用：None/非列表 → []；丢弃结构非法条目（LLM 抖动不炸管线）。"""
        if value is None or not isinstance(value, list):
            return []
        cleaned: list[object] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            claim, source = item.get("claim"), item.get("source")
            if not isinstance(claim, str) or not isinstance(source, str):
                continue
            cleaned.append(item)
        return cleaned


class FundManagerDecision(BaseModel):
    """Layer V Fund Manager 的审批决策。

    decision 受 Literal 约束，仅允许 approve/reject/return（ADR-0011 Layer V）。
    校验前做归一化（去首尾空白 + 转小写），容许 LLM 输出的大小写抖动；
    归一化后仍非法则抛 ValidationError 中断管线，不降级为任何默认决策
    （harden-llm-output-validation 决策 1、2）。
    """

    decision: Literal["approve", "reject", "return"]
    reasoning: str = ""

    @field_validator("decision", mode="before")
    @classmethod
    def _normalize_decision(cls, value: object) -> object:
        """归一化决策值：仅处理大小写与首尾空白，不做同义词映射。"""
        if isinstance(value, str):
            return value.strip().lower()
        return value
