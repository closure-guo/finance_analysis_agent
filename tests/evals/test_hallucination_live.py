"""add-hallucination-rate-metric nightly @live：真实报告 + 真实行情校验。

无 LANGFUSE key 跳过；akshare 行情失败时数据源缺失 → claim 全部 unverifiable
（如实报告，不因网络波动硬失败）。报告落 reports/。
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest
from evals.hallucination.measure import render_report, run_offline

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_env() -> bool:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except Exception:  # noqa: BLE001, S110
        pass
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        pytest.skip("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未设置，跳过 @live 用例")
    return True


def _latest_deep_report(db_path: Path) -> tuple[str, str] | None:
    """取最近一条深度会话的 assistant 最终报告文本 + 股票代码。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_id, stock_code FROM sessions WHERE session_type='analysis' "
        "ORDER BY created_at DESC LIMIT 3"
    ).fetchall()
    for r in rows:
        events = conn.execute(
            "SELECT event_json FROM session_events WHERE session_id=?",
            (r["session_id"],),
        ).fetchall()
        text = "".join(
            (json.loads(e["event_json"]).get("token") or "")
            for e in events
            if json.loads(e["event_json"]).get("type") == "chat_token"
        )
        if len(text) > 200:
            conn.close()
            return text, str(r["stock_code"] or "")
    conn.close()
    return None


def test_hallucination_live_report(live_env: bool):
    db_path = Path(os.environ.get("SESSIONS_DB_PATH", "data/sessions.db"))
    found = _latest_deep_report(db_path)
    assert found, f"{db_path} 无深度会话报告可用（sample 不足）"
    report_text, stock_code = found

    data_map: dict[str, float] = {}
    try:
        from finance_agent.data.akshare_client import AKShareClient

        quote = AKShareClient().fetch_stock_quote(stock_code)
        if quote.get("price") is not None:
            data_map["price"] = float(quote["price"])
        if quote.get("market_cap"):
            data_map["cap_billion"] = float(quote["market_cap"]) / 1e8
        pe = quote.get("PE_ttm") or quote.get("PE")
        if pe is not None:
            data_map["pe"] = float(pe)
        if quote.get("PB") is not None:
            data_map["pb"] = float(quote["PB"])
    except Exception as e:  # noqa: BLE001 - 行情失败降级为无数据源
        print(f"[HALLUCINATION] 行情拉取失败（数据源缺失，claim 归 unverifiable）: {e}")

    result = run_offline(report_text, data_map)
    from datetime import datetime

    out = Path("reports") / f"hallucination-report-{datetime.now():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(result), encoding="utf-8")
    print(
        f"[HALLUCINATION] {stock_code} claims {len(result.claims)}"
        f"（可验证 {result.countable}/不可验证 {result.unverifiable}）"
        f" 幻觉率 {f'{result.rate:.2%}' if result.rate is not None else '—'}；报告: {out}"
    )
