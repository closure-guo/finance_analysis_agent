"""1.6 最终冒烟：#109 修复后，1 标的 × analysts × glm-5.3，捕获 v3 覆盖率终版。

包 citation_node.compute_coverage 捕获 CoverageReport（coverage/unmatched/event_covered），
与 v1 基线（002412 首跑 0.6957）对比，验证 #109 修复后报告完整 + v3 规则生效。

用法：
    uv run python tests/scripts/smoke_v3_final.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests" / "scripts"))

import backtest_pilot_2023 as pilot_util  # noqa: E402

TICKER = "002412"
QUERY = "综合评估投资价值"
V1_BASELINE = 0.6957


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()

    import evals.ablation as ablation

    import finance_agent.nodes.citation_node as cn

    captured: dict = {}
    original_compute = cn.compute_coverage

    def wrapped(markdown, stated, event_values=None):
        rep = original_compute(markdown, stated, event_values)
        captured["coverage_report"] = rep
        captured["markdown_len"] = len(markdown)
        return rep

    cn.compute_coverage = wrapped

    print(f"1.6 最终冒烟: {TICKER} × analysts × glm-5.3", flush=True)
    snapshot = ablation.build_snapshot(TICKER)
    out = ablation.run_variant_once("analysts", snapshot, QUERY)
    print(f"citation_pass={out['citation_pass']}", flush=True)

    rep = captured.get("coverage_report")
    print("\n=== v3 覆盖率终版（#109 修复后） ===")
    print(f"报告 markdown 总长: {captured.get('markdown_len')} 字符")
    print(f"coverage={rep.coverage:.4f} (v1 基线 {V1_BASELINE})")
    print(f"total={rep.total} matched={rep.matched} unmatched={len(rep.unmatched)}")
    print(f"event_covered={rep.event_covered}")
    print(f"unmatched: {rep.unmatched}")
    print(f"delta vs v1: {rep.coverage - V1_BASELINE:+.4f}")

    import json

    out_path = Path("reports/backtest/smoke-v3-final.json")
    out_path.write_text(
        json.dumps(
            {
                "coverage": rep.coverage,
                "total": rep.total,
                "matched": rep.matched,
                "unmatched": rep.unmatched,
                "event_covered": rep.event_covered,
                "markdown_len": captured.get("markdown_len"),
                "v1_baseline": V1_BASELINE,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n结果已存 {out_path}")


if __name__ == "__main__":
    main()
