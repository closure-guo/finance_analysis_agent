#!/usr/bin/env python
"""构建 fix-citation-contract-diseases 离线重判 fixture（一次性，需 akshare 网络）。

数据确定性论证：
- 财务报表 / 财务指标 / 季度数据：2026-08-26 运行日后不可变（FY2025 年报、
  2026Q2 季报均已发布），今天重取 == 运行日取值；
- 技术指标：kline 历史 K 线不可变，按 日期 <= 2026-08-25（运行日 09:06 开盘前
  最后交易日）截尾后经 calc_technical 重算，与运行时序列逐值一致；
- macro_indicators：月度数据，最近一次发布（2026-07 月 CPI/PPI 等）在运行日
  与今日之间无新版本，重取等价。

用法：
    uv run python tests/scripts/build_citation_rejudge_fixture.py

产出：
    tests/fixtures/citation_rejudge_002412.json
      - claims: round-2 verify_citations 67 条（Langfuse span metadata 全保真，
        round-1 的 68 条因 Langfuse 8KB 截断 + journal 背压丢尾不可全量恢复，
        两轮疾病构成一致，重判基线取 round-2）
      - state: 重算的验证用 state 快照（DataFrame 序列化为 columns+records）
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

TRACE_ID = "69a0e220fe58ede18f4e155a181b69cd"  # deep_analysis:汉森制药
STOCK = "002412"
KLINE_END = "2026-08-26"  # 运行时 K 线实际末日（初版 08-25 假设有误：由 MA5/MA20 双方程解出隐含收盘 13.09，与 08-26 真实收盘一致）
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "citation_rejudge_002412.json"


def fetch_r2_claims() -> list[dict]:
    load_dotenv(ROOT / ".env")
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        sys.exit("LANGFUSE_PUBLIC_KEY/SECRET_KEY 未配置（.env 缺失），无法提取历史 claims。")
    pub, sec = os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"]
    auth = base64.b64encode(f"{pub}:{sec}".encode()).decode()
    req = urllib.request.Request(
        f"http://localhost:3000/api/public/traces/{TRACE_ID}",
        headers={"Authorization": "Basic " + auth},
    )
    trace = json.loads(urllib.request.urlopen(req, timeout=30).read())
    for o in trace.get("observations", []):
        rep = (o.get("metadata") or {}).get("citation_report")
        if rep:
            print(f"round-2 报告: total={rep['total']} failed={rep['failed']}")
            return [r["claim"] | {"_orig_status": r["status"]} for r in rep["results"]]
    sys.exit("trace 中无 citation_report metadata")


def _san(obj):
    """numpy/NaN → 纯 JSON 类型。"""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _san(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_san(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if math.isnan(f) else f
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


def build_state() -> dict:
    from finance_agent.data.akshare_client import AKShareClient
    from finance_agent.nodes.compute import compute_metrics

    ak = AKShareClient()
    kline = ak.fetch_kline(STOCK, days=400)
    kline = kline[kline["日期"].astype(str) <= KLINE_END].tail(250).reset_index(drop=True)
    print(f"kline: {len(kline)} 行, 末日期 {kline['日期'].iloc[-1]}")

    state: dict = {
        "stock_code": STOCK,
        "stock_name": "汉森制药",
        "balance_sheet": ak.fetch_balance_sheet(STOCK),
        "income_statement": ak.fetch_income_statement(STOCK),
        "cash_flow_statement": ak.fetch_cash_flow(STOCK),
        "financial_indicators": ak.fetch_indicators(STOCK),
        "quarterly_income": ak.fetch_quarterly_income(STOCK),
        "kline": kline,
        "benchmark_kline": None,
        "macro_indicators": ak.fetch_macro_indicators(),
    }
    computed = compute_metrics(state)  # type: ignore[arg-type]
    state.update(computed)
    return state


def main() -> int:
    claims = fetch_r2_claims()
    state = build_state()

    # ── 确定性锚点校验：重建序列尾值必须逼近 LLM 当年引用的「最新」──
    tech = state["technical_indicators"]
    anchors = {
        "MA.5": (tech["MA"]["5"][-1], 11.216),
        "MA.20": (tech["MA"]["20"][-1], 8.224),
        "RSI.14": (tech["RSI"]["14"][-1], 92.45),
    }
    for name, (actual, expected) in anchors.items():
        ok = actual is not None and abs(actual - expected) / expected < 0.02
        print(f"锚点 {name}: 重建={actual} 引用={expected} -> {'OK' if ok else 'MISMATCH'}")

    dfs = {
        k: json.loads(df.to_json(orient="columns", force_ascii=False, date_format="iso"))
        for k, df in state.items()
        if isinstance(df, pd.DataFrame) and not df.empty
    }
    scalars = {
        k: _san(v) for k, v in state.items() if k not in dfs and k not in ("benchmark_kline",)
    }
    fixture = {
        "metadata": {
            "trace_id": TRACE_ID,
            "stock_code": STOCK,
            "run_date": "2026-08-26",
            "kline_end": KLINE_END,
            "claims_round": 2,
            "orig_fail": 41,
            "orig_total": 67,
        },
        "claims": _san(claims),
        "state": {"dataframes": dfs, "json": scalars},
    }
    FIXTURE_PATH.write_text(json.dumps(fixture, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fixture 已写入 {FIXTURE_PATH} ({FIXTURE_PATH.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
