"""1.6：v3 端到端冒烟覆盖率实证（refine-citation-coverage-v3 验收）。

跑 1 标的 × analysts 变体 × glm-5.3，捕获 verify_citations 的 coverage 输出：
- 新普查（D1 四规则 + D2/D4 补登记 + D5 event_covered）下的 coverage/unmatched；
- 与 v1 基线（002412 首跑 coverage 0.6957）对比，验证 unmatched 收敛。

用法：
    uv run python tests/scripts/smoke_v3_coverage.py
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
V1_BASELINE_COVERAGE = 0.6957  # 汉森制药首跑（验证报告 2026-09-01）


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()  # 分析 glm-5.3（与消融一致）

    import evals.ablation as ablation

    captured: dict = {}
    original_verify = ablation.verify_citations

    def wrapped(state: dict) -> dict:
        out = original_verify(state)
        captured["coverage"] = out.get("citation_coverage")
        captured["report_markdown_logged"] = "report_markdown" in out
        return out

    ablation.verify_citations = wrapped

    print(f"1.6 冒烟: {TICKER} × analysts × glm-5.3", flush=True)
    snapshot = ablation.build_snapshot(TICKER)
    out = ablation.run_variant_once("analysts", snapshot, QUERY)
    print(f"citation_pass={out['citation_pass']}", flush=True)

    cov = captured.get("coverage")
    print("\n=== v3 coverage 实证 ===")
    print(f"coverage={cov.coverage if cov else None} (v1 基线 {V1_BASELINE_COVERAGE})")
    print(f"total={cov.total} matched={cov.matched} unmatched={len(cov.unmatched)}")
    print(f"event_covered={cov.event_covered}")
    print(f"unmatched: {cov.unmatched}")
    print(f"report_markdown 落库: {captured.get('report_markdown_logged')}")


if __name__ == "__main__":
    main()
