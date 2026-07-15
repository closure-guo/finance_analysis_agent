"""FastAPI backend — SSE streaming for 5-layer analysis + sessions + NLP + streaming chat."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
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

from finance_agent.graph import build_5layer_graph  # noqa: E402
from finance_agent.llm import call_llm_stream  # noqa: E402
from finance_agent.react_agent import (  # noqa: E402
    search_stock_tool,
)
from finance_agent.session_store import (  # noqa: E402
    append_chat,
    create_chat_session,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_sessions,
    rename_session,
    update_session_report,
    update_session_status,
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


# ── Deep research clarification plan (Kimi-style intent confirmation) ──
# 固定的 5 层管线研究计划，用于深度研究前的意图澄清环节展示给用户确认。

DEFAULT_CLARIFY_PLAN: list[dict] = [
    {"title": "数据准备", "desc": "获取行情、财报、技术指标，勾稽校验与指标计算"},
    {"title": "Layer I 多维分析", "desc": "基本面、技术面、宏观、舆情 4 个分析师并行"},
    {"title": "Layer II 多空辩论", "desc": "看多 / 看空两轮辩论，研究经理汇总结论"},
    {"title": "Layer III 交易决策", "desc": "交易员制定买卖方向与仓位建议"},
    {"title": "Layer IV 风控压力测试", "desc": "激进 / 保守 / 中性三方辩论 + 风控裁决"},
    {"title": "Layer V 基金经理审批", "desc": "审批最终决策，生成结构化研报"},
]


# ── Request models ──


class AnalyzeRequest(BaseModel):
    stock_code: str = ""
    stock_name: str | None = None
    query: str = ""  # Natural language input
    analysis_type: str = "comprehensive"
    peer_codes: str | None = None
    enable_web_search: bool = False
    api_key: str | None = None
    session_id: str | None = None  # 追问时传入会话 ID
    focus: str = ""  # 深度研究意图澄清环节用户填写的关注点（Kimi 风格反问回答）


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    context: dict | None = None
    api_key: str | None = None


class ClarifyRequest(BaseModel):
    query: str
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


def _truncate(text: str, n: int = 80) -> str:
    """截断文本到 n 个字符，超长追加省略号，并折叠换行。"""
    text = (text or "").strip().replace("\n", " ")
    return text[:n] + "…" if len(text) > n else text


_ACTION_ZH = {"buy": "买入", "sell": "卖出", "hold": "持有", "watch": "观望"}


def _decision_summary(decision: Any, label: str) -> str:
    """从 TradeDecision 对象/dict 生成一行决策摘要。"""
    if not decision:
        return f"{label}已生成"
    action = getattr(decision, "action", None)
    confidence = getattr(decision, "confidence", None)
    if action is None and isinstance(decision, dict):
        action = decision.get("action", "")
        confidence = decision.get("confidence")
    action_zh = _ACTION_ZH.get(action, action or "")
    if confidence is not None:
        try:
            return f"{label}：{action_zh}（置信度 {float(confidence):.0%}）"
        except (TypeError, ValueError):
            pass
    return f"{label}：{action_zh}"


def _node_summary(node_name: str, accumulated: dict, update: dict) -> str:
    """为已完成的管线节点生成一行式摘要，供按阶段展示的日志使用。"""
    if node_name == "check_cache":
        if accumulated.get("cache_result") == "HIT":
            return "缓存命中，复用已持久化数据"
        return "缓存未命中，准备获取最新数据"

    if node_name == "fetch_data":
        name = accumulated.get("stock_name") or accumulated.get("stock_code") or ""
        parts = []
        if accumulated.get("balance_sheet") is not None:
            parts.append("三大报表")
        if accumulated.get("kline") is not None:
            parts.append("K线行情")
        if accumulated.get("macro_indicators"):
            parts.append("宏观指标")
        if accumulated.get("news_list"):
            parts.append("新闻舆情")
        if accumulated.get("peer_financials"):
            parts.append("同业数据")
        src = "、".join(parts) if parts else "财务数据"
        return f"已获取 {name} 的{src}" if name else f"已获取{src}"

    if node_name == "validate_financials":
        result = accumulated.get("validation_result", "")
        warnings = accumulated.get("validation_warnings") or []
        if result == "FAIL":
            return "勾稽校验失败（硬等式不通过）"
        if warnings:
            return f"勾稽校验通过，{len(warnings)} 项软警告"
        return "勾稽校验全部通过"

    if node_name == "compute_metrics":
        count = 0
        for key in (
            "solvency_metrics",
            "profitability_metrics",
            "efficiency_metrics",
            "cashflow_metrics",
        ):
            d = accumulated.get(key)
            if isinstance(d, dict):
                count += len(d)
        parts = [f"计算 {count} 项核心指标"]
        hs = accumulated.get("health_score")
        if isinstance(hs, dict) and hs:
            score = hs.get("score", hs.get("health_score"))
            if score is not None:
                parts.append(f"健康度 {score}")
        anomalies = accumulated.get("anomalies") or []
        if anomalies:
            parts.append(f"{len(anomalies)} 项异常")
        return "，".join(parts)

    if node_name == "verify_citations":
        if accumulated.get("citation_pass"):
            return "引用校验通过"
        return "引用校验完成（存在不通过项）"

    if node_name in ("bull_r1", "bull_r2", "bear_r1", "bear_r2"):
        history = accumulated.get("debate_history") or []
        for m in reversed(history):
            role = getattr(m, "role", None) or (m.get("role", "") if isinstance(m, dict) else "")
            if role in ("bull", "bear"):
                content = getattr(m, "content", None) or (
                    m.get("content", "") if isinstance(m, dict) else ""
                )
                return _truncate(content) or "辩论论点已生成"
        return "辩论论点已生成"

    if node_name == "research_manager":
        conclusion = accumulated.get("research_manager_conclusion") or ""
        return _truncate(conclusion) or "研究结论已汇总"

    if node_name == "trader":
        return _decision_summary(
            accumulated.get("trader_plan") or accumulated.get("trade_decision"), "交易建议"
        )

    if node_name in (
        "aggressive_r1",
        "aggressive_r2",
        "conservative_r1",
        "conservative_r2",
        "neutral_r1",
        "neutral_r2",
    ):
        history = accumulated.get("risk_debate_history") or []
        if history:
            last = history[-1]
            content = getattr(last, "content", None) or (
                last.get("content", "") if isinstance(last, dict) else ""
            )
            return _truncate(content) or "风控论点已生成"
        return "风控论点已生成"

    if node_name == "risk_judge":
        return _decision_summary(accumulated.get("final_trade_decision"), "风控裁决")

    if node_name == "fund_manager":
        decision = accumulated.get("fund_manager_decision", "")
        returns = accumulated.get("return_count", 0)
        if decision == "approve":
            return "基金经理审批通过"
        if decision == "return":
            return f"退回交易员修改（第 {returns} 次）"
        if decision == "reject":
            return "基金经理拒绝方案"
        return "基金经理决策完成"

    if node_name == "generate_report":
        report = accumulated.get("final_report") or ""
        return f"报告已生成（{len(report)} 字符）"

    if node_name == "generate_file":
        paths = accumulated.get("file_paths") or {}
        formats = [k for k, v in paths.items() if v]
        if formats:
            return f"已导出 {'/'.join(formats).upper()} 文件"
        return "文件导出完成"

    return ""


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

    if isinstance(output, dict) and not output.get("summary"):
        summary = _node_summary(node_name, accumulated, update)
        if summary:
            output["summary"] = summary

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
        "focus": (req.focus or "").strip(),
    }

    stock_name_display = stock_name or stock_code

    session_id = create_session(
        stock_code=stock_code,
        stock_name=stock_name_display,
        status="running",
    )

    yield _sse(
        {
            "type": "analysis_start",
            "analysis_id": analysis_id,
            "session_id": session_id,
            "stock_code": stock_code,
            "stock_name": stock_name_display,
            "timestamp": _now(),
        }
    )

    yield _sse(
        {
            "type": "session_created",
            "session_id": session_id,
            "display_name": f"{stock_name_display} {_now()[-5:]}",
            "timestamp": _now(),
        }
    )

    completed: set[str] = set()
    accumulated: dict = dict(initial_state)
    report_sent = False

    try:
        # ADR-0015：注入 Langfuse CallbackHandler 使 5 层管线节点自动挂成 span 树
        from finance_agent.langfuse_tracing import get_callback_handler, get_langfuse

        _handler = get_callback_handler()
        _lf = get_langfuse()
        _config: dict = {"recursion_limit": 100}
        if _handler is not None:
            _config["callbacks"] = [_handler]
            # ADR-0015：通过 metadata 传 langfuse_session_id，CallbackHandler 在根 chain
            # 自动调用 propagate_attributes 聚合到 Langfuse session
            _config["metadata"] = {"langfuse_session_id": session_id}

        for mode, chunk in graph.stream(
            initial_state,
            config=_config,
            stream_mode=["updates", "custom"],
        ):
            # Custom mode: forward thinking tokens from nodes
            if mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type") == "thinking":
                    yield _sse(
                        {
                            "type": "thinking_token",
                            "token": chunk.get("token", ""),
                            "node": chunk.get("node", ""),
                            "timestamp": _now(),
                        }
                    )
                continue

            # Updates mode: existing node progress logic
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

            if accumulated.get("final_report") and not report_sent:
                report_sent = True
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
                update_session_report(
                    session_id,
                    report_markdown=report_md,
                    chart_data=accumulated.get("chart_data") or {},
                    analyst_reports=_safe_dump(accumulated.get("analyst_reports") or {}),
                    agent_process=agent_process,
                    analyst_summaries=analyst_summaries,
                    duration_ms=duration_ms,
                    status="completed",
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

        if _lf is not None:
            with contextlib.suppress(Exception):
                _lf.flush()

    except Exception as e:
        update_session_status(session_id, "failed")
        yield _sse(
            {
                "type": "error",
                "node_id": "unknown",
                "session_id": session_id,
                "message": str(e),
                "traceback": str(e.__traceback__),
                "timestamp": _now(),
            }
        )


# ── Deep research intent clarification (Kimi-style) ──


def _generate_clarify_understanding(
    query: str,
    stock_name: str,
    stock_code: str,
    api_key: str | None,
) -> dict:
    """用 LLM 生成意图理解 + 1-2 个澄清问题（Kimi 风格"反问"）。

    返回 {"understanding": str, "questions": [{"id", "text"}, ...]}。
    LLM 失败时回退到默认文案、questions 为空。
    """
    from finance_agent.llm import call_llm
    from finance_agent.nodes._llm_utils import parse_json_response

    system = (
        "你是A股投研助手的意图理解模块（Kimi 风格澄清环节）。根据用户输入和已识别的股票，"
        "输出 JSON：\n"
        '{"understanding": "基于用户原始输入，用2-3句话概括其深度分析意图，包括：用户关注的核心问题、'
        "期望的分析角度（如基本面/技术面/估值/行业对比/舆情等）、隐含的投资视角。不要简单重复股票名和代码，"
        '要体现出对用户真实需求的理解。不使用emoji，不超过120字",'
        ' "questions": [{"id": "q1", "text": "一个针对性的澄清问题，帮用户明确研究方向"}]}\n'
        "questions 生成 1-2 个，聚焦于：分析侧重点（基本面/技术面/估值/成长性/舆情）、"
        "时间维度（短期/中长期）、风险偏好、是否需要同业对比等。"
        "如果用户输入已足够明确，questions 为空数组 []。只输出 JSON，不要多余解释。"
    )
    prompt = f"用户输入：{query}\n已识别股票：{stock_name}({stock_code})"
    fallback = {
        "understanding": f"您希望对 {stock_name}({stock_code}) 进行深度投研分析",
        "questions": [],
    }
    try:
        resp = call_llm(prompt, system=system, api_key=api_key, max_tokens=480, quick=True)
        data = parse_json_response(resp)
        understanding = (data.get("understanding") or "").strip() if isinstance(data, dict) else ""
        raw_qs = data.get("questions") if isinstance(data, dict) else None
        questions = []
        if isinstance(raw_qs, list):
            for i, q in enumerate(raw_qs[:2]):
                if isinstance(q, dict) and q.get("text"):
                    questions.append(
                        {"id": q.get("id") or f"q{i + 1}", "text": str(q["text"]).strip()}
                    )
                elif isinstance(q, str) and q.strip():
                    questions.append({"id": f"q{i + 1}", "text": q.strip()})
        return {
            "understanding": understanding or fallback["understanding"],
            "questions": questions,
        }
    except Exception:  # noqa: BLE001 - best-effort LLM understanding
        return fallback


def _generate_clarify_understanding_stream(
    query: str,
    stock_name: str,
    stock_code: str,
    api_key: str | None,
):
    """流式生成意图理解，yield (kind, text) 元组。

    kind:
      - "thinking": LLM reasoning_content（思考过程）
      - "answer": LLM answer content（JSON 片段）
    最终返回解析后的 {"understanding": ..., "questions": [...]} 通过 ("done", dict) 传递。
    """
    from finance_agent.nodes._llm_utils import parse_json_response

    system = (
        "你是A股投研助手的意图理解模块（Kimi 风格澄清环节）。根据用户输入和已识别的股票，"
        "输出 JSON：\n"
        '{"understanding": "基于用户原始输入，用2-3句话概括其深度分析意图，包括：用户关注的核心问题、'
        "期望的分析角度（如基本面/技术面/估值/行业对比/舆情等）、隐含的投资视角。不要简单重复股票名和代码，"
        '要体现出对用户真实需求的理解。不使用emoji，不超过120字",'
        ' "questions": [{"id": "q1", "text": "一个针对性的澄清问题，帮用户明确研究方向"}]}\n'
        "questions 生成 1-2 个，聚焦于：分析侧重点（基本面/技术面/估值/成长性/舆情）、"
        "时间维度（短期/中长期）、风险偏好、是否需要同业对比等。"
        "如果用户输入已足够明确，questions 为空数组 []。只输出 JSON，不要多余解释。"
    )
    prompt = f"用户输入：{query}\n已识别股票：{stock_name}({stock_code})"
    fallback = {
        "understanding": f"您希望对 {stock_name}({stock_code}) 进行深度投研分析",
        "questions": [],
    }

    answer_parts: list[str] = []
    try:
        for kind, text in call_llm_stream(
            prompt, system=system, api_key=api_key, max_tokens=480, quick=True
        ):
            if kind == "thinking":
                yield ("thinking", text)
            elif kind == "answer":
                answer_parts.append(text)
                yield ("answer", text)

        full_answer = "".join(answer_parts)
        data = parse_json_response(full_answer)
        understanding = (data.get("understanding") or "").strip() if isinstance(data, dict) else ""
        raw_qs = data.get("questions") if isinstance(data, dict) else None
        questions = []
        if isinstance(raw_qs, list):
            for i, q in enumerate(raw_qs[:2]):
                if isinstance(q, dict) and q.get("text"):
                    questions.append(
                        {"id": q.get("id") or f"q{i + 1}", "text": str(q["text"]).strip()}
                    )
                elif isinstance(q, str) and q.strip():
                    questions.append({"id": f"q{i + 1}", "text": q.strip()})
        yield (
            "done",
            {
                "understanding": understanding or fallback["understanding"],
                "questions": questions,
            },
        )
    except Exception:  # noqa: BLE001
        yield ("done", fallback)


@app.post("/api/clarify")
async def clarify(req: ClarifyRequest):
    """深度研究前的意图澄清环节（SSE 流式）。

    推送事件类型：
      - clarify_tool: 工具调用信息（搜索股票）
      - clarify_thinking: LLM 思考过程（reasoning_content）
      - clarify_answer: LLM 答案片段（意图理解 JSON 片段）
      - clarify_done: 完整的澄清数据（股票代码、候选、问题等）
    """
    query = (req.query or "").strip()
    api_key = req.api_key if req.api_key and req.api_key.startswith("sk-") else None

    def _error_data(msg: str) -> dict:
        return {
            "status": "error",
            "query": query,
            "stock_code": "",
            "stock_name": "",
            "understanding": "",
            "questions": [],
            "plan": [],
            "needs_selection": False,
            "candidates": [],
            "message": msg,
        }

    def _clarify_stream():
        if not query:
            yield _sse(
                {
                    "type": "clarify_done",
                    "data": _error_data("请输入股票名称或代码"),
                    "timestamp": _now(),
                }
            )
            return

        yield _sse(
            {
                "type": "clarify_tool",
                "tool": "search_stock",
                "args": {"query": query},
                "status": "running",
                "timestamp": _now(),
            }
        )

        try:
            result = search_stock_tool(query, api_key)
        except Exception as e:  # noqa: BLE001
            yield _sse(
                {
                    "type": "clarify_tool",
                    "tool": "search_stock",
                    "status": "error",
                    "error": str(e),
                    "timestamp": _now(),
                }
            )
            yield _sse(
                {
                    "type": "clarify_done",
                    "data": _error_data(f"股票识别失败：{e}"),
                    "timestamp": _now(),
                }
            )
            return

        found = bool(result.get("found"))
        raw_candidates = result.get("candidates", []) if found else []
        needs_confirmation = bool(result.get("needs_confirmation"))
        source = result.get("source", "")

        def _norm(c: dict) -> dict:
            return {
                "stock_code": c.get("stock_code") or c.get("code", ""),
                "stock_name": c.get("stock_name") or c.get("name", ""),
            }

        candidates = [_norm(c) for c in raw_candidates if _norm(c)["stock_code"]]

        stock_code = ""
        stock_name = ""
        needs_selection = False

        if (
            candidates
            and not needs_confirmation
            or candidates
            and needs_confirmation
            and len(candidates) == 1
        ):
            stock_code = candidates[0]["stock_code"]
            stock_name = candidates[0]["stock_name"]
        elif candidates and needs_confirmation:
            needs_selection = True

        cand_desc = "、".join(f"{c['stock_name']}({c['stock_code']})" for c in candidates[:3])
        if len(candidates) > 3:
            cand_desc += f" 等{len(candidates)}只"
        yield _sse(
            {
                "type": "clarify_tool",
                "tool": "search_stock",
                "status": "done",
                "result_summary": cand_desc or "未找到匹配股票",
                "source": source,
                "found": found,
                "timestamp": _now(),
            }
        )

        questions: list[dict] = []
        if stock_code:
            understanding = ""
            for kind, text in _generate_clarify_understanding_stream(
                query, stock_name, stock_code, api_key
            ):
                if kind == "thinking":
                    yield _sse({"type": "clarify_thinking", "token": text, "timestamp": _now()})
                elif kind == "answer":
                    yield _sse({"type": "clarify_answer", "token": text, "timestamp": _now()})
                elif kind == "done":
                    understanding = text["understanding"]
                    questions = text["questions"]
        elif needs_selection:
            understanding = "找到多个匹配的股票，请选择要深度分析的目标。"
        else:
            understanding = "未能识别到具体的股票，请提供更准确的股票名称或6位代码。"

        show_plan = bool(stock_code or needs_selection)

        yield _sse(
            {
                "type": "clarify_done",
                "data": {
                    "status": "ok",
                    "query": query,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "understanding": understanding,
                    "questions": questions,
                    "plan": DEFAULT_CLARIFY_PLAN if show_plan else [],
                    "needs_selection": needs_selection,
                    "candidates": candidates,
                    "message": "" if show_plan else "未找到匹配的股票，请尝试更准确的名称或6位代码",
                },
                "timestamp": _now(),
            }
        )

    return StreamingResponse(_stream_from_sync(_clarify_stream()), media_type="text/event-stream")


# ── Analyze (harness-based ReAct) ──


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """深度分析 -- 通过 harness ReAct Agent 编排工具调用。

    走 ADR-0014 的 mini_harness 统一编排层：
    - build_agent(mode="deep") 构建 Agent（含 ContextManager、ToolManager）
    - stream_agent_to_sse 将 StreamEvent 映射为前端 SSE
    - 上下文管理（token 预算、渐进压缩）由 ContextManager 自动处理
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        analysis_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        stock_code = req.stock_code.strip()
        stock_name = req.stock_name or ""

        # ── Fast path: stock_code 已知，直接走管线 ──
        if stock_code:
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

        # ── 走 harness ReAct Agent ──
        from finance_agent.agent_factory import build_agent, stream_agent_to_sse

        # API key: 优先用请求中的，无效则回退到环境变量
        api_key = req.api_key if req.api_key and req.api_key.startswith("sk-") else None

        # 构建 deep 模式 Agent（含 session_id 上下文注入）
        agent = build_agent(
            mode="deep",
            api_key=api_key,
            analysis_type=req.analysis_type,
            peer_codes=req.peer_codes.split(",") if req.peer_codes else None,
            enable_web_search=req.enable_web_search,
            session_id=req.session_id,
        )

        # session 管理状态
        session_id = req.session_id
        session_created_sent = False
        collected_metadata: dict = {}

        def on_metadata(metadata: dict):
            """收集 TOOL_METADATA（chart_data、analyst_reports 等）用于 session 持久化。"""
            collected_metadata.update(metadata)

        def on_resolved(sc: str, sn: str):
            """股票代码解析完成回调 -- 创建 analysis session 并保存报告。"""
            nonlocal session_id, session_created_sent
            if not session_id:
                # 创建 analysis session（保存报告、图表数据等）
                session_id = create_session(
                    stock_code=sc,
                    stock_name=sn,
                    report_markdown=collected_metadata.get("report_markdown", ""),
                    chart_data=collected_metadata.get("chart_data") or {},
                    analyst_reports=collected_metadata.get("analyst_reports") or {},
                )
                session_created_sent = True
            # 保存用户查询到 chat_history
            append_chat(session_id, "user", req.query)

        # 对时效性查询，预调 web_search 并将结果注入用户消息
        _time_sensitive_keywords = ["推荐", "热点", "今天", "今日", "最近", "最新", "利好", "买入"]
        _has_stock_code = bool(re.search(r"\d{6}", req.query))
        user_query = req.query

        if not _has_stock_code and any(kw in req.query for kw in _time_sensitive_keywords):
            # 预调 web_search
            from finance_agent.agent_factory import _web_search

            search_query = f"{req.query} A股 热点 推荐 最新"

            # 先发送 thinking_token，确保前端 ThinkingBanner 渲染
            yield _sse(
                {
                    "type": "thinking_token",
                    "token": "用户询问包含时效性关键词，我先搜索最新市场信息。\n",
                    "timestamp": _now(),
                }
            )

            # 发送 tool_call SSE 事件
            yield _sse(
                {
                    "type": "tool_call",
                    "name": "web_search",
                    "args": {"query": search_query},
                    "timestamp": _now(),
                }
            )

            # 执行搜索
            search_result = ""
            try:
                search_result = await _web_search(search_query)
            except Exception as e:
                search_result = f"搜索失败: {e}"

            # 截取前 2000 字符
            search_summary = search_result[:2000] if len(search_result) > 2000 else search_result

            # 发送 tool_result SSE 事件
            yield _sse(
                {
                    "type": "tool_result",
                    "name": "web_search",
                    "result": search_summary,
                    "timestamp": _now(),
                }
            )

            # 注入搜索结果到用户消息
            user_query = (
                f"{req.query}\n\n"
                f"[以下是 web_search 的搜索结果，请基于这些信息提取具体股票名称，"
                f"然后调用 search_stock 获取股票代码，再调用 run_deep_analysis：]\n"
                f"{search_summary}"
            )

        # 流式输出 Agent 事件
        async for sse_str in stream_agent_to_sse(
            agent,
            user_query,
            on_metadata=on_metadata,
            on_resolved=on_resolved,
            extra_events={
                "analysis_id": analysis_id,
                "session_id": session_id or "",
                "duration_ms": 0,  # 占位，实际在 stream 结束后计算
            },
            session_id=session_id,
        ):
            # 拦截 resolved 事件，在前面插入 session_created
            if session_created_sent and '"type": "resolved"' in sse_str:
                yield _sse(
                    {
                        "type": "session_created",
                        "session_id": session_id,
                        "display_name": req.query.strip()[:30] or "深度分析",
                        "timestamp": _now(),
                    }
                )
                session_created_sent = False
            # 在 report_ready 事件中注入 session_id 和 duration_ms
            if '"type": "report_ready"' in sse_str and session_id:
                import json as _json

                with contextlib.suppress(Exception):
                    data = _json.loads(sse_str.replace("data: ", "").strip())
                    data["session_id"] = session_id
                    data["duration_ms"] = int((time.time() - start_time) * 1000)
                    yield _sse(data)
                    continue
            yield sse_str

        # 如果分析未执行（LLM 生成了文字回复），检查是否有 search_stock 结果可以 fallback
        if not collected_metadata.get("stock_code"):
            # Fallback: Agent 找到了股票但没有调用 run_deep_analysis，直接启动管线
            fb_stock_code = collected_metadata.get("search_stock_code", "")
            fb_stock_name = collected_metadata.get("search_stock_name", "")
            if fb_stock_code:
                yield _sse(
                    {
                        "type": "thinking_token",
                        "token": "\n▶ 自动启动深度分析管线…\n",
                        "timestamp": _now(),
                    }
                )
                async for event in _stream_from_sync(
                    _run_graph_streaming(fb_stock_code, fb_stock_name, req, analysis_id, start_time)
                ):
                    yield event
            else:
                # 没有找到股票，保存对话到 session
                if session_id:
                    append_chat(session_id, "user", req.query)
                else:
                    display_name = req.query.strip()[:30] or "深度分析"
                    session_id = create_chat_session(display_name)
                    append_chat(session_id, "user", req.query)
                    yield _sse(
                        {
                            "type": "session_created",
                            "session_id": session_id,
                            "display_name": display_name,
                            "timestamp": _now(),
                        }
                    )

        # done 事件最后发送
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

            # 模式推断：有 session_id 时检查 session 类型
            # - analysis 类型 -> follow-up（报告追问）
            # - chat 类型 -> quick（快速聊天追问，附带历史上下文）
            if req.session_id:
                from finance_agent.session_store import get_session as _get_session

                _session = _get_session(req.session_id)
                if _session and _session.get("session_type") == "analysis":
                    mode = "follow-up"
                else:
                    mode = "quick"
            else:
                mode = "quick"

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
            async for sse_str in stream_agent_to_sse(agent, req.message, session_id=req.session_id):
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

        # done 事件最后发送
        yield _sse({"type": "done", "timestamp": _now()})

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
    """返回北京时间字符串，与 agent_factory._now() 保持一致"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
