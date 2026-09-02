"""issue #105 归因：citation_pass 偏低是校验器误杀还是 LLM 真错？

最小归因实验：1 标的（002412）× analysts 变体 × 1 次，glm-5.3（与消融同模型）。
包一层 verify_citations 捕获 citation_report 的逐 claim status + bucket，输出：
- FAIL 桶分布（value_mismatch / path_unresolvable / semantic_* / internal_inconsistency）
- 每个 FAIL 的 field_ref / stated / ground_truth / delta / interp（前若干条）

结论判定：
- FAIL 集中在 value_mismatch 且 delta 明显 → LLM 真错（数据引用错）
- FAIL 集中在 path_unresolvable / semantic_* 且 ground_truth 可得 → 校验器契约摩擦
- FAIL 集中 semantic_term 且 ground_truth 为 None → 词表外/契约病（类 D5 降级未覆盖）

用法：
    uv run python tests/scripts/attribution_105.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests" / "scripts"))

import backtest_pilot_2023 as pilot_util  # noqa: E402

TICKER = "002412"
QUERY = "综合评估投资价值"


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()  # 分析 glm-5.3（与消融一致）

    import evals.ablation as ablation

    captured: list[dict] = []
    original_verify = ablation.verify_citations

    def wrapped(state: dict) -> dict:
        out = original_verify(state)
        rep = out.get("citation_report")
        results = rep.results if hasattr(rep, "results") else (rep or {}).get("results", [])
        for r in results:
            claim = r.claim if hasattr(r, "claim") else (r or {}).get("claim", {})
            captured.append(
                {
                    "status": getattr(r, "status", None)
                    if hasattr(r, "status")
                    else (r or {}).get("status"),
                    "bucket": getattr(r, "bucket", None)
                    if hasattr(r, "bucket")
                    else (r or {}).get("bucket"),
                    "field_ref": getattr(claim, "field_ref", None)
                    if hasattr(claim, "field_ref")
                    else claim.get("field_ref"),
                    "claim_type": getattr(claim, "claim_type", None)
                    if hasattr(claim, "claim_type")
                    else claim.get("claim_type"),
                    "stated": getattr(claim, "stated_value", None)
                    if hasattr(claim, "stated_value")
                    else claim.get("stated_value"),
                    "ground_truth": getattr(r, "ground_truth", None)
                    if hasattr(r, "ground_truth")
                    else (r or {}).get("ground_truth"),
                    "delta": getattr(r, "delta", None)
                    if hasattr(r, "delta")
                    else (r or {}).get("delta"),
                    "interp": str(
                        getattr(claim, "interpretation", "")
                        if hasattr(claim, "interpretation")
                        else (claim or {}).get("interpretation", "")
                    )[:60],
                }
            )
        return out

    ablation.verify_citations = wrapped

    print(f"归因实验: {TICKER} × analysts × glm-5.3", flush=True)
    snapshot = ablation.build_snapshot(TICKER)
    out = ablation.run_variant_once("analysts", snapshot, QUERY)
    print(f"citation_pass={out['citation_pass']}", flush=True)

    fails = [c for c in captured if c["status"] == "FAIL"]
    unv = [c for c in captured if c["status"] == "UNVERIFIABLE"]
    total = len(captured)
    print(f"\n=== claims 总 {total}（FAIL {len(fails)} / UNVERIFIABLE {len(unv)}）===")
    print("FAIL 桶分布:", dict(Counter(c["bucket"] for c in fails)))
    print("FAIL claim_type:", dict(Counter(c["claim_type"] for c in fails)))
    print("\nFAIL 明细（前 12 条）:")
    for c in fails[:12]:
        print(
            f"  [{c['bucket']}] {c['claim_type']} {c['field_ref']} "
            f"stated={c['stated']} gt={c['ground_truth']} delta={c['delta']} "
            f"| {c['interp']}"
        )
    # 分类结论
    bucket_c = Counter(c["bucket"] for c in fails)
    n_value = bucket_c.get("value_mismatch", 0)
    n_path = bucket_c.get("path_unresolvable", 0)
    n_sem = sum(v for k, v in bucket_c.items() if str(k).startswith("semantic"))
    print("\n=== 归因初判 ===")
    print(
        f"value_mismatch={n_value}（LLM 真错面）/ path_unresolvable={n_path}（契约/路径面）/ semantic_*={n_sem}（术语/期次面）"
    )


if __name__ == "__main__":
    main()
