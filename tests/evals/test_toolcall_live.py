"""add-toolcall-evaluation nightly @live：拉真实 Langfuse 跑工具调用评估。

无 LANGFUSE key 跳过；报告落 reports/；金标样本门禁由离线 fixtures 承载，
本用例为生产流量监控（分布 + 违例清单，不因方差硬失败）。
"""

import os
from pathlib import Path

import pytest
from evals.toolcall.measure import evaluate, render_report

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_langfuse() -> bool:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except Exception:  # noqa: BLE001, S110
        pass
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        pytest.skip("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未设置，跳过 @live 用例")
    return True


def test_toolcall_live_report(live_langfuse: bool):
    from evals.toolcall.run import fetch_toolcall_traces

    traces = fetch_toolcall_traces(limit_pages=2)
    assert traces, "Langfuse 应返回 react_loop traces"

    report, sequences = evaluate(traces)
    # 埋点上线后应有工具调用被观测到（近期 E2E stub trace 可能无调用——不硬断言，
    # 只保证无异常且报告可生成）
    from datetime import datetime

    out = Path("reports") / f"toolcall-report-{datetime.now():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(report), encoding="utf-8")
    print(f"[E2E][TOOLCALL] traces {len(traces)}，调用 {report.total_calls}；报告: {out}")
