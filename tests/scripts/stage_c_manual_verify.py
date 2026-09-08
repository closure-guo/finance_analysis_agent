"""stage-c 人工验证脚本：双真实模型版本注册 + 观点判定 + 校准分段数据。

用法: uv run python tests/scripts/stage_c_manual_verify.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finance_agent.data.akshare_client import AKShareClient  # noqa: E402
from finance_agent.outcome.track_record.job import settle_open_predictions  # noqa: E402
from finance_agent.outcome.track_record.model import (  # noqa: E402
    get_active_agent,
    insert_prediction,
    list_predictions,
    register_agent,
)

DB = Path(__file__).resolve().parents[2] / "data" / "gui-test-sessions.db"
CLIENT = AKShareClient()

# (symbol, name, direction, confidence, days_ago, horizon)
V1_SPECS = [
    ("600519", "贵州茅台", "long", 0.9, 12, 2),
    ("000858", "五粮液", "long", 0.75, 12, 3),
    ("601318", "中国平安", "short", 0.6, 11, 2),
    ("600036", "招商银行", "long", 0.45, 11, 3),
    ("000333", "美的集团", "long", 0.3, 10, 2),
    ("300750", "宁德时代", "short", 0.8, 10, 3),
    ("002412", "汉森制药", "long", 0.65, 9, 2),
    ("601888", "中国中免", "short", 0.5, 9, 3),
]
V2_SPECS = [
    ("600519", "贵州茅台", "short", 0.85, 8, 2),
    ("000858", "五粮液", "short", 0.7, 8, 3),
    ("601318", "中国平安", "long", 0.55, 7, 2),
    ("600036", "招商银行", "short", 0.4, 7, 3),
    ("000333", "美的集团", "short", 0.9, 6, 2),
    ("300750", "宁德时代", "long", 0.65, 6, 3),
    ("002412", "汉森制药", "short", 0.35, 5, 2),
    ("601888", "中国中免", "long", 0.75, 5, 3),
]


def entry_price_on(symbol: str, days_ago: int) -> float | None:
    """取 days_ago 之前的最近真实收盘价作为入场价（真实行情，不臆造）。"""
    df = CLIENT.fetch_kline(symbol, days=60)
    if df is None or df.empty:
        return None
    df = df.copy()
    df["日期"] = df["日期"].astype(str).str[:10]
    cutoff = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    eligible = df[df["日期"] <= cutoff]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["收盘"])


def seed(specs, trace_prefix: str) -> int:
    n = 0
    for symbol, name, direction, confidence, days_ago, horizon in specs:
        trace_id = f"{trace_prefix}-{symbol}"
        existing = {p.get("langfuse_trace_id") for p in list_predictions(db_path=DB)}
        if trace_id in existing:
            print(f"skip: {trace_id}")
            continue
        price = entry_price_on(symbol, days_ago)
        if price is None:
            print(f"no kline for {symbol}, skip")
            continue
        created = (datetime.now() - timedelta(days=days_ago)).isoformat()
        insert_prediction(
            {
                "source_type": "live",
                "symbol": f"{symbol}.SH" if symbol.startswith(("6", "9")) else f"{symbol}.SZ",
                "symbol_name": name,
                "direction": direction,
                "entry_price": price,
                "horizon_days": horizon,
                "confidence": confidence,
                "langfuse_trace_id": trace_id,
                "rationale_snapshot": {
                    "source": "stage-c manual verify",
                    "view": f"{name} {direction}",
                },
                "created_at": created,
            },
            db_path=DB,
            status="open",
        )
        n += 1
        print(f"inserted: {trace_prefix} {symbol} {direction} conf={confidence} entry={price}")
    return n


def main() -> None:
    # v1: deepseek-v4-flash-0731（阿里云）
    a1 = register_agent("deepseek-v4-flash-0731", note="stage-c verify: 阿里云 MaaS", db_path=DB)
    print(f"v1 registered: seq={a1['version_seq']}")
    n1 = seed(V1_SPECS, "stagec-v1")

    # v2: glm-5.3（智谱）
    a2 = register_agent("glm-5.3", note="stage-c verify: 智谱", db_path=DB)
    print(f"v2 registered: seq={a2['version_seq']}")
    n2 = seed(V2_SPECS, "stagec-v2")

    print("--- 真实行情判定（新浪回退 K 线；基准缺失降级 raw_return） ---")
    result = settle_open_predictions(db_path=DB)
    print(f"settle result: {result}")

    for p in list_predictions(db_path=DB):
        if str(p.get("langfuse_trace_id", "")).startswith("stagec-"):
            print(
                f"{p['langfuse_trace_id']} v{p.get('version_seq')} {p['direction']} "
                f"conf={p.get('confidence')} status={p['status']}"
            )
    active = get_active_agent(db_path=DB)
    print(f"active agent: v{active['version_seq']} {active['model_version']}")


if __name__ == "__main__":
    main()
