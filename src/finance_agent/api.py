"""FastAPI backend — SSE streaming for 5-layer analysis + sessions + NLP + streaming chat."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()  # 加载 .env，须在 finance_agent 模块导入前执行（llm.py 等在 import 时读取环境变量）

from finance_agent.graph import build_5layer_graph
from finance_agent.llm import call_llm_with_tools
from finance_agent.react_agent import (
    REACT_SYSTEM_PROMPT,
    REACT_TOOLS,
    search_stock_tool,
)
from finance_agent.session_store import (
    append_chat,
    create_chat_session,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_sessions,
    rename_session,
)

app = FastAPI(title="Finance Analysis Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_5layer_graph()

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

# Initialize session DB
init_db()

# ── Node → Layer/Description mapping (shared with frontend) ──

LAYER_STEPS: list[dict] = [
    {"node": "check_cache", "layer": "PREP", "desc": "数据准备", "icon": "database"},
    {"node": "fetch_data", "layer": "PREP", "desc": "获取财务数据", "icon": "download"},
    {"node": "validate_financials", "layer": "PREP", "desc": "勾稽校验", "icon": "check-double"},
    {"node": "compute_metrics", "layer": "PREP", "desc": "指标计算", "icon": "calculator"},
    {"node": "technical_analyst", "layer": "Layer I", "desc": "技术面分析", "icon": "chart-line"},
    {"node": "verify_citations", "layer": "校验", "desc": "引用校验", "icon": "shield-alt"},
    {"node": "bull_r1", "layer": "Layer II", "desc": "看多辩论 R1", "icon": "arrow-up"},
    {"node": "bear_r1", "layer": "Layer II", "desc": "看空辩论 R1", "icon": "arrow-down"},
    {"node": "bull_r2", "layer": "Layer II", "desc": "看多辩论 R2", "icon": "arrow-up"},
    {"node": "bear_r2", "layer": "Layer II", "desc": "看空辩论 R2", "icon": "arrow-down"},
    {"node": "research_manager", "layer": "Layer II", "desc": "研究结论", "icon": "flag"},
    {"node": "trader", "layer": "Layer III", "desc": "交易决策", "icon": "hand-holding-usd"},
    {"node": "aggressive_r1", "layer": "Layer IV", "desc": "激进风控 R1", "icon": "fire"},
    {"node": "conservative_r1", "layer": "Layer IV", "desc": "保守风控 R1", "icon": "shield-alt"},
    {"node": "neutral_r1", "layer": "Layer IV", "desc": "中性风控 R1", "icon": "balance-scale"},
    {"node": "aggressive_r2", "layer": "Layer IV", "desc": "激进风控 R2", "icon": "fire"},
    {"node": "conservative_r2", "layer": "Layer IV", "desc": "保守风控 R2", "icon": "shield-alt"},
    {"node": "neutral_r2", "layer": "Layer IV", "desc": "中性风控 R2", "icon": "balance-scale"},
    {"node": "risk_judge", "layer": "Layer IV", "desc": "风控裁决", "icon": "gavel"},
    {"node": "fund_manager", "layer": "Layer V", "desc": "基金经理审批", "icon": "user-tie"},
    {"node": "generate_report", "layer": "报告", "desc": "报告生成", "icon": "file-alt"},
    {"node": "generate_file", "layer": "报告", "desc": "文件导出", "icon": "file-export"},
]

_NODE_MAP = {s["node"]: s for s in LAYER_STEPS}
_ALL_NODES = [s["node"] for s in LAYER_STEPS]

# Node → thinking description (streamed to frontend during execution)
_NODE_THINKING: dict[str, str] = {
    "check_cache": "正在检查缓存数据…",
    "fetch_data": "正在获取财务数据（行情、财报、技术指标）…",
    "validate_financials": "正在进行勾稽校验，验证数据一致性…",
    "compute_metrics": "正在计算关键技术指标（MACD、RSI、KDJ 等）…",
    "technical_analyst": "Layer I：技术面分析师正在分析价格趋势与技术指标…",
    "verify_citations": "正在校验分析引用的数据来源…",
    "bull_r1": "Layer II：看多分析师正在构建看多论点…",
    "bear_r1": "Layer II：看空分析师正在构建看空论点…",
    "bull_r2": "Layer II：看多分析师进行第二轮辩论…",
    "bear_r2": "Layer II：看空分析师进行第二轮辩论…",
    "research_manager": "Layer II：研究经理正在汇总辩论结论…",
    "trader": "Layer III：交易员正在制定交易决策…",
    "aggressive_r1": "Layer IV：激进风控分析师正在评估…",
    "conservative_r1": "Layer IV：保守风控分析师正在评估…",
    "neutral_r1": "Layer IV：中性风控分析师正在评估…",
    "aggressive_r2": "Layer IV：激进风控分析师进行第二轮评估…",
    "conservative_r2": "Layer IV：保守风控分析师进行第二轮评估…",
    "neutral_r2": "Layer IV：中性风控分析师进行第二轮评估…",
    "risk_judge": "Layer IV：风控裁决正在综合评估风险…",
    "fund_manager": "Layer V：基金经理正在审批最终决策…",
    "generate_report": "正在生成深度分析报告…",
    "generate_file": "正在导出报告文件…",
}


# ── Request models ──


class AnalyzeRequest(BaseModel):
    stock_code: str = ""
    stock_name: str | None = None
    query: str = ""  # Natural language input
    analysis_type: str = "comprehensive"
    peer_codes: str | None = None
    enable_web_search: bool = False
    api_key: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    context: dict | None = None
    api_key: str | None = None


class RenameRequest(BaseModel):
    display_name: str


# ── Helpers ──


def _sse(data: dict) -> str:
    """Format a SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _stream_from_sync(gen):
    """把同步生成器转换为异步生成器，在线程中运行避免阻塞事件循环。

    用于在 async def event_stream 中迭代同步的 _run_graph_streaming 生成器。
    5 层分析图执行可能需要 90+ 秒，直接在事件循环中迭代会阻塞 SSE 流式输出。
    """
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _run():
        try:
            for item in gen:
                asyncio.run_coroutine_threadsafe(q.put(item), loop)
        except Exception as e:  # noqa: BLE001
            asyncio.run_coroutine_threadsafe(q.put(e), loop)
        finally:
            asyncio.run_coroutine_threadsafe(q.put(None), loop)

    loop.run_in_executor(None, _run)

    while True:
        item = await q.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        yield item


