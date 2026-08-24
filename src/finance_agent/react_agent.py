"""ReAct Agent — LLM 自主决策调用工具（股票搜索 + 深度分析）。

替代原来 /api/analyze 中 resolve_stock 失败直接报错的逻辑：
1. LLM 收到用户查询（可能是模糊的，如"光模块龙头企业"）
2. LLM 自主决定调用 search_stock 工具搜索股票
3. 拿到股票代码后，LLM 调用 run_deep_analysis 工具执行 5 层分析
4. 分析结果流式返回

如果用户直接输入了股票代码，跳过 ReAct 循环，直接执行深度分析。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from finance_agent.app_search import get_stock_list, search_stocks
from finance_agent.llm.gateway import complete_text
from finance_agent.web_search import format_search_for_llm, has_tavily_key, tavily_search

# ── Tool schemas (OpenAI function calling format) ──

SEARCH_STOCK_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_stock",
        "description": (
            "根据自然语言查询搜索A股股票。当用户输入股票名称、行业描述、公司特征等模糊查询时调用。"
            "例如：'光模块龙头企业'、'白酒龙头'、'宁德时代'。返回匹配的候选股票列表。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如股票名称、行业、公司特征等",
                },
            },
            "required": ["query"],
        },
    },
}

DEEP_ANALYSIS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_deep_analysis",
        "description": (
            "对指定A股股票执行深度分析（5层架构：4分析师并行->多空辩论->交易决策->"
            "风控压力测试->基金经理审批->报告生成）。需要提供股票代码。"
            "如果用户输入了模糊查询，请先调用 search_stock 获取股票代码。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "6位A股股票代码，如 300308",
                },
                "stock_name": {
                    "type": "string",
                    "description": "股票名称，如 中际旭创",
                },
            },
            "required": ["stock_code"],
        },
    },
}

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "搜索网页获取实时信息。当用户询问股票推荐、今日热点、市场动态等"
            "需要最新信息的问题时调用。例如：'今天推荐买入的股票'、'A股热点'。"
            "搜索后从结果中提取具体股票名称，再调用 search_stock 获取代码，最后调用 run_deep_analysis。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
            },
            "required": ["query"],
        },
    },
}

REACT_TOOLS = [SEARCH_STOCK_TOOL, DEEP_ANALYSIS_TOOL, WEB_SEARCH_TOOL]


# ── Stock search tool implementation ──
#
# 四级短路降级：AKShare 验证是唯一信任锚点，LLM 和 Web Search 都是信息源，
# 必须经过验证才能输出。越靠前的层越可信越便宜，一旦命中直接返回。

# 时效性/非具体关键词：随时间变化，LLM 常识推理易"幻觉"出单只热门股
# （如把"热门股票"→贵州茅台并以 high confidence 返回），导致 Agent 跳过确认
# 直接进管线。命中此类词时跳过 STEP 2c，改走 Web Search / 模糊搜索返回多候选。
_TIME_SENSITIVE_KEYWORDS = [
    "热门",
    "热点",
    "热股",
    "推荐",
    "今天",
    "今日",
    "最近",
    "最新",
    "当下",
    "现在",
    "当前",
    "涨幅",
    "跌幅",
    "涨停",
    "跌停",
    "利好",
    "利空",
]


def search_stock_tool(query: str, api_key: str | None = None) -> dict:
    """股票搜索工具 — 四级短路降级。

    STEP 1: 输入分类（零 LLM 调用）→ code / name / description
    STEP 2a: 代码验证（AKShare）         ← code 类型走这里
    STEP 2b: 名称精确匹配（AKShare）      ← name 类型走这里
    STEP 2c: LLM 常识推理 + AKShare 验证  ← 高置信命中直接返回；低置信标记 NEED_SEARCH
    STEP 3:  Web Search + LLM 提取 + AKShare 验证  ← 时效性补丁
    STEP 4:  AKShare 模糊搜索            ← 最终兜底，返回列表

    Returns:
        单候选: {"candidates": [{...}], "found": True, "source": "...", "confidence": 1.0}
        多候选: {"candidates": [...], "found": True, "source": "...", "confidence": 0.4, "needs_confirmation": True}
        未命中: {"candidates": [], "found": False, "message": "..."}
    """
    query = query.strip()
    if not query:
        return {"candidates": [], "found": False, "message": "查询为空"}

    # ── STEP 1: 输入分类（零 LLM 调用）──
    input_type = _classify_input(query)

    # ── STEP 2a: 代码验证（AKShare）──
    if input_type == "code":
        code = re.search(r"\d{6}", query).group()
        verified = _verify_stock_code(code)
        if verified:
            return {
                "candidates": [verified],
                "found": True,
                "source": "akshare_exact",
                "confidence": 1.0,
            }

    # ── STEP 2b: 名称精确匹配（AKShare）──
    if input_type in ("name", "code"):
        matched = _match_stock_name(query)
        if matched:
            return {
                "candidates": [matched],
                "found": True,
                "source": "akshare_exact",
                "confidence": 1.0,
            }

    # ── STEP 2c 前置守卫：时效性查询跳过 LLM 常识推理 ──
    # "热门股票"/"今天推荐"等查询随时间变化，LLM 易幻觉出单只股票并以 high
    # confidence 返回（AKShare 验证通过后即单候选 → Agent 直接进管线）。
    # 此处强制跳过 LLM 推理，落到 STEP 3 Web Search / STEP 4 模糊搜索返回多候选。
    is_time_sensitive = any(kw in query for kw in _TIME_SENSITIVE_KEYWORDS)

    # ── STEP 2c: LLM 常识推理 ──
    llm_result = None if is_time_sensitive else _search_with_llm_reasoning(query, api_key)
    if llm_result and llm_result.get("confidence") == "high":
        verified = _verify_stock_code(llm_result["stock_code"])
        if verified:
            return {
                "candidates": [verified],
                "found": True,
                "source": "llm_reasoning",
                "confidence": 0.9,
            }

    # ── STEP 3: Web Search（时效性补丁）──
    # 触发条件：LLM 低置信/验证失败，或 2a/2b 未命中
    if has_tavily_key():
        web_candidates = _search_with_web_search(query, api_key)
        if web_candidates:
            return {
                "candidates": web_candidates[:5],
                "found": True,
                "source": "web_search",
                "confidence": 0.7,
                "needs_confirmation": len(web_candidates) > 1,
            }

    # ── STEP 4: AKShare 模糊搜索（最终兜底）──
    fuzzy_candidates = _akshare_fuzzy_search(query)
    if fuzzy_candidates:
        return {
            "candidates": fuzzy_candidates,
            "found": True,
            "source": "akshare_fuzzy",
            "confidence": 0.4,
            "needs_confirmation": True,
        }

    return {"candidates": [], "found": False, "message": f"未找到匹配 '{query}' 的股票"}


# ── STEP 1: 输入分类 ──


def _classify_input(query: str) -> str:
    """分类输入类型：code / name / description。零 LLM 调用。

    - 纯6位数字或包含6位数字 → code
    - 短中文（<=8字），无时效性关键词 → name
    - 其他 → description
    """
    query = query.strip()

    # 包含6位数字 → 代码
    if re.search(r"\d{6}", query):
        return "code"

    # 时效性/非具体关键词 → 描述（随时间变化，不应按具体股票名处理）
    if any(kw in query for kw in _TIME_SENSITIVE_KEYWORDS):
        return "description"

    # 时效性/概念性关键词 → 描述
    _concept_keywords = [
        "龙头",
        "最大",
        "最好",
        "最猛",
        "第一",
        "领先",
        "巨头",
        "概念",
        "概念股",
        "板块",
        "代表",
        "头部",
        " TOP",
        "top",
    ]
    if any(kw in query for kw in _concept_keywords):
        return "description"

    # 短中文，无时效性关键词 → 名称
    if len(query) <= 8 and re.search(r"[\u4e00-\u9fff]", query):
        return "name"

    return "description"


# ── STEP 2b: 名称精确匹配 ──


def _match_stock_name(query: str) -> dict | None:
    """在 AKShare 股票列表中匹配名称。

    先精确匹配，再包含匹配（如"茅台"→"贵州茅台"）。
    """
    query = query.strip()
    stocks = get_stock_list()
    if not stocks:
        return None

    # 从 query 中提取可能的名称（去掉多余文字）
    # 如果是代码类型，提取6位数字对应的名称
    code_match = re.search(r"\d{6}", query)
    if code_match:
        code = code_match.group()
        for s in stocks:
            if s["code"] == code:
                return {"stock_code": s["code"], "stock_name": s["name"]}
        return None

    # 精确匹配
    for s in stocks:
        if s["name"] == query:
            return {"stock_code": s["code"], "stock_name": s["name"]}

    # 包含匹配（如"茅台"→"贵州茅台"）
    for s in stocks:
        if query in s["name"]:
            return {"stock_code": s["code"], "stock_name": s["name"]}

    return None


# ── STEP 2c: LLM 常识推理 ──


def _search_with_llm_reasoning(query: str, api_key: str | None = None) -> dict | None:
    """LLM 常识推理 — 只回答知识截止期内稳定的映射。

    返回:
        高置信: {"stock_code": "300308", "stock_name": "中际旭创", "confidence": "high", "reason": "..."}
        低置信: {"stock_code": None, "confidence": "low", "need_search": True, "reason": "时效性问题"}
    """
    system = """你是A股股票代码解析助手。用户会输入股票名称、行业描述、公司特征等。

