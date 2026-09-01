#!/usr/bin/env python
"""harden-citation-semantic-coverage 冒烟验证驱动（tasks.md 验收项）：三标的深度分析 → Langfuse 取证。

产出: reports/citation_smoke_harden_<ts>.json（运行产物，不入库；供验证报告引证）

验收标准（openspec/changes/harden-citation-semantic-coverage/tasks.md）：
  1. citation FAIL 率 < 10%（逐标的）
  2. citation_coverage score ≥ 0.8（正文数字普查覆盖率，只监控不进路由）
  3. 中际旭创(300308) 技术类期次错位 FAIL 清零：semantic_period_mismatch 桶
     且 field_ref 为 technical_indicators 的 FAIL 数 = 0（incident 022 历史值 13）
  4. 无格式类重试触发：分析师节点重跑（同名 span 出现 >1 次）时，citation_report
     中须存在 value_mismatch 桶 FAIL（格式类桶直判放行，不得触发重跑）

用法:
    uv run python tests/scripts/verify_smoke_harden_citation.py \
        --codes 002412,600519,300308 --names 汉森制药,贵州茅台,中际旭创
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001 - dotenv 缺失时走已有 env
    pass

API_BASE = os.environ.get("SMOKE_API_BASE", "http://127.0.0.1:8000")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
TERMINAL_STATUS = {"completed", "failed", "interrupted", "error"}
ANALYST_NODES = ("technical_analyst", "macro_analyst", "fundamental_analyst", "sentiment_analyst")
FORMAT_BUCKETS = {
    "path_unresolvable",
    "semantic_term_mismatch",
    "semantic_period_mismatch",
    "internal_inconsistency",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class LangfuseClient:
    """Langfuse v3 公共 REST API 只读客户端。"""

    def __init__(self) -> None:
        self.host = LANGFUSE_HOST
        self.auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])

    def find_deep_trace(self, stock_name: str, after: str) -> dict | None:
        page = 1
        best: dict | None = None
        best_ts = ""
        while True:
            r = requests.get(
                f"{self.host}/api/public/traces",
                params={"limit": 50, "page": page},
                auth=self.auth,
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
            for t in d.get("data") or []:
                name = t.get("name") or ""
                ts = t.get("timestamp") or ""
                if name == f"deep_analysis:{stock_name}" and ts >= after and ts > best_ts:
                    best, best_ts = t, ts
            meta = d.get("meta") or {}
            if page >= (meta.get("totalPages") or 1):
                break
            page += 1
        return best

    def trace_detail(self, trace_id: str) -> dict:
        r = requests.get(f"{self.host}/api/public/traces/{trace_id}", auth=self.auth, timeout=30)
        r.raise_for_status()
        return r.json()

    def trace_scores(self, trace: dict, detail: dict) -> dict:
        scores = detail.get("scores") or trace.get("scores") or []
        # 同名 score 多条时取时间戳最新（重试会二次上报 citation_coverage，
        # 列表序不保证时序，直接取最后一条会误读重试前的旧值）
        best: dict[str, tuple[str, object]] = {}
        for s in scores:
            if not isinstance(s, dict):
                continue
            name, ts = s.get("name"), s.get("timestamp") or ""
            if name and (name not in best or ts >= best[name][0]):
                best[name] = (ts, s.get("value"))
        return {k: v for k, (_, v) in best.items()}


def start_analysis(stock_code: str, stock_name: str) -> str:
    payload = {"query": f"深度分析{stock_name}", "stock_code": stock_code, "stock_name": stock_name}
    with requests.post(
        f"{API_BASE}/api/analyze", json=payload, stream=True, timeout=(10, 30)
    ) as resp:
        resp.raise_for_status()
        session_id = ""
        deadline = time.time() + 20
        for raw in resp.iter_lines(decode_unicode=True):
            line = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
            if not line or not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[len("data:") :])
            except ValueError:
                continue
            if ev.get("type") == "session_created":
                session_id = ev.get("session_id") or ""
                break
            if time.time() > deadline:
                break
        if not session_id:
            raise RuntimeError(f"{stock_name}: SSE 未解析到 session_id")
        return session_id


def wait_terminal(session_id: str, interval: float = 12.0) -> dict:
    start = time.time()
    while True:
        r = requests.get(f"{API_BASE}/api/sessions/{session_id}", timeout=15)
        r.raise_for_status()
        s = r.json()
        if (s.get("status") or "") in TERMINAL_STATUS:
            return {"status": s["status"], "duration_s": round(time.time() - start, 1)}
        time.sleep(interval)


def analyst_reruns(detail: dict) -> dict[str, int]:
    """分析师节点 span 出现次数（>1 = 发生了定向重试）。"""
    counts: Counter[str] = Counter()
    for obs in detail.get("observations") or []:
        name = obs.get("name") or ""
        if name in ANALYST_NODES:
            counts[name] += 1
    return {k: v for k, v in counts.items() if v > 1}


def verify_span_markers(detail: dict) -> dict:
    """verify_citations span 上的告警/降级标记。"""
    markers: dict[str, object] = {}
    for obs in detail.get("observations") or []:
        if (obs.get("name") or "") != "verify_citations":
            continue
        md = obs.get("metadata") or {}
        for key in (
            "citation_format_fail_incident_candidate",
            "citation_coverage_alert",
            "citation_retry_deescalated",
            "citation_minor_fail_deescalated",
        ):
            if key in md:
                markers[key] = md[key]
    return markers


def evaluate(stock_name: str, stock_code: str, report: dict, scores: dict, detail: dict) -> dict:
    results = report.get("results") or []
    total = report.get("total") or len(results)
    failed = report.get("failed") or sum(1 for r in results if r.get("status") == "FAIL")
    fail_rate = (failed / total) if total else 0.0
    buckets = Counter(
        r.get("bucket") for r in results if r.get("status") == "FAIL" and r.get("bucket")
    )
    tech_period_fails = sum(
        1
        for r in results
        if r.get("status") == "FAIL"
        and r.get("bucket") == "semantic_period_mismatch"
        and str((r.get("claim") or {}).get("field_ref") or "").startswith("technical_indicators")
    )
    coverage = scores.get("citation_coverage")
    reruns = analyst_reruns(detail)
    format_only_retry = bool(reruns) and "value_mismatch" not in buckets

    checks = {
        "fail_rate_lt_10pct": fail_rate < 0.10,
        "coverage_gte_0.8": (coverage is not None and coverage >= 0.8),
        "no_format_class_retry": not format_only_retry,
    }
    if stock_code == "300308":
        checks["tech_period_mismatch_zero"] = tech_period_fails == 0

    return {
        "stock_name": stock_name,
        "stock_code": stock_code,
        "total": total,
        "failed": failed,
        "fail_rate": round(fail_rate, 4),
        "unverifiable": report.get("unverifiable"),
        "coverage_gaps": report.get("coverage_gaps"),
        "fail_buckets": dict(buckets),
        "citation_coverage": coverage,
        "citation_pass_score": scores.get("citation_pass"),
        "unverifiable_ratio_score": scores.get("citation_unverifiable_ratio"),
        "tech_period_mismatch_fails": tech_period_fails,
        "analyst_reruns": reruns,
        "span_markers": verify_span_markers(detail),
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="harden-citation 冒烟验证")
    ap.add_argument("--codes", default="002412,600519,300308")
    ap.add_argument("--names", default="汉森制药,贵州茅台,中际旭创")
    args = ap.parse_args()
    codes = args.codes.split(",")
    names = args.names.split(",")
    assert len(codes) == len(names), "codes/names 数量不一致"

    lf = LangfuseClient()
    started_at = _now_iso()
    runs: list[dict] = []

    for code, name in zip(codes, names, strict=True):
        print(f"[{_now_iso()}] 触发 {name}({code}) ...", flush=True)
        t0 = time.time()
        session_id = start_analysis(code, name)
        term = wait_terminal(session_id)
        print(
            f"[{_now_iso()}] {name} 终态 {term['status']}（{term['duration_s']}s），取证中...",
            flush=True,
        )
        time.sleep(8)  # 等 Langfuse 异步落 trace/scores
        trace = lf.find_deep_trace(name, after=started_at)
        if trace is None:
            runs.append(
                {"stock_name": name, "stock_code": code, "error": "trace 未找到", "passed": False}
            )
            continue
        detail = lf.trace_detail(trace["id"])
        md = detail.get("metadata") or trace.get("metadata") or {}
        report = md.get("citation_report") if isinstance(md, dict) else None
        if not report:
            runs.append(
                {
                    "stock_name": name,
                    "stock_code": code,
                    "error": "citation_report 缺失",
                    "passed": False,
                }
            )
            continue
        scores = lf.trace_scores(trace, detail)
        ev = evaluate(name, code, report, scores, detail)
        ev["session_status"] = term["status"]
        ev["wall_clock_s"] = round(time.time() - t0, 1)
        ev["trace_id"] = trace["id"]
        runs.append(ev)
        verdict = "✅" if ev["passed"] else "❌"
        print(
            f"  {verdict} {name}: FAIL {ev['failed']}/{ev['total']} ({ev['fail_rate']:.1%}) "
            f"coverage={ev['citation_coverage']} buckets={ev['fail_buckets']} reruns={ev['analyst_reruns']}",
            flush=True,
        )

    out = {
        "generated_at": _now_iso(),
        "started_after": started_at,
        "all_passed": all(r.get("passed") for r in runs),
        "runs": runs,
    }
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"citation_smoke_harden_{ts}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {path}")
    print(f"总判定: {'✅ 全部通过' if out['all_passed'] else '❌ 存在未达标标的'}")
    return 0 if out["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
