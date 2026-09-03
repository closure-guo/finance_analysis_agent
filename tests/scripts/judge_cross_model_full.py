"""judge 跨模型一致性（全文版）：完整 judge 输入 → glm-5.3 独立重标。

与首版（2500 字符截断输入）的区别：消除截断伪影，得到干净的校准数字。
"""

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

MATERIAL = Path(r"D:/WorkSpace/finance_analysis_agent/reports/judge_consistency_material_full.json")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()

    from finance_agent.llm.gateway import complete_text

    items = json.loads(MATERIAL.read_text(encoding="utf-8"))["items"]
    print(f"全文跨模型重标: {len(items)} 条 × glm-5.3", flush=True)
    results = []
    for i, it in enumerate(items):
        ask = (
            it["report"]
            + '\n\n【独立复评】请按上述同一评审标准独立打 1-5 分。只输出 JSON: {"score": <1-5>, "reason": "<一句话>"}'
        )
        try:
            answer, _ = complete_text([{"role": "user", "content": ask}], purpose="deep")
            m = re.search(r'"score"\s*:\s*(\d+)', str(answer))
            score = int(m.group(1)) if m else None
            mr = re.search(r'"reason"\s*:\s*"(.+?)"', str(answer), re.S)
            reason = mr.group(1) if mr else ""
        except Exception as e:  # noqa: BLE001
            score, answer, reason = None, f"ERROR: {e}", ""
        results.append(
            {
                "idx": i,
                "dim": it["dim"],
                "judge_score": it["judge_score"],
                "cross_score": score,
                "judge_reason": it.get("judge_reason", ""),
                "cross_reason": reason[:80],
            }
        )
        print(f"  [{i}] {it['dim']}: judge={it['judge_score']} cross={score}", flush=True)

    valid = [r for r in results if r["judge_score"] is not None and r["cross_score"] is not None]
    exact = sum(1 for r in valid if r["judge_score"] == r["cross_score"])
    within1 = sum(1 for r in valid if abs(r["judge_score"] - r["cross_score"]) <= 1)
    diffs = [r for r in valid if r["judge_score"] != r["cross_score"]]
    big = [r for r in valid if abs(r["judge_score"] - r["cross_score"]) >= 2]
    print("\n=== 全文版跨模型一致率 ===")
    print(f"有效对 {len(valid)}/{len(results)}")
    print(f"完全一致: {exact}/{len(valid)} = {exact / len(valid):.0%}")
    print(f"±1 内一致: {within1}/{len(valid)} = {within1 / len(valid):.0%}")
    print(f"≥2 分大分歧: {len(big)} → {[r['idx'] for r in big]}")
    out = Path(r"D:/WorkSpace/finance_analysis_agent/reports/judge_cross_model_full.json")
    out.write_text(
        json.dumps(
            {"summary": {"n": len(valid), "exact": exact, "within1": within1}, "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"结果 → {out}")


if __name__ == "__main__":
    main()
