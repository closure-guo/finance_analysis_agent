"""FastAPI backend - SSE streaming for 5-layer analysis + sessions + NLP + streaming chat."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

_logger = logging.getLogger("finance_agent.api")

load_dotenv()  # 加载 .env，须在 finance_agent 模块导入前执行（llm.py 等在 import 时读取环境变量）

from finance_agent.graph import build_5layer_graph  # noqa: E402
from finance_agent.llm import LLMConfig  # noqa: E402
from finance_agent.pipeline_runner import PipelineRunner, build_layer_tree  # noqa: E402
from finance_agent.react_agent import (  # noqa: E402
    _TIME_SENSITIVE_KEYWORDS as _TIME_SENSITIVE_KEYWORDS_REACT,
)
from finance_agent.session_store import (  # noqa: E402
    append_chat,
    append_session_event,
    create_chat_session,
    create_session,
    delete_session,
    get_max_event_seq,
    get_session,
    get_terminal_event,
    init_db,
    list_session_events,
    list_sessions,
    rename_session,
    set_pipeline_anchor,
    update_pipeline_snapshot,
    update_pipeline_timelines,
    update_session_for_clarify,
    update_session_report,
    update_session_status,
    upsert_chat,
)
from finance_agent.stream_registry import registry  # noqa: E402
from finance_agent.timeline_builder import apply_chat_event  # noqa: E402


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动时清扫悬挂 running 会话：后端重启后 PipelineRunner 内存态已丢失，置 failed 供前端恢复展示。"""
    PipelineRunner.mark_swept_failed()
    # 决策结算日批 scheduler(旁路;TESTING/DECISION_SETTLE_ENABLED=0 返回 None)
    # 旁路铁律:scheduler 任何失败不得影响 API 启动,记 ERROR 降级继续
    from finance_agent.outcome.scheduler import start_scheduler, stop_scheduler

    _scheduler = None
    try:
        _scheduler = start_scheduler()
    except Exception:
        _logger.exception("decision settle scheduler 启动失败,降级继续运行 API")
    yield
    stop_scheduler(_scheduler)


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

# 决策日志表(幂等建表,decision_log 与 sessions 同库;decision-outcome-tracking)
from finance_agent.outcome.store import init_decision_log, insert_decision  # noqa: E402

init_decision_log()

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


class LLMConfigRequest(BaseModel):  # noqa: N815  # 字段 camelCase 为前端 JSON 契约
    """请求级 LLM 配置（前端设置面板提交），字段为 None 时后端回退环境变量。

    字段用 camelCase 命名，与 LLMConfig dataclass 及前端 JSON 契约一致。
    """

    model: str | None = None
    baseUrl: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    apiKey: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    thinking: str | None = None


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
    llm_config: LLMConfigRequest | None = None  # 请求级 LLM 配置（model/baseUrl/apiKey/thinking）


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    context: dict | None = None
    api_key: str | None = None
    user_id: str | None = None  # Langfuse user 聚合（ADR-0015）
    llm_config: LLMConfigRequest | None = None  # 请求级 LLM 配置（model/baseUrl/apiKey/thinking）


class RenameRequest(BaseModel):
    display_name: str


class ModelsRequest(BaseModel):
    """模型发现请求体（POST /api/llm-config/models）。"""

    baseUrl: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    apiKey: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约


# ── Helpers ──


def _to_llm_config(req: LLMConfigRequest | None) -> LLMConfig | None:
    """将 Pydantic LLMConfigRequest 转换为内部 LLMConfig dataclass。

    req 为 None 或所有字段均为 None 时返回 None（回退环境变量默认行为）。
    """
    if req is None:
        return None
    cfg = LLMConfig(
        model=req.model,
        baseUrl=req.baseUrl,
        apiKey=req.apiKey,
        thinking=req.thinking,
    )
    # 全 None 时返回 None，避免无意义的空配置传播
    if not any([cfg.model, cfg.baseUrl, cfg.apiKey, cfg.thinking]):
        return None
    return cfg


def _sse(data: dict) -> str:
    """Format a SSE data line.

    当 data 含 seq 字段时，在 data: 行前添加 id: 行，
    使原生 EventSource 的自动 Last-Event-ID 机制生效。
    """
    seq = data.get("seq")
    idLine = f"id: {seq}\n" if seq is not None else ""
    return f"{idLine}data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


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


