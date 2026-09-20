"""B1/B5c 下腿抽查工作表生成（采样协议 v2，2026-09-20）。

背景：
- B1 有条件转正（§19.2）的条件 = 下腿补独立抽查（owner 校准系预填照录，含机器-机器成分）
- B5c 过门（§19.11，5/5=1.00）provenance 注 = 随采样协议 v2 下腿补抽查

分层规则（§19.2 教训：自报把握零区分度 → 分层挂判定正例/票结构）：
- B5c 低把握 = 三票有分票；中把握 = AI 独立复核披露的换判合理对；高把握 = 一致票抽 10%
- B1 低把握 = 机器判「否」（未吸收，信息量高）全抽；高把握 = 机器判「是」抽 10%
- 均排除已校准行；seed 固定可复现

产物（人工列留空，owner 独立判读后再对照机器列）：
- tests/validation/2026-09-20-p2-calibration-b5c-lowerleg.csv
- tests/validation/2026-09-20-p2-calibration-b1-lowerleg.csv
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.causal_ablation import family_b_materials as fb  # noqa: E402

P2 = _ROOT / "reports/ablation/p2"
MATERIALS_DIR = P2 / "materials"
B5C_CACHE = P2 / "judged-b5-conclusion-v1.jsonl"
B1_FULL = P2 / "judged-b1.jsonl"
B1_CALIBRATED = P2 / "judged-b1-v2.jsonl"
B5C_CALIBRATED_CSV = _ROOT / "tests/validation/2026-09-19-p2-calibration-b5c.csv"
B5C_OUT = _ROOT / "tests/validation/2026-09-20-p2-calibration-b5c-lowerleg.csv"
B1_OUT = _ROOT / "tests/validation/2026-09-20-p2-calibration-b1-lowerleg.csv"
SEED = 20260920

ARM_DRAFT = "full_no_riskfm"
ARM_FINAL = "full"
# AI 独立复核（§19.11）披露的换判合理对：中把握层（601899 已在校准 5 行内，排除）
B5C_BORDERLINE = ("600276::b5c", "600036::b5c")


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _decision_block(report: str) -> str:
    m = re.search(r"(#+[^\n]*交易决策[^\n]*\n)(.*?)(?=\n#+ |\Z)", report, re.S)
    return m.group(2).strip() if m else ""


def export_b5c() -> int:
    rows = _load_jsonl(B5C_CACHE)
    by_id = {r["unit_id"]: r for r in rows}
    calibrated = set()
    with B5C_CALIBRATED_CSV.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r.get("人工判定(a/b/tie)", "").strip():
                calibrated.add(r["unit_id"])

    real = [r for r in rows if not r["unit_id"].endswith("::b5c-dark")]
    split = [r for r in real if len(set(r.get("votes") or [])) > 1]  # 低把握：分票
    borderline = [by_id[u] for u in B5C_BORDERLINE if u in by_id]
    picked_low = {r["unit_id"] for r in split} | {r["unit_id"] for r in borderline}
    high_pool = [
        r
        for r in real
        if len(set(r.get("votes") or [])) == 1
        and r["unit_id"] not in calibrated
        and r["unit_id"] not in picked_low
    ]
    rng = random.Random(SEED)  # noqa: S311 — 可复现抽样 fixture，非加密用途
    high_pick = rng.sample(sorted(high_pool, key=lambda r: r["unit_id"]), k=min(2, len(high_pool)))

    columns = (
        "unit_id",
        "ticker",
        "分层(低/中/高)",
        "三票",
        "机器判定(初稿a/风控终稿b/tie)",
        "决定性准则",
        "机器理由",
        "初稿指令",
        "风控终稿指令",
        "人工判定(a/b/tie)",
        "人工理由(可空)",
    )
    tier = {}
    for r in split:
        tier[r["unit_id"]] = "低（分票）"
    for r in borderline:
        tier.setdefault(r["unit_id"], "中（复核披露换判合理）")
    for r in high_pick:
        tier[r["unit_id"]] = f"高（一致票抽 10%，seed={SEED}）"

    with B5C_OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for uid in sorted(tier):
            r = by_id[uid]
            t = r["ticker"]
            draft = _decision_block(
                str(
                    fb.load_material(MATERIALS_DIR, t, ARM_DRAFT)["state"].get("final_report") or ""
                )
            )
            final = _decision_block(
                str(
                    fb.load_material(MATERIALS_DIR, t, ARM_FINAL)["state"].get("final_report") or ""
                )
            )
            writer.writerow(
                {
                    "unit_id": uid,
                    "ticker": t,
                    "分层(低/中/高)": tier[uid],
                    "三票": "/".join(r.get("votes") or []),
                    "机器判定(初稿a/风控终稿b/tie)": r.get("verdict"),
                    "决定性准则": "；".join(r.get("decisive_criteria") or []),
                    "机器理由": str(r.get("judge_reason") or "")[:800],
                    "初稿指令": draft[:1200],
                    "风控终稿指令": final[:1200],
                }
            )
    print(f"[b5c-lowerleg] {len(tier)} 行 → {B5C_OUT.name}")
    for uid in sorted(tier):
        print(f"  {tier[uid]}｜{uid}")
    return 0


def export_b1() -> int:
    full = _load_jsonl(B1_FULL)
    calibrated = {r["unit_id"] for r in _load_jsonl(B1_CALIBRATED)}
    rest = [r for r in full if r["unit_id"] not in calibrated]
    negatives = sorted(
        (r for r in rest if r["judge_label"] is False), key=lambda r: r["unit_id"]
    )  # 机器判否：正例层全抽
    positives = sorted((r for r in rest if r["judge_label"] is True), key=lambda r: r["unit_id"])
    rng = random.Random(SEED)  # noqa: S311 — 可复现抽样 fixture，非加密用途
    pos_pick = rng.sample(positives, k=max(1, round(len(positives) * 0.10)))

    columns = (
        "unit_id",
        "ticker",
        "风险点",
        "分层(低/高)",
        "决策动作",
        "决策理由",
        "证据引用",
        "FM裁决",
        "机器判定(被吸收?是/否)",
        "机器理由",
        "人工判定(被吸收?是/否)",
        "人工判定(是否新增?是/否)",
        "人工备注(可空)",
    )
    with B1_OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for r, tier_label in [
            *[(r, "低（机器判否·正例层全抽）") for r in negatives],
            *[(r, f"高（机器判是·抽 10%，seed={SEED}）") for r in pos_pick],
        ]:
            writer.writerow(
                {
                    "unit_id": r["unit_id"],
                    "ticker": r["ticker"],
                    "风险点": r.get("risk_point"),
                    "分层(低/高)": tier_label,
                    "决策动作": r.get("decision_action"),
                    "决策理由": str(r.get("decision_reasoning") or "")[:800],
                    "证据引用": str(r.get("evidence_refs") or "")[:400],
                    "FM裁决": str(r.get("fm_reasoning") or "")[:400],
                    "机器判定(被吸收?是/否)": "否" if r["judge_label"] is False else "是",
                    "机器理由": str(r.get("judge_reason") or "")[:600],
                }
            )
    print(
        f"[b1-lowerleg] 低把握 {len(negatives)} + 高把握 {len(pos_pick)} = {len(negatives) + len(pos_pick)} 行 → {B1_OUT.name}"
    )
    return 0


def main() -> int:
    export_b5c()
    export_b1()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
