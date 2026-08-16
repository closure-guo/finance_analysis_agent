"""Agent 节点共享的 LLM 工具函数。"""

from __future__ import annotations

import json
import re
from typing import cast

# ── 管线确定性 stub（agent-turn-box-display delta task 5.5）──
#
# TESTING=1 时 call_llm_streaming 不连真实 LLM，按 node_name 产出：
#   1. 固定思考 token（经 stream writer 写入 custom 流，node 用图节点名），
#      使前端 PipelineCard 能按 agent 阶段分组渲染（E2E 断言对象）；
#   2. 该节点 schema 合法的最小 answer（AnalystReport/DebateMessage/TradeDecision 等），
#      保证 parse_json_response + Pydantic 校验通过、管线确定推进。
# 生产链路（无 TESTING）不受影响，仍走 call_llm_stream -> litellm。

# 函数级 node_name -> 图节点名（前端 NODE_DISPLAY_NAMES 的 key）。
# 节点 writer 用的是函数级名（如 bull_debater 被 bull_r1/bull_r2 两个图节点复用，
# 图上下文不可知），统一映射为首个图节点名，保证前端分组标题正确。
_NODE_NAME_MAP: dict[str, str] = {
    "technical_analyst": "technical_analyst",
    "macro_analyst": "technical_analyst",
    "fundamental_analyst": "technical_analyst",
    "sentiment_analyst": "technical_analyst",
    "bull_debater": "bull_r1",
    "bear_debater": "bear_r1",
    "research_manager": "research_manager",
    "trader": "trader",
    "aggressive_debater": "aggressive_r1",
    "conservative_debater": "conservative_r1",
    "neutral_debater": "neutral_r1",
    "risk_judge": "risk_judge",
    "fund_manager": "fund_manager",
}

# 各分析师 stub answer 的 agent_name（AnalystReport.agent_name 字段值）
_ANALYST_AGENT_NAMES: dict[str, str] = {
    "technical_analyst": "technical",
    "macro_analyst": "macro",
    "fundamental_analyst": "fundamental",
    "sentiment_analyst": "sentiment",
}

# 各辩论角色 stub answer 的 role（DebateMessage.role 字段值）
_DEBATER_ROLES: dict[str, str] = {
    "bull_debater": "bull",
    "bear_debater": "bear",
    "aggressive_debater": "aggressive",
    "conservative_debater": "conservative",
    "neutral_debater": "neutral",
}

# 交易决策 stub answer（Trader / Risk Judge 共用 TradeDecision schema）
_STUB_TRADE_DECISION: dict = {
    "action": "hold",
    "confidence": 0.6,
    "reasoning": "STUB 交易决策：多因素均衡，建议持有观察（测试数据）",
}


def _stub_pipeline_answer(node_name: str) -> str:
    """按 node_name 返回该节点可解析的最小合法 answer（JSON 字符串或纯文本）。"""
    if node_name in _ANALYST_AGENT_NAMES:
        agent_name = _ANALYST_AGENT_NAMES[node_name]
        # claims 为空：verify_citations 零 claim 时 all_passed=True，管线确定推进
        return json.dumps(
            {
                "agent_name": agent_name,
                "summary": f"STUB {agent_name} 分析摘要（测试数据）",
                "key_findings": [f"STUB 发现：{agent_name} 指标正常"],
                "claims": [],
                "markdown": f"## {agent_name} 分析\n\nSTUB 分析正文（测试数据）。",
            },
            ensure_ascii=False,
        )
    if node_name in _DEBATER_ROLES:
        role = _DEBATER_ROLES[node_name]
        return json.dumps(
            {
                "role": role,
                "round": 1,
                "content": f"STUB {role} 方论点（测试数据）",
                "key_arguments": [f"STUB 论据：{role} 方观点成立"],
            },
            ensure_ascii=False,
        )
    if node_name in ("trader", "risk_judge"):
        return json.dumps(_STUB_TRADE_DECISION, ensure_ascii=False)
    if node_name == "fund_manager":
        # 固定 approve：保证管线确定走 generate_report（return 会回退 trader 引入不确定性）
        return json.dumps(
            {"decision": "approve", "reasoning": "STUB 审批通过（测试数据）"}, ensure_ascii=False
        )
    # research_manager 输出纯文本结论；未知节点兜底纯文本
    return f"STUB {node_name or 'unknown'} 结论（测试数据）"


def _is_testing() -> bool:
    """运行时读取 TESTING 开关（与 finance_agent.api 同源，避免模块级缓存导致测试隔离失效）。"""
    import os

    return os.getenv("TESTING") == "1"


