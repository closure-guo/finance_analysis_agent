"""calibrate-fm-approval nightly @live：拉取真实 Langfuse 跑 FM 决策度量。

与 @live E2E 同纪律：需要 LANGFUSE_PUBLIC_KEY/SECRET，未配置时跳过；
nightly（pytest -m live）跑真实数据，防 stub 漂移。报告落 reports/。
"""

import os
from pathlib import Path

import pytest
from evals.fm_decision.measure import render_report, run_offline

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_langfuse() -> bool:
    # run.py 的 _load_env 会加载项目 .env；本地开发 key 常挂在 .env 而非 shell
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except Exception:  # noqa: BLE001, S110 - dotenv 缺失时跳过
        pass
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        pytest.skip("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未设置，跳过 @live 用例")
    return True


def test_fm_decision_live_report(live_langfuse: bool):
    from evals.fm_decision.run import fetch_fund_manager_traces

    traces = fetch_fund_manager_traces()
    assert traces, "Langfuse 应返回 fund_manager trace（空即异常）"

    result = run_offline(traces)
    agg, reason = result["aggregate"], result["reason_complete"]

    # 分布抽样参考（不设占比下限，取证为 approve ~53%/return ~30%/reject ~17%）
    total = agg["total"]
    assert total >= 10, "FM 决策样本应足够支撑分布统计"
    counts = agg["counts"]
    assert set(counts) & {"approve", "return", "reject"}, "分布应覆盖三档决策"

    # 理由完整门禁：live 数据缺失理由即失败（防无理由拒绝退化）
    assert reason["missing_count"] == 0, f"存在缺失理由的决策: {reason['missing'][:5]}"

    # 产物落盘
    from datetime import datetime
    from pathlib import Path

    out = Path("reports") / f"fm-decision-report-{datetime.now():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_report(agg, result["veto_recall"], reason, result["parse_fail"]),
        encoding="utf-8",
    )
    print(f"[E2E][FM] 分布: {counts} 总 {total}；报告: {out}")
