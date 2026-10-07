"""存量生产库日主分类 dry-run（add-prediction-pool-integrity，只读）。

用法：
    uv run python tests/scripts/dry_run_day_master.py [--db data/sessions.db]

输出每 symbol 的 open 观点分组：归属日 / 主 vs duplicate 计数 /
将被关闭的行 id 列表。不写任何数据——本脚本仅调用
list_predictions（纯 SELECT）与 AKShareClient 网络读，不含
update_prediction_status 等任何写路径。

与日批同源（outcome/track_record/job.py settle_open_predictions 第二阶段）：
- 基准交易日历 = fetch_index_kline("000300", days=280) 的「日期」列
  （经 _normalize_dates 同款 str[:10] 规范化，升序）；
- 日主判定 = day_master_ids(open 池, calendar)。

降级路径：基准指数拉取失败/为空 → calendar=[] → derive_attribution_date
退化为自然日归属（同日去重仍成立，与 job 层降级模式一致）。脚本会显式
打印所用模式；自然日模式下归属日 ≠ 交易日归属，跨节假日的归属日会偏移，
核对结论须注明模式。

注意：必须显式 limit=100_000（与 model.py 钳制上限一致）。默认 50 会把
生产库 76 条 open 静默截断为最新 50 条——本脚本不犯 job.py 已修的 P1。
"""

from __future__ import annotations

import argparse

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.outcome.track_record.judgment import (
    day_master_ids,
    derive_attribution_date,
)
from finance_agent.outcome.track_record.model import list_predictions

BENCHMARK_CODE = "000300"  # 与 outcome/track_record/job.py 一致
KLINE_DAYS = 280  # 与 track_record job 默认 kline_days 一致


def _load_calendar(client: AKShareClient) -> tuple[list[str], str]:
    """拉基准指数日 K 并构造升序交易日历，返回 (calendar, 模式说明)。

    失败/空行情 → ([], "natural-day 降级")，不抛异常（与 job 层降级一致）。
    """
    try:
        bench = client.fetch_index_kline(BENCHMARK_CODE, days=KLINE_DAYS)
    except Exception as e:  # noqa: BLE001  网络失败必须走降级而非中断核对
        print(f"[WARN] 基准指数 {BENCHMARK_CODE} 拉取异常({e})，日主判定降级为自然日归属")
        return [], "natural-day 降级（基准行情拉取失败）"
    if bench is None or bench.empty:
        print(f"[WARN] 基准指数 {BENCHMARK_CODE} 返回空行情，日主判定降级为自然日归属")
        return [], "natural-day 降级（基准行情为空）"
    # 同 job._normalize_dates：日期列规范化为 YYYY-MM-DD 字符串（升序由取数源保证）
    dates = [str(d)[:10] for d in bench["日期"]]
    return sorted(dates), f"交易日历归属（基准 {BENCHMARK_CODE} 近 {len(dates)} 个交易日）"


def _classify(
    preds: list[dict], calendar: list[str]
) -> tuple[set[str], dict[str, list[tuple[dict, str]]]]:
    """给定日历跑日主判定，返回 (masters, 按 symbol 的 (row, 归属日) 标注)。"""
    masters = day_master_ids(preds, calendar)
    by_symbol: dict[str, list[tuple[dict, str]]] = {}
    for p in preds:
        day = derive_attribution_date(str(p["created_at"]), calendar)
        by_symbol.setdefault(str(p["symbol"]), []).append((p, day))
    return masters, by_symbol


def _print_scenario(
    title: str,
    masters: set[str],
    by_symbol: dict[str, list[tuple[dict, str]]],
) -> tuple[int, int]:
    """打印一个情景下的逐 symbol 分类，返回 (主数, duplicate 数)。"""
    print(f"\n──── 情景：{title} ────")
    total_master = 0
    total_dup = 0
    for sym in sorted(by_symbol):
        annotated = by_symbol[sym]
        dups = [p for p, _ in annotated if str(p["prediction_id"]) not in masters]
        ms = [p for p, _ in annotated if str(p["prediction_id"]) in masters]
        total_master += len(ms)
        total_dup += len(dups)
        print(f"\n{sym}: open={len(annotated)} 主={len(ms)} duplicate={len(dups)}")
        attr_days = sorted({day for _, day in annotated})
        print(f"    归属日分布: {attr_days}")
        for p, day in sorted(annotated, key=lambda t: (t[1], str(t[0]["created_at"]))):
            tag = "主" if str(p["prediction_id"]) in masters else "duplicate→将关闭"
            print(
                f"    [{tag}] {p['prediction_id']} 归属日={day} "
                f"created={p['created_at']} dir={p['direction']}"
            )
    print(
        f"\n== {title}: open={sum(len(v) for v in by_symbol.values())} "
        f"主={total_master} 将关闭 duplicate={total_dup} =="
    )
    return total_master, total_dup


def main() -> None:
    parser = argparse.ArgumentParser(description="存量库日主分类 dry-run（只读）")
    parser.add_argument("--db", default="data/sessions.db")
    parser.add_argument(
        "--next-trading-day",
        default="2026-10-08",
        help="上限情景假设的次一交易日（仅用于分组，具体日期不影响分组结果）",
    )
    args = parser.parse_args()

    print(f"== dry-run day-master 核对（db={args.db}，只读）==")
    # 与 job.py 第二阶段同源：status=open 全量读取，显式大 limit 防 50 行截断
    preds = [
        p
        for p in list_predictions(status="open", db_path=args.db, limit=100_000)
        if p["status"] == "open"
    ]
    print(f"open 池读取: {len(preds)} 条（status=open, limit=100_000）")

    client = AKShareClient()
    calendar, mode = _load_calendar(client)
    print(f"归属日模式: {mode}")
    if calendar:
        print(f"日历范围: {calendar[0]} .. {calendar[-1]}")

    # 情景 A：与日批今日同源（日历截至最后一个已完成交易日）
    masters_a, by_symbol_a = _classify(preds, calendar)
    m_a, d_a = _print_scenario(
        f"A·今日日历窗口（截至 {calendar[-1] if calendar else '无'}）", masters_a, by_symbol_a
    )

    # 情景 B（上限参考）：日历补上次一交易日后再判定。晚于日历末日的产出
    # （收盘后/节假日）本应归属「次一交易日」，但日历未含该日时
    # derive_attribution_date 按文档降级为自然日——两情景的差异行即
    # 「降级窗口内产出」的观点，正式日批若在次一交易日 K 线落地后运行，
    # 关闭的 duplicate 只会更多（本情景给出上限），不会更少。
    if calendar and args.next_trading_day > calendar[-1]:
        masters_b, by_symbol_b = _classify(preds, calendar + [args.next_trading_day])
        m_b, d_b = _print_scenario(
            f"B·日历补次一交易日 {args.next_trading_day}（上限参考）", masters_b, by_symbol_b
        )
        print(f"\n两情景差异：duplicate {d_a} → {d_b}（差 {d_b - d_a} 条为降级窗口产出）")
    else:
        print("\n情景 B 跳过（日历末日不早于假设次一交易日）")

    print("（dry-run 未改动任何数据；正式关闭由日批第二阶段执行 duplicate_of_day）")


if __name__ == "__main__":
    main()
