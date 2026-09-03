"""judge 跨模型一致性抽查（人工盲评的降级方案：独立模型重标 + 分歧人工裁）。

同 judge 的完整输入（rubric+报告，来自 judge trace），换 glm-5.3 独立打分，
与 judge（deepseek-v4-flash）分数对比：完全一致率 / ±1 一致率 / 分歧清单。
诚实披露：测的是跨模型一致率，非与人类一致；分歧条目需人工裁定。

用法：
    uv run python tests/scripts/judge_cross_model.py
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

MATERIAL = Path(r"D:/WorkSpace/finance_analysis_agent/reports/judge_consistency_material.json")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()  # 分析 glm-5.3（独立于 judge 的 deepseek-v4-flash）

    from finance_agent.llm.gateway import complete_text

    data = json.loads(MATERIAL.read_text(encoding="utf-8"))
    items = data["items"]
    print(f"跨模型重标: {len(items)} 条 × glm-5.3（judge=deepseek-v4-flash）", flush=True)

    results = []
    for i, it in enumerate(items):
        prompt = it["report"]  # judge 当时的完整输入（rubric+报告）
        ask = (
            prompt + "\n\n【独立复评】请按上述同一评审标准独立打 1-5 分。"
            '只输出 JSON: {"score": <1-5>, "reason": "<一句话>"}'
        )
        try:
            answer, _meta = complete_text([{"role": "user", "content": ask}], purpose="deep")
            m = re.search(r'"score"\s*:\s*(\d+)', str(answer))
            score = int(m.group(1)) if m else None
        except Exception as e:  # noqa: BLE001
            score = None
            answer = f"ERROR: {e}"
        results.append(
            {
                "idx": i,
                "dim": it["dim"],
                "judge_score": it["judge_score"],
                "cross_score": score,
                "judge_reason": it.get("judge_reason", ""),
                "cross_answer": str(answer)[:150],
            }
        )
        print(f"  [{i}] dim={it['dim']} judge={it['judge_score']} cross={score}", flush=True)

    # 一致率
    valid = [r for r in results if r["judge_score"] is not None and r["cross_score"] is not None]
    exact = sum(1 for r in valid if r["judge_score"] == r["cross_score"])
    within1 = sum(1 for r in valid if abs(r["judge_score"] - r["cross_score"]) <= 1)
    diffs = [r for r in valid if r["judge_score"] != r["cross_score"]]
    print("\n=== 跨模型一致率（glm-5.3 vs deepseek-v4-flash judge） ===")
    print(f"有效对 {len(valid)}/{len(results)}（judge 分 None 的剔除）")
    print(f"完全一致: {exact}/{len(valid)} = {exact / len(valid):.0%}")
    print(f"±1 内一致: {within1}/{len(valid)} = {within1 / len(valid):.0%}")
    print(f"\n分歧条目（待人工裁定）: {len(diffs)}")
    for r in diffs:
        print(
            f"  [{r['idx']}] {r['dim']}: judge={r['judge_score']} cross={r['cross_score']} | judge说: {r['judge_reason'][:60]}"
        )

    out = Path(r"D:/WorkSpace/finance_analysis_agent/reports/judge_cross_model.json")
    out.write_text(
        json.dumps(
            {"summary": {"n": len(valid), "exact": exact, "within1": within1}, "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n结果已存 {out}")


if __name__ == "__main__":
    main()