def _extract_output(node_name: str, update: dict, accumulated: dict) -> dict:
    """Extract structured output from a node update for the frontend."""
    output: dict[str, Any] = {}

    if node_name in ("technical_analyst",):
        reports = accumulated.get("analyst_reports") or {}
        report = reports.get("technical") or reports.get(node_name)
        if report:
            if hasattr(report, "model_dump"):
                output = report.model_dump()
            elif isinstance(report, dict):
                output = report

    elif node_name in (
        "bull_r1",
        "bull_r2",
        "bear_r1",
        "bear_r2",
        "aggressive_r1",
        "aggressive_r2",
        "conservative_r1",
        "conservative_r2",
        "neutral_r1",
        "neutral_r2",
        "research_manager",
        "risk_judge",
    ):
        history = accumulated.get("debate_history") or []
        if history:
            last = history[-1]
            if hasattr(last, "model_dump"):
                output = last.model_dump()
            elif isinstance(last, dict):
                output = last

    elif node_name == "trader":
        decision = accumulated.get("trade_decision")
        if decision:
            if hasattr(decision, "model_dump"):
                output = decision.model_dump()
            elif isinstance(decision, dict):
                output = decision

    elif node_name == "fund_manager":
        output = update if isinstance(update, dict) else {}

    elif node_name == "generate_report":
        output = {"report_markdown": accumulated.get("final_report", "")}

    elif node_name == "generate_file":
        file_paths = accumulated.get("file_paths") or {}
        output = {"file_paths": file_paths}

    return output


def _merge_update(accumulated: dict, node_name: str, update: dict) -> None:
    """Merge a graph node update into accumulated state."""
    if not isinstance(update, dict):
        return
    for key, val in update.items():
        if key == "analyst_reports" and isinstance(val, dict):
            existing = accumulated.get("analyst_reports") or {}
            existing.update(val)
            accumulated["analyst_reports"] = existing
        elif key == "debate_history" and isinstance(val, list):
            existing = accumulated.get("debate_history") or []
            existing.extend(val)
            accumulated["debate_history"] = existing
        else:
            accumulated[key] = val


def _extract_analyst_summaries(accumulated: dict) -> dict:
    """Extract one-line summaries from each analyst report for chat context."""
    summaries: dict[str, str] = {}
    reports = accumulated.get("analyst_reports") or {}
    for name, report in reports.items():
        if hasattr(report, "summary"):
            summaries[name] = report.summary
        elif isinstance(report, dict):
            summaries[name] = str(report.get("summary", ""))
    return summaries


