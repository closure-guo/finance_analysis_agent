"""B1 全量补判（2026-09-20 跑批；对齐旧批 196 行全量判定口径）。

analysis 腿默认 B1_PER_TICKER=4（每标的 4 行闸门）→ 80 行；旧批终读是全量判定，
观测重跑须同口径。本脚本绕过闸门补判剩余行，缓存追加同一文件（按 unit_id 幂等）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

from evals.causal_ablation import family_b_judge as fj  # noqa: E402
from evals.causal_ablation import family_b_materials as fb  # noqa: E402
from evals.causal_ablation import family_b_text as ft  # noqa: E402

MATERIALS = _ROOT / "reports/ablation/p2/materials-20260920"
CACHE = _ROOT / "reports/ablation/p2/out-20260920/judged-b1.jsonl"


def main() -> int:
    load_dotenv()
    done: set[str] = set()
    if CACHE.exists():
        done = {
            str(json.loads(x).get("unit_id"))
            for x in CACHE.read_text(encoding="utf-8").splitlines()
            if x.strip()
        }
    states = {}
    for p in sorted(MATERIALS.glob("*.full.pkl")):
        t = p.name.split(".")[0]
        states[t] = fb.load_material(MATERIALS, t)["state"]
    b1_rows = ft.judge_material_rows(
        [{"ticker": t, "_state": states[t], "b1": ft.b1_unit(states[t])} for t in states]
    )
    refs = {t: ft.analyst_reference_points(states[t]) for t in states}
    for row in b1_rows:
        row["reference_points"] = refs[str(row.get("ticker") or "")]
    todo = [r for r in b1_rows if str(r.get("unit_id")) not in done]
    print(f"[b1-backfill] 全量 {len(b1_rows)}｜已判 {len(done)}｜待判 {len(todo)}", flush=True)
    if not todo:
        return 0
    fresh = fj.run_b1_judgments(todo, per_ticker=10_000)  # 闸门放开（全量口径）
    with CACHE.open("a", encoding="utf-8") as fh:
        for r in fresh:
            fh.write(json.dumps(r, ensure_ascii=False) + chr(10))
    print(f"[b1-backfill] 新判 {len(fresh)} 行 → {CACHE}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
