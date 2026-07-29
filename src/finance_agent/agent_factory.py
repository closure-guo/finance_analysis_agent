"""Agent 工厂函数。

根据模式构建 ReAct Agent，配置工具集、max_iterations 和 system prompt。

三种模式：
- quick: 工具=[web_search], max_iterations=3
- deep: 工具=[search_stock, run_deep_analysis, web_search], max_iterations=10
- follow-up: 工具=[web_search], max_iterations=3, 注入 session 上下文
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Callable
from typing import Any

from finance_agent.harness import Agent, PermissionMode
from finance_agent.prompts.loader import load_prompt

# ───────────────────────────────────────────────
# System Prompts（ADR-0016：从 prompts/*.md 加载，Langfuse 优先 + 本地兜底）
# ───────────────────────────────────────────────


def _quick_mode_prompt() -> str:
    return load_prompt("quick_mode").strip()


def _deep_mode_prompt() -> str:
    return load_prompt("deep_mode").strip()


def _follow_up_mode_prompt() -> str:
    return load_prompt("follow_up_mode").strip()


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


async def _stub_web_search(query: str) -> str:
    """TESTING=1 专用的 stub web_search 工具。

    返回带固定标记的、可被 parse_search_output 解析的搜索结果，
    不调用真实 Tavily API，使 E2E 能确定性验证"思考->web search->思考"序列
    （agent-turn-box-display delta）。

    Args:
        query: 搜索关键词
    """
    # 加延迟，让 E2E 能确定性捕获"正在搜索"中间态
    # （否则 search_start 与 search_result 几乎同时，中间态一闪而过；
    #  需足够长以覆盖 Playwright 轮询间隔与首轮渲染时机的不确定性）
    await asyncio.sleep(5.0)
    return (
        "[1] STUB 搜索结果：茅台最新消息\n"
        "https://stub.example.com/maotai-news\n"
        f"针对查询“{query}”的固定 stub 搜索结果，用于 E2E 确定性测试。\n"
        "\n"
        "[2] STUB 搜索结果：茅台提价公告\n"
        "https://stub.example.com/maotai-price\n"
        "茅台年内第二次提价的固定 stub 内容。\n"
    )


MAX_WEB_SOURCES = 20
MAX_SOURCE_CONTENT_LEN = 500

_web_search_cache: dict[str, str] = {}


def _make_web_search_with_collector(collector: list[dict]):
    """创建 web_search 工具，同时将搜索结果收集到 collector 用于引用溯源。"""

    async def web_search(query: str) -> str:
        """搜索网页获取实时信息

        Args:
            query: 搜索关键词
        """
        from finance_agent.web_search import format_search_for_llm, has_tavily_key, tavily_search

        if not has_tavily_key():
            return "[错误] 未配置 TAVILY_API_KEY，无法执行搜索。"
        if query in _web_search_cache:
            return _web_search_cache[query]
        response = tavily_search(query)
        result_text = format_search_for_llm(response)
        _web_search_cache[query] = result_text
        if len(collector) < MAX_WEB_SOURCES:
            for r in response.results:
                entry = {
                    "query": query,
                    "title": r.title,
                    "url": r.url,
                    "content": r.content[:MAX_SOURCE_CONTENT_LEN],
                }
                if entry not in collector:
                    collector.append(entry)
                    if len(collector) >= MAX_WEB_SOURCES:
                        break
        return result_text

    return web_search


def _make_batch_web_search(collector: list[dict]):
    """创建 batch_web_search 工具，并行搜索多个关键词并收集信源。"""

    async def batch_web_search(queries: list[str]) -> str:
        """并行批量搜索多个关键词，获取更全面的信息

        适用于需要从多个维度搜集信息的场景，如分析一只股票时同时搜索
        最新新闻、财务数据、行业对比、分析师观点等。

        Args:
            queries: 搜索关键词列表，建议 2-5 个不同维度的查询
        """
        from finance_agent.web_search import (
            batch_tavily_search,
            format_batch_for_llm,
            has_tavily_key,
        )

        if not has_tavily_key():
            return "[错误] 未配置 TAVILY_API_KEY，无法执行搜索。"
        if not queries:
            return "[错误] 查询列表为空"
        uncached = [q for q in queries if q not in _web_search_cache]
        cached_responses_text = [_web_search_cache[q] for q in queries if q in _web_search_cache]
        if uncached:
            responses = batch_tavily_search(uncached)
            new_text = format_batch_for_llm(responses)
            for resp in responses:
                _web_search_cache[resp.query] = format_batch_for_llm([resp])
                if len(collector) < MAX_WEB_SOURCES:
                    for r in resp.results:
                        entry = {
                            "query": resp.query,
                            "title": r.title,
                            "url": r.url,
                            "content": r.content[:MAX_SOURCE_CONTENT_LEN],
                        }
                        if entry not in collector:
                            collector.append(entry)
                            if len(collector) >= MAX_WEB_SOURCES:
                                break
        else:
            new_text = ""
        combined = "\n".join(t for t in [*cached_responses_text, new_text] if t)
        return combined or "[未找到相关信息]"

    return batch_web_search


def _make_search_stock(api_key: str | None = None):
    """创建 search_stock 工具，注入 api_key 闭包。"""

    async def search_stock(query: str = "") -> str:
        """根据自然语言解析 A 股股票代码

        Args:
            query: 股票名称、代码或描述，如 "茅台"、"600519"、"贵州茅台"
        """
        if not query or not query.strip():
            return "[错误] 查询为空，请提供股票名称或代码"

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

    def _get(c: dict, *keys: str) -> str:
        """兼容 stock_code/code 和 stock_name/name 两种键名。"""
        for k in keys:
            v = c.get(k)
            if v:
                return str(v)
        return ""

    if len(candidates) == 1:
        c = candidates[0]
        code = _get(c, "stock_code", "code")
        name = _get(c, "stock_name", "name")
        return f"找到股票：{name}({code})"

    lines = ["找到多个候选股票，请确认："]
    for i, c in enumerate(candidates, 1):
        code = _get(c, "stock_code", "code")
        name = _get(c, "stock_name", "name")
        lines.append(f"{i}. {name}({code})")
    return "\n".join(lines)


def _parse_stock_result_text(text: str) -> dict | None:
    """从 _format_stock_result 的输出文本中解析股票代码和名称。

    输入示例：
      "找到股票：中际旭创(300308)"
    返回：
      {"code": "300308", "name": "中际旭创"}
    """
    import re

    m = re.search(r"找到股票：(.+?)\((\d{6})\)", text)
    if m:
        return {"name": m.group(1), "code": m.group(2)}
    return None


def _make_run_deep_analysis(
    api_key: str | None = None,
    analysis_type: str = "comprehensive",
    peer_codes: list | None = None,
    enable_web_search: bool = False,
    session_id: str | None = None,
    web_sources: list[dict] | None = None,
):
    """创建 run_deep_analysis 流式工具，注入配置闭包。

    LLM 只看到 stock_code 和 stock_name，其余参数通过闭包注入。
    返回一个异步生成器，yield StreamEvent（PROGRESS + TOOL_RESULT）。
    session_id 用于 Langfuse session 聚合与 trace 属性（ADR-0015）。
    """

    async def run_deep_analysis(stock_code: str, stock_name: str = ""):
        """运行 5 层深度分析管线

        Args:
            stock_code: A 股股票代码，如 "600519"
            stock_name: 股票名称，如 "贵州茅台"
        """
        # ReAct 主链路快照与状态兜底（design.md §8 第 1 层）：
        # 工具自带 executor 线程不经 PipelineRunner，故在工具内维护
        # pipeline_snapshot 与会话 status，使「切换会话恢复」对真实主链路生效。
        # 事件流（StreamEvent yield 序列、metadata 结构、chunk_queue）保持不变。
        from finance_agent import session_store as _session_store
        from finance_agent.api import (
            _ALL_NODES,
            LAYER_STEPS,
            _extract_output,
            _merge_update,
        )
        from finance_agent.harness import ActionType, StreamEvent, ToolResult
        from finance_agent.pipeline_runner import (
            _current_node,
            _progress,
            apply_node_event,
            build_layer_tree,
        )

        # session_id 非空时才写快照/状态（理论空路径保持现状行为）
        _track_snapshot = bool(session_id)
        _tree: list[dict] = build_layer_tree() if _track_snapshot else []

        def _now_ms() -> int:
            import time as _time

            return int(_time.time() * 1000)

        def _persist_snapshot(tree: list[dict], now_ms: int) -> None:
            """把当前 layerTree 组装成快照并落库（与 PipelineRunner._run 同契约）。"""
            _session_store.update_pipeline_snapshot(
                session_id,
                {
                    "layerTree": tree,
                    "currentNodeId": _current_node(tree),
                    "progress": _progress(tree),
                    "updatedAt": now_ms,
                },
            )

        initial_state = {
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "analysis_type": analysis_type,
            "peer_codes": peer_codes,
            "enable_web_search": enable_web_search,
            "api_key": api_key,
            "web_sources": web_sources or [],
        }

        accumulated: dict = dict(initial_state)
        completed: set[str] = set()
        started_nodes: set[str] = set()  # 已发 node_start 的节点（去重）

        # 状态兜底：工具入口置 running（管线本体已在 executor 线程运行）
        if _track_snapshot:
            _session_store.update_session_status(session_id, "running")

        # 在线程中运行同步 graph.stream，避免阻塞事件循环
        # ADR-0015：CallbackHandler 通过 langchain callback 机制工作（不依赖 OTel
        # context 跨线程传播），直接在子线程跑即可。
        loop = asyncio.get_event_loop()
        chunk_queue: asyncio.Queue = asyncio.Queue()

        def _run_graph():
            try:
                for mode, chunk in _stream_graph(initial_state, session_id=session_id):
                    asyncio.run_coroutine_threadsafe(chunk_queue.put((mode, chunk)), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(chunk_queue.put(e), loop)
            finally:
                asyncio.run_coroutine_threadsafe(chunk_queue.put(None), loop)

        loop.run_in_executor(None, _run_graph)

        # 节点真实生命周期时间戳（custom 流的 node_start/node_end），
        # 用于给 updates 流的 node_complete 附加 server_*（修复快速节点计时恒 0）。
        node_lifecycle: dict[str, dict] = {}

        try:
            while True:
                item = await chunk_queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item

                mode, chunk = item

                # Custom mode: forward thinking tokens + 节点生命周期时间戳
                if mode == "custom":
                    if isinstance(chunk, dict):
                        ctype = chunk.get("type")
                        if ctype == "thinking":
                            # 透传管线节点名（此前丢弃 chunk["node"]，导致前端所有管线思考
                            # 归入 nodeTimelines['']，按 agent 分组不可达——真实 bug 修复）
                            node = chunk.get("node", "")
                            yield StreamEvent.think(
                                chunk.get("token", ""), metadata={"node": node} if node else None
                            )
                        elif ctype == "node_start":
                            # 节点真实入口时间戳（timed_node 装饰器发出）
                            node_lifecycle.setdefault(chunk["node"], {})["start_ts"] = chunk["ts"]
                        elif ctype == "node_end":
                            # 节点真实出口时间戳与耗时；记录并立即下发 node_timing 事件
                            # （node_complete 由 updates chunk 驱动、可能已先于 node_end 发出，
                            #  故真实耗时经独立 node_timing 下发，前端据此覆盖近似值）。
                            node_name = chunk["node"]
                            lc = node_lifecycle.setdefault(node_name, {})
                            lc["end_ts"] = chunk["ts"]
                            lc["duration_ms"] = chunk.get("duration_ms")
                            if _track_snapshot:
                                _now = _now_ms()
                                _tree = apply_node_event(
                                    _tree,
                                    {
                                        "type": "node_timing",
                                        "node_id": node_name,
                                        "server_start_ts": lc.get("start_ts"),
                                        "server_end_ts": lc.get("end_ts"),
                                        "server_duration_ms": lc.get("duration_ms"),
                                    },
                                    _now,
                                )
                                _persist_snapshot(_tree, _now)
                            yield StreamEvent.progress(
                                content=f"{node_name} timing",
                                metadata={
                                    "node": node_name,
                                    "sse_type": "node_timing",
                                    "node_id": node_name,
                                    "server_start_ts": lc.get("start_ts"),
                                    "server_end_ts": lc.get("end_ts"),
                                    "server_duration_ms": lc.get("duration_ms"),
                                },
                            )
                    continue

                # Updates mode: existing node progress logic
                for node_name, update in chunk.items():
                    if node_name not in _ALL_NODES:
                        continue

                    if isinstance(update, dict) and update:
                        _merge_update(accumulated, node_name, update)

                    idx = _ALL_NODES.index(node_name)
                    for i in range(idx + 1):
                        completed.add(_ALL_NODES[i])

                    step_info = {s["node"]: s for s in LAYER_STEPS}.get(node_name, {})

                    # 节点首次出现：先发 node_start（与 fast path 事件序列对齐）
                    if node_name not in started_nodes:
                        started_nodes.add(node_name)
                        start_meta = {
                            "node": node_name,
                            "sse_type": "node_start",
                            "node_id": node_name,
                            "layer": step_info.get("layer", ""),
                            "desc": step_info.get("desc", node_name),
                        }
                        # 附加后端真实入口时间戳（custom 流 node_start 已先行到达）
                        _lc = node_lifecycle.get(node_name, {})
                        if "start_ts" in _lc:
                            start_meta["server_start_ts"] = _lc["start_ts"]
                        if _track_snapshot:
                            _now = _now_ms()
                            _tree = apply_node_event(
                                _tree,
                                {
                                    "type": "node_start",
                                    "node_id": node_name,
                                    **(
                                        {"server_start_ts": start_meta["server_start_ts"]}
                                        if "server_start_ts" in start_meta
                                        else {}
                                    ),
                                },
                                _now,
                            )
                            _persist_snapshot(_tree, _now)
                        yield StreamEvent.progress(
                            content=f"{step_info.get('layer', '')}: {step_info.get('desc', node_name)}...",
                            metadata=start_meta,
                        )

                    output = _extract_output(
                        node_name, update if isinstance(update, dict) else {}, accumulated
                    )

                    # yield PROGRESS with detailed metadata -> stream_agent_to_sse 映射为 node_complete
                    # 注：真实耗时经独立 node_timing 事件下发（node_end 到达时），此处不附加，
                    # 因 node_end 时序上晚于本 updates chunk，duration 此刻尚不可得。
                    if _track_snapshot:
                        _now = _now_ms()
                        _tree = apply_node_event(
                            _tree,
                            {"type": "node_complete", "node_id": node_name, "output": output},
                            _now,
                        )
                        _persist_snapshot(_tree, _now)
                    yield StreamEvent.progress(
                        content=f"{step_info.get('layer', '')}: {step_info.get('desc', node_name)} ✓",
                        metadata={
                            "node": node_name,
                            "sse_type": "node_complete",
                            "node_id": node_name,
                            "layer": step_info.get("layer", ""),
                            "desc": step_info.get("desc", node_name),
                            "completed": sorted(completed),
                            "progress": len(completed) / len(LAYER_STEPS),
                            "output": output,
                        },
                    )
        except Exception:
            # 异常兜底：置 failed 后 re-raise（行为与 PipelineRunner._run 对齐）
            if _track_snapshot:
                _session_store.update_session_status(session_id, "failed")
            raise

        # 正常结束：写最终快照并置 completed（组装 report metadata 前）
        if _track_snapshot:
            _persist_snapshot(_tree, _now_ms())
            _session_store.update_session_status(session_id, "completed")

        report_md = accumulated.get("final_report", "")
        metadata = {
            "chart_data": accumulated.get("chart_data") or {},
            "analyst_reports": accumulated.get("analyst_reports") or {},
            "stock_code": stock_code,
            "stock_name": accumulated.get("stock_name") or stock_name or stock_code,
            "report_markdown": report_md,
            "web_sources": web_sources or [],
            "sse_type": "report_ready",
        }

        # LLM 上下文只放摘要
        llm_output = f"深度分析完成。股票：{metadata['stock_name']}({stock_code})。\n"
        llm_output += f"报告已生成，共 {len(report_md)} 字符。\n"
        if len(report_md) > 2000:
            llm_output += f"报告摘要：\n{report_md[:2000]}...\n"
        else:
            llm_output += f"报告内容：\n{report_md}"

        yield StreamEvent(
            event_type=ActionType.TOOL_RESULT,
            content=llm_output,
            tool_result=ToolResult(
                tool_call_id="",
                name="run_deep_analysis",
                output=llm_output,
                metadata=metadata,
            ),
        )

    return run_deep_analysis


def _stream_graph(initial_state: dict, config: dict | None = None, session_id: str | None = None):
    """执行 5 层管线同步流式迭代。

    ADR-0015：注入 Langfuse CallbackHandler 使图节点自动挂成 span 树（Send 扇出
    会自动传播 callback）。CallbackHandler 通过 OTel context.attach 设置 current
    span，使 call_llm 的 generation（start_as_current_observation）能挂到节点 span 下。
    """
    from finance_agent.graph import build_5layer_graph

    if config is None:
        config = {"recursion_limit": 100}

    from finance_agent.langfuse_tracing import get_callback_handler, get_langfuse

    _handler = get_callback_handler()
    _lf = get_langfuse()
    if _handler is not None:
        config = {**config, "callbacks": [*config.get("callbacks", []), _handler]}
        # ADR-0015：通过 metadata 传 langfuse_session_id，CallbackHandler 自动聚合到 session
        if session_id:
            config["metadata"] = {**config.get("metadata", {}), "langfuse_session_id": session_id}

    graph = build_5layer_graph()

    try:
        yield from graph.stream(  # type: ignore[call-overload]
            initial_state,
            config=config,
            stream_mode=["updates", "custom"],
        )
    finally:
        if _lf is not None:
            with contextlib.suppress(Exception):
                _lf.flush()


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
        prompt = _quick_mode_prompt().format(now=_now())
        agent = Agent(
            model=model,
            api_key=api_key,
            system_prompt=prompt,
            permission_mode=PermissionMode.YOLO,
            max_iterations=3,
            llm=llm_client,
        )
        # TESTING=1 时注册 stub web_search（固定结果，不调真实 Tavily），
        # 与 StubLLMClient 的 tool_call 场景配合，确定性复现"思考->web search->思考"。
        from finance_agent.api import TESTING

        agent.tools.register(_stub_web_search if TESTING else _web_search, name="web_search")
        session_id = kwargs.get("session_id")
        if session_id:
            _inject_chat_history(agent, session_id)
        return agent

    if mode == "deep":
        prompt = _deep_mode_prompt().format(now=_now())
        agent = Agent(
            model=model,
            api_key=api_key,
            system_prompt=prompt,
            permission_mode=PermissionMode.YOLO,
            max_iterations=10,
            llm=llm_client,
        )
        web_sources_collector: list[dict] = []
        agent.tools.register(_make_search_stock(api_key), name="search_stock")
        agent.tools.register(
            _make_run_deep_analysis(
                api_key=api_key,
                analysis_type=analysis_type,
                peer_codes=peer_codes,
                enable_web_search=enable_web_search,
                session_id=kwargs.get("session_id"),
                web_sources=web_sources_collector,
            ),
            name="run_deep_analysis",
        )
        # TESTING=1 时注册 stub web_search（固定结果，不调真实 Tavily），
        # 与 quick 分支同一 stub 逻辑，使深度模式澄清阶段也能确定性复现
        # "思考->web search->思考"时间序列（agent-turn-box-display delta task 5.4）。
        from finance_agent.api import TESTING

        agent.tools.register(
            _stub_web_search if TESTING else _make_web_search_with_collector(web_sources_collector),
            name="web_search",
        )
        agent.tools.register(_make_batch_web_search(web_sources_collector), name="batch_web_search")
        session_id = kwargs.get("session_id")
        if session_id:
            _inject_chat_history(agent, session_id)
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
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")


def _make_llm_client(model: str, api_key: str | None = None):
    """创建 litellm 适配的 LLM 客户端。

    TESTING=1 时返回 StubLLMClient（按固定节奏吐文本 delta），不连真 LLM。
    见 docs/superpowers/plans/2026-07-26-f3a-e2e-core-specs.md Task 1。
    """
    from finance_agent.api import TESTING

    if TESTING:
        # F3a: 返回可控 stub LLM 客户端（按固定节奏吐文本 delta）
        # STUB_SCENARIO=tool_call 时启用"思考1->tool_call(web_search)->思考2->回答"场景，
        # 用于 E2E 确定性验证思考-搜索-思考时间序列（agent-turn-box-display delta）。
        from finance_agent.harness.stub_llm_client import StubLLMClient

        return StubLLMClient(scenario=os.getenv("STUB_SCENARIO"))

    from finance_agent.harness.litellm_client import LiteLLMClient

    return LiteLLMClient(model=model, api_key=api_key)


def _inject_chat_history(agent: Agent, session_id: str) -> None:
    """将 session 中的历史对话以标准 user/assistant 消息轮次注入 agent 上下文。

    用标准消息角色（而非 system prompt 纯文本）注入历史，
    使 LLM 能正确理解多轮对话的指代关系。
    """
    session = _load_session(session_id)
    chat_history_raw = session.get("chat_history", [])
    if isinstance(chat_history_raw, str):
        try:
            chat_history = json.loads(chat_history_raw)
        except json.JSONDecodeError:
            chat_history = []
    else:
        chat_history = chat_history_raw

    for h in chat_history:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role == "user":
            agent.context.append_user(content)
        else:
            agent.context.append_assistant(content)


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

    return _follow_up_mode_prompt().format(
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
    on_resolved: Callable[[str, str], None] | None = None,
    extra_events: dict | None = None,
    force_tool: bool = False,
    session_id: str | None = None,
    user_id: str | None = None,
):
    """运行 Agent 并将 StreamEvent 映射为前端 SSE 格式。

    Args:
        agent: ReAct Agent 实例
        user_input: 用户输入
        on_metadata: TOOL_METADATA 事件的回调（用于 session 创建等）
        on_resolved: 股票代码解析完成回调 (stock_code, stock_name)
        extra_events: 额外的事件上下文（如 session_id 用于 session_created）
        session_id: Langfuse session 聚合 ID（ADR-0015）。设置后用 react_loop span
            包裹 ReAct 执行并 propagate_attributes(session_id)。
        user_id: Langfuse user 聚合 ID（ADR-0015）。设置后 propagate_attributes(user_id)。

    Yields:
        SSE 格式的字符串: "data: {...}\\n\\n"
    """
    from finance_agent.harness import ActionType

    last_web_search_query = ""  # 追踪 web_search 的查询参数

    # ADR-0015: react_loop span 包裹 ReAct 执行，使顶层 trace 结构为
    # [react_loop] -> [search_stock] / [run_deep_analysis span -> 5 层]。
    # 手动管理上下文以避免重构大段事件映射循环；异常路径下 span 由 OTel
    # span processor 周期性导出兜底。
    from contextlib import nullcontext as _nullcontext

    from finance_agent.langfuse_tracing import get_langfuse as _get_langfuse

    _lf = _get_langfuse()
    _react_cm: contextlib.AbstractContextManager[Any] = _nullcontext()
    _propagate_cm: contextlib.AbstractContextManager[Any] = _nullcontext()
    if _lf is not None:
        _react_cm = _lf.start_as_current_observation(
            as_type="span", name="react_loop", input={"query": user_input}
        )
        if session_id or user_id:
            try:
                from langfuse import propagate_attributes

                _propagate_cm = propagate_attributes(session_id=session_id, user_id=user_id)
            except Exception:  # noqa: S110
                pass
    _react_cm.__enter__()
    _propagate_cm.__enter__()
    async for event in agent.run(user_input, force_tool=force_tool):
        ts = _now()

        if event.event_type == ActionType.ANSWER:
            yield _sse({"type": "chat_token", "token": event.content, "timestamp": ts})

        elif event.event_type == ActionType.THINK:
            # 原生思考增量（DeepSeek reasoning_content），与回答（chat_token）分离。
            # 管线运行期间的思考带 node metadata（管线节点名），透传给前端按 agent 阶段分组。
            meta = event.metadata or {}
            payload: dict = {"type": "thinking_token", "token": event.content, "timestamp": ts}
            if meta.get("node"):
                payload["node"] = meta["node"]
            yield _sse(payload)

        elif event.event_type == ActionType.TOOL_CALL:
            tc = event.tool_call
            # 跳过 permission_required 事件（tool_call 为 None，只有 permission_request）
            if not tc:
                continue
            name = tc.name or ""
            args = tc.arguments if tc else {}
            if name == "web_search":
                last_web_search_query = str(args.get("query", ""))
                yield _sse(
                    {"type": "search_start", "query": last_web_search_query, "timestamp": ts}
                )
            yield _sse(
                {
                    "type": "tool_call",
                    "name": name,
                    "args": args,
                    "timestamp": ts,
                }
            )

        elif event.event_type == ActionType.PROGRESS:
            # 映射为前端期望的 node_start / node_complete 事件
            meta = event.metadata or {}
            sse_type = meta.get("sse_type", "node_complete")
            if sse_type == "node_timing":
                # 节点真实耗时（node_end 到达时下发），前端据此覆盖 updates 近似值
                yield _sse(
                    {
                        "type": "node_timing",
                        "node_id": meta.get("node_id", ""),
                        "server_start_ts": meta.get("server_start_ts"),
                        "server_end_ts": meta.get("server_end_ts"),
                        "server_duration_ms": meta.get("server_duration_ms"),
                        "timestamp": ts,
                    }
                )
            elif sse_type == "node_start":
                payload = {
                    "type": "node_start",
                    "node_id": meta.get("node_id", ""),
                    "layer": meta.get("layer", ""),
                    "desc": meta.get("desc", ""),
                    "timestamp": ts,
                }
                # 透传后端真实入口时间戳（当前运行节点实时已运行时长基于此）
                if "server_start_ts" in meta:
                    payload["server_start_ts"] = meta["server_start_ts"]
                yield _sse(payload)
            elif sse_type == "node_complete":
                yield _sse(
                    {
                        "type": "node_complete",
                        "node_id": meta.get("node_id", ""),
                        "layer": meta.get("layer", ""),
                        "desc": meta.get("desc", ""),
                        "completed": meta.get("completed", []),
                        "progress": meta.get("progress", 0),
                        "output": meta.get("output", {}),
                        "timestamp": ts,
                    }
                )
            else:
                yield _sse(
                    {
                        "type": "pipeline_progress",
                        "content": event.content,
                        "metadata": meta,
                        "timestamp": ts,
                    }
                )

        elif event.event_type == ActionType.TOOL_METADATA:
            if on_metadata and event.metadata:
                on_metadata(event.metadata)
            yield _sse(
                {
                    "type": "pipeline_update",
                    "metadata": event.metadata or {},
                    "timestamp": ts,
                }
            )

        elif event.event_type == ActionType.TOOL_RESULT:
            tr = event.tool_result
            if tr:
                # 处理 metadata（chart_data、analyst_reports 等）
                if tr.metadata:
                    if on_metadata:
                        on_metadata(tr.metadata)

                    sse_type = tr.metadata.get("sse_type", "")

                    # run_deep_analysis 的最终结果：发送 report_ready
                    if sse_type == "report_ready" or tr.name == "run_deep_analysis":
                        stock_code = tr.metadata.get("stock_code", "")
                        stock_name = tr.metadata.get("stock_name", "")
                        if on_resolved:
                            on_resolved(stock_code, stock_name)
                        yield _sse(
                            {
                                "type": "resolved",
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                "timestamp": ts,
                            }
                        )
                        yield _sse(
                            {
                                "type": "report_ready",
                                "report_markdown": tr.metadata.get("report_markdown", ""),
                                "chart_data": tr.metadata.get("chart_data", {}),
                                "stock_name": stock_name,
                                "web_sources": tr.metadata.get("web_sources", []),
                                "timestamp": ts,
                            }
                        )
                    else:
                        yield _sse(
                            {
                                "type": "pipeline_update",
                                "metadata": tr.metadata,
                                "timestamp": ts,
                            }
                        )
                else:
                    # 普通工具结果
                    result_data = tr.output
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        result_data = json.loads(tr.output)

                    # web_search: 解析纯文本结果，发送结构化搜索来源
                    if tr.name == "web_search" and isinstance(result_data, str):
                        from finance_agent.web_search import parse_search_output

                        search_results = parse_search_output(result_data)
                        if search_results:
                            yield _sse(
                                {
                                    "type": "search_result",
                                    "query": last_web_search_query,
                                    "results": [
                                        {"title": r.title, "url": r.url, "content": r.content}
                                        for r in search_results
                                    ],
                                    "count": len(search_results),
                                    "timestamp": ts,
                                }
                            )

                    # search_stock: 解析纯文本结果，发送结构化股票信息
                    if tr.name == "search_stock" and isinstance(result_data, str):
                        stock_info = _parse_stock_result_text(result_data)
                        if stock_info:
                            # 通过 on_metadata 回调通知调用方（用于 fallback）
                            if on_metadata:
                                on_metadata(
                                    {
                                        "search_stock_code": stock_info["code"],
                                        "search_stock_name": stock_info["name"],
                                    }
                                )
                            yield _sse(
                                {
                                    "type": "stock_resolved",
                                    "stock_code": stock_info["code"],
                                    "stock_name": stock_info["name"],
                                    "timestamp": ts,
                                }
                            )

                    yield _sse(
                        {
                            "type": "tool_result",
                            "name": tr.name,
                            "result": result_data,
                            "timestamp": ts,
                        }
                    )

        elif event.event_type == ActionType.ERROR:
            yield _sse({"type": "error", "message": event.content, "timestamp": ts})

    # ADR-0015: 退出 react_loop span 与 session 聚合上下文
    _propagate_cm.__exit__(None, None, None)
    _react_cm.__exit__(None, None, None)

    yield _sse({"type": "chat_done", "timestamp": _now()})
    # NOTE: done 事件由调用方发送（确保 session_created 等事件先发完）


def _sse(data: dict) -> str:
    """格式化 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
