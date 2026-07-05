"""FastAPI backend — SSE streaming for 5-layer analysis + quick chat."""

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
from finance_agent.llm import call_llm

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
    stock_code: str
    stock_name: str | None = None
    analysis_type: str = "comprehensive"
    peer_codes: str | None = None
    enable_web_search: bool = False
    api_key: str | None = None


class ChatRequest(BaseModel):
    message: str
    context: dict | None = None
    api_key: str | None = None


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


# ── Routes ──


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/pipeline")
async def get_pipeline():
    """Return the pipeline node definitions for the frontend."""
    return {"steps": LAYER_STEPS}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Start 5-layer analysis and stream SSE events."""

    async def event_stream() -> AsyncGenerator[str, None]:
        analysis_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        initial_state = {
            "stock_code": req.stock_code.strip(),
            "stock_name": req.stock_name or req.stock_code.strip(),
            "analysis_type": req.analysis_type or "comprehensive",
            "peer_codes": [c.strip() for c in (req.peer_codes or "").split(",") if c.strip()]
            or None,
            "enable_web_search": req.enable_web_search,
            "api_key": req.api_key,
        }

        # Emit start event
        yield _sse(
            {
                "type": "analysis_start",
                "analysis_id": analysis_id,
                "stock_code": req.stock_code,
                "stock_name": req.stock_name or req.stock_code,
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

                    # Node start
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

                    # Merge update
                    _merge_update(
                        accumulated, node_name, update if isinstance(update, dict) else {}
                    )

                    # Mark completed
                    idx = _ALL_NODES.index(node_name)
                    for i in range(idx + 1):
                        completed.add(_ALL_NODES[i])

                    # Update stock_name from fetched data
                    if accumulated.get("stock_name") in (None, "", req.stock_code):
                        quote = accumulated.get("stock_quote") or {}
                        info = accumulated.get("industry_info") or {}
                        fetched_name = quote.get("name") or info.get("name")
                        if fetched_name:
                            accumulated["stock_name"] = fetched_name

                    # Extract structured output
                    output = _extract_output(
                        node_name, update if isinstance(update, dict) else {}, accumulated
                    )

                    # Node complete
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

                # Check for final report
                if accumulated.get("final_report"):
                    file_paths = accumulated.get("file_paths") or {}
                    yield _sse(
                        {
                            "type": "report_ready",
                            "analysis_id": analysis_id,
                            "report_markdown": accumulated["final_report"],
                            "chart_data": accumulated.get("chart_data") or {},
                            "file_paths": file_paths,
                            "stock_name": accumulated.get("stock_name", req.stock_code),
                            "duration_ms": int((time.time() - start_time) * 1000),
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

        # Done
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


@app.post("/api/chat")
async def quick_chat(req: ChatRequest):
    """Quick mode — single LLM call without the 5-layer pipeline."""
    try:
        system = "你是专业的A股投研分析师助手。请基于上下文回答用户的问题，回答要简洁、专业、有数据支撑。"
        if req.context:
            context_str = json.dumps(req.context, ensure_ascii=False, default=str)[:2000]
            system += f"\n\n分析上下文：\n{context_str}"

        response = call_llm(req.message, system=system, api_key=req.api_key)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """Download generated report files."""
    safe_name = Path(filename).name  # Prevent path traversal
    file_path = REPORTS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
