"""Layer I 分析师 Agent — 4 个并行分析师节点。

每个分析师：
1. 从 state 读取 PREP 数据
2. 构建 prompt context
3. 调用 LLM
4. 解析 JSON 响应为 AnalystReport
5. 返回 state 更新
"""

from __future__ import annotations

import json

from finance_agent.llm import call_llm
from finance_agent.models import AnalystReport
from finance_agent.nodes._llm_utils import parse_json_response
from finance_agent.prompts.loader import load_prompt


def technical_analyst(state: dict) -> dict:
    """Layer I 技术面分析师 Agent。"""
    context = _build_technical_context(state)
    system = load_prompt("technical_analyst")
    api_key = state.get("api_key")

    response = call_llm(context, system=system, api_key=api_key)
    data = parse_json_response(response)
    report = AnalystReport.model_validate(data)

    return {"analyst_reports": {"technical": report}}


def _build_technical_context(state: dict) -> str:
    """构建技术面分析的 LLM context。"""
    sections = []

    stock_name = state.get("stock_name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    sections.append(f"股票: {stock_name}({stock_code})")

    indicators = state.get("technical_indicators") or {}
    if indicators:
        sections.append(f"技术指标数据:\n{json.dumps(indicators, ensure_ascii=False, default=str)}")

    return "\n\n".join(sections)
