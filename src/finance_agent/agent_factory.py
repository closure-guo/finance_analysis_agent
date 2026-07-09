"""Agent 工厂函数。

根据模式构建 ReAct Agent，配置工具集、max_iterations 和 system prompt。

三种模式：
- quick: 工具=[web_search], max_iterations=3
- deep: 工具=[search_stock, run_deep_analysis, web_search], max_iterations=10
- follow-up: 工具=[web_search], max_iterations=3, 注入 session 上下文
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from finance_agent.harness import Agent, PermissionMode

# ───────────────────────────────────────────────
# System Prompts
# ───────────────────────────────────────────────

QUICK_MODE_PROMPT = """# Identity
你是一个智能问答助手，擅长 A 股投资领域，同时也能回答用户的通用问题（如天气、新闻、常识等）。

# Safety
IMPORTANT: 投资相关回答仅供参考研究，不构成投资建议。

# Tone & Style
- 使用中文回答
- 简洁直接，不要冗长
- 不使用 emoji

# Workflow
优先用自身知识回答。用户询问实时信息（天气、股价、新闻、政策、赛事等）时，调用 web_search 补充。
对于非投资类的通用问题，正常友好地回答，不要以"与投资无关"为由拒答。

# Tool Policy
- web_search: 获取实时信息（天气、行情、新闻、政策等）。简单知识性问题不需要搜索。

# Environment
当前时间：{now}

# Reminders
- 保持简洁
- 实时性问题才搜索
- 友好回答用户的通用问题，不要拒答
""".strip()


DEEP_MODE_PROMPT = """# Identity
你是一个 A 股投研分析助手。用户输入股票名称或代码，你调用深度分析管线生成完整研报。

# Safety
IMPORTANT: 报告由 AI 系统基于公开数据自动生成，仅供参考研究，不构成投资建议。
IMPORTANT: 不要直接给出买卖建议，所有交易建议必须来自 run_deep_analysis 工具的输出。

# Tone & Style
- 使用中文回答
- 专业、客观、简洁
- 不使用 emoji

# Workflow
用户想分析股票时，先用 search_stock 解析股票代码，再调用 run_deep_analysis 运行 5 层分析管线。
管线运行期间，进度会自动推送给用户，你不需要描述进度。
管线完成后，基于报告内容给用户一个简短的摘要（3-5 句），不要复述完整报告。

# Tool Policy
- search_stock: 用户输入股票名称时使用，解析为股票代码
- run_deep_analysis: 股票代码确认后调用，运行 5 层分析管线
- web_search: 补充实时信息（如最新新闻、政策变化），不替代深度分析

# Domain Knowledge
A 股市场 5 层分析架构：4 个分析师并行（宏观/基本面/技术面/舆情）-> Bull/Bear 辩论 -> 交易员决策 -> 风险管理辩论 -> 基金经理批准。分析基于 AKShare 公开数据。

# Environment
当前时间：{now}

# Reminders
- 先 search_stock 再 run_deep_analysis，不要跳过股票解析
- 报告完成后给摘要，不要复述全文
""".strip()


FOLLOW_UP_MODE_PROMPT = """# Identity
你正在与用户讨论之前生成的股票分析报告。基于报告内容回答用户的追问。

# Safety
IMPORTANT: 回答仅供参考研究，不构成投资建议。

# Tone & Style
- 使用中文回答
- 引用报告中的具体数据支持你的回答
- 不使用 emoji

# Workflow
用户的问题通常围绕已有报告展开。优先从报告上下文中找答案。
如果用户询问报告之外的新信息（如最新行情、新闻），调用 web_search 补充。

# Tool Policy
- web_search: 获取报告之外的实时信息

# Domain Knowledge
之前的分析报告：
{report_excerpt}

分析师摘要：
{analyst_summaries}

之前的对话：
{chat_history}

# Environment
当前时间：{now}
报告生成时间：{created_at}