请根据你的知识判断：
- 如果是明确的股票名称或常识映射（如"茅台"→贵州茅台600519），返回高置信结果
- 如果是时效性问题（如"光模块龙头"、"最猛的"、"现在谁最强"），你不确定当前情况，标记 need_search=true

返回JSON格式：
高置信：{"stock_code": "600519", "stock_name": "贵州茅台", "confidence": "high", "reason": "常识映射"}
低置信：{"stock_code": null, "confidence": "low", "need_search": true, "reason": "时效性问题，需要搜索最新信息"}

注意：
- 只返回A股股票（沪市6开头、深市0/3开头、科创板688开头、北交所8开头）
- 股票代码必须是6位数字
- 不要编造不存在的股票代码
- 对于"龙头"、"最强"等时效性描述，优先标记 need_search=true"""

    try:
        text, meta = complete_text(
            [{"role": "system", "content": system}, {"role": "user", "content": query}],
            purpose="quick",
            max_tokens=200,
            temperature=0.3,
            # 无 llm_config：legacy._request_config_dict(None, api_key) 返回 None
            llm_config=None,
            trace={"name": "react_agent", "metadata": {"agent": "react_agent"}},
        )
        # legacy 行为保留：content 为空时回退 reasoning_content
        resp = text or meta.get("raw_reasoning") or ""
        data = _parse_json_safely(resp)
        if data and data.get("stock_code") and data.get("confidence") == "high":
            return {
                "stock_code": str(data["stock_code"]),
                "stock_name": str(data.get("stock_name", data["stock_code"])),
                "confidence": "high",
                "reason": data.get("reason", ""),
            }
        if data and data.get("confidence") == "low":
            return {"stock_code": None, "confidence": "low", "need_search": True}
    except Exception:  # noqa: S110 - best-effort LLM reasoning
        pass
    return None


# ── 共用：AKShare 代码验证 ──


def _verify_stock_code(code: str) -> dict | None:
    """用 AKShare 验证股票代码是否存在，返回 {stock_code, stock_name} 或 None。"""
    results = search_stocks(code, limit=1)
    if results:
        label, c = results[0]
        name = label.split(" (")[0] if " (" in label else c
        return {"stock_code": c, "stock_name": name}
    return None


# ── STEP 3: Web Search ──


def _search_with_web_search(query: str, api_key: str | None = None) -> list[dict]:
    """用 Tavily web search 搜索最新信息，LLM 从结果中提取股票代码，AKShare 验证。

    解决 LLM 知识时效性问题：例如"光模块龙头企业"——LLM 可能不知道现在谁是龙头，
    但 web search 能搜到最新文章，LLM 再从文章内容中提取股票代码。
    """
    year = datetime.now().year
    search_query = f"{query} A股 股票代码 {year}"

    try:
        search_resp = tavily_search(search_query, max_results=5)
        if not search_resp.results:
            return []

        search_text = format_search_for_llm(search_resp)

        system = """你是A股股票信息提取助手。下面是网络搜索结果，请从中提取提到的A股股票代码和名称。

