"""Natural language stock name resolution — LLM first, AKShare fallback."""

from __future__ import annotations

import json
import re

from finance_agent.app_search import search_stocks
from finance_agent.llm import call_llm


def resolve_stock(query: str, api_key: str | None = None) -> dict | None:
    """Resolve natural language input to stock_code + stock_name.

    Returns {"stock_code": "300750", "stock_name": "宁德时代"} or None.
    """
    query = query.strip()
    if not query:
        return None

    # 1. If input is already a 6-digit stock code, use directly
    code_match = re.search(r"\b(\d{6})\b", query)
    if code_match:
        code = code_match.group(1)
        results = search_stocks(code, limit=1)
        if results:
            label, c = results[0]
            return {"stock_code": c, "stock_name": label.split(" (")[0] if " (" in label else c}
        return {"stock_code": code, "stock_name": code}

    # 2. Try LLM resolution
    llm_result = _resolve_with_llm(query, api_key)
    if llm_result:
        # Verify with AKShare
        results = search_stocks(llm_result["stock_code"], limit=1)
        if results:
            label, c = results[0]
            return {
                "stock_code": c,
                "stock_name": label.split(" (")[0] if " (" in label else llm_result["stock_name"],
            }
        return llm_result

    # 3. Fallback: AKShare fuzzy search
    results = search_stocks(query, limit=5)
    if results:
        # Return best match
        label, code = results[0]
        name = label.split(" (")[0] if " (" in label else label
        return {"stock_code": code, "stock_name": name}

    return None


def _resolve_with_llm(query: str, api_key: str | None = None) -> dict | None:
    """Use LLM to extract stock code from natural language."""
    system = """你是A股股票代码解析助手。用户会输入股票名称、行业描述、公司特征等自然语言查询，你需要根据你的知识提取对应的A股股票代码。

请根据你的知识推理，不要局限于固定股票列表。例如：
- "光模块龙头企业" → 中际旭创 300308
- "白酒龙头" → 贵州茅台 600519
- "新能源电池龙头" → 宁德时代 300750
- "光伏龙头" → 隆基绿能 601012

请只返回JSON格式，不要其他内容：
{"stock_code": "600519", "stock_name": "贵州茅台", "confidence": "high"}

如果不确定或不知道，返回：
{"stock_code": null, "stock_name": null, "confidence": "low"}

注意：
- 只返回A股股票（沪市6开头、深市0/3开头、科创板688开头）
- 股票代码必须是6位数字
- 不要编造不存在的股票代码"""

    try:
        resp = call_llm(query, system=system, api_key=api_key, max_tokens=100)
        # Extract JSON from response
        json_match = re.search(r"\{[^}]+\}", resp)
        if json_match:
            data = json.loads(json_match.group())
            if data.get("stock_code") and data.get("confidence") != "low":
                return {
                    "stock_code": str(data["stock_code"]),
                    "stock_name": str(data.get("stock_name", data["stock_code"])),
                }
    except Exception:  # noqa: S110 - best-effort LLM stock resolution; ignore failures
        pass
    return None
