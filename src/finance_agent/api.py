"""FastAPI backend — SSE streaming for 5-layer analysis + sessions + NLP + streaming chat."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
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
from finance_agent.pipeline_runner import PipelineRunner, build_layer_tree  # noqa: E402
from finance_agent.react_agent import (  # noqa: E402
    _TIME_SENSITIVE_KEYWORDS as _TIME_SENSITIVE_KEYWORDS_REACT,
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
    update_session_for_clarify,
    update_session_report,
    update_session_status,
)
from finance_agent.timeline_builder import apply_chat_event  # noqa: E402


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动时清扫悬挂 running 会话：后端重启后 PipelineRunner 内存态已丢失，置 failed 供前端恢复展示。"""
    PipelineRunner.mark_swept_failed()
    yield


app = FastAPI(title="Finance Analysis Agent API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 测试模式开关（F2：E2E 门禁基础设施）──
# TESTING=1 时注册测试专用端点（/api/test/seed, /api/test/reset），
# 完整 LLM stub 实现推迟到 F3（见 agent_factory._make_llm_client）
TESTING: bool = os.getenv("TESTING") == "1"

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
    {"node": "fundamental_analyst", "layer": "Layer I", "desc": "基本面分析", "icon": "chart-line"},
    {"node": "technical_analyst", "layer": "Layer I", "desc": "技术面分析", "icon": "chart-line"},
    {"node": "macro_analyst", "layer": "Layer I", "desc": "宏观分析", "icon": "globe"},
    {"node": "sentiment_analyst", "layer": "Layer I", "desc": "舆情分析", "icon": "comments"},
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
    session_id: str | None = None  # 追问时传入会话 ID
    focus: str = ""  # 深度研究意图澄清环节用户填写的关注点（Kimi 风格反问回答）
    user_id: str | None = None  # Langfuse user 聚合（ADR-0015）


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    context: dict | None = None
    api_key: str | None = None
    user_id: str | None = None  # Langfuse user 聚合（ADR-0015）


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

    if node_name in (
        "technical_analyst",
        "fundamental_analyst",
        "macro_analyst",
        "sentiment_analyst",
    ):
        # 4 个并行分析师各自写 analyst_reports 的不同 key（technical/fundamental/macro/sentiment）
        reports = accumulated.get("analyst_reports") or {}
        key = node_name.replace("_analyst", "")
        report = reports.get(key) or reports.get(node_name)
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


# ── 测试专用端点（仅 TESTING=1 下可用）──
if TESTING:

    @app.post("/api/test/seed")
    async def test_seed(req: dict):
        """测试数据造数端点。

        接收 display_name / session_type / chat_history（含可选 thinking + tool_calls），
        内部经 session_store.create_session + append_chat 写入真实存储，
        供历史会话恢复等 E2E 确定性构造会话（agent-turn-box-display delta task 5.6）。
        """
        # 旧版 smoke 断言（{symbol}）保持占位响应，避免破坏既有契约
        if "chat_history" not in req:
            return {"status": "ok", "mode": "testing"}
        session_id = create_session(
            session_type=req.get("session_type", "chat"),
            display_name=req.get("display_name"),
        )
        for entry in req.get("chat_history", []):
            append_chat(
                session_id,
                role=entry["role"],
                content=entry["content"],
                thinking=entry.get("thinking"),
                tool_calls=entry.get("tool_calls"),
            )
        return {"session_id": session_id}

    @app.post("/api/test/reset")
    async def test_reset(req: dict):
        """测试数据清理端点骨架（F2 只返回占位响应，清理逻辑在 F3 落地）。"""
        return {"status": "ok", "mode": "testing"}


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
    session_id: str | None = None,
) -> Generator[str, None, None]:
    """执行 5 层图分析，流式 yield SSE 事件。

    封装了 PREP → Layer I-V → 报告生成的完整流程，
    可作为 ReAct 循环中 run_deep_analysis 工具的执行体。

    Args:
        session_id: 可选外部传入的 session_id。若未提供，内部创建新 session。
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

    # 若 session_id 为外部传入，说明 session_created 已由调用方发送，避免重复
    session_created_externally = bool(session_id)

    if not session_id:
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

    if not session_created_externally:
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
            # ADR-0015：通过 metadata 传 langfuse_session_id / langfuse_user_id，
            # CallbackHandler 在根 chain 自动调用 propagate_attributes 聚合
            _config["metadata"] = {"langfuse_session_id": session_id}
            if req.user_id:
                _config["metadata"]["langfuse_user_id"] = req.user_id

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


# ── Analyze (harness-based ReAct) ──


def _parse_sse_data(sse_str: str) -> dict | None:
    """从 SSE 字符串中解析 data JSON，失败返回 None。"""
    try:
        body = sse_str.strip().split("data: ", 1)[1]
        return json.loads(body)
    except (IndexError, json.JSONDecodeError, ValueError):
        return None


def _summarize_tool_result(result) -> str:
    """将工具结果浓缩为前端可展示的简短文本（与前端逻辑保持一致）。"""
    if isinstance(result, str):
        return result[:150]
    if isinstance(result, list):
        items: list[str] = []
        for r in result[:3]:
            if isinstance(r, dict):
                items.append(
                    r.get("title")
                    or r.get("name")
                    or r.get("code")
                    or json.dumps(r, ensure_ascii=False)[:50]
                )
            else:
                items.append(str(r)[:50])
        return "、".join(items)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)[:150]
    return ""


class _ChatCollector:
    """收集 Agent 流式事件中的最终回复、思考过程与工具调用，用于持久化到 chat_history。"""

    def __init__(self) -> None:
        self.response: str = ""
        self.thinking: str = ""
        self.tool_calls: list[dict] = []
        # 结构化时序（思考/搜索/工具调用交错），镜像前端 applyChatStreamEvent，
        # 持久化到 chat_history 的 agentTimeline 字段
        self.agent_timeline: list[dict] = []

    def feed(self, data: dict) -> None:
        t = data.get("type")
        # 维护结构化时序（timeline 构建器为纯函数，不可变更新后重新赋值）
        self.agent_timeline = apply_chat_event(self.agent_timeline, data)
        if t == "chat_token":
            # 回答增量（content，与 reasoning 分离）
            self.response += data.get("token", "")
        elif t == "thinking_token":
            # 原生思考增量（DeepSeek reasoning_content），直接累积
            self.thinking += data.get("token", "")
        elif t == "tool_call":
            name = data.get("name", "")
            # run_deep_analysis 触发的是管线 UI（非对话流工具调用框），跳过以与前端保持一致
            if name == "run_deep_analysis":
                return
            self.tool_calls.append(
                {
                    "name": name,
                    "args": data.get("args", {}),
                    "result_text": "",
                    "done": False,
                }
            )
        elif t == "tool_result":
            name = data.get("name", "")
            result_text = _summarize_tool_result(data.get("result"))
            for tc in reversed(self.tool_calls):
                if tc["name"] == name and not tc["done"]:
                    tc["result_text"] = result_text
                    tc["done"] = True
                    break


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

        if not req.query:
            yield _sse({"type": "error", "message": "请输入股票代码或名称", "timestamp": _now()})
            yield _sse({"type": "done", "timestamp": _now()})
            return

        # API key: 优先用请求中的，无效则回退到环境变量
        api_key = req.api_key if req.api_key and req.api_key.startswith("sk-") else None

        # ── Session 生命周期：从首次输入开始 ──
        session_id = req.session_id
        if session_id:
            session = get_session(session_id)
            if not session:
                yield _sse({"type": "error", "message": "Session not found", "timestamp": _now()})
                yield _sse({"type": "done", "timestamp": _now()})
                return
        else:
            display_name = req.query.strip()[:30] or "深度分析"
            session_id = create_session(
                stock_code="",
                stock_name="",
                display_name=display_name,
                status="clarifying",
                session_type="analysis",
            )
            yield _sse(
                {
                    "type": "session_created",
                    "session_id": session_id,
                    "display_name": display_name,
                    "timestamp": _now(),
                }
            )

        # 追加用户输入到 chat_history
        append_chat(session_id, "user", req.query)

        stock_code = req.stock_code.strip()
        stock_name = req.stock_name or ""

        # ── Fast path: stock_code 已知，直接走管线 ──
        # 新会话（未传 session_id）且已解析出股票代码时走 fast path；
        # 追问/复用旧会话时走 ReAct 路径
        if stock_code and not req.session_id:
            update_session_for_clarify(
                session_id, stock_code=stock_code, stock_name=stock_name, status="running"
            )
            # 管线后台执行：SSE 仅订阅事件队列，客户端断开不中断管线，
            # 节点事件由 PipelineRunner 持续写入 pipeline_snapshot 供断线恢复
            PipelineRunner.start(
                session_id,
                lambda: _run_graph_streaming(
                    stock_code, stock_name, req, analysis_id, start_time, session_id=session_id
                ),
                {
                    "layerTree": build_layer_tree(),
                    "currentNodeId": "",
                    "progress": 0.0,
                    "updatedAt": int(time.time() * 1000),
                },
            )
            # 订阅事件队列：在线时实时转发，断开仅停止订阅；
            # 空转时定期发心跳注释，防止代理断连并保持响应活跃
            heartbeat_counter = 0
            while True:
                events = PipelineRunner.get_events(session_id)
                for event in events:
                    yield event
                if not events:
                    if not PipelineRunner.is_running(session_id):
                        break
                    # 每 10 次空转（约 2 秒）发一次心跳，保持 SSE 连接活跃
                    heartbeat_counter += 1
                    if heartbeat_counter >= 10:
                        heartbeat_counter = 0
                        yield ": heartbeat\n\n"
                await asyncio.sleep(0.2)
            # 跳出后兜底排空：覆盖 get_events 与 done 置位之间的竞态窗口
            for event in PipelineRunner.get_events(session_id):
                yield event
            # 管线失败时给在线客户端发 error（对齐 _run_graph_streaming 的 error 结构），否则发 done
            session = get_session(session_id) or {}
            if session.get("status") == "failed":
                yield _sse(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "message": "管线执行失败，请查看会话详情或重试",
                        "timestamp": _now(),
                    }
                )
            else:
                yield _sse(
                    {
                        "type": "done",
                        "analysis_id": analysis_id,
                        "session_id": session_id,
                        "duration_ms": int((time.time() - start_time) * 1000),
                        "timestamp": _now(),
                    }
                )
            return

        # ── 走 harness ReAct Agent ──
        from finance_agent.agent_factory import build_agent, stream_agent_to_sse

        # 从 session 恢复 focus，与用户输入合并
        session = get_session(session_id) or {}
        accumulated_focus = (session.get("focus") or "").strip()
        current_focus = (req.focus or "").strip()
        if current_focus:
            accumulated_focus = f"{accumulated_focus}\n{current_focus}".strip()

        # 构建 deep 模式 Agent，注入 session_id 以恢复历史对话
        agent = build_agent(
            mode="deep",
            api_key=api_key,
            analysis_type=req.analysis_type,
            peer_codes=req.peer_codes.split(",") if req.peer_codes else None,
            enable_web_search=req.enable_web_search,
            session_id=session_id,
        )

        collected_metadata: dict = {}
        analysis_executed = False
        collector = _ChatCollector()

        def on_metadata(metadata: dict):
            """收集 TOOL_METADATA（chart_data、analyst_reports 等）用于 session 持久化。"""
            collected_metadata.update(metadata)

        def on_resolved(sc: str, sn: str):
            """股票代码解析完成回调 -- 更新 session。"""
            update_session_for_clarify(
                session_id,
                stock_code=sc,
                stock_name=sn,
                display_name=f"{sn}({sc})",
            )

        # 对时效性查询，预调 web_search 并将结果注入用户消息
        _time_sensitive_keywords = _TIME_SENSITIVE_KEYWORDS_REACT
        _has_stock_code = bool(re.search(r"\d{6}", req.query))
        user_query = req.query

        if not _has_stock_code and any(kw in req.query for kw in _time_sensitive_keywords):
            # 预调 web_search
            from finance_agent.agent_factory import _web_search

            search_query = f"{req.query} A股 热点 推荐 最新"

            _pre_thinking = {
                "type": "thinking_token",
                "token": "用户询问包含时效性关键词，我先搜索最新市场信息。\n",
                "timestamp": _now(),
            }
            collector.feed(_pre_thinking)
            yield _sse(_pre_thinking)
            _pre_tool_call = {
                "type": "tool_call",
                "name": "web_search",
                "args": {"query": search_query},
                "timestamp": _now(),
            }
            collector.feed(_pre_tool_call)
            yield _sse(_pre_tool_call)
            # 补发 search_start：前端 tool_call 对 web_search 因 isSearchToolName 被跳过，
            # 搜索横幅由 search_start/search_result 驱动——预搜索此前漏发致无搜索横幅。
            yield _sse({"type": "search_start", "query": search_query, "timestamp": _now()})

            search_result = ""
            try:
                search_result = await _web_search(search_query)
            except Exception as e:
                search_result = f"搜索失败: {e}"

            search_summary = search_result[:2000] if len(search_result) > 2000 else search_result
            _pre_tool_result = {
                "type": "tool_result",
                "name": "web_search",
                "result": search_summary,
                "timestamp": _now(),
            }
            collector.feed(_pre_tool_result)
            yield _sse(_pre_tool_result)
            # 补发 search_result（结构化来源），驱动前端搜索横幅从"搜索中"转"已搜索 N 个网页"
            from finance_agent.web_search import parse_search_output

            _pre_results = parse_search_output(search_result)
            yield _sse(
                {
                    "type": "search_result",
                    "query": search_query,
                    "results": [
                        {"title": r.title, "url": r.url, "content": r.content} for r in _pre_results
                    ],
                    "count": len(_pre_results),
                    "timestamp": _now(),
                }
            )
            user_query = (
                f"{req.query}\n\n"
                f"[以下是 web_search 的搜索结果，请基于这些信息提取具体股票名称，"
                f"然后调用 search_stock 获取股票代码，再调用 run_deep_analysis：]\n"
                f"{search_summary}"
            )

        # 如果 session 已有 focus，注入用户消息上下文
        if accumulated_focus:
            user_query = f"{user_query}\n\n[已收集的用户关注点/澄清回答：\n{accumulated_focus}]"

        # 流式输出 Agent 事件
        stream_error = False
        try:
            async for sse_str in stream_agent_to_sse(
                agent,
                user_query,
                on_metadata=on_metadata,
                on_resolved=on_resolved,
                extra_events={
                    "analysis_id": analysis_id,
                    "session_id": session_id,
                    "duration_ms": 0,
                },
                session_id=session_id,
                user_id=req.user_id,
            ):
                # 记录 Assistant 文本回复 / 思考 / 工具调用，用于后续保存到 chat_history
                data = _parse_sse_data(sse_str)
                if data is not None:
                    collector.feed(data)
                    if data.get("type") == "report_ready":
                        analysis_executed = True

                # 在 report_ready 事件中注入 session_id 和 duration_ms
                if data is not None and data.get("type") == "report_ready" and session_id:
                    data["session_id"] = session_id
                    data["duration_ms"] = int((time.time() - start_time) * 1000)
                    yield _sse(data)
                    continue
                yield sse_str
        except Exception as exc:
            # 流式输出本身异常（如 Langfuse 上下文/回调抛错）时，向前端发送 error + done，
            # 避免连接被静默关闭、前端无限等待（"深度模式无响应"）。
            import logging as _api_lg

            _api_lg.getLogger("finance_agent.api").exception("深度分析流式输出异常")
            stream_error = True
            yield _sse(
                {
                    "type": "error",
                    "message": f"分析过程出错: {exc}",
                    "timestamp": _now(),
                }
            )

        # 保存 Assistant 回复到 chat_history（含思考过程与工具调用，便于历史会话回显）
        if collector.response.strip():
            append_chat(
                session_id,
                "assistant",
                collector.response.strip(),
                thinking=collector.thinking.strip() or None,
                tool_calls=collector.tool_calls or None,
                agent_timeline=collector.agent_timeline or None,
            )

        # 如果 Agent 调用了 run_deep_analysis，说明已进入分析阶段
        if collected_metadata.get("report_markdown") or collected_metadata.get("stock_code"):
            analysis_executed = True

        # 如果分析未执行（且未发生异常），说明 Agent 仍在澄清阶段，保存状态
        if not analysis_executed and not stream_error:
            # 更新 focus：如果 Assistant 的回复包含澄清问题，则 focus 保持当前累积；
            # 否则追加到 focus（用户可能直接在回答中补充了关注点）
            # 这里简化处理：将当前 req.focus 合并到 session focus
            if current_focus:
                update_session_for_clarify(session_id, focus=accumulated_focus, status="clarifying")
            else:
                update_session_for_clarify(session_id, status="clarifying")
            yield _sse(
                {
                    "type": "awaiting_input",
                    "session_id": session_id,
                    "pending_intent": "awaiting_focus",
                    "timestamp": _now(),
                }
            )
        else:
            # 分析已完成，session 状态已被 _run_graph_streaming 更新为 completed
            pass

        # done 事件最后发送
        yield _sse(
            {
                "type": "done",
                "analysis_id": analysis_id,
                "session_id": session_id,
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

            # ADR-0015：新对话时先创建 session，使 Langfuse session 聚合可用
            # （session_id 须在 agent 运行前确定，否则 propagate_attributes 拿不到）
            if not req.session_id:
                _display_name = req.message.strip()[:30] or "快速问答"
                req_session_id = create_chat_session(_display_name)
                append_chat(req_session_id, "user", req.message)
            else:
                req_session_id = req.session_id
                append_chat(req_session_id, "user", req.message)

            agent = build_agent(
                mode=mode,
                api_key=api_key,
                session_id=req_session_id,
            )

            # 流式输出 Agent 事件，同时收集回复 / 思考 / 工具调用用于持久化
            collector = _ChatCollector()
            async for sse_str in stream_agent_to_sse(
                agent, req.message, session_id=req_session_id, user_id=req.user_id
            ):
                data = _parse_sse_data(sse_str)
                if data is not None:
                    collector.feed(data)
                yield sse_str

            # 持久化对话到 session（含思考过程与工具调用，便于历史会话回显）
            if collector.response:
                append_chat(
                    req_session_id,
                    "assistant",
                    collector.response,
                    thinking=collector.thinking.strip() or None,
                    tool_calls=collector.tool_calls or None,
                    agent_timeline=collector.agent_timeline or None,
                )
                if not req.session_id:
                    # 新对话：通知前端 session_id
                    yield _sse(
                        {
                            "type": "session_created",
                            "session_id": req_session_id,
                            "display_name": _display_name,
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
