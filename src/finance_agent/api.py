"""FastAPI backend — SSE streaming for 5-layer analysis + sessions + NLP + streaming chat."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from finance_agent.graph import build_5layer_graph
from finance_agent.llm import call_llm_stream, call_llm_with_tools
from finance_agent.nlp import resolve_stock
from finance_agent.session_store import (
    append_chat,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_sessions,
    rename_session,
)
from finance_agent.web_search import (
    WEB_SEARCH_TOOL,
    format_search_for_llm,
    has_tavily_key,
    tavily_search,
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


# ── Analyze ──


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Start 5-layer analysis and stream SSE events."""

    async def event_stream() -> AsyncGenerator[str, None]:
        analysis_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # ── Natural language resolution ──
        stock_code = req.stock_code.strip()
        stock_name = req.stock_name or ""

        if not stock_code and req.query:
            yield _sse({"type": "parsing", "query": req.query, "timestamp": _now()})
            resolved = resolve_stock(req.query, api_key=req.api_key)
            if not resolved:
                yield _sse(
                    {
                        "type": "error",
                        "message": f"无法识别股票：{req.query}",
                        "timestamp": _now(),
                    }
                )
                yield _sse({"type": "done", "timestamp": _now()})
                return
            stock_code = resolved["stock_code"]
            stock_name = resolved["stock_name"]
            yield _sse(
                {
                    "type": "resolved",
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "timestamp": _now(),
                }
            )

        if not stock_code:
            yield _sse({"type": "error", "message": "请输入股票代码或名称", "timestamp": _now()})
            yield _sse({"type": "done", "timestamp": _now()})
            return

        initial_state = {
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "analysis_type": req.analysis_type or "comprehensive",
            "peer_codes": [c.strip() for c in (req.peer_codes or "").split(",") if c.strip()]
            or None,
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

                    _merge_update(
                        accumulated, node_name, update if isinstance(update, dict) else {}
                    )

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

                # Stream report chunks when ready
                if accumulated.get("final_report"):
                    file_paths = accumulated.get("file_paths") or {}
                    stock_name_final = accumulated.get("stock_name", stock_code)
                    duration_ms = int((time.time() - start_time) * 1000)

                    # Send report chunks progressively
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

                    # Save session to SQLite
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
    """Quick mode — single LLM call with optional web search tool call."""

    async def chat_stream() -> AsyncGenerator[str, None]:
        system = (
            "你是一个智能助手，擅长A股投研分析。用户可能输入股票名称、代码、投资问题，也可能问其他领域的问题。"
            "对于投资相关问题，请给出专业分析，包含关键财务指标、行业地位和投资逻辑。"
            "对于非投资问题，正常回答即可。"
            "不展示推理过程，直接给结论。回答控制在300字以内。"
        )

        # Try NLP resolution for stock context (quick mode)
        if not req.session_id:
            try:
                resolved = resolve_stock(req.message, req.api_key)
                if resolved.get("stock_code"):
                    stock_name = resolved.get("stock_name", "")
                    stock_code = resolved["stock_code"]
                    system += f"\n\n用户询问的股票：{stock_name}({stock_code})。请基于你的知识提供该股票的快速分析。"
            except Exception:  # noqa: S110 - best-effort NLP stock resolution; ignore failures
                pass

        # Load session context if provided (follow-up mode)
        if req.session_id:
            session = get_session(req.session_id)
            if session:
                report_md = session.get("report_markdown", "")
                summaries = session.get("analyst_summaries", {})
                if report_md:
                    system += f"\n\n分析报告：\n{report_md[:3000]}"
                if summaries:
                    summaries_str = json.dumps(summaries, ensure_ascii=False)
                    system += f"\n\n分析师摘要：\n{summaries_str}"
                append_chat(req.session_id, "user", req.message)

        if req.context:
            context_str = json.dumps(req.context, ensure_ascii=False, default=str)[:2000]
            system += f"\n\n分析上下文：\n{context_str}"

        try:
            # ── Step 1: Try tool calling if Tavily is configured ──
            use_search = has_tavily_key() and not req.session_id

            # Heuristic: force tool call for real-time questions
            _realtime_keywords = [
                "天气",
                "气温",
                "新闻",
                "最新",
                "今天",
                "现在",
                "目前",
                "当前",
                "股价",
                "行情",
                "涨跌",
                "比分",
                "比赛",
                "比分",
                "利率",
                "汇率",
                "油价",
                "金价",
                "票房",
                "热搜",
                "热点",
            ]
            needs_search = any(kw in req.message for kw in _realtime_keywords)

            if use_search:
                resp = call_llm_with_tools(
                    req.message,
                    system=system
                    + "\n\n对于需要实时信息的问题（天气、新闻、股价等），必须调用 web_search 工具搜索，不要询问澄清问题，直接搜索并回答。在回答中用 [1][2] 标注引用来源。",
                    tools=[WEB_SEARCH_TOOL],
                    api_key=req.api_key,
                    tool_choice="required" if needs_search else "auto",
                )

                msg = resp.choices[0].message

                # Check if LLM decided to call the tool
                if msg.tool_calls:
                    tool_call = msg.tool_calls[0]
                    # Extract query from tool call arguments
                    import json as _json

                    args = _json.loads(tool_call.function.arguments)
                    search_query = args.get("query", req.message)

                    # Notify frontend: search starting
                    yield _sse({"type": "search_start", "query": search_query, "timestamp": _now()})

                    # Execute Tavily search
                    try:
                        search_resp = tavily_search(search_query)
                        # Notify frontend: search results
                        yield _sse(
                            {
                                "type": "search_result",
                                "query": search_query,
                                "results": [
                                    {"title": r.title, "url": r.url, "content": r.content[:200]}
                                    for r in search_resp.results
                                ],
                                "count": search_resp.count,
                                "timestamp": _now(),
                            }
                        )

                        # Build messages for second LLM call with tool result
                        tool_result = format_search_for_llm(search_resp)
                        messages = [
                            {
                                "role": "system",
                                "content": system
                                + "\n\n请基于搜索结果回答，用 [1][2] 标注引用来源。",
                            },
                            {"role": "user", "content": req.message},
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": tool_call.id,
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": tool_call.function.arguments,
                                        },
                                    }
                                ],
                            },
                            {"role": "tool", "tool_call_id": tool_call.id, "content": tool_result},
                        ]

                        # Stream the final answer
                        full_response = ""
                        for kind, token in call_llm_stream(
                            "", messages=messages, api_key=req.api_key
                        ):
                            if kind == "thinking":
                                yield _sse(
                                    {"type": "thinking_token", "token": token, "timestamp": _now()}
                                )
                            else:
                                full_response += token
                                yield _sse(
                                    {"type": "chat_token", "token": token, "timestamp": _now()}
                                )

                        if req.session_id:
                            append_chat(req.session_id, "assistant", full_response)
                        yield _sse({"type": "chat_done", "timestamp": _now()})
                        return

                    except Exception as e:
                        # Search failed — notify and fall through to pure LLM
                        yield _sse({"type": "search_error", "message": str(e), "timestamp": _now()})

            # ── Step 2: Pure LLM answer (no tools or search failed) ──
            full_response = ""
            for kind, token in call_llm_stream(
                req.message, system=system, api_key=req.api_key, quick=not req.session_id
            ):
                if kind == "thinking":
                    yield _sse({"type": "thinking_token", "token": token, "timestamp": _now()})
                else:
                    full_response += token
                    yield _sse({"type": "chat_token", "token": token, "timestamp": _now()})

            if req.session_id:
                append_chat(req.session_id, "assistant", full_response)

            yield _sse({"type": "chat_done", "timestamp": _now()})
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