def _extract_agent_process(accumulated: dict) -> dict:
    """Extract Layer II-V intermediate outputs for session storage."""
    return {
        "research_conclusion": accumulated.get("research_manager_conclusion", ""),
        "trade_decision": _safe_dump(accumulated.get("trade_decision")),
        "risk_debate": _safe_dump(accumulated.get("risk_debate_history")),
        "fund_manager_decision": accumulated.get("fund_manager_decision", ""),
    }


def _safe_dump(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_safe_dump(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe_dump(v) for k, v in obj.items()}
    return obj


def _stream_report_chunks(markdown: str, chunk_size: int = 200) -> list[str]:
    """Split markdown into chunks for progressive rendering."""
    chunks: list[str] = []
    lines = markdown.split("\n")
    current = ""
    for line in lines:
        current += line + "\n"
        if len(current) >= chunk_size:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


# ── Routes ──


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/pipeline")
async def get_pipeline():
    """Return the pipeline node definitions for the frontend."""
    return {"steps": LAYER_STEPS}


# ── Sessions CRUD ──


@app.get("/api/sessions")
async def get_sessions():
    """List all sessions (metadata only)."""
    return {"sessions": list_sessions()}


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get full session by id."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.patch("/api/sessions/{session_id}")
async def rename_session_api(session_id: str, req: RenameRequest):
    """Rename a session."""
    if not rename_session(session_id, req.display_name):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
async def delete_session_api(session_id: str):
    """Delete a session."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


# ── Graph streaming (encapsulated as a reusable tool) ──


def _run_graph_streaming(
    stock_code: str,
    stock_name: str,
    req: AnalyzeRequest,
    analysis_id: str,
    start_time: float,
) -> Generator[str, None, None]:
    """执行 5 层图分析，流式 yield SSE 事件。

    封装了 PREP → Layer I-V → 报告生成的完整流程，
    可作为 ReAct 循环中 run_deep_analysis 工具的执行体。
    """
    initial_state = {
        "stock_code": stock_code,
        "stock_name": stock_name or stock_code,
        "analysis_type": req.analysis_type or "comprehensive",
        "peer_codes": [c.strip() for c in (req.peer_codes or "").split(",") if c.strip()] or None,
        "enable_web_search": req.enable_web_search,
        "api_key": req.api_key,
    }

    yield _sse(
        {
            "type": "analysis_start",
            "analysis_id": analysis_id,
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "timestamp": _now(),
        }
    )

    completed: set[str] = set()
    accumulated: dict = dict(initial_state)

    try:
        for chunk in graph.stream(
            initial_state,
            config={"recursion_limit": 100},
            stream_mode="updates",
        ):
            for node_name, update in chunk.items():
                if node_name not in _NODE_MAP:
                    if isinstance(update, dict) and update:
                        _merge_update(accumulated, node_name, update)
                    continue

                step_info = _NODE_MAP[node_name]
                yield _sse(
                    {
                        "type": "node_start",
                        "node_id": node_name,
                        "layer": step_info["layer"],
                        "desc": step_info["desc"],
                        "icon": step_info["icon"],
                        "timestamp": _now(),
                    }
                )

                node_thinking = _NODE_THINKING.get(node_name, f"正在执行：{step_info['desc']}…")
                yield _sse(
                    {
                        "type": "thinking_token",
                        "token": f"\n▶ {node_thinking}\n",
                        "timestamp": _now(),
                    }
                )

                _merge_update(accumulated, node_name, update if isinstance(update, dict) else {})

                idx = _ALL_NODES.index(node_name)
                for i in range(idx + 1):
                    completed.add(_ALL_NODES[i])

                if accumulated.get("stock_name") in (None, "", stock_code):
                    quote = accumulated.get("stock_quote") or {}
                    info = accumulated.get("industry_info") or {}
                    fetched_name = quote.get("name") or info.get("name")
                    if fetched_name:
                        accumulated["stock_name"] = fetched_name

                output = _extract_output(
                    node_name, update if isinstance(update, dict) else {}, accumulated
                )

                yield _sse(
                    {
                        "type": "node_complete",
                        "node_id": node_name,
                        "layer": step_info["layer"],
                        "desc": step_info["desc"],
                        "completed": sorted(completed),
                        "progress": len(completed) / len(LAYER_STEPS),
                        "output": output,
                        "timestamp": _now(),
                    }
                )

                summary_text = ""
                if isinstance(output, dict):
                    summary_text = output.get("summary", "")
                if summary_text:
                    yield _sse(
                        {
                            "type": "thinking_token",
                            "token": f"  ✓ {summary_text}\n",
                            "timestamp": _now(),
                        }
                    )

            if accumulated.get("final_report"):
                file_paths = accumulated.get("file_paths") or {}
                stock_name_final = accumulated.get("stock_name", stock_code)
                duration_ms = int((time.time() - start_time) * 1000)

                report_md = accumulated["final_report"]
                chunks = _stream_report_chunks(report_md)

                for i, chunk_text in enumerate(chunks):
                    yield _sse(
                        {
                            "type": "report_chunk",
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "text": chunk_text,
                            "timestamp": _now(),
                        }
                    )

                analyst_summaries = _extract_analyst_summaries(accumulated)
                agent_process = _extract_agent_process(accumulated)
                session_id = create_session(
                    stock_code=stock_code,
                    stock_name=stock_name_final,
                    report_markdown=report_md,
                    chart_data=accumulated.get("chart_data") or {},
                    analyst_reports=_safe_dump(accumulated.get("analyst_reports") or {}),
                    agent_process=agent_process,
                    analyst_summaries=analyst_summaries,
                    duration_ms=duration_ms,
                )

                yield _sse(
                    {
                        "type": "report_ready",
                        "analysis_id": analysis_id,
                        "session_id": session_id,
                        "report_markdown": report_md,
                        "chart_data": accumulated.get("chart_data") or {},
                        "file_paths": file_paths,
                        "stock_name": stock_name_final,
                        "duration_ms": duration_ms,
                        "timestamp": _now(),
                    }
                )

    except Exception as e:
        yield _sse(
            {
                "type": "error",
                "node_id": "unknown",
                "message": str(e),
                "traceback": str(e.__traceback__),
                "timestamp": _now(),
            }
        )


# ── Analyze (ReAct loop) ──


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Start analysis via ReAct loop — LLM decides which tools to call.

    Tools available:
    - search_stock: Search for stocks by natural language query
    - run_deep_analysis: Execute the 5-layer analysis pipeline
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        analysis_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        stock_code = req.stock_code.strip()
        stock_name = req.stock_name or ""

        # ── Fast path: stock_code already provided, skip ReAct ──
        if stock_code:
            yield _sse(
                {
                    "type": "thinking_token",
                    "token": f"📋 开始执行深度分析：{stock_name or stock_code}（{stock_code}）…\n",
                    "timestamp": _now(),
                }
            )
            async for event in _stream_from_sync(
                _run_graph_streaming(stock_code, stock_name, req, analysis_id, start_time)
            ):
                yield event
            yield _sse(
                {
                    "type": "done",
                    "analysis_id": analysis_id,
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "timestamp": _now(),
                }
            )
            return

        if not req.query:
            yield _sse({"type": "error", "message": "请输入股票代码或名称", "timestamp": _now()})
            yield _sse({"type": "done", "timestamp": _now()})
            return

        # ── ReAct loop: LLM decides which tools to call ──
        yield _sse(
            {
                "type": "thinking_token",
                "token": "🤔 让我先分析一下你的需求…\n\n",
                "timestamp": _now(),
            }
        )

        messages: list[dict] = [
            {"role": "system", "content": REACT_SYSTEM_PROMPT},
            {"role": "user", "content": req.query},
        ]

        max_iterations = 6
        analysis_executed = False

        for iteration in range(max_iterations):
            try:
                resp = await asyncio.to_thread(
                    call_llm_with_tools,
                    "",
                    tools=REACT_TOOLS,
                    api_key=req.api_key,
                    messages=messages,
                    tool_choice="required",
                    model=os.environ.get("LLM_MODEL", "deepseek/deepseek-v4-pro"),
                )
            except Exception as e:
                yield _sse(
                    {
                        "type": "error",
                        "message": f"LLM 调用失败：{e}",
                        "timestamp": _now(),
                    }
                )
                break

            msg = resp.choices[0].message

            if msg.tool_calls:
                # Build assistant message with tool_calls for conversation history
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                # Stream LLM thinking content if present
                if msg.content:
                    yield _sse(
                        {
                            "type": "thinking_token",
                            "token": msg.content + "\n",
                            "timestamp": _now(),
                        }
                    )

                for tool_call in msg.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    yield _sse(
                        {
                            "type": "tool_call",
                            "name": tool_name,
                            "args": args,
                            "iteration": iteration,
                            "timestamp": _now(),
                        }
                    )

                    if tool_name == "search_stock":
                        search_query = args.get("query", req.query)
                        result = await asyncio.to_thread(
                            search_stock_tool, search_query, api_key=req.api_key
                        )

                        yield _sse(
                            {
                                "type": "tool_result",
                                "name": "search_stock",
                                "result": result,
                                "timestamp": _now(),
                            }
                        )

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )

                    elif tool_name == "run_deep_analysis":
                        stock_code = args.get("stock_code", "").strip()
                        stock_name = args.get("stock_name", stock_code)

                        if not stock_code:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(
                                        {"error": "缺少 stock_code 参数"}, ensure_ascii=False
                                    ),
                                }
                            )
                            continue

                        yield _sse(
                            {
                                "type": "resolved",
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                "timestamp": _now(),
                            }
                        )

                        analysis_executed = True
                        async for event in _stream_from_sync(
                            _run_graph_streaming(
                                stock_code, stock_name, req, analysis_id, start_time
                            )
                        ):
                            yield event

                        yield _sse(
                            {
                                "type": "done",
                                "analysis_id": analysis_id,
                                "duration_ms": int((time.time() - start_time) * 1000),
                                "timestamp": _now(),
                            }
                        )
                        return

                    else:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(
                                    {"error": f"未知工具：{tool_name}"}, ensure_ascii=False
                                ),
                            }
                        )

            else:
                # LLM didn't call any tool — stream its answer, then force retry
                content = msg.content or ""
                if content:
                    yield _sse(
                        {
                            "type": "thinking_token",
                            "token": content + "\n",
                            "timestamp": _now(),
                        }
                    )

                # Don't give up — remind LLM to use tools and continue loop
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "请使用 search_stock 工具搜索用户提到的股票，不要直接回复文本。如果你已经知道股票代码，请直接调用 run_deep_analysis。",
                    }
                )
                continue

        # ReAct loop exhausted without executing analysis
        if not analysis_executed:
            yield _sse(
                {
                    "type": "error",
                    "message": "分析流程未完成，请尝试提供更明确的股票名称或代码",
                    "timestamp": _now(),
                }
            )

        yield _sse(
            {
                "type": "done",
                "analysis_id": analysis_id,
                "duration_ms": int((time.time() - start_time) * 1000),
                "timestamp": _now(),
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Streaming Chat ──


@app.post("/api/chat")
async def quick_chat(req: ChatRequest):
    """Quick mode / Follow-up mode - ReAct Agent with web_search tool."""

    async def chat_stream() -> AsyncGenerator[str, None]:
        try:
            from finance_agent.agent_factory import build_agent, stream_agent_to_sse

            # 模式推断：有 session_id 则为追问，否则为快速问答
            mode = "follow-up" if req.session_id else "quick"

            # API key: 优先用请求中的，无效则回退到环境变量
            api_key = req.api_key if req.api_key and req.api_key.startswith("sk-") else None

            agent = build_agent(
                mode=mode,
                api_key=api_key,
                session_id=req.session_id,
            )

            # 追问模式：记录用户消息到 session
            if req.session_id:
                append_chat(req.session_id, "user", req.message)

            # 流式输出 Agent 事件
            full_response = ""
            async for sse_str in stream_agent_to_sse(agent, req.message):
                # 收集回复内容用于 session 记录
                if "chat_token" in sse_str:
                    try:
                        data_line = sse_str.strip().split("data: ", 1)[1]
                        data = json.loads(data_line)
                        full_response += data.get("token", "")
                    except (IndexError, json.JSONDecodeError):
                        pass
                yield sse_str

            # 持久化对话到 session
            if full_response:
                if req.session_id:
                    # 追问模式：追加助手回复到已有 session
                    append_chat(req.session_id, "assistant", full_response)
                else:
                    # 快速模式：创建新 session 并记录完整对话
                    display_name = req.message.strip()[:30] or "快速问答"
                    new_session_id = create_chat_session(display_name)
                    append_chat(new_session_id, "user", req.message)
                    append_chat(new_session_id, "assistant", full_response)
                    yield _sse(
                        {
                            "type": "session_created",
                            "session_id": new_session_id,
                            "display_name": display_name,
                            "timestamp": _now(),
                        }
                    )

        except Exception as e:
            yield _sse({"type": "error", "message": str(e), "timestamp": _now()})

    return StreamingResponse(
        chat_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """Download generated report files."""
    safe_name = Path(filename).name
    file_path = REPORTS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
