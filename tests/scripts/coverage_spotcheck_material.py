#!/usr/bin/env python
"""citation_coverage 人工抽查材料生成（harden-citation-semantic-coverage tasks.md 遗留项）。

对一次冒烟的 trace，把普查未认领（unmatched）数字逐条列出，并带：
- 出处原句（在观测消息中检索 raw 的上下文窗口）；
- trace_id / 标的名（可回溯证据）；
- 最近 claim（field_ref / stated_value / 偏差百分比），解释"为什么对不上"；
- 机制分类（2026-09-02 版，替代原 scale_miss/sign_mismatch/rounded 粗分类）。

机制分类（机器预判，人工终裁 human_verdict 列）：
- sign_mismatch        量纲匹配但符号相反（正文「下滑10.05%」vs stated -10.05）→ 建议 accept
- rounded              同一指标约数差（0.5%~2% 内）→ 建议 accept
- comparison_unclaimed 该数值出现在某 claim 的解释文本里（比较值被引用但未建档）→ 建议 reject
- value_mismatch       存在相近量级 claim 但值差 >2%（如 1400亿 vs 1720.5亿）→ 待裁/疑似错误
- commentary_no_claim  无任何相近 claim（历史股价/叙述占比/幅度）→ 覆盖纪律待裁

用法:
    uv run python tests/scripts/coverage_spotcheck_material.py <trace_id> [<trace_id>...] [--out PATH]
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402


def _find_env() -> Path:
    """向上搜索最近 .env（worktree 嵌套在 .worktrees/ 下，主仓库 .env 在上上级）。"""
    for p in Path(__file__).resolve().parents:
        cand = p / ".env"
        if cand.exists():
            return cand
    return Path(".env")


load_dotenv(_find_env())

import requests  # noqa: E402

from finance_agent.citation import value_close  # noqa: E402
from finance_agent.citation_coverage import _CLAIM_SCALES  # noqa: E402

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
AUTH = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])


def fetch(trace_id: str) -> dict:
    r = requests.get(f"{LANGFUSE_HOST}/api/public/traces/{trace_id}", auth=AUTH, timeout=30)
    r.raise_for_status()
    return r.json()


def _walk_strings(node, out: list):
    """递归收集所有 >200 字符且含 %/亿/万/元的字符串（观测消息正文等）。"""
    if isinstance(node, dict):
        for v in node.values():
            _walk_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_strings(v, out)
    elif isinstance(node, str) and len(node) > 200 and re.search(r"[%％亿万元倍xX]", node):
        out.append(node)


def find_context(texts: list[str], raw: str) -> str | None:
    """在文本块中找 raw 出现位置，返回前后各 55 字符窗口。

    先按原样匹配；失败则退化到「数字 + 可选空格 + 单位」宽容匹配
    （正文可能在数字与单位间有空格，如 "75.85 %"）。
    """
    patterns = [re.escape(raw)]
    m_unit = re.match(r"^(?P<num>-?\d+(?:\.\d+)?)\s*(?P<unit>.+)$", raw)
    if m_unit:
        patterns.append(re.escape(m_unit.group("num")) + r"\s*" + re.escape(m_unit.group("unit")))
    for txt in texts:
        for pat in patterns:
            m = re.search(pat, txt)
            if m:
                s = max(0, m.start() - 55)
                e = min(len(txt), m.end() + 55)
                return txt[s:e].replace("\n", " ")
    return None


def _parse_raw(raw: str) -> float:
    num = float("".join(ch for ch in raw if ch.isdigit() or ch in ".-"))
    scale = 1e8 if "亿" in raw else 1e4 if "万" in raw else 1.0
    return num * scale


def classify_v2(raw: str, value: float, claims: list[dict], texts: list[str]) -> str:
    """机制分类（见模块 docstring）。"""
    stated = [
        float(c["stated_value"]) for c in claims if isinstance(c.get("stated_value"), (int, float))
    ]

    # 1) 符号相反
    for sv in stated:
        for sc in _CLAIM_SCALES:
            t = sv * sc
            if t and value_close(abs(value), abs(t)) and (value < 0) != (t < 0):
                return "sign_mismatch"
    # 2) 约数（0.5%~2% 内、但 value_close 未命中）
    for sv in stated:
        for sc in _CLAIM_SCALES:
            t = sv * sc
            if (
                t
                and abs(abs(value) - abs(t)) / max(abs(t), 1e-9) < 0.02
                and not value_close(value, t)
            ):
                return "rounded"
    # 3) 比较值被 claim 解释引用（如「较2024年21.93%下滑」）
    interps = " ".join(str(c.get("interpretation") or "") for c in claims)
    if raw in interps or raw.replace(" ", "") in interps.replace(" ", ""):
        return "comparison_unclaimed"
    # 4) 存在相近量级 claim（值差 >2%，如 1400亿 vs 1720.5亿）
    for sv in stated:
        for sc in _CLAIM_SCALES:
            t = sv * sc
            if t and abs(abs(value) - abs(t)) / max(abs(t), 1e-9) < 0.25:
                return "value_mismatch"
    # 5) 无任何相近 claim
    return "commentary_no_claim"


def nearest_claims(value: float, claims: list[dict], n: int = 1) -> list[dict]:
    scored = []
    for c in claims:
        sv = c.get("stated_value")
        if not isinstance(sv, (int, float)):
            continue
        for sc in _CLAIM_SCALES:
            t = sv * sc
            if not t:
                continue
            dev = abs(abs(value) - abs(t)) / max(abs(t), 1e-9)
            scored.append((dev, sc, c))
    scored.sort(key=lambda x: x[0])
    out = []
    for dev, sc, c in scored[:n]:
        out.append(
            {
                "field_ref": c.get("field_ref"),
                "stated": c.get("stated_value"),
                "scale": sc,
                "dev_pct": round(dev * 100, 1),
                "interp": str(c.get("interpretation"))[:48],
            }
        )
    return out


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("trace_ids", nargs="+", help="Langfuse trace_id 列表")
    parser.add_argument(
        "--out", default=None, help="CSV 输出路径（默认 reports/coverage_spotcheck.csv）"
    )
    opts = parser.parse_args()
    out_path = Path(opts.out) if opts.out else None
    rows: list[dict] = []
    for tid in opts.trace_ids:
        d = fetch(tid)
        name = d.get("name") or tid
        rep = ((d.get("metadata") or {}).get("citation_report")) or {}
        claims = [(r.get("claim") or {}) for r in (rep.get("results") or [])]
        texts: list[str] = []
        _walk_strings(d, texts)
        cov_scores = [
            s
            for s in d.get("scores") or []
            if isinstance(s, dict) and s.get("name") == "citation_coverage"
        ]
        cov_scores.sort(key=lambda s: s.get("timestamp") or "")
        for s in cov_scores[-1:]:
            unmatched = (s.get("metadata") or {}).get("unmatched") or []
            print(f"== {name} trace={tid}: coverage={s.get('value')} unmatched={len(unmatched)}")
            for raw in unmatched:
                value = _parse_raw(raw)
                cat = classify_v2(raw, value, claims, texts)
                ctx = find_context(texts, raw)
                near = nearest_claims(value, claims)
                rows.append(
                    {
                        "trace_id": tid,
                        "trace": name,
                        "raw": raw,
                        "value": value,
                        "category": cat,
                        "source_sentence": ctx or "",
                        "nearest_claim": (near[0]["field_ref"] if near else ""),
                        "nearest_stated": (near[0]["stated"] if near else ""),
                        "dev_pct": (near[0]["dev_pct"] if near else ""),
                        "nearest_interp": (near[0]["interp"] if near else ""),
                        "human_verdict": "",
                    }
                )
                print(f"  {raw:>12} → {cat}  nearest={near[0]['field_ref'] if near else '-'}")
    if not rows:
        print("无数据", file=sys.stderr)
        return 1
    out = out_path or (ROOT / "reports" / "coverage_spotcheck.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "trace_id",
                "trace",
                "raw",
                "value",
                "category",
                "source_sentence",
                "nearest_claim",
                "nearest_stated",
                "dev_pct",
                "nearest_interp",
                "human_verdict",
            ],
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"\n抽查表已写入 {out}（{len(rows)} 行，human_verdict 列留空待人工填写）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
