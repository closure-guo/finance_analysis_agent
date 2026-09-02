"""1.6 离线版：从冒烟 run 的 analyst trace 抽 markdown+claims，重建 state，
确定性跑 verify_citations → v3 coverage 证据（零 LLM）。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests" / "scripts"))

import backtest_pilot_2023 as pilot_util  # noqa: E402

TID = {
    "fundamental": "4d304d04cac6",
    "macro": "eddb5f2f4ecb",
    "technical": "db4c03414cee",
    "sentiment": "ef2d6e25c420",
}
V1_BASELINE = 0.6957


def fetch(tid: str) -> dict:
    import os

    import requests
    from dotenv import load_dotenv

    load_dotenv(_ROOT.parent / ".env")
    host = "http://localhost:3000"
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    # id 前缀 → 全 id：先搜最近 traces
    r = requests.get(
        f"{host}/api/public/traces", auth=auth, params={"limit": 100, "page": 1}, timeout=30
    )
    for t in r.json().get("data") or []:
        if (t.get("id") or "").startswith(tid):
            full = requests.get(f"{host}/api/public/traces/{t['id']}", auth=auth, timeout=30).json()
            return full
    raise SystemExit(f"trace {tid} not found")


def extract(answer: str) -> tuple[str, list]:
    txt = re.sub(r"^```(json)?\s*|\s*```$", "", answer.strip())
    try:
        d = json.loads(txt, strict=False)  # strict=False：允许字符串内控制字符
        return d.get("markdown") or "", d.get("claims") or []
    except json.JSONDecodeError:
        return "", []


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()

    import evals.ablation as ablation

    from finance_agent.nodes.citation_node import verify_citations

    reports: dict[str, dict] = {}
    for agent, tid in TID.items():
        d = fetch(tid)
        for o in d.get("observations") or []:
            ans = ((o.get("output") or {}).get("answer")) or ""
            if ans:
                md, claims = extract(ans)
                reports[agent] = {
                    "agent_name": agent,
                    "summary": "",
                    "markdown": md,
                    "claims": claims,
                }
                print(f"{agent}: markdown {len(md)} 字, claims {len(claims)}")
                break

    snapshot = ablation.build_snapshot("002412")
    state = {**snapshot, "analyst_reports": reports}
    out = verify_citations(state)

    cov = out.get("citation_coverage")
    rep = out.get("citation_report") or {}
    results = rep.get("results") or []
    from collections import Counter

    fails = Counter(
        (r.get("bucket") or r.get("status")) for r in results if r.get("status") == "FAIL"
    )
    print("\n=== 1.6 v3 端到端（离线重算） ===")
    print(f"coverage={cov} (v1 基线 {V1_BASELINE})")
    print(f"citation_pass={out.get('citation_pass')} FAIL={dict(fails)}")
    md = "\n\n".join(r.get("markdown") or "" for r in reports.values())
    stated = [
        float((r.get("claim") or {}).get("stated_value"))
        for r in results
        if isinstance((r.get("claim") or {}).get("stated_value"), (int, float))
    ]
    from finance_agent.citation_coverage import compute_coverage

    covrep = compute_coverage(md, stated)
    print(f"total={covrep.total} matched={covrep.matched} unmatched={len(covrep.unmatched)}")
    print(f"event_covered={covrep.event_covered}")
    print(f"unmatched: {covrep.unmatched}")


if __name__ == "__main__":
    main()