def parse_json_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON，处理 markdown 代码块包裹和尾部多余文本。

    容错（incident 016 遗留行失败）：方舟 GLM-5.2 概率性输出尾逗号
    （"Illegal trailing comma before end of array"），下游节点解析无
    try/except，此处必须自行消化常见格式瑕疵，避免单次坏输出炸整行。
    """
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)
    text = text.strip()
    # Try direct parse first
    try:
        return cast(dict, json.loads(text))
    except json.JSONDecodeError:
        pass
    # Fallback: extract first JSON object using raw_decode
    decoder = json.JSONDecoder()
    idx = text.find("{")
    if idx >= 0:
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            return cast(dict, obj)
        except json.JSONDecodeError:
            pass
        # 尾逗号清理后重试：`,]` / `,}`（含空白/换行）→ 删逗号
        cleaned = re.sub(r",(\s*[}\]])", r"\1", text[idx:])
        try:
            obj, _ = decoder.raw_decode(cleaned)
            return cast(dict, obj)
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No JSON object found", text, 0)


_JSON_RETRY_SUFFIX = (
    "\n\n[系统提示] 上一次响应为空或不是合法 JSON。请直接输出一个合法的 JSON 对象，"
    "不要输出 JSON 以外的任何文字。"
)


def call_llm_for_json(
    prompt: str,
    system: str = "",
    api_key: str | None = None,
    node_name: str = "",
    llm_config=None,
    prompt_name: str | None = None,
    prompt_version: str | int | None = None,
    stock_code: str | None = None,
) -> dict:
    """call_llm_streaming + parse_json_response 收口：坏输出带强化指令重试一次。

    方舟 GLM-5.2 在部分 prompt 下稳定触发「thinking 后即止」（incident 017
    实测：aggressive_debater 连续多次 reasoning 正常而 content 为空，
    与 max_tokens 配额无关）。下游节点（debate/risk/trader/fund_manager）
    解析无降级，单次空输出即炸整行 —— 统一经本函数调用并重试。

    重试一次后仍失败向上抛 JSONDecodeError：保留 fund_manager
    「非法输出中断管线、不静默降级」的既有设计（重试 ≠ 降级）。
    其余参数与 call_llm_streaming 一致，原样透传。
    """
    kwargs: dict = {
        "system": system,
        "api_key": api_key,
        "node_name": node_name,
        "llm_config": llm_config,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "stock_code": stock_code,
    }
    response = call_llm_streaming(prompt, **kwargs)
    try:
        return parse_json_response(response)
    except json.JSONDecodeError:
        response = call_llm_streaming(prompt + _JSON_RETRY_SUFFIX, **kwargs)
        return parse_json_response(response)


def focus_hint(state: dict) -> str:
    """从 state 提取用户关注点（深度研究意图澄清环节收集），返回 LLM context 注入行。

    focus 为空时返回空字符串，调用方据此决定是否 append。
    """
    focus = (state.get("focus") or "").strip()
    if not focus:
        return ""
    return f"用户关注点: {focus}"


def call_llm_streaming(
    prompt: str,
    system: str = "",
    api_key: str | None = None,
    node_name: str = "",
    llm_config=None,
    prompt_name: str | None = None,
    prompt_version: str | int | None = None,
    stock_code: str | None = None,
) -> str:
    """Like call_llm but streams thinking tokens via LangGraph custom stream writer.

    Uses call_llm_stream to get real LLM reasoning_content (thinking) and answer.
    Thinking tokens are forwarded to the LangGraph stream writer for real-time display.
    Returns the complete answer string (same interface as call_llm).

    llm_config（LLMConfig | None）透传给 call_llm_stream，实现请求级配置注入。

    prompt_name / prompt_version（ADR-0015 Task 4）：透传给 call_llm_stream，
    经 metadata 挂到 Langfuse generation，兑现「Prompt 元数据可追溯」。

    node_name 透传给 call_llm_stream 的 agent 参数（Langfuse generation 命名），
    stock_code 原样透传（Langfuse 过滤字段）。
    """
    from finance_agent.llm import call_llm_stream

    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        writer = None

    # TESTING=1：管线确定性 stub（不调真实 LLM）。
    # 思考 token 的 node 用图节点名（前端 NODE_DISPLAY_NAMES 的 key），
    # 使 PipelineCard 按 agent 阶段分组；answer 为该节点 schema 合法的最小 JSON。
    if _is_testing():
        if writer:
            writer(
                {
                    "type": "thinking",
                    "node": _NODE_NAME_MAP.get(node_name, node_name),
                    "token": f"[STUB] {node_name or 'unknown'} 正在分析（确定性测试数据）\n",
                }
            )
        # stub 管线默认瞬时推进，CI 等快环境下 node 分组标题（流式中间态）
        # 一闪即逝导致 E2E 抓不到。加可配置的节点延迟，让分组标题在屏幕上
        # 停留足够窗口（report_ready 后管线卡隐藏、分组消失）。
        # 默认 0.25s；可用 STUB_NODE_DELAY 覆盖（0 表示不延迟）。
        import os
        import time

        delay = float(os.getenv("STUB_NODE_DELAY", "0.25"))
        if delay > 0:
            time.sleep(delay)
        return _stub_pipeline_answer(node_name)

    answer_parts: list[str] = []
    for kind, text in call_llm_stream(
        prompt,
        system=system,
        api_key=api_key,
        llm_config=llm_config,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        agent=node_name,
        stock_code=stock_code,
    ):
        if kind == "thinking" and writer:
            writer({"type": "thinking", "node": node_name, "token": text})
        elif kind == "answer":
            answer_parts.append(text)

    return "".join(answer_parts)
