#!/usr/bin/env python
"""citation_coverage 人工抽查材料生成（harden-citation-semantic-coverage tasks.md 遗留项）。

对一次冒烟的 trace，把普查未认领（unmatched）数字逐条列出并对照全部 claim 的
stated_value 做归因分类，产出人工抽查表（CSV + Markdown），供人工确认普查口径：

分类口径（机器预判，人工终裁）：
- sign_mismatch：量纲匹配但符号相反（如正文「下滑53.78%」vs stated -53.78）——口径待裁
- scale_miss：数值按 {1,100,0.01,1e4,1e8} 缩放均认不上，但存在同指标 claim——疑似真实逃逸
- no_related_claim：无任何相关 claim——真实逃逸（普查设计目标）
- rounded：四舍五入/约数差异（如 1169元 vs 1168.5）——口径可接受

用法:
    uv run python tests/scripts/coverage_spotcheck_material.py <trace_id> [<trace_id>...]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from finance_agent.citation import value_close  # noqa: E402
from finance_agent.citation_coverage import _CLAIM_SCALES  # noqa: E402

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
AUTH = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])


def fetch(trace_id: str) -> dict:
    r = requests.get(f"{LANGFUSE_HOST}/api/public/traces/{trace_id}", auth=AUTH, timeout=30)
    r.raise_for_status()
    return r.json()


def classify(raw: str, value: float, stated: list[float]) -> str:
    for sv in stated:
        for scale in _CLAIM_SCALES:
            if value_close(abs(value), abs(sv) * scale) and (value < 0) != (sv * scale < 0):
                return "sign_mismatch"
            if value_close(value, sv * scale):
                return "matched_late"  # 不应出现（普查应已认领），出现即 bug 线索
    for sv in stated:
        for scale in _CLAIM_SCALES:
            target = sv * scale
            if target and abs(abs(value) - abs(target)) / max(abs(target), 1e-9) < 0.02:
                return "rounded"
    return "no_related_claim" if not stated else "scale_miss"


def main() -> int:
    rows: list[dict] = []
    for tid in sys.argv[1:]:
        d = fetch(tid)
        name = d.get("name") or tid
        rep = ((d.get("metadata") or {}).get("citation_report")) or {}
        stated = [
            float((r.get("claim") or {}).get("stated_value"))
            for r in rep.get("results") or []
            if isinstance((r.get("claim") or {}).get("stated_value"), (int, float))
        ]
        cov_scores = [
            s
            for s in d.get("scores") or []
            if isinstance(s, dict) and s.get("name") == "citation_coverage"
        ]
        # 重试会二次上报 coverage：只取时间戳最新（最终态），避免把重试前
        # 的 unmatched 与重试后的 citation_report 混读（matched_late 伪影）
        cov_scores.sort(key=lambda s: s.get("timestamp") or "")
        for s in cov_scores[-1:]:
            unmatched = (s.get("metadata") or {}).get("unmatched") or []
            print(
                f"== {name}: coverage={s.get('value')} unmatched={len(unmatched)} stated_n={len(stated)}"
            )
            for raw in unmatched:
                # raw 形如 "78.3%" / "-3.7个百分点" / "5.8亿" / "1.13倍"
                num = float("".join(ch for ch in raw if ch.isdigit() or ch in ".-"))
                unit_scale = 1.0
                if "亿" in raw:
                    unit_scale = 1e8
                elif "万" in raw:
                    unit_scale = 1e4
                value = num * unit_scale
                cat = classify(raw, value, stated)
                rows.append({"trace": name, "raw": raw, "value": value, "category": cat})
                print(f"  {raw:>12} → {cat}")
    out = ROOT / "reports" / "coverage_spotcheck.csv"
    import csv

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["trace", "raw", "value", "category", "human_verdict"])
        w.writeheader()
        for row in rows:
            w.writerow({**row, "human_verdict": ""})
    print(f"\n抽查表已写入 {out}（human_verdict 列留空待人工填写）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