def _persist_decision_log(
    accumulated: dict, session_id: str, stock_code: str, stock_name: str
) -> None:
    """批准的 TradeDecision 落 decision_log(旁路:任何失败仅 ERROR,不阻断报告)。"""
    try:
        if accumulated.get("fund_manager_decision") != "approve":
            return
        decision = accumulated.get("final_trade_decision") or {}
        if not decision.get("action"):
            return
        # entry_price 代码回填:quote 优先,kline 收盘兜底
        entry_price = (accumulated.get("stock_quote") or {}).get("price")
        if entry_price is None:
            kline = accumulated.get("kline")
            if kline is not None and len(kline) > 0:
                last = kline.iloc[-1] if hasattr(kline, "iloc") else kline[-1]
                entry_price = float(last["收盘"])
        if entry_price is None:
            _logger.warning("decision_log 跳过: %s 无可靠 entry_price", stock_code)
            return
        position_size = decision.get("position_size")
        insert_decision(
            {
                "decision_id": None,  # store 生成
                "session_id": session_id,
                "langfuse_trace_id": accumulated.get("langfuse_trace_id"),
                "timestamp": datetime.now().isoformat(),
                "ticker": stock_code,
                "name": stock_name,
                "action": decision["action"],
                "entry_price": float(entry_price),
                "stop_loss": decision.get("stop_loss"),
                "target_price": decision.get("target_price"),
                "confidence": decision.get("confidence"),
                "position_size": float(position_size)
                if isinstance(position_size, (int, float))
                else None,
            }
        )
        _logger.info("decision_log 已落库: %s %s", stock_code, decision["action"])
    except Exception:
        _logger.exception("decision_log 落库失败(不阻断业务)")


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

        接收 display_name / session_type / chat_history（含可选 thinking + tool_calls
        + agentTimeline），内部经 session_store.create_session + append_chat 写入真实存储；
        顶层可选 pipeline_timelines（{node: [TimelineItem]}）与 pipeline_snapshot（dict），
        分别经 update_pipeline_timelines / update_pipeline_snapshot 落库，
        供历史会话恢复等 E2E 确定性构造会话（persist-full-session-timeline delta）。
        """
        # 旧版 smoke 断言（{symbol}）保持占位响应，避免破坏既有契约
        if "chat_history" not in req:
            return {"status": "ok", "mode": "testing"}
        session_id = create_session(
            session_type=req.get("session_type", "chat"),
            display_name=req.get("display_name"),
            report_markdown=req.get("report_markdown", ""),
            status=req.get("status", "completed"),
        )
        for entry in req.get("chat_history", []):
            append_chat(
                session_id,
                role=entry["role"],
                content=entry["content"],
                thinking=entry.get("thinking"),
                tool_calls=entry.get("tool_calls"),
                agent_timeline=entry.get("agentTimeline"),
            )
        # 顶层管线字段（persist-full-session-timeline）：E2E 造「已完成管线会话」需要
        # pipeline_snapshot（走 completed 分支恢复分层时间轴）与 pipeline_timelines（恢复节点时序）
        pipeline_timelines = req.get("pipeline_timelines")
        if isinstance(pipeline_timelines, dict):
            update_pipeline_timelines(session_id, pipeline_timelines)
        pipeline_snapshot = req.get("pipeline_snapshot")
        if isinstance(pipeline_snapshot, dict):
            update_pipeline_snapshot(session_id, pipeline_snapshot)
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
    return {"sessions": await asyncio.to_thread(list_sessions)}


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get full session by id."""
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.patch("/api/sessions/{session_id}")
async def rename_session_api(session_id: str, req: RenameRequest):
    """Rename a session."""
    renamed = await asyncio.to_thread(rename_session, session_id, req.display_name)
    if not renamed:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
