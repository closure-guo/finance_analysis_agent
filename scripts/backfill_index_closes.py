"""回填指数收盘历史(add-index-performance-compare)。

与日批 sync_index_closes 共用同一幂等写入(INSERT OR REPLACE),重跑安全。
用法:
    uv run python scripts/backfill_index_closes.py            # 默认近 280 交易日
    uv run python scripts/backfill_index_closes.py --db-path data/sessions.db
"""

import argparse

from finance_agent.outcome.track_record.index_compare import sync_index_closes
from finance_agent.outcome.track_record.model import init_track_record_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="回填指数收盘历史")
    parser.add_argument("--days", type=int, default=280, help="拉取的交易日长度(默认 280 ≈ 1.1 年)")
    parser.add_argument("--db-path", default=None, help="SQLite 路径(缺省走 SESSIONS_DB_PATH/默认)")
    args = parser.parse_args()
    init_track_record_tables(args.db_path)
    result = sync_index_closes(days=args.days, db_path=args.db_path)
    print(f"stored={result['stored']} failed={result['failed']}")


if __name__ == "__main__":
    main()