请返回JSON格式（最多5个候选）：
{"candidates": [{"stock_code": "300308", "stock_name": "中际旭创", "reason": "搜索结果中提到中际旭创是光模块龙头"}]}

注意：
- 只提取A股股票（沪市6开头、深市0/3开头、科创板688开头、北交所8开头）
- 股票代码必须是6位数字
- 如果搜索结果中没有提到具体股票，返回空列表 {"candidates": []}
- 不要编造搜索结果中没有的股票"""

        prompt = f"用户查询：{query}\n\n网络搜索结果：\n{search_text}"

        text, meta = complete_text(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            purpose="quick",
            max_tokens=400,
            temperature=0.3,
            # 无 llm_config：legacy._request_config_dict(None, api_key) 返回 None
            llm_config=None,
            trace={"name": "react_agent", "metadata": {"agent": "react_agent"}},
        )
        # legacy 行为保留：content 为空时回退 reasoning_content
        resp = text or meta.get("raw_reasoning") or ""
        data = _parse_json_safely(resp)
        if data:
            raw = data.get("candidates", [])
            results: list[dict] = []
            for c in raw:
                if c.get("stock_code"):
                    # AKShare 验证——防止搜到退市股/新三板
                    verified = _verify_stock_code(str(c["stock_code"]))
                    if verified:
                        results.append(verified)
                    # 验证失败的不加入结果（信任锚点原则）
            return results
    except Exception:  # noqa: S110 - best-effort web search; ignore failures
        pass
    return []


# ── STEP 4: AKShare 模糊搜索 ──


def _akshare_fuzzy_search(query: str) -> list[dict]:
    """AKShare 模糊搜索 — 最终兜底，返回候选列表。

    从查询中提取关键词，在全 A 股列表中做子串匹配。
    """
    keywords = _extract_keywords(query)
    candidates: list[dict] = []
    for kw in keywords:
        results = search_stocks(kw, limit=5)
        for label, code in results:
            name = label.split(" (")[0] if " (" in label else label
            if not any(code == ex["stock_code"] for ex in candidates):
                candidates.append({"stock_code": code, "stock_name": name})
    return candidates[:5]


# ── 辅助函数 ──


def _extract_keywords(query: str) -> list[str]:
    """从自然语言查询中提取搜索关键词。

    "分析一下光模块那个龙头企业" → ["光模块"]
    """
    stopwords = {
        "分析",
        "一下",
        "那个",
        "龙头企业",
        "龙头",
        "的",
        "了",
        "是",
        "在",
        "和",
        "与",
        "什么",
        "哪个",
        "哪些",
        "最",
        "猛",
        "大",
        "好",
        "第一",
        "领先",
        "巨头",
        "概念",
        "板块",
    }
    parts = re.split(r"[，,。.\s、！!？?]+", query)
    keywords = [p.strip() for p in parts if p.strip() and p.strip() not in stopwords]
    if not keywords:
        keywords = [query]
    return keywords


def _parse_json_safely(text: str) -> dict | None:
    """从 LLM 响应中安全提取 JSON 对象，处理嵌套花括号和 markdown 标记。"""
    # 1. 先尝试直接解析整个文本
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. 去掉 markdown ```json ... ``` 标记后重试
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. 用平衡花括号匹配提取第一个完整 JSON 对象
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