async def delete_session_api(session_id: str):
    """Delete a session."""
    deleted = await asyncio.to_thread(delete_session, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    """取消会话的活跃生成任务。无活跃任务时检查终态事件做幂等返回。

    对应 delta spec Task 4.2。Fast path 由 PipelineRunner 后台线程驱动，
    需额外调 PipelineRunner.cancel 设置取消标志终止线程。
    """
    result = await registry.cancel(session_id)
    pipelineResult = await asyncio.to_thread(PipelineRunner.cancel, session_id)
    if not result and not pipelineResult:
        # 无活跃任务：检查是否已有终态事件（幂等返回）
        terminal = await asyncio.to_thread(get_terminal_event, session_id)
        if terminal:
            return {"ok": True, "status": terminal["type"]}
        raise HTTPException(status_code=404, detail="No active task for this session")
    return {"ok": True, "status": "interrupted"}


@app.get("/api/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """恢复端点：经 registry.subscribe 返回 SSE 流，支持 after_seq/Last-Event-ID 断点续传。

    对应 delta spec Task 4.1。204 语义：无事件且无活跃任务时返回 204，
    避免对空会话下发无意义终态事件。
    """
    # session 存在性校验
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 解析 afterSeq：Last-Event-ID 头优先，否则查询参数，默认 0
    lastEventId = request.headers.get("Last-Event-ID")
    if lastEventId is not None:
        try:
            afterSeq = int(lastEventId)
        except ValueError:
            afterSeq = 0
    else:
        try:
            afterSeq = int(request.query_params.get("after_seq", "0"))
        except ValueError:
            afterSeq = 0

    # 204 语义：无事件且无活跃任务时返回 204
    events = await asyncio.to_thread(list_session_events, session_id, afterSeq)
    hasActive = registry.is_active(session_id)
    if not events and not hasActive:
        return Response(status_code=204)

    async def sse_stream() -> AsyncGenerator[str, None]:
        async for event in registry.subscribe(session_id, afterSeq):
            yield _sse(event)

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Graph streaming (encapsulated as a reusable tool) ──


def _run_graph_streaming(
    stock_code: str,
    stock_name: str,
    req: AnalyzeRequest,
    analysis_id: str,
    start_time: float,
    session_id: str | None = None,
    llm_config: LLMConfig | None = None,
) -> Generator[str, None, None]:
    """执行 5 层图分析，流式 yield SSE 事件。

    封装了 PREP → Layer I-V → 报告生成的完整流程，
    可作为 ReAct 循环中 run_deep_analysis 工具的执行体。

    Args:
        session_id: 可选外部传入的 session_id。若未提供，内部创建新 session。
        llm_config: 请求级 LLM 配置，透传到管线节点的 call_llm_streaming。
    """
    initial_state = {
        "stock_code": stock_code,
        "stock_name": stock_name or stock_code,
        "analysis_type": req.analysis_type or "comprehensive",
        "peer_codes": [c.strip() for c in (req.peer_codes or "").split(",") if c.strip()] or None,
        "enable_web_search": req.enable_web_search,
        "api_key": req.api_key,
        "focus": (req.focus or "").strip(),
        # 请求级 LLM 配置透传到管线节点（call_llm_streaming / call_llm）
        "llm_config": llm_config,
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
                # 旁路落库批准的 TradeDecision(失败仅 ERROR,不阻断报告)
                _persist_decision_log(accumulated, session_id, stock_code, stock_name_final)

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


def _upsert_assistant_chat(session_id: str, collector: _ChatCollector) -> None:
    """增量持久化 collector 内容到 chat_history（upsert 语义）。

    在 SSE 循环中每 10 秒调用，确保运行中会话的 assistant 消息
    在用户中途切走后仍可从 chat_history 恢复。与最终持久化共用 upsert 语义，
    避免循环内 upsert 与最终 append 重复落库。
    """
    response = collector.response.strip()
    thinking = collector.thinking.strip() or None
    tool_calls = collector.tool_calls or None
    agent_timeline = collector.agent_timeline or None
    if not (response or thinking or tool_calls or agent_timeline):
        return
    upsert_chat(
        session_id,
        "assistant",
        response,
        thinking=thinking,
        tool_calls=tool_calls,
        agent_timeline=agent_timeline,
    )


# ── ReAct 路径后台生成任务（registry 驱动，生成与连接解耦）──


async def _subscribe_sse(
    session_id: str,
    after_seq: int = 0,
    on_event: Any = None,
) -> AsyncGenerator[str, None]:
    """订阅 registry 事件流并转发为 SSE 字符串。

    客户端断开仅退订（生成器取消），不影响后台生成任务。
    用后台 task 消费 subscribe 生成器，主循环 wait_for 取事件，
    超时发心跳保持 SSE 连接活跃（wait_for 直接作用于生成器会损坏它）。
    on_event：yield 前对事件 dict 的就地修改回调（如 Fast path 补充 done 展示字段）。
    """
    gen = registry.subscribe(session_id, after_seq)
    outQueue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _consume() -> None:
        try:
            async for ev in gen:
                await outQueue.put(ev)
        except Exception:
            _logger.exception("订阅消费异常 session=%s", session_id)
        finally:
            await outQueue.put(None)

    consumer = asyncio.create_task(_consume())
    try:
        while True:
            try:
                ev = await asyncio.wait_for(outQueue.get(), timeout=10.0)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if ev is None:
                return
            if on_event is not None:
                on_event(ev)
            yield _sse(ev)
            if ev.get("type") in ("done", "interrupted", "error"):
                return
    finally:
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await consumer


# SSE 响应统一头（禁缓存、禁代理缓冲）
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_error_response(message: str) -> StreamingResponse:
    """构造 error + done 的短 SSE 响应（参数校验失败等无法进入任务流程的场景）。"""

    async def _err_gen() -> AsyncGenerator[str, None]:
        yield _sse({"type": "error", "message": message, "timestamp": _now()})
        yield _sse({"type": "done", "timestamp": _now()})

    return StreamingResponse(_err_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _persist_interrupted(session_id: str, collector: _ChatCollector) -> None:
    """中断兜底持久化：collector 已收集的部分回复落库并标注中断。

    spec 要求 chat_history 不出现无 assistant 回复的悬空 user 消息：
    collector 全空（任务刚启动即被取消）时落库占位 assistant 消息。
    """
    if collector.response.strip():
        collector.response += "\n\n[输出中断]"
    elif collector.thinking.strip() or collector.tool_calls or collector.agent_timeline:
        # 仅有思考/工具调用：保留过程，内容标注中断
        collector.response = "[输出中断]"
    else:
        collector.response = "[输出中断]"
    _upsert_assistant_chat(session_id, collector)


async def _run_chat_task(
    session_id: str,
    req: ChatRequest,
    display_name: str | None,
    api_key: str | None,
    llm_config: LLMConfig | None = None,
) -> None:
    """/api/chat 后台生成任务：quick/follow-up ReAct Agent。

    事件经 registry.publish 写入 journal 并 fan-out；客户端断开仅退订。
    中断/异常时部分回复落库、status 流转，终态事件由任务自身与
    registry._run_task 协作发布（终态 CAS 保证唯一）。
    """
    from finance_agent.agent_factory import build_agent, stream_agent_to_sse

    collector = _ChatCollector()
    try:
        # 新会话：session_created 作为首个事件入 journal（恢复重放的事实源）
        if display_name is not None:
            await registry.publish(
                session_id,
                {
                    "type": "session_created",
                    "session_id": session_id,
                    "display_name": display_name,
                    "timestamp": _now(),
                },
            )
        # user 消息在任务内落库：409（single-flight 拒绝）时不追加，避免污染历史
        await asyncio.to_thread(append_chat, session_id, "user", req.message)
        # 状态置 running：恢复端点与前端运行指示依赖
        await asyncio.to_thread(update_session_status, session_id, "running")

        # 模式推断：analysis 会话 -> follow-up（报告追问）；chat 会话 -> quick
        session = await asyncio.to_thread(get_session, session_id) or {}
        mode = "follow-up" if session.get("session_type") == "analysis" else "quick"

        agent = build_agent(
            mode=mode, api_key=api_key, session_id=session_id, llm_config=llm_config
        )

        lastPersistTime = time.time()
        PERSIST_INTERVAL = 10
        async for sse_str in stream_agent_to_sse(
            agent, req.message, session_id=session_id, user_id=req.user_id
        ):
            data = _parse_sse_data(sse_str)
            if data is None:
                # 心跳注释行不进 journal（传输层保活，非业务事件）
                continue
            collector.feed(data)
            await registry.publish(session_id, data)
            # 增量持久化：每 10s upsert，避免运行中切走后 assistant 回复丢失
            now = time.time()
            if now - lastPersistTime >= PERSIST_INTERVAL:
                await asyncio.to_thread(_upsert_assistant_chat, session_id, collector)
                lastPersistTime = now

        # 正常完成：最终持久化 + 状态流转 + done 终态
        await asyncio.to_thread(_upsert_assistant_chat, session_id, collector)
        await asyncio.to_thread(update_session_status, session_id, "completed")
        await registry.publish(
            session_id, {"type": "done", "session_id": session_id, "timestamp": _now()}
        )
    except asyncio.CancelledError:
        await asyncio.to_thread(_persist_interrupted, session_id, collector)
        await asyncio.to_thread(update_session_status, session_id, "interrupted")
        raise
    except Exception as exc:
        await asyncio.to_thread(_upsert_assistant_chat, session_id, collector)
        await asyncio.to_thread(
            update_session_status,
            session_id,
            "failed",
            failure_reason=f"{type(exc).__name__}: {exc}",
        )
        raise


async def _run_react_analysis(
    session_id: str,
    req: AnalyzeRequest,
    analysis_id: str,
    start_time: float,
    display_name: str | None,
    api_key: str | None,
    llm_config: LLMConfig | None = None,
) -> None:
    """/api/analyze ReAct 路径后台生成任务（无股票代码或追问时的 harness Agent 编排）。

    事件经 registry.publish 写入 journal 并 fan-out；客户端断开仅退订。
    """
    from finance_agent.agent_factory import build_agent, stream_agent_to_sse

    collector = _ChatCollector()
    collectedMetadata: dict = {}
    analysisExecuted = False
    try:
        if display_name is not None:
            await registry.publish(
                session_id,
                {
                    "type": "session_created",
                    "session_id": session_id,
                    "display_name": display_name,
                    "timestamp": _now(),
                },
            )
        await asyncio.to_thread(append_chat, session_id, "user", req.query)
        await asyncio.to_thread(update_session_status, session_id, "running")

        # 从 session 恢复 focus，与用户输入合并
        session = await asyncio.to_thread(get_session, session_id) or {}
        accumulatedFocus = (session.get("focus") or "").strip()
        currentFocus = (req.focus or "").strip()
        if currentFocus:
            accumulatedFocus = f"{accumulatedFocus}\n{currentFocus}".strip()

        agent = build_agent(
            mode="deep",
            api_key=api_key,
            analysis_type=req.analysis_type,
            peer_codes=req.peer_codes.split(",") if req.peer_codes else None,
            enable_web_search=req.enable_web_search,
            session_id=session_id,
            llm_config=llm_config,
        )

        def on_metadata_cb(metadata: dict) -> None:
            """收集 TOOL_METADATA（chart_data、analyst_reports 等）用于 session 持久化。"""
            collectedMetadata.update(metadata)

        def on_resolved_cb(sc: str, sn: str) -> None:
            """股票代码解析完成回调 -- 更新 session。"""
            asyncio.create_task(
                asyncio.to_thread(
                    update_session_for_clarify,
                    session_id,
                    stock_code=sc,
                    stock_name=sn,
                    display_name=f"{sn}({sc})",
                )
            )

        # 对时效性查询，预调 web_search 并将结果注入用户消息
        userQuery = req.query
        hasStockCode = bool(re.search(r"\d{6}", req.query))

        if not hasStockCode and any(kw in req.query for kw in _TIME_SENSITIVE_KEYWORDS_REACT):
            from finance_agent.agent_factory import _web_search

            searchQuery = f"{req.query} A股 热点 推荐 最新"

            preThinking = {
                "type": "thinking_token",
                "token": "用户询问包含时效性关键词，我先搜索最新市场信息。\n",
                "timestamp": _now(),
            }
            collector.feed(preThinking)
            await registry.publish(session_id, preThinking)
            preToolCall = {
                "type": "tool_call",
                "name": "web_search",
                "args": {"query": searchQuery},
                "timestamp": _now(),
            }
            collector.feed(preToolCall)
            await registry.publish(session_id, preToolCall)
            # 补发 search_start：前端搜索横幅由 search_start/search_result 驱动
            # 同步 feed collector：search_start 生成 searching 状态的 search item，
            # 持久化到 chat_history.agentTimeline，刷新后才能恢复搜索横幅
            searchStartEvent = {"type": "search_start", "query": searchQuery, "timestamp": _now()}
            collector.feed(searchStartEvent)
            await registry.publish(session_id, searchStartEvent)

            searchResult = ""
            try:
                searchResult = await _web_search(searchQuery)
            except Exception as e:
                searchResult = f"搜索失败: {e}"

            searchSummary = searchResult[:2000] if len(searchResult) > 2000 else searchResult
            preToolResult = {
                "type": "tool_result",
                "name": "web_search",
                "result": searchSummary,
                "timestamp": _now(),
            }
            collector.feed(preToolResult)
            await registry.publish(session_id, preToolResult)
            # 补发 search_result（结构化来源），驱动搜索横幅转"已搜索 N 个网页"
            # 同步 feed collector：search_result 将 searching item 更新为 done 并写入 results，
            # 持久化后刷新才能恢复完整的搜索横幅（含结果数量）
            from finance_agent.web_search import parse_search_output

            preResults = parse_search_output(searchResult)
            searchResultEvent = {
                "type": "search_result",
                "query": searchQuery,
                "results": [
                    {"title": r.title, "url": r.url, "content": r.content} for r in preResults
                ],
                "count": len(preResults),
                "timestamp": _now(),
            }
            collector.feed(searchResultEvent)
            await registry.publish(session_id, searchResultEvent)
            userQuery = (
                f"{req.query}\n\n"
                f"[以下是 web_search 的搜索结果，请基于这些信息提取具体股票名称，"
                f"然后调用 search_stock 获取股票代码，再调用 run_deep_analysis：]\n"
                f"{searchSummary}"
            )

        # 如果 session 已有 focus，注入用户消息上下文
        if accumulatedFocus:
            userQuery = f"{userQuery}\n\n[已收集的用户关注点/澄清回答：\n{accumulatedFocus}]"

        lastPersistTime = time.time()
        PERSIST_INTERVAL = 10
        async for sse_str in stream_agent_to_sse(
            agent,
            userQuery,
            on_metadata=on_metadata_cb,
            on_resolved=on_resolved_cb,
            session_id=session_id,
            user_id=req.user_id,
        ):
            data = _parse_sse_data(sse_str)
            if data is None:
                continue
            collector.feed(data)
            if data.get("type") == "report_ready":
                analysisExecuted = True
                data["session_id"] = session_id
                data["duration_ms"] = int((time.time() - start_time) * 1000)
            await registry.publish(session_id, data)
            now = time.time()
            if now - lastPersistTime >= PERSIST_INTERVAL:
                await asyncio.to_thread(_upsert_assistant_chat, session_id, collector)
                lastPersistTime = now

        # 最终持久化（upsert 语义，避免与增量重复落库）
        await asyncio.to_thread(_upsert_assistant_chat, session_id, collector)

        # 如果 Agent 调用了 run_deep_analysis，说明已进入分析阶段
        if collectedMetadata.get("report_markdown") or collectedMetadata.get("stock_code"):
            analysisExecuted = True

        if not analysisExecuted:
            # 分析未执行：Agent 仍在澄清阶段，保存状态并通知前端等待输入
            if currentFocus:
                await asyncio.to_thread(
                    update_session_for_clarify,
                    session_id,
                    focus=accumulatedFocus,
                    status="clarifying",
                )
            else:
                await asyncio.to_thread(update_session_for_clarify, session_id, status="clarifying")
            await registry.publish(
                session_id,
                {
                    "type": "awaiting_input",
                    "session_id": session_id,
                    "pending_intent": "awaiting_focus",
                    "timestamp": _now(),
                },
            )
        # 分析已执行：session 状态已被 _run_graph_streaming 更新为 completed

        # done 终态（完整展示字段；registry._run_task 的自动 done 被终态 CAS 拒绝）
        await registry.publish(
            session_id,
            {
                "type": "done",
                "analysis_id": analysis_id,
                "session_id": session_id,
                "duration_ms": int((time.time() - start_time) * 1000),
                "timestamp": _now(),
            },
        )
    except asyncio.CancelledError:
        await asyncio.to_thread(_persist_interrupted, session_id, collector)
        await asyncio.to_thread(update_session_status, session_id, "interrupted")
        raise
    except Exception as exc:
        await asyncio.to_thread(_upsert_assistant_chat, session_id, collector)
        await asyncio.to_thread(
            update_session_status,
            session_id,
            "failed",
            failure_reason=f"{type(exc).__name__}: {exc}",
        )
        raise


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """深度分析 -- Fast path 直走管线，ReAct 路径由 registry 后台任务驱动。

    生成与连接解耦（resume-stream-on-session-switch）：
    - Fast path（stock_code 已知）：PipelineRunner 后台线程，事件桥接 journal
    - ReAct 路径（无股票代码/追问）：registry.start 后台任务 + 订阅转发，
      运行中重复请求返回 409 session_busy
    """
    analysis_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    if not req.query:
        return _sse_error_response("请输入股票代码或名称")

    # API key: 优先用请求中的，无效则回退到环境变量
    api_key = req.api_key if req.api_key and req.api_key.startswith("sk-") else None
    # 请求级 LLM 配置（LLMConfigRequest → LLMConfig），None 时回退环境变量
    llm_config = _to_llm_config(req.llm_config)

    # ── Session 生命周期：从首次输入开始 ──
    session_id = req.session_id
    display_name: str | None = None
    if session_id:
        session = await asyncio.to_thread(get_session, session_id)
        if not session:
            return _sse_error_response("Session not found")
    else:
        display_name = req.query.strip()[:30] or "深度分析"
        session_id = await asyncio.to_thread(
            create_session,
            stock_code="",
            stock_name="",
            display_name=display_name,
            status="clarifying",
            session_type="analysis",
        )

    stock_code = req.stock_code.strip()
    stock_name = req.stock_name or ""

    # ── Fast path: stock_code 已知，直接走管线 ──
    # 新会话（未传 session_id）且已解析出股票代码时走 fast path；
    # 追问/复用旧会话时走 ReAct 路径
    if stock_code and not req.session_id:
        # 追加用户输入到 chat_history
        await asyncio.to_thread(append_chat, session_id, "user", req.query)
        # 持久化管线触发锚点：fast path 下 chat_history 仅一条 user，锚点 = 1
        await asyncio.to_thread(set_pipeline_anchor, session_id)
        await asyncio.to_thread(
            update_session_for_clarify,
            session_id,
            stock_code=stock_code,
            stock_name=stock_name,
            status="running",
        )
        # session_created 同步写入 journal（恢复端点重放的事实源；
        # 在线客户端经 subscribe 重放收到，无需单独直发）。
        # 同步写避免 await 点：确保 PipelineRunner.start 在客户端断开前执行，
        # 且 session_created 先于管线事件入 journal（重放顺序正确）
        append_session_event(
            session_id,
            {
                "type": "session_created",
                "session_id": session_id,
                "display_name": display_name,
                "timestamp": _now(),
            },
        )
        # 管线后台执行：事件经 PipelineRunner._run 的 publish 桥接到 journal，
        # 客户端断开不中断管线，终态由 _run 的 finally 发布
        loop = asyncio.get_running_loop()
        PipelineRunner.start(
            session_id,
            lambda: _run_graph_streaming(
                stock_code,
                stock_name,
                req,
                analysis_id,
                start_time,
                session_id=session_id,
                llm_config=llm_config,
            ),
            {
                "layerTree": build_layer_tree(),
                "currentNodeId": "",
                "progress": 0.0,
                "updatedAt": int(time.time() * 1000),
                # 管线启动时间戳（毫秒）：前端刷新重建用作「已用时」计时起点
                "pipeline_start_ts": int(start_time * 1000),
            },
            loop=loop,
        )

        # done 终态补充展示字段：duration_ms 等由端点注入
        # （前端 App.tsx 依赖 duration_ms 显示"分析完成 · 耗时 X 秒"）
        def _enrich_done(ev: dict) -> None:
            if ev.get("type") == "done":
                ev["analysis_id"] = analysis_id
                ev["duration_ms"] = int((time.time() - start_time) * 1000)
                ev["timestamp"] = _now()

        return StreamingResponse(
            _subscribe_sse(session_id, on_event=_enrich_done),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # ── ReAct 路径：registry 后台任务 + 订阅转发（生成与连接解耦）──
    started = await registry.start(
        session_id,
        _run_react_analysis(
            session_id,
            req,
            analysis_id,
            start_time,
            display_name,
            api_key,
            llm_config=llm_config,
        ),
    )
    if not started:
        # single-flight：会话已有活跃任务，拒绝新消息（不追加 user 消息）
        return JSONResponse(status_code=409, content={"error": "session_busy"})
    # 追问时跳过历史事件重放：用当前 journal 最大 seq 作为 after_seq，
    # 避免上一轮 done 终态事件导致 registry.subscribe 提前 return（SSE 流终止）
    afterSeq = await asyncio.to_thread(get_max_event_seq, session_id)
    return StreamingResponse(
        _subscribe_sse(session_id, after_seq=afterSeq),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── Streaming Chat ──


@app.post("/api/chat")
async def quick_chat(req: ChatRequest):
    """Quick mode / Follow-up mode - registry 后台任务驱动的 ReAct Agent。

    生成与连接解耦（resume-stream-on-session-switch）：registry.start 后台任务
    持有生成逻辑，SSE 响应仅订阅转发；运行中重复请求返回 409 session_busy。
    """
    # API key: 优先用请求中的，无效则回退到环境变量
    api_key = req.api_key if req.api_key and req.api_key.startswith("sk-") else None
    # 请求级 LLM 配置（LLMConfigRequest → LLMConfig），None 时回退环境变量
    llm_config = _to_llm_config(req.llm_config)

    # ADR-0015：新对话时先创建 session，使 Langfuse session 聚合可用
    # （session_id 须在 agent 运行前确定，否则 propagate_attributes 拿不到）
    session_id = req.session_id
    display_name: str | None = None
    if session_id:
        session = await asyncio.to_thread(get_session, session_id)
        if not session:
            return _sse_error_response("Session not found")
    else:
        display_name = req.message.strip()[:30] or "快速问答"
        session_id = await asyncio.to_thread(create_chat_session, display_name)

    # 追问时跳过历史事件重放：用当前 journal 最大 seq 作为 after_seq，
    # 避免上一轮 done 终态事件导致 registry.subscribe 提前 return（SSE 流终止），
    # 与 /api/analyze ReAct 路径对齐。
    # 须在 registry.start 前取值：新会话的 session_created 由任务发布，
    # start 后再取 max_seq 可能跳过该事件，导致前端拿不到 session_id
    afterSeq = await asyncio.to_thread(get_max_event_seq, session_id)
    started = await registry.start(
        session_id,
        _run_chat_task(session_id, req, display_name, api_key, llm_config=llm_config),
    )
    if not started:
        # single-flight：会话已有活跃任务，拒绝新消息（不追加 user 消息）
        return JSONResponse(status_code=409, content={"error": "session_busy"})
    return StreamingResponse(
        _subscribe_sse(session_id, after_seq=afterSeq),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── LLM 配置端点（add-custom-llm-api）──


@app.get("/api/llm-config")
async def get_llm_config():
    """返回后端默认 LLM 配置（环境变量），供前端设置面板展示 placeholder。

    不返回 apiKey（安全：不向后端暴露密钥）。
    """
    return {
        "model": os.getenv("LLM_MODEL", "deepseek/deepseek-v4-pro"),
        "baseUrl": os.getenv("LLM_BASE_URL", ""),
        "thinking": os.getenv("LLM_THINKING", "enabled"),
    }


@app.post("/api/llm-config/models")
async def list_models(req: ModelsRequest):
    """调用 OpenAI 兼容的 GET {baseUrl}/models 拉取模型列表。

    baseUrl / apiKey 回退环境变量。端点不支持时返回空列表 + error 提示。
    """
    import httpx

    baseUrl = (req.baseUrl or "").strip()
    # apiKey 允许回退环境变量（用户可能只填了 baseUrl 想探测端点，密钥用已配置的）
    apiKey = req.apiKey or os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))

    # 模型发现是「探测用户指定端点」的工具：baseUrl 为空时**不回退环境变量**，
    # 否则会悄悄用环境端点（如 LLM_BASE_URL）返回该端点模型，违背用户直觉（决策 A）。
    # 分析链路 call_llm 的回退不受影响（仍是 请求配置 → 环境变量 → 默认值）。
    if not baseUrl:
        return {"models": [], "error": "请先配置 API Base URL 再刷新模型列表"}

    url = baseUrl.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {apiKey}"} if apiKey else {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return {"models": [], "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"models": [], "error": f"{type(e).__name__}: {e}"}

    # OpenAI 兼容格式：{"data": [{"id": "model-name"}, ...]}
    models = []
    for item in data.get("data", []):
        modelId = item.get("id") if isinstance(item, dict) else None
        if modelId:
            models.append(modelId)

    return {"models": sorted(models), "error": None}


@app.post("/api/llm-config/test")
async def test_llm_config(req: LLMConfigRequest):
    """用给定 llm_config 发送极简 LLM 请求（max_tokens=1），返回连通性测试结果。

    返回 success / latencyMs / model 或 success=false + error / errorType。
    错误分类：auth / network / model_not_found / unknown。
    """
    import time as _time

    cfg = _to_llm_config(req)
    startMs = _time.time()

    try:
        from finance_agent.llm import call_llm

        call_llm("Hi", max_tokens=1, llm_config=cfg)
        latencyMs = int((_time.time() - startMs) * 1000)
        # 解析最终使用的 model（cfg.model 或环境变量）
        usedModel = (cfg.model if cfg else None) or os.getenv(
            "LLM_MODEL", "deepseek/deepseek-v4-pro"
        )
        return {"success": True, "latencyMs": latencyMs, "model": usedModel}
    except Exception as e:
        latencyMs = int((_time.time() - startMs) * 1000)
        errorType = _classify_llm_error(e)
        return {
            "success": False,
            "latencyMs": latencyMs,
            "error": f"{type(e).__name__}: {e}",
            "errorType": errorType,
        }


def _classify_llm_error(e: Exception) -> str:
    """将 LLM 调用异常分类为 auth / network / model_not_found / unknown。

    当 NotFoundError 的响应体为 HTML（如网站 404 页面）时，判定为 base_url 错误
    而非模型不存在——请求打到了网页服务器而非 API 端点。
    """
    errorName = type(e).__name__
    errorMessage = str(e).lower()

    # 认证错误
    if "auth" in errorName.lower() or "authentication" in errorName.lower():
        return "auth"
    if "401" in errorMessage or "invalid api key" in errorMessage:
        return "auth"

    # base_url 错误：NotFoundError 但响应体是 HTML（打到了网页服务器而非 API 端点）
    if "notfound" in errorName.lower() and ("<!doctype" in errorMessage or "<html" in errorMessage):
        return "network"

    # 模型不存在
    if "notfound" in errorName.lower():
        return "model_not_found"
    if "model" in errorMessage and "not found" in errorMessage:
        return "model_not_found"

    # 网络/连接错误
    if "connection" in errorName.lower() or "timeout" in errorName.lower():
        return "network"
    if (
        "connection" in errorMessage
        or "timeout" in errorMessage
        or "unreachable" in errorMessage
        or "refused" in errorMessage
    ):
        return "network"

    return "unknown"


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
