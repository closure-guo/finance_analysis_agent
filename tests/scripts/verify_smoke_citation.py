#!/usr/bin/env python
"""契约修复冒烟验证驱动（任务 1）：触发多标的深度模式分析 → 轮询终态 → Langfuse 取证。

产出: reports/citation_smoke_verify_<ts>.json（运行产物，不入库；供 incident 记录引证）

验收标准（fix-citation-contract-diseases 修复后的冒烟口径，见 docs/incidents/020）：
  1. citation FAIL 率 < 10%（历史值 65-75%）
  2. 重试未触发：以 trace score citation_pass=true 且 citation_report.failed==0 为证
     （等价于 iteration_count 停滞在首轮；state 不落 Langfuse / sessions 表）
  3. 技术类 claim 的 field_ref 采用负索引语义（-N）且解析成功（status != FAIL）
  4. 基本面类 claim 的 field_ref 使用英文 state 键（无中文根键）
  5. 亿级数值（|ground_truth| >= 1e8）不再因绝对容差误判（PASS 而非 FAIL）

用法:
    uv run python tests/scripts/verify_smoke_citation.py \
        --codes 002412,600519,300308 --names 汉森制药,贵州茅台,中际旭创
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001 - dotenv 缺失时环境变量不加载，走已有 env
    pass

API_BASE = os.environ.get("SMOKE_API_BASE", "http://127.0.0.1:8000")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
TERMINAL_STATUS = {"completed", "failed", "interrupted", "error"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class LangfuseClient:
    """Langfuse v3 公共 REST API 只读客户端（观测 trace 的 citation_report 与 scores）。"""

    def __init__(self) -> None:
        self.host = LANGFUSE_HOST
        self.auth = (
            os.environ["LANGFUSE_PUBLIC_KEY"],
            os.environ["LANGFUSE_SECRET_KEY"],
        )

    def find_deep_trace(self, stock_name: str, after: str | None = None) -> dict | None:
        """在 after 之后创建的 deep_analysis:<stock> trace 中取最新一条（after=None 取最新）。"""
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
            rows = d.get("data") or []
            for t in rows:
                name = t.get("name") or ""
                ts = t.get("timestamp") or ""
                if (
                    name == f"deep_analysis:{stock_name}"
                    and ts > best_ts
                    and (after is None or ts >= after)
                ):
                    best, best_ts = t, ts
            meta = d.get("meta") or {}
            if page >= (meta.get("totalPages") or 1):
                break
            page += 1
        return best

    def trace_report(self, trace: dict) -> dict | None:
        md = trace.get("metadata") or {}
        return md.get("citation_report") if isinstance(md, dict) else None

    def trace_scores(self, trace: dict) -> dict:
        """trace scores 兜底：list 响应可能为字符串列表，改拉详情取标准对象。"""
        scores = trace.get("scores") or []
        if all(isinstance(s, dict) for s in scores):
            return {s.get("name"): s.get("value") for s in scores}  # type: ignore[union-attr]
        r = requests.get(
            f"{self.host}/api/public/traces/{trace.get('id')}", auth=self.auth, timeout=30
        )
        r.raise_for_status()
        detail = r.json()
        return {
            s.get("name"): s.get("value")
            for s in (detail.get("scores") or [])
            if isinstance(s, dict)
        }


def start_analysis(stock_code: str, stock_name: str) -> str:
    """fast-path 触发：POST /api/analyze，解析 SSE 中 session_created 的 session_id。"""
    payload = {"query": f"深度分析{stock_name}", "stock_code": stock_code, "stock_name": stock_name}
    with requests.post(
        f"{API_BASE}/api/analyze",
        json=payload,
        stream=True,
        timeout=(10, 30),
    ) as resp:
        resp.raise_for_status()
        session_id = ""
        deadline = time.time() + 20
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            try:
                ev = json.loads(raw[len("data:") :])
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


def wait_terminal(session_id: str, stock_name: str, interval: float = 12.0) -> dict:
    start = time.time()
    while True:
        r = requests.get(f"{API_BASE}/api/sessions/{session_id}", timeout=15)
        r.raise_for_status()
        s = r.json()
        status = s.get("status") or ""
        if status in TERMINAL_STATUS:
            return {
                "session_id": session_id,
                "stock_name": stock_name,
                "status": status,
                "duration_s": round(time.time() - start, 1),
            }
        time.sleep(interval)


def _check_technical(results: list[dict]) -> dict:
    """技术类 claim：负索引语义且解析成功（status != FAIL）。"""
    tech = [
        r
        for r in results
        if str((r.get("claim") or {}).get("field_ref") or "").startswith("technical_indicators")
    ]
    if not tech:
        return {"n": 0, "all_negative_index": True, "failed": 0, "note": "无技术类 claim"}
    all_neg = all(
        "-" in str((r.get("claim") or {}).get("field_ref") or "").split(".")[-1]
        or any(
            p.startswith("-") for p in str((r.get("claim") or {}).get("field_ref") or "").split(".")
        )
        for r in tech
    )
    failed = sum(1 for r in tech if r.get("status") == "FAIL")
    return {"n": len(tech), "all_negative_index": all_neg, "failed": failed}


def _check_fundamental(results: list[dict]) -> dict:
    """基本面类 claim：field_ref 根键不得含中文字符（修 B 后 state 键为英文）。"""
    bad: list[str] = []
    n = 0
    for r in results:
        ref = str((r.get("claim") or {}).get("field_ref") or "")
        root = ref.split(".")[0].split("[")[0]
        if not root:
            continue
        n += 1
        if any("\u4e00" <= ch <= "\u9fff" for ch in root):
            bad.append(ref)
    return {"n": n, "chinese_root_count": len(bad), "chinese_roots": bad[:10]}


def _check_billion_scale(results: list[dict]) -> dict:
    """亿级数值 claim（|gt| >= 1e8）：不得因绝对容差 FAIL（相对 0.5% 语义下应 PASS）。"""
    big = [
        r
        for r in results
        if isinstance(r.get("ground_truth"), (int, float)) and abs(float(r["ground_truth"])) >= 1e8
    ]
    failed = [r for r in big if r.get("status") == "FAIL"]
    return {
        "n": len(big),
        "failed": len(failed),
        "fail_details": [
            {
                "field_ref": (r.get("claim") or {}).get("field_ref"),
                "stated": (r.get("claim") or {}).get("stated_value"),
                "gt": r.get("ground_truth"),
                "delta": r.get("delta"),
            }
            for r in failed[:5]
        ],
    }


def _summary(report: dict) -> dict:
    total = report.get("total", 0)
    failed = report.get("failed", 0)
    return {
        "total": total,
        "passed": report.get("passed"),
        "failed": failed,
        "unverifiable": report.get("unverifiable"),
        "fail_rate": round(failed / total, 4) if total else 0.0,
        "acceptance": {
            "fail_rate_lt_10pct": (failed / total < 0.10) if total else False,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="契约修复冒烟验证驱动")
    ap.add_argument("--codes", required=True, help="逗号分隔股票代码")
    ap.add_argument("--names", required=True, help="逗号分隔股票名称（与 codes 一一对应）")
    ap.add_argument("--out", default="reports/citation_smoke_verify.json")
    ap.add_argument(
        "--collect-only",
        action="store_true",
        help="仅取证：跳过触发，从 <out>.runs.json 读取已启动的 runs",
    )
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if len(codes) != len(names):
        print("codes 与 names 数量不一致", file=sys.stderr)
        return 2

    lf = LangfuseClient()
    runs_file = Path(args.out).with_suffix(".runs.json")
    started: list[dict]
    if args.collect_only:
        started = json.loads(runs_file.read_text(encoding="utf-8"))
        print(f"[{_now_iso()}] collect-only：读取 {len(started)} 个已触发 run")
        trigger_ts = _now_iso()
    else:
        trigger_ts = _now_iso()
        started = []
        for code, name in zip(codes, names, strict=True):
            print(f"[{_now_iso()}] 触发 {name}({code}) 深度分析…")
            sid = start_analysis(code, name)
            started.append({"session_id": sid, "stock_code": code, "stock_name": name})
            time.sleep(5)  # 错峰启动，降低并发负载峰值
        runs_file.write_text(json.dumps(started, ensure_ascii=False), encoding="utf-8")
        print(f"runs 已暂存 {runs_file}（collect-only 可复用）")

    verdicts = []
    for item in started:
        term = wait_terminal(item["session_id"], item["stock_name"])
        print(f"[{_now_iso()}] {item['stock_name']} 终态: {term['status']} ({term['duration_s']}s)")
        verdict: dict[str, Any] = {"run": item, "terminal": term}
        if term["status"] == "completed":
            trace = lf.find_deep_trace(
                item["stock_name"], after=None if args.collect_only else trigger_ts
            )
            if trace is None:
                verdict["evidence"] = {"error": "Langfuse 未找到对应 trace"}
            else:
                report = lf.trace_report(trace)
                scores = lf.trace_scores(trace)
                if report:
                    verdict["evidence"] = {
                        "trace_id": trace.get("id"),
                        "trace_timestamp": trace.get("timestamp"),
                        "input": trace.get("input"),
                        "scores": scores,
                        "summary": _summary(report),
                        "technical": _check_technical(report.get("results") or []),
                        "fundamental": _check_fundamental(report.get("results") or []),
                        "billion_scale": _check_billion_scale(report.get("results") or []),
                    }
                else:
                    verdict["evidence"] = {
                        "error": "trace 无 citation_report",
                        "trace_id": trace.get("id"),
                    }
        verdicts.append(verdict)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": _now_iso(), "runs": verdicts}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"验证产物已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
