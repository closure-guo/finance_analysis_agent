"""回测正式批受控驱动（2026-09-25 申报单执行入口；owner 已批预算）。

为什么不经 run_backtest.py CLI：CLI 的 stratified_sample 在 1500 天指数历史上
从起点扫描，「每 regime 首个窗口」落在 2020-2021 深历史——而切点声明的
「深历史（2025 年前样本）永久定位通路验证」在代码中无执法点（spec-代码缺口，
issue #172）。深历史样本会带 skill 结论句产出，正是泄漏控制要防的形态。

本驱动以**日期裁剪**执法该规则：决策日强制落在
[2025-01-01, 2026-08-26]（非深历史 ∩ T+20 已结算干净窗口）。

裁剪后三 regime 覆盖（沪深300 120 交易日窗口，runner 同源数据步长=1 精扫，2026-09-25 实测）：
- bull      2025-01-27（+11.6%）
- sideways  2025-03-31（+5.0%）
- bear      2025-04-07（-10.2%，范围内唯一 bear 窗口）

注意：`stratified_sample` 的扫描步长 30 天会**跳过唯一 bear 窗口**（步长=1 才扫
得到），故本驱动内置步长=1 的同规则约束抽样（分类阈值/随机种子与库一致）。
标的池 = cohort universe-v1 同池（10 只），与 forward 腿同标的保可比；
结论按 spec decision-backtest「干净窗口优先」条款限定于已覆盖 regime。
报告：JSON 落 reports/backtest/（gitignored），md 落 evals/backtest/results/（入库）。

用法：
    PYTHONPATH=src:. python tests/scripts/formal_backtest_driver.py            # 全量 n=30
    PYTHONPATH=src:. python tests/scripts/formal_backtest_driver.py --smoke    # 冒烟 3 样本×1 重复
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

TRIM_START = "2024-08-01"  # 首个 120 交易日窗口止于 ≥2025-01（深历史执法）
TRIM_END = "2026-08-26"  # 干净窗口：决策日距跑批日 ≥20 交易日
DATE_LO, DATE_HI = "2025-01-01", TRIM_END
UNIVERSE_FILE = REPO / "data" / "cohort" / "universe-v1.json"
WINDOW_DAYS = 120
UP_THRESHOLD, DOWN_THRESHOLD = 0.10, -0.10


def _sample_constrained(trimmed, codes: list[str], *, per_regime: int, seed: int = 42):
    """步长=1 的分层市场状态约束抽样（stratified_sample 同规则、细步长）。

    stratified_sample 步长 30 天会跳过范围内唯一的 bear 窗口（2025-04-07），
    本函数以逐日滑窗扫描保证单窗口 regime 不被跳采；分类阈值与标的随机
    选取（seed=42、无放回）与库实现一致。
    """
    dates = trimmed["日期"].astype(str).str[:10].tolist()
    close = trimmed["收盘"].astype(float).tolist()
    rng = np.random.default_rng(seed)
    found: dict[str, str] = {}
    for end in range(WINDOW_DAYS, len(trimmed) + 1):
        d = dates[end - 1]
        if d < DATE_LO or d > DATE_HI:
            continue
        seg = close[end - WINDOW_DAYS : end]
        total = seg[-1] / seg[0] - 1
        regime = (
            "bull" if total > UP_THRESHOLD else ("bear" if total < DOWN_THRESHOLD else "sideways")
        )
        if regime not in found:
            found[regime] = d
    if len(codes) < per_regime:
        raise AssertionError(f"标的池不足 per_regime={per_regime}")
    sample = []
    for regime, decision_date in sorted(found.items()):
        chosen = list(rng.choice(codes, size=per_regime, replace=False))
        for code in chosen:
            sample.append({"code": str(code), "regime": regime, "decision_date": decision_date})
    return sample


def main() -> int:
    parser = argparse.ArgumentParser(description="回测正式批受控驱动（深历史日期裁剪）")
    parser.add_argument("--per-regime", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--smoke", action="store_true", help="冒烟：per-regime=1、repeats=1（3 次回放）"
    )
    parser.add_argument("--name", default=None, help="报告名主干")
    args = parser.parse_args()
    per_regime, repeats = (1, 1) if args.smoke else (args.per_regime, args.repeats)

    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")

    from evals.backtest.run_backtest import run_backtest, run_batch_probe

    from finance_agent.data.akshare_client import SETTLEMENT_ADJUST, AKShareClient

    client = AKShareClient()
    index_full = client.fetch_index_kline("000300", days=1500)

    trimmed = index_full[
        (index_full["日期"].astype(str).str[:10] >= TRIM_START)
        & (index_full["日期"].astype(str).str[:10] <= TRIM_END)
    ].reset_index(drop=True)
    first_window_end = str(trimmed["日期"].astype(str).str[:10].iloc[119])
    if first_window_end < DATE_LO:
        raise AssertionError(f"深历史执法失败：裁剪后首个窗口决策日 {first_window_end} < {DATE_LO}")

    import json

    universe = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    codes = [str(c["ticker"]) for c in universe["constituents"]]

    sample = _sample_constrained(trimmed, codes, per_regime=per_regime)
    dates = sorted({s["decision_date"] for s in sample})
    regimes = {s["regime"] for s in sample}
    print(f"[抽样] {len(sample)} 样本 | 决策日 {dates} | regime {sorted(regimes)}")
    for s in sample:
        if not (DATE_LO <= s["decision_date"] <= DATE_HI):
            raise AssertionError(f"决策日越界（深历史/未来）: {s}")
    if not args.smoke and regimes != {"bull", "bear", "sideways"}:
        raise AssertionError(f"全量批 regime 覆盖不全: {sorted(regimes)}")

    klines = {code: client.fetch_kline(code, days=1500, adjust=SETTLEMENT_ADJUST) for code in codes}
    probe = run_batch_probe(codes, dates, client=client)
    as_of = datetime.now().strftime("%Y-%m-%d")

    report = run_backtest(
        sample,
        klines,
        benchmark_kline=index_full,
        repeats=repeats,
        batch_kind="formal",
        as_of=as_of,
        probe=probe,
        sanity_note="2026-09-25 申报单批：universe-v1 同池 × 3 regime 决策日；深历史日期裁剪由本驱动执法（#172）",
        preregister_dir=REPO / "evals" / "ablation" / "preregister",
    )
    positioning = report.get("positioning") or report.get("batch", {}).get("positioning")
    print(f"[完成] positioning={positioning}")
    print(f"[结论] {report.get('conclusion')}")

    # 落盘（复刻 CLI main() 写盘段：run_backtest 只返回 dict，写盘是调用方职责）。
    # 先 JSON 后 MD：渲染失败时数据已持久化，MD 可从 JSON 重渲染。
    import json as _json

    from evals.backtest.report import render_backtest_report_md

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = args.name or f"formal-{stamp}"
    json_dir = REPO / "reports" / "backtest"
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / f"backtest-{stamp}.json"
    json_path.write_text(_json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_dir = REPO / "evals" / "backtest" / "results"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{name}.md"
    md_path.write_text(render_backtest_report_md(report, name=name), encoding="utf-8")
    print(f"[报告] {json_path}（JSON）")
    print(f"[报告] {md_path}（md）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