# Reminders
- 优先引用报告内容
- 报告中没有的信息才搜索
""".strip()


# ───────────────────────────────────────────────
# 工具定义
# ───────────────────────────────────────────────


async def _web_search(query: str) -> str:
    """搜索网页获取实时信息

    Args:
        query: 搜索关键词
    """
    from finance_agent.web_search import format_search_for_llm, has_tavily_key, tavily_search

    if not has_tavily_key():
        return "[错误] 未配置 TAVILY_API_KEY，无法执行搜索。"
    response = tavily_search(query)
    return format_search_for_llm(response)


def _make_search_stock(api_key: str | None = None):
    """创建 search_stock 工具，注入 api_key 闭包。"""

    async def search_stock(query: str) -> str:
        """根据自然语言解析 A 股股票代码

        Args:
            query: 股票名称、代码或描述，如 "茅台"、"600519"、"贵州茅台"
        """
        from finance_agent.react_agent import search_stock_tool

        result = search_stock_tool(query, api_key)
        return _format_stock_result(result)

    return search_stock


def _format_stock_result(result: dict) -> str:
    """将 search_stock_tool 的 dict 结果格式化为 LLM 友好的字符串。"""
    if not result.get("found"):
        return result.get("message", "未找到匹配的股票")

    candidates = result.get("candidates", [])
    if not candidates:
        return result.get("message", "未找到匹配的股票")

    if len(candidates) == 1:
        c = candidates[0]
        code = c.get("code", "")
        name = c.get("name", "")
        return f"找到股票：{name}({code})"

    lines = ["找到多个候选股票，请确认："]
    for i, c in enumerate(candidates, 1):
        code = c.get("code", "")
        name = c.get("name", "")
        lines.append(f"{i}. {name}({code})")
    return "\n".join(lines)


def _make_run_deep_analysis(
    api_key: str | None = None,
    analysis_type: str = "comprehensive",
    peer_codes: list | None = None,
    enable_web_search: bool = False,
):
    """创建 run_deep_analysis 流式工具，注入配置闭包。

    LLM 只看到 stock_code 和 stock_name，其余参数通过闭包注入。
    返回一个异步生成器，yield StreamEvent（PROGRESS + TOOL_RESULT）。
    """

    async def run_deep_analysis(stock_code: str, stock_name: str = ""):
        """运行 5 层深度分析管线

        Args:
            stock_code: A 股股票代码，如 "600519"
            stock_name: 股票名称，如 "贵州茅台"
        """
        from finance_agent.harness import ActionType, StreamEvent, ToolResult

        initial_state = {
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "analysis_type": analysis_type,
            "peer_codes": peer_codes,
            "enable_web_search": enable_web_search,
            "api_key": api_key,
        }

        accumulated: dict = dict(initial_state)

        for chunk in _stream_graph(initial_state):
            for node_name, update in chunk.items():
                if isinstance(update, dict) and update:
                    accumulated.update(update)

                yield StreamEvent.progress(
                    content=f"{node_name} 完成",
                    metadata={"node": node_name},
                )

        report_md = accumulated.get("final_report", "")
        metadata = {
            "chart_data": accumulated.get("chart_data") or {},
            "analyst_reports": accumulated.get("analyst_reports") or {},
            "stock_code": stock_code,
            "stock_name": accumulated.get("stock_name") or stock_name or stock_code,
        }

        yield StreamEvent(
            event_type=ActionType.TOOL_RESULT,
            content=report_md,
            tool_result=ToolResult(
                tool_call_id="",
                name="run_deep_analysis",
                output=report_md,
                metadata=metadata,
            ),
        )

    return run_deep_analysis


def _stream_graph(initial_state: dict, config: dict | None = None):
    """执行 5 层管线同步流式迭代。"""
    from finance_agent.graph import build_5layer_graph

    if config is None:
        config = {"recursion_limit": 100}

    graph = build_5layer_graph()
    yield from graph.stream(
        initial_state,
        config=config,
        stream_mode="updates",
    )


# ───────────────────────────────────────────────
# 工厂函数
# ───────────────────────────────────────────────


def build_agent(
    mode: str = "quick",
    api_key: str | None = None,
    analysis_type: str = "comprehensive",
    peer_codes: list | None = None,
    enable_web_search: bool = False,
    **kwargs: Any,
) -> Agent:
    """构建指定模式的 ReAct Agent。

    Args:
        mode: 模式 ("quick" | "deep" | "follow-up")
        api_key: LLM API 密钥
        analysis_type: 分析类型（深度模式，闭包注入 run_deep_analysis）
        peer_codes: 对标股代码（深度模式，闭包注入）
        enable_web_search: 是否启用搜索（深度模式，闭包注入）
        **kwargs: 额外参数（session_id 等）

    Returns:
        配置好的 Agent 实例
    """
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
    llm_client = _make_llm_client(model, api_key)

    if mode == "quick":
        agent = Agent(
            model=model,
            api_key=api_key,
            system_prompt=QUICK_MODE_PROMPT.format(now=_now()),
            permission_mode=PermissionMode.YOLO,
            max_iterations=3,
            llm=llm_client,
        )
        agent.tools.register(_web_search, name="web_search")
        return agent

    if mode == "deep":
        agent = Agent(
            model=model,
            api_key=api_key,
            system_prompt=DEEP_MODE_PROMPT.format(now=_now()),
            permission_mode=PermissionMode.YOLO,
            max_iterations=10,
            llm=llm_client,
        )
        agent.tools.register(_make_search_stock(api_key), name="search_stock")
        agent.tools.register(
            _make_run_deep_analysis(
                api_key=api_key,
                analysis_type=analysis_type,
                peer_codes=peer_codes,
                enable_web_search=enable_web_search,
            ),
            name="run_deep_analysis",
        )
        agent.tools.register(_web_search, name="web_search")
        return agent

    if mode == "follow-up":
        session_id = kwargs.get("session_id")
        if not session_id:
            raise ValueError("follow-up 模式需要 session_id")

        session = _load_session(session_id)
        system_prompt = _build_follow_up_prompt(session)

        agent = Agent(
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            permission_mode=PermissionMode.YOLO,
            max_iterations=3,
            llm=llm_client,
        )
        agent.tools.register(_web_search, name="web_search")
        return agent

    raise ValueError(f"未知模式: {mode}")


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _make_llm_client(model: str, api_key: str | None = None):
    """创建 litellm 适配的 LLM 客户端。"""
    from finance_agent.harness.litellm_client import LiteLLMClient

    return LiteLLMClient(model=model, api_key=api_key)


def _load_session(session_id: str) -> dict:
    """从 session_store 加载 session。"""
    from finance_agent.session_store import get_session

    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    return session


def _build_follow_up_prompt(session: dict) -> str:
    """构建追问模式的 system prompt，注入报告上下文。"""
    import json

    report_md = session.get("report_markdown", "")
    report_excerpt = report_md[:6000]

    analyst_summaries_raw = session.get("analyst_summaries", "{}")
    if isinstance(analyst_summaries_raw, str):
        try:
            analyst_summaries = json.loads(analyst_summaries_raw)
        except json.JSONDecodeError:
            analyst_summaries = {}
    else:
        analyst_summaries = analyst_summaries_raw

    chat_history_raw = session.get("chat_history", "[]")
    if isinstance(chat_history_raw, str):
        try:
            chat_history = json.loads(chat_history_raw)
        except json.JSONDecodeError:
            chat_history = []
    else:
        chat_history = chat_history_raw

    # 格式化聊天历史
    history_lines = []
    for msg in chat_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        label = "用户" if role == "user" else "助手"
        history_lines.append(f"{label}: {content}")
    history_text = "\n".join(history_lines) if history_lines else "（无历史对话）"

    return FOLLOW_UP_MODE_PROMPT.format(
        now=_now(),
        report_excerpt=report_excerpt,
        analyst_summaries=json.dumps(analyst_summaries, ensure_ascii=False),
        chat_history=history_text,
        created_at=session.get("created_at", "未知"),
    )


# ───────────────────────────────────────────────
# SSE 事件流映射
# ───────────────────────────────────────────────


async def stream_agent_to_sse(
    agent: Agent,
    user_input: str,
    on_metadata: Callable[[dict], None] | None = None,
):
    """运行 Agent 并将 StreamEvent 映射为前端 SSE 格式。

    Args:
        agent: ReAct Agent 实例
        user_input: 用户输入
        on_metadata: TOOL_METADATA 事件的回调（用于 session 创建等）

    Yields:
        SSE 格式的字符串: "data: {...}\\n\\n"
    """
    from finance_agent.harness import ActionType

    async for event in agent.run(user_input):
        if event.event_type == ActionType.ANSWER:
            yield _sse({"type": "chat_token", "token": event.content})

        elif event.event_type == ActionType.THINK:
            yield _sse({"type": "thinking_token", "token": event.content})

        elif event.event_type == ActionType.TOOL_CALL:
            tc = event.tool_call
            yield _sse(
                {
                    "type": "tool_call",
                    "name": tc.name if tc else "",
                    "arguments": tc.arguments if tc else {},
                }
            )

        elif event.event_type == ActionType.PROGRESS:
            yield _sse(
                {
                    "type": "pipeline_progress",
                    "content": event.content,
                    "metadata": event.metadata or {},
                }
            )

        elif event.event_type == ActionType.TOOL_METADATA:
            if on_metadata and event.metadata:
                on_metadata(event.metadata)
            yield _sse(
                {
                    "type": "tool_metadata",
                    "metadata": event.metadata or {},
                }
            )

        elif event.event_type == ActionType.TOOL_RESULT:
            # TOOL_RESULT 不直接发给前端，进入 LLM 上下文
            # 但如果有 metadata，触发回调
            if event.tool_result and event.tool_result.metadata:
                if on_metadata:
                    on_metadata(event.tool_result.metadata)
                yield _sse(
                    {
                        "type": "tool_metadata",
                        "metadata": event.tool_result.metadata,
                    }
                )

        elif event.event_type == ActionType.ERROR:
            yield _sse({"type": "error", "message": event.content})

    yield _sse({"type": "chat_done"})


def _sse(data: dict) -> str:
    """格式化 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
