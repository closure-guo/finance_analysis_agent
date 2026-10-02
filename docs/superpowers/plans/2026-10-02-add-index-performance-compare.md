# 跑赢指数对比 (add-index-performance-compare) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 战绩页新增「跑赢指数对比」卡片:组合区间收益 vs 五大指数(上证/沪深300/中证500/中证1000/创业板指)同期收益的横条对比,含「跑赢 N/M 个指数」摘要。

**Architecture:** 新增 `index_closes` SQLite 表(指数收盘,幂等 upsert)+ 新模块 `index_compare.py`(指数集常量、日批同步、区间收益计算)+ `GET /api/v1/track-record/index-compare` 端点 + 前端 `IndexCompareCard` 组件。盯市日批顺带同步指数收盘(单指数失败隔离);判定链路(settle/judgment/daily_marks/equity_curve 语义)零改动。

**Tech Stack:** Python 3.12 + FastAPI + sqlite3 + pandas(取数侧)/ React 18 + TS + Vitest + Playwright

## Global Constraints

- 判定口径不动:win/loss 基准仍为沪深300(`BENCHMARK_CODE="000300"`,metrics.md 预登记);本变更不得触碰 `settle.py`/`judgment.py`/`daily_marks`/`equity_curve` 既有语义
- E2E 红线:禁止 route.fulfill/MSW 拦截业务接口;造数走 `TESTING=1` 的 `/api/test/seed`(既有模式)
- TDD 红线:先写失败测试,再写实现;每任务独立提交
- 跑赢判定 = 组合收益 > 指数收益 直读比较,不复用判定链 ±2% 中性带
- 指数基期向过去取(≤ 窗口起点最近可得日);窗口内无早期数据时取窗口内最早可得日并经 `effective_start_date` 披露;绝不向未来取值
- 指数落库失败 SHALL NOT 使盯市任务失败、SHALL NOT 计入 marked/skipped/errors 汇总(新增独立键 index_stored/index_failed)
- 验证命令:`uv run pytest`、`uv run ruff check`、`uv run mypy`、`cd frontend && npm test`、`cd tests/e2e/playwright && npx playwright test`
- 提交信息格式沿用仓库惯例 `feat(track-record): ...`;工作分支在 `.worktrees/` 下创建

**File Structure(总览):**

```
src/finance_agent/outcome/track_record/
├── model.py              # 修改:TRACK_RECORD_EXTRA_DDL 加 index_closes;新增 upsert_index_closes/list_index_closes
├── index_compare.py      # 新建:UNIVERSE 常量 + sync_index_closes + build_index_compare
└── marking.py            # 修改:run_daily_marking 顺带 sync_index_closes
src/finance_agent/api.py  # 修改:index-compare 端点 + /api/test/seed 扩展
scripts/backfill_index_closes.py  # 新建:一次性回填
tests/outcome/test_index_compare.py       # 新建:存储/同步/计算单测
tests/test_api_track_record.py            # 修改:端点集成测试
frontend/src/types.ts                     # 修改:IndexCompare 类型
frontend/src/pages/trackRecord/IndexCompareCard.tsx   # 新建
frontend/src/pages/trackRecord/TrackRecordPage.tsx    # 修改:挂卡片
frontend/src/test/trackRecord/indexCompareCard.test.tsx    # 新建
frontend/src/test/trackRecord/trackRecordPage.test.tsx    # 修改
tests/e2e/playwright/tests/track-record-index-compare.spec.ts  # 新建
```

---

### Task 1: index_closes 存储层

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`(TRACK_RECORD_EXTRA_DDL 末尾追加;新函数放在 `list_equity_curve` 之后)
- Test: `tests/outcome/test_index_compare.py`(新建)

**Interfaces:**
- Produces: `upsert_index_closes(rows: list[tuple[str, str, float]], db_path: str | Path | None = None) -> int`(rows 元素为 (index_code, trade_date, close),返回写入行数);`list_index_closes(index_code: str, end: str | None = None, db_path: str | Path | None = None) -> list[dict[str, Any]]`(返回 [{index_code, trade_date, close}],trade_date ASC,end 为含右边界)

- [ ] **Step 1: Write the failing test**

新建 `tests/outcome/test_index_compare.py`:

```python
"""add-index-performance-compare:指数收盘存储、日批同步、区间收益读数单测。"""

import pytest

from finance_agent.outcome.track_record.model import (
    init_track_record_tables,
    list_index_closes,
    upsert_index_closes,
)


@pytest.fixture()
def db(tmp_path):
    db = tmp_path / "t.db"
    init_track_record_tables(db)
    return db


class TestIndexClosesStorage:
    def test_upsert_and_list(self, db):
        n = upsert_index_closes(
            [("000300", "2026-09-28", 4000.0), ("000300", "2026-09-29", 4040.0)], db_path=db
        )
        assert n == 2
        rows = list_index_closes("000300", db_path=db)
        assert [r["trade_date"] for r in rows] == ["2026-09-28", "2026-09-29"]
        assert rows[0]["close"] == pytest.approx(4000.0)

    def test_idempotent_replace(self, db):
        upsert_index_closes([("000300", "2026-09-28", 4000.0)], db_path=db)
        upsert_index_closes([("000300", "2026-09-28", 4010.0)], db_path=db)
        rows = list_index_closes("000300", db_path=db)
        assert len(rows) == 1 and rows[0]["close"] == pytest.approx(4010.0)

    def test_list_end_boundary_inclusive_and_empty(self, db):
        upsert_index_closes(
            [("000905", "2026-09-28", 6000.0), ("000905", "2026-10-09", 6600.0)], db_path=db
        )
        assert list_index_closes("000905", end="2026-09-28", db_path=db)[0]["trade_date"] == "2026-09-28"
        assert list_index_closes("000852", db_path=db) == []
        assert list_index_closes("000905", end="2026-01-01", db_path=db) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_index_compare.py -v`
Expected: FAIL — `ImportError: cannot import name 'upsert_index_closes'`

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/outcome/track_record/model.py` — 在 `TRACK_RECORD_EXTRA_DDL` 字符串末尾(`idx_audit_pred` 索引之后、结尾 `"""` 之前)追加:

```sql

-- ── add-index-performance-compare ──
CREATE TABLE IF NOT EXISTS index_closes (
  index_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  close      REAL NOT NULL,
  PRIMARY KEY (index_code, trade_date)
);
```

在同文件 `list_equity_curve` 函数之后追加:

```python
# ── index_closes:指数收盘(add-index-performance-compare;展示层对比用,判定链不读)──
def upsert_index_closes(
    rows: list[tuple[str, str, float]],
    db_path: str | Path | None = None,
) -> int:
    """批量幂等写入指数收盘(INSERT OR REPLACE,单事务),返回写入行数。"""
    if not rows:
        return 0
    conn = _connect(db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO index_closes (index_code, trade_date, close) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def list_index_closes(
    index_code: str,
    end: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """按指数读收盘序列(trade_date ASC),end 为含右边界;无 start(基期回退需全历史)。"""
    conn = _connect(db_path)
    try:
        if end is None:
            cur = conn.execute(
                "SELECT index_code, trade_date, close FROM index_closes"
                " WHERE index_code = ? ORDER BY trade_date ASC",
                (index_code,),
            )
        else:
            cur = conn.execute(
                "SELECT index_code, trade_date, close FROM index_closes"
                " WHERE index_code = ? AND trade_date <= ? ORDER BY trade_date ASC",
                (index_code, end),
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_index_compare.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py tests/outcome/test_index_compare.py
git commit -m "feat(track-record): index_closes 存储层——指数收盘幂等落库 (add-index-performance-compare)"
```

---

### Task 2: 指数集常量 + sync_index_closes 同步函数

**Files:**
- Create: `src/finance_agent/outcome/track_record/index_compare.py`
- Test: `tests/outcome/test_index_compare.py`(追加类)

**Interfaces:**
- Consumes: Task 1 的 `upsert_index_closes(rows, db_path) -> int`
- Produces: `INDEX_COMPARE_UNIVERSE: list[dict[str, str]]`(每项 {code, name});`sync_index_closes(*, client: Any = None, db_path: str | Path | None = None, days: int = 280) -> dict[str, Any]`(返回 {stored: int, failed: list[str]},**任何单指数异常都不外抛**)

- [ ] **Step 1: Write the failing test**

`tests/outcome/test_index_compare.py` 追加(顶部 import 区加 `from unittest.mock import MagicMock`;`import pandas as pd`):

```python
from finance_agent.outcome.track_record.index_compare import (
    INDEX_COMPARE_UNIVERSE,
    sync_index_closes,
)


def _fake_client(closes_by_code: dict[str, list[tuple[str, float]]], fail_codes: set[str] | None = None):
    """构造 AKShareClient 替身:fetch_index_kline 返回中文列名 DataFrame,失败码抛异常。"""
    fail_codes = fail_codes or set()

    class _C:
        def fetch_index_kline(self, index_code: str, days: int = 250):
            if index_code in fail_codes:
                raise RuntimeError(f"rate limited: {index_code}")
            rows = closes_by_code.get(index_code, [])
            return pd.DataFrame({"日期": [d for d, _ in rows], "收盘": [c for _, c in rows]})

    return _C()


class TestSyncIndexCloses:
    def test_universe_has_five_major_indices(self):
        assert [u["code"] for u in INDEX_COMPARE_UNIVERSE] == [
            "000001", "000300", "000905", "000852", "399006",
        ]
        assert all(u["name"] for u in INDEX_COMPARE_UNIVERSE)

    def test_sync_stores_all_and_reports_count(self, db):
        client = _fake_client({
            "000300": [("2026-09-28", 4000.0), ("2026-09-29", 4040.0)],
            "000001": [("2026-09-28", 3000.0)],
        })
        result = sync_index_closes(client=client, db_path=db)
        assert result["stored"] == 3 and result["failed"] == []
        assert len(list_index_closes("000300", db_path=db)) == 2

    def test_sync_single_failure_isolated(self, db):
        client = _fake_client(
            {"000300": [("2026-09-28", 4000.0)]}, fail_codes={"000905", "399006"}
        )
        result = sync_index_closes(client=client, db_path=db)
        assert result["failed"] == ["000905", "399006"]
        assert result["stored"] >= 1  # 其余指数照常落库
        assert len(list_index_closes("000300", db_path=db)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_index_compare.py -v -k sync`
Expected: FAIL — `ModuleNotFoundError: No module named 'finance_agent.outcome.track_record.index_compare'`

- [ ] **Step 3: Write minimal implementation**

新建 `src/finance_agent/outcome/track_record/index_compare.py`:

```python
"""指数区间收益对比(add-index-performance-compare)。

指数收盘落库与区间收益读数;win/loss 判定基准仍为 BENCHMARK_CODE(沪深300),
判定链路不消费本模块。口径细则见 openspec/changes/add-index-performance-compare
的 specs/index-comparison。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from finance_agent.outcome.track_record.model import upsert_index_closes

logger = logging.getLogger(__name__)

# 对比指数集(代码级常量,非配置项——见 design Non-Goals)
INDEX_COMPARE_UNIVERSE: list[dict[str, str]] = [
    {"code": "000001", "name": "上证指数"},
    {"code": "000300", "name": "沪深300"},
    {"code": "000905", "name": "中证500"},
    {"code": "000852", "name": "中证1000"},
    {"code": "399006", "name": "创业板指"},
]


def sync_index_closes(
    *,
    client: Any = None,
    db_path: str | Path | None = None,
    days: int = 280,
) -> dict[str, Any]:
    """拉取指数集 K 线并幂等落库;单指数失败仅 WARNING,不外抛。

    日批(daily_marking)与回填脚本共用:days 为拉取的交易日长度,
    280 交易日 ≈ 1.1 年,覆盖前端最长 1y 窗口。返回 {stored, failed}。
    """
    if client is None:
        from finance_agent.data.akshare_client import AKShareClient

        client = AKShareClient()
    stored = 0
    failed: list[str] = []
    for u in INDEX_COMPARE_UNIVERSE:
        code = u["code"]
        try:
            df = client.fetch_index_kline(code, days=days)
            if df is None or df.empty:
                failed.append(code)
                logger.warning("指数 %s(%s) 行情为空,本批跳过", code, u["name"])
                continue
            rows = [
                (code, str(d), float(c))
                for d, c in zip(df["日期"], df["收盘"], strict=False)
            ]
            stored += upsert_index_closes(rows, db_path=db_path)
        except Exception as e:  # noqa: BLE001 - 单指数失败隔离,展示层不得放大
            failed.append(code)
            logger.warning("指数 %s(%s) 收盘落库失败: %s", code, u["name"], e)
    return {"stored": stored, "failed": failed}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_index_compare.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/index_compare.py tests/outcome/test_index_compare.py
git commit -m "feat(track-record): 指数集常量与 sync_index_closes 幂等同步 (add-index-performance-compare)"
```

---

### Task 3: 盯市日批顺带落库(失败隔离)

**Files:**
- Modify: `src/finance_agent/outcome/track_record/marking.py:141-165`(`run_daily_marking`)
- Test: `tests/outcome/test_index_compare.py`(追加)

**Interfaces:**
- Consumes: Task 2 的 `sync_index_closes(*, client, db_path, days)`
- Produces: `run_daily_marking` 返回 dict 追加键 `index_stored: int`、`index_failed: list[str]`;marked/skipped/errors 三键语义不变

- [ ] **Step 1: Write the failing test**

`tests/outcome/test_index_compare.py` 追加(顶部加 `from finance_agent.outcome.track_record.marking import run_daily_marking`):

```python
class TestDailyMarkingIndexSync:
    def _seed_open_prediction(self, db):
        from finance_agent.outcome.track_record.model import insert_prediction

        insert_prediction(
            {
                "source_type": "live",
                "symbol": "600519.SH",
                "symbol_name": "贵州茅台",
                "direction": "long",
                "entry_price": 100.0,
                "horizon_days": 20,
                "confidence": 0.8,
                "rationale_snapshot": {"action": "buy"},
                "created_at": "2026-09-01T10:00:00",
            },
            db_path=db,
        )

    def test_marking_summary_has_index_keys_and_stores(self, db):
        self._seed_open_prediction(db)
        client = _fake_client({"000300": [("2026-09-28", 4000.0)]})
        result = run_daily_marking(client=client, db_path=db, kline_days=5)
        assert result["index_stored"] >= 1
        assert result["index_failed"] == []
        # 盯市三键不受指数落库影响(errors 仍为盯市自身口径)
        assert set(result) >= {"marked", "skipped", "errors", "index_stored", "index_failed"}

    def test_marking_index_sync_all_failed_still_ok(self, db):
        self._seed_open_prediction(db)
        client = _fake_client({}, fail_codes={u["code"] for u in INDEX_COMPARE_UNIVERSE})
        result = run_daily_marking(client=client, db_path=db, kline_days=5)
        assert result["index_stored"] == 0
        assert len(result["index_failed"]) == 5
        # 盯市主链路照常返回(不抛错、无额外 errors)
        assert "metrics_date" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_index_compare.py -v -k marking`
Expected: FAIL — `KeyError: 'index_stored'`

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/outcome/track_record/marking.py` 的 `run_daily_marking`——在 `metrics_date = persist_metrics_snapshot(db_path=db_path)` 之后、`return` 之前插入:

```python
    # add-index-performance-compare:指数集收盘顺带落库(展示层对比用)。
    # 失败隔离铁律:任何指数异常不得使盯市失败、不得计入 marked/skipped/errors;
    # 判定链仍读 daily_marks.benchmark_price,与 index_closes 互不影响。
    index_summary: dict[str, Any] = {"index_stored": 0, "index_failed": ["_sync_error"]}
    try:
        from finance_agent.outcome.track_record.index_compare import sync_index_closes

        index_summary = sync_index_closes(client=client, db_path=db_path, days=kline_days)
    except Exception as e:  # noqa: BLE001 - 展示层数据缺失不得放大成盯市失败
        logger.warning("指数收盘同步整体失败(仅展示层): %s", e)
```

并把函数末行改为:

```python
    return {**mark_result, "equity_points": len(points), "metrics_date": metrics_date, **index_summary}
```

(确认 `marking.py` 顶部已有 `from typing import Any`;`logger` 已存在。)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_index_compare.py -v`
Expected: PASS(8 passed)

- [ ] **Step 5: 回归既有盯市测试**

Run: `uv run pytest tests/outcome/test_track_record_metrics.py -v`
Expected: PASS(全绿——summary 新增键不破坏既有断言;若有断言精确键集合的用例,按「新增键向后兼容」原则更新该断言并在提交信息说明)

- [ ] **Step 6: Commit**

```bash
git add src/finance_agent/outcome/track_record/marking.py tests/outcome/test_index_compare.py
git commit -m "feat(track-record): 盯市日批顺带同步指数收盘,失败隔离 (add-index-performance-compare)"
```

---

### Task 4: 回填脚本

**Files:**
- Create: `scripts/backfill_index_closes.py`

**Interfaces:**
- Consumes: Task 2 的 `sync_index_closes`;`init_track_record_tables`
- Produces: CLI `uv run python scripts/backfill_index_closes.py [--days 280] [--db-path PATH]`,stdout 打印 `stored=<n> failed=[...]`;幂等可重跑

- [ ] **Step 1: Write the script**(薄壳,逻辑已被 Task 2 单测覆盖;冒烟由 Step 2 验证)

```python
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
```

- [ ] **Step 2: 冒烟验证(对临时库)**

Run: `uv run python scripts/backfill_index_closes.py --db-path /tmp/backfill-smoke.db --days 5`
Expected: `stored=<5 的倍数> failed=[]`(本机可直连行情源时;若 AKShare 限流/断网,failed 非空但脚本退出码为 0,记录实况即可,不算任务失败)。随后删除临时库。

- [ ] **Step 3: 对生产库执行回填 + 抽验**

生产库在容器内:`docker exec finance-agent-backend-1 python -c "import finance_agent.outcome.track_record.index_compare as m; print(m.sync_index_closes(days=280))"`
(容器内镜像已含 src;若镜像无最新代码,`docker compose up -d --build backend` 后执行。)
抽验:`docker exec finance-agent-backend-1 python -c "from finance_agent.outcome.track_record.model import list_index_closes; rows=list_index_closes('000300'); print(len(rows), rows[-1])"`
Expected: ≥ 200 行且最后一行为最近交易日。

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_index_closes.py
git commit -m "feat(track-record): 指数收盘历史回填脚本 (add-index-performance-compare)"
```

---

### Task 5: build_index_compare 区间收益计算

**Files:**
- Modify: `src/finance_agent/outcome/track_record/index_compare.py`(追加)
- Test: `tests/outcome/test_index_compare.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 `list_index_closes`、`list_equity_curve`(model.py 既有)
- Produces: `build_index_compare(span: str = "all", db_path: str | Path | None = None) -> dict[str, Any]`,返回 `{span, window: {start, end}, agent_return, indices}`;indices 顺序同 UNIVERSE,每项 `{code, name, return, effective_start_date, beat}`;`build_index_compare` 不含 as_of/disclaimer(端点层附加)

- [ ] **Step 1: Write the failing test**

`tests/outcome/test_index_compare.py` 追加(顶部加 `from finance_agent.outcome.track_record.model import upsert_equity_point` 与 `from finance_agent.outcome.track_record.index_compare import build_index_compare`):

```python
def _seed_curve(db, points: list[tuple[str, float]]):
    for d, nav in points:
        upsert_equity_point(d, nav, benchmark_nav=1.0, db_path=db)


class TestBuildIndexCompare:
    def test_window_agent_return_and_beat(self, db):
        _seed_curve(db, [("2026-09-28", 1.0), ("2026-10-09", 1.05)])
        upsert_index_closes(
            [
                ("000300", "2026-09-26", 4000.0),  # 基期回退:窗口首日 09-28 无值 → 用 09-26
                ("000300", "2026-10-09", 4040.0),  # +1.0% → agent 5% 跑赢
                ("000905", "2026-09-28", 6000.0),  # +10% → agent 跑输
                ("000905", "2026-10-09", 6600.0),
            ],
            db_path=db,
        )
        out = build_index_compare("all", db_path=db)
        assert out["window"] == {"start": "2026-09-28", "end": "2026-10-09"}
        assert out["agent_return"] == pytest.approx(0.05)
        by = {i["code"]: i for i in out["indices"]}
        assert by["000300"]["return"] == pytest.approx(0.01)
        assert by["000300"]["beat"] is True
        assert by["000300"]["effective_start_date"] == "2026-09-26"
        assert by["000905"]["beat"] is False
        assert [i["code"] for i in out["indices"]] == [u["code"] for u in INDEX_COMPARE_UNIVERSE]

    def test_index_starting_mid_window_uses_earliest_in_window(self, db):
        _seed_curve(db, [("2026-09-28", 1.0), ("2026-10-09", 1.05)])
        upsert_index_closes([("000852", "2026-10-01", 2500.0), ("000852", "2026-10-09", 2525.0)], db_path=db)
        out = build_index_compare("all", db_path=db)
        by = {i["code"]: i for i in out["indices"]}
        assert by["000852"]["effective_start_date"] == "2026-10-01"
        assert by["000852"]["return"] == pytest.approx(0.01)

    def test_index_all_missing_in_window_is_null(self, db):
        _seed_curve(db, [("2026-09-28", 1.0), ("2026-10-09", 1.05)])
        upsert_index_closes([("399006", "2026-12-01", 2000.0)], db_path=db)  # 全在窗口外
        out = build_index_compare("all", db_path=db)
        by = {i["code"]: i for i in out["indices"]}
        assert by["399006"]["return"] is None
        assert by["399006"]["beat"] is None
        assert by["399006"]["effective_start_date"] is None

    def test_curve_insufficient_points(self, db):
        _seed_curve(db, [("2026-09-28", 1.0)])
        out = build_index_compare("all", db_path=db)
        assert out["agent_return"] is None
        assert all(i["beat"] is None for i in out["indices"])
        assert out["window"]["start"] == "2026-09-28"

    def test_curve_empty(self, db):
        out = build_index_compare("all", db_path=db)
        assert out["window"] == {"start": None, "end": None}
        assert out["agent_return"] is None

    def test_span_window_truncates_to_actual_coverage(self, db):
        _seed_curve(db, [("2026-06-01", 1.0), ("2026-09-28", 1.02), ("2026-10-09", 1.05)])
        out = build_index_compare("1y", db_path=db)
        assert out["span"] == "1y"
        assert out["window"] == {"start": "2026-06-01", "end": "2026-10-09"}  # 1y 截断到实际覆盖

    def test_span_3m_cutoff(self, db):
        _seed_curve(db, [("2026-01-05", 1.0), ("2026-09-28", 1.10), ("2026-10-09", 1.05)])
        out = build_index_compare("3m", db_path=db)
        # 3m 截点 ≈ 2026-07-09 → 窗口从 09-28 起
        assert out["window"]["start"] == "2026-09-28"
        assert out["agent_return"] == pytest.approx(round(1.05 / 1.10 - 1, 6))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_index_compare.py -v -k build`
Expected: FAIL — `ImportError: cannot import name 'build_index_compare'`

- [ ] **Step 3: Write minimal implementation**

`index_compare.py` 追加(顶部补 `import calendar`、`from datetime import date`,import 区补 `list_equity_curve`):

```python
from finance_agent.outcome.track_record.model import (
    list_equity_curve,
    list_index_closes,
    upsert_index_closes,
)

_SPAN_MONTHS = {"all": None, "3m": 3, "6m": 6, "1y": 12}


def _shift_months(d: date, months: int) -> date:
    """日历月平移;目标月无对应日(如 01-31 −1 月)钳制到当月最后一天。"""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def build_index_compare(
    span: str = "all",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """跑赢指数对比读数(口径见 specs/index-comparison;as_of/disclaimer 由端点层附加)。"""
    curve = list_equity_curve(db_path=db_path)
    window_start = curve[0]["curve_date"] if curve else None
    window_end = curve[-1]["curve_date"] if curve else None
    months = _SPAN_MONTHS.get(span)
    if months and curve:
        cutoff = _shift_months(date.fromisoformat(str(window_end)), -months).isoformat()
        window_start = max(str(window_start), cutoff)

    agent_return: float | None = None
    if len(curve) >= 2:
        first = next(p for p in curve if p["curve_date"] >= window_start)
        if first["agent_nav"]:
            agent_return = round(float(curve[-1]["agent_nav"]) / float(first["agent_nav"]) - 1.0, 6)

    indices: list[dict[str, Any]] = []
    for u in INDEX_COMPARE_UNIVERSE:
        ret: float | None = None
        eff: str | None = None
        rows = list_index_closes(u["code"], end=str(window_end) if window_end else None, db_path=db_path)
        if rows and window_start is not None:
            base = None
            for r in rows:  # 行按日期升序;取 ≤ 窗口起点的最近可得日(向过去回退)
                if r["trade_date"] <= window_start:
                    base = r
                else:
                    break
            if base is None:  # 窗口起点前无数据 → 取窗口内最早可得日(如实披露)
                base = rows[0]
            if base["close"]:
                ret = round(float(rows[-1]["close"]) / float(base["close"]) - 1.0, 6)
                eff = str(base["trade_date"])
        beat = (
            agent_return > ret
            if agent_return is not None and ret is not None
            else None
        )
        indices.append({"code": u["code"], "name": u["name"], "return": ret, "effective_start_date": eff, "beat": beat})

    return {
        "span": span,
        "window": {"start": window_start, "end": window_end},
        "agent_return": agent_return,
        "indices": indices,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_index_compare.py -v`
Expected: PASS(15 passed)

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/index_compare.py tests/outcome/test_index_compare.py
git commit -m "feat(track-record): build_index_compare 区间收益与跑赢读数 (add-index-performance-compare)"
```

---

### Task 6: index-compare API 端点

**Files:**
- Modify: `src/finance_agent/api.py:2224`(`track_record_equity_curve` 端点之后插入)
- Test: `tests/test_api_track_record.py`(追加)

**Interfaces:**
- Consumes: Task 5 的 `build_index_compare(span, db_path)`;api.py 既有 `_track_as_of()`、`_DISCLAIMER`
- Produces: `GET /api/v1/track-record/index-compare?span=all|3m|6m|1y`(缺省 all;非法 span → 422),响应 `{span, window, agent_return, indices, as_of, disclaimer}`

- [ ] **Step 1: Write the failing test**

`tests/test_api_track_record.py` 追加(顶部 import 区补 `import pytest`、`from finance_agent.outcome.track_record.model import upsert_index_closes`):

```python
def test_index_compare_span_validation(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).get("/api/v1/track-record/index-compare?span=2y")
    assert resp.status_code == 422


def test_index_compare_empty(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).get("/api/v1/track-record/index-compare")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window"]["start"] is None
    assert data["agent_return"] is None
    assert len(data["indices"]) == 5
    assert all(i["beat"] is None for i in data["indices"])
    assert data["as_of"] and data["disclaimer"]


def test_index_compare_returns(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    upsert_equity_point("2026-09-28", 1.0, benchmark_nav=1.0, db_path=db)
    upsert_equity_point("2026-10-09", 1.05, benchmark_nav=0.99, db_path=db)
    upsert_index_closes(
        [("000300", "2026-09-26", 4000.0), ("000300", "2026-10-09", 4040.0)], db_path=db
    )
    resp = TestClient(app).get("/api/v1/track-record/index-compare?span=all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_return"] == pytest.approx(0.05)
    by = {i["code"]: i for i in data["indices"]}
    assert by["000300"]["beat"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_track_record.py -v -k index_compare`
Expected: FAIL — 404 Not Found

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/api.py`——在 `track_record_equity_curve` 端点函数之后插入:

```python
@app.get("/api/v1/track-record/index-compare")
async def track_record_index_compare(span: str = "all") -> dict[str, Any]:
    """add-index-performance-compare:跑赢指数对比读数(展示层)。

    组合区间收益取 equity_curve 窗口首尾净值,指数收益取 index_closes 同窗口
    首尾收盘;win/loss 判定口径不变(仍锚 000300,见 docs/evals/metrics.md)。
    """
    if span not in ("all", "3m", "6m", "1y"):
        raise HTTPException(status_code=422, detail="span 必须为 all/3m/6m/1y")
    from finance_agent.outcome.track_record.index_compare import build_index_compare

    data = await asyncio.to_thread(build_index_compare, span)
    return {**data, "as_of": _track_as_of(), "disclaimer": _DISCLAIMER}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_track_record.py -v`
Expected: PASS(既有用例 + 3 个新用例全绿)

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_track_record.py
git commit -m "feat(track-record): index-compare 读数端点 (add-index-performance-compare)"
```

---

### Task 7: /api/test/seed 扩展 track_record 造数

**Files:**
- Modify: `src/finance_agent/api.py:688`(`test_seed` 内,`pipeline_snapshot` 写入之后追加)
- Test: `tests/test_api_track_record.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 `upsert_index_closes`、既有 `upsert_equity_point`/`init_track_record_tables`(均写 `_default_db_path()`——E2E 环境 `SESSIONS_DB_PATH` 已指向独立测试库)
- Produces: `POST /api/test/seed` 接受顶层可选 `track_record: {equity_curve: [{curve_date, agent_nav, benchmark_nav?}], index_closes: [{index_code, trade_date, close}]}`(仅 TESTING=1 注册,既有约束不变)

- [ ] **Step 1: Write the failing test**

`tests/test_api_track_record.py` 追加:

```python
def test_seed_track_record_block(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).post(
        "/api/test/seed",
        json={
            "track_record": {
                "equity_curve": [
                    {"curve_date": "2026-09-28", "agent_nav": 1.0, "benchmark_nav": 1.0},
                    {"curve_date": "2026-10-09", "agent_nav": 1.05, "benchmark_nav": 0.99},
                ],
                "index_closes": [
                    {"index_code": "000300", "trade_date": "2026-09-28", "close": 4000.0},
                    {"index_code": "000300", "trade_date": "2026-10-09", "close": 4040.0},
                ],
            }
        },
    )
    assert resp.status_code == 200
    data = TestClient(app).get("/api/v1/track-record/index-compare?span=all").json()
    assert data["agent_return"] == pytest.approx(0.05)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_track_record.py -v -k seed_track`
Expected: FAIL — seed 忽略 track_record 块,agent_return 为 None

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/api.py` 的 `test_seed` 内,`update_pipeline_snapshot(session_id, pipeline_snapshot)` 块之后追加:

```python
        # add-index-performance-compare:战绩页 E2E 造数(equity_curve/index_closes
        # 写入真实存储层;SESSIONS_DB_PATH 已被 e2e webServer 指向独立测试库)
        track_seed = req.get("track_record")
        if isinstance(track_seed, dict):
            from finance_agent.outcome.track_record.model import (
                init_track_record_tables,
                upsert_equity_point,
                upsert_index_closes,
            )

            init_track_record_tables()
            for pt in track_seed.get("equity_curve", []):
                upsert_equity_point(
                    pt["curve_date"],
                    pt["agent_nav"],
                    benchmark_nav=pt.get("benchmark_nav"),
                )
            upsert_index_closes(
                [
                    (r["index_code"], r["trade_date"], r["close"])
                    for r in track_seed.get("index_closes", [])
                ]
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_track_record.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_track_record.py
git commit -m "test(api): test/seed 支持 track_record 造数 (add-index-performance-compare)"
```

---

### Task 8: 前端类型 + IndexCompareCard 组件

**Files:**
- Modify: `frontend/src/types.ts`(EquityCurveResponse 附近追加)
- Create: `frontend/src/pages/trackRecord/IndexCompareCard.tsx`
- Test: `frontend/src/test/trackRecord/indexCompareCard.test.tsx`(新建;写法参照 `frontend/src/test/trackRecord/trackRecordPage.test.tsx` 的既有 fetch mock 模式)

**Interfaces:**
- Consumes: `GET /api/v1/track-record/index-compare` 响应(Task 6)
- Produces: `IndexCompareIndex`/`IndexCompareResponse` 类型(types.ts 导出);`IndexCompareCard({ span }: { span: TrackTimeSpan })` 组件,testid 约定:`index-compare-card`、`index-compare-summary`(N/M 摘要文本)、`index-compare-empty`、`index-compare-row-{code}`

- [ ] **Step 1: Write the failing test**

新建 `frontend/src/test/trackRecord/indexCompareCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { IndexCompareCard } from '../../pages/trackRecord/IndexCompareCard'

const RESP = {
  span: 'all',
  window: { start: '2026-09-28', end: '2026-10-09' },
  agent_return: 0.05,
  indices: [
    { code: '000001', name: '上证指数', return: 0.03, effective_start_date: '2026-09-28', beat: true },
    { code: '000300', name: '沪深300', return: 0.01, effective_start_date: '2026-09-26', beat: true },
    { code: '000905', name: '中证500', return: 0.1, effective_start_date: '2026-09-28', beat: false },
    { code: '000852', name: '中证1000', return: null, effective_start_date: null, beat: null },
    { code: '399006', name: '创业板指', return: 0.02, effective_start_date: '2026-09-28', beat: true },
  ],
  as_of: '2026-10-02',
  disclaimer: '历史业绩不代表未来表现',
}

afterEach(() => vi.unstubAllGlobals())

describe('IndexCompareCard', () => {
  it('渲染 N/M 摘要并按收益降序排列,跑赢绿↑跑输红↓', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => RESP }))
    render(<IndexCompareCard span="all" />)
    await screen.findByTestId('index-compare-summary')
    expect(screen.getByTestId('index-compare-summary').textContent).toContain('跑赢 3/5 个指数')
    const rows = screen.getAllByTestId(/^index-compare-row-/)
    expect(rows.map(r => r.dataset.testid)).toEqual([
      'index-compare-row-000905', // 0.10
      'index-compare-row-399006', // 0.02
      'index-compare-row-000001', // 0.03 → 降序应为 000905, 000001, 399006
      'index-compare-row-000300',
      'index-compare-row-000852',
    ])
  })
})
```

**注意**:上面期望数组故意写错序(000905, 399006, 000001, …)以体现 TDD——正确的降序是 0.10, 0.03, 0.02, 0.01, null → `['index-compare-row-000905', 'index-compare-row-000001', 'index-compare-row-399006', 'index-compare-row-000300', 'index-compare-row-000852']`。**实现前先按此修正期望数组再跑失败**,避免把错误期望做绿。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- indexCompareCard`
Expected: FAIL — 无法解析 `../../pages/trackRecord/IndexCompareCard`

- [ ] **Step 3: Write minimal implementation**

`frontend/src/types.ts`(`EquityCurveResponse` 之后追加):

```ts
// 跑赢指数对比(add-index-performance-compare)
export interface IndexCompareIndex {
  code: string
  name: string
  return: number | null
  effective_start_date: string | null
  beat: boolean | null
}

export interface IndexCompareResponse {
  span: 'all' | '3m' | '6m' | '1y'
  window: { start: string | null; end: string | null }
  agent_return: number | null
  indices: IndexCompareIndex[]
  as_of: string
  disclaimer: string
}
```

新建 `frontend/src/pages/trackRecord/IndexCompareCard.tsx`:

```tsx
import { useEffect, useState } from 'react'

import type { IndexCompareResponse, TrackTimeSpan } from '../../types'

// 跑赢指数对比卡片(add-index-performance-compare):组合区间收益 vs 主要指数同期收益。
// span 随战绩页跨度偏好传入;指数缺数灰显,beat 直读比较(与判定链 ±2% 带无关)。
export function IndexCompareCard({ span }: { span: TrackTimeSpan }) {
  const [data, setData] = useState<IndexCompareResponse | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    setFailed(false)
    fetch(`/api/v1/track-record/index-compare?span=${span}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: IndexCompareResponse) => {
        if (alive) setData(d)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [span])

  return (
    <div data-testid="index-compare-card" className="rounded-lg border border-[var(--border-default)] p-4">
      <div className="mb-2 text-sm font-medium">跑赢指数对比</div>
      {failed && <div className="text-xs text-[var(--text-secondary)]">对比数据加载失败</div>}
      {data && data.agent_return !== null && (
        <>
          <div data-testid="index-compare-summary" className="mb-3 text-lg font-semibold">
            跑赢 {data.indices.filter(i => i.beat === true).length}/{data.indices.filter(i => i.beat !== null).length} 个指数
          </div>
          <div className="flex flex-col gap-1.5">
            {[...data.indices]
              .sort((a, b) => (b.return ?? -Infinity) - (a.return ?? -Infinity))
              .map(i => (
                <div key={i.code} data-testid={`index-compare-row-${i.code}`} className="flex items-center gap-2 text-sm">
                  <span className="w-20 shrink-0">{i.name}</span>
                  {i.return === null ? (
                    <span className="text-[var(--text-secondary)]">无数据</span>
                  ) : (
                    <>
                      <span className="flex-1">
                        {(i.return * 100).toFixed(2)}%
                        {i.effective_start_date !== data.window.start && (
                          <span className="ml-1 text-xs text-[var(--text-secondary)]">
                            (自 {i.effective_start_date} 起算)
                          </span>
                        )}
                      </span>
                      <span style={{ color: i.beat ? 'var(--status-success-default)' : 'var(--status-error-default)' }}>
                        {i.beat ? '↑ 跑赢' : '↓ 跑输'}
                      </span>
                    </>
                  )}
                </div>
              ))}
          </div>
        </>
      )}
      {data && data.agent_return === null && (
        <div data-testid="index-compare-empty" className="text-xs text-[var(--text-secondary)]">
          净值数据积累中,暂无法对比
        </div>
      )}
      <div className="mt-2 text-xs text-[var(--text-secondary)]">{data?.disclaimer}</div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- indexCompareCard`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/trackRecord/IndexCompareCard.tsx frontend/src/test/trackRecord/indexCompareCard.test.tsx
git commit -m "feat(frontend): 跑赢指数对比卡片组件 (add-index-performance-compare)"
```

---

### Task 9: 战绩页接入 + 页面单测

**Files:**
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`(净值图卡片之后挂载)
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`(追加用例)

**Interfaces:**
- Consumes: Task 8 的 `IndexCompareCard({ span })`
- Produces: 战绩页净值图区块之后渲染 `<IndexCompareCard span={prefs.timeSpan} />`(prefs 为页面既有 `loadTrackPrefs()` 读取,与净值图同源)

- [ ] **Step 1: Write the failing test**

`trackRecordPage.test.tsx` 追加(沿用该文件既有 fetch mock 模式;在既有 mock 响应表里补 `index-compare` 路由):

```tsx
describe('战绩页:跑赢指数对比卡片', () => {
  it('渲染卡片与摘要', async () => {
    // 沿用文件内既有 renderPage/mock 设施;fetch mock 表新增:
    // /api/v1/track-record/index-compare → 上一个测试文件的 RESP 结构
    renderTrackRecordPage()
    const card = await screen.findByTestId('index-compare-card')
    expect(card).toBeVisible()
    expect(await screen.findByTestId('index-compare-summary')).toHaveTextContent(/跑赢 \d+\/\d+ 个指数/)
  })
})
```

(实现者按该文件既有 helper 的真实名字改写;断言不变:卡片可见 + 摘要文本匹配。)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- trackRecordPage`
Expected: FAIL — 找不到 `index-compare-card`

- [ ] **Step 3: Write minimal implementation**

`TrackRecordPage.tsx`:顶部 `import { IndexCompareCard } from './IndexCompareCard'`;在净值图所在区块的闭合标签之后(约 `prefs.navChartForm` 面板同级、下一区块之前)插入:

```tsx
          <IndexCompareCard span={prefs.timeSpan} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS(全量前端单测,防既有快照/查询回归)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test/trackRecord/trackRecordPage.test.tsx
git commit -m "feat(frontend): 战绩页挂载跑赢指数对比卡片 (add-index-performance-compare)"
```

---

### Task 10: E2E spec(门禁)

**Files:**
- Create: `tests/e2e/playwright/tests/track-record-index-compare.spec.ts`

**Interfaces:**
- Consumes: Task 7 的 `/api/test/seed` track_record 造数;Task 9 的页面挂载
- Produces: 默认门禁 config 下自动纳入(不在 testIgnore 名单);红线:不 mock 业务接口,数据经 seed 端点写真实测试库

- [ ] **Step 1: Write the spec**

```ts
import { expect, test } from '@playwright/test'

/**
 * add-index-performance-compare:跑赢指数对比卡片 E2E 门禁。
 * 红线:不 mock /api/v1/track-record/*;数据经 TESTING=1 的 /api/test/seed 写入
 * 独立测试库(e2e webServer 的 SESSIONS_DB_PATH)。测试间有数据依赖,串行执行。
 */
test.describe.configure({ mode: 'serial' })

test.describe('战绩页:跑赢指数对比', () => {
  test('无数据时空态渲染,卡片可见', async ({ page }) => {
    await page.goto('/track-record')
    await expect(page.getByTestId('track-record')).toBeVisible()
    await expect(page.getByTestId('index-compare-card')).toBeVisible()
    await expect(page.getByTestId('index-compare-empty')).toBeVisible()
  })

  test('造数后渲染摘要与对比条,跑赢/跑输分色', async ({ page, request }) => {
    const seedResp = await request.post('http://localhost:8000/api/test/seed', {
      data: {
        track_record: {
          equity_curve: [
            { curve_date: '2026-09-01', agent_nav: 1.0, benchmark_nav: 1.0 },
            { curve_date: '2026-09-30', agent_nav: 1.05, benchmark_nav: 0.99 },
          ],
          index_closes: [
            { index_code: '000001', trade_date: '2026-09-01', close: 3000.0 },
            { index_code: '000001', trade_date: '2026-09-30', close: 3060.0 }, // +2% 跑输
            { index_code: '000300', trade_date: '2026-09-01', close: 4000.0 },
            { index_code: '000300', trade_date: '2026-09-30', close: 4040.0 }, // +1% 跑输
            { index_code: '000905', trade_date: '2026-09-01', close: 6000.0 },
            { index_code: '000905', trade_date: '2026-09-30', close: 5940.0 }, // -1% 跑赢
            { index_code: '000852', trade_date: '2026-09-01', close: 2500.0 },
            { index_code: '000852', trade_date: '2026-09-30', close: 2450.0 }, // -2% 跑赢
            // 399006 不造 → 无数据灰显,摘要分母为 4
          ],
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto('/track-record')
    await expect(page.getByTestId('index-compare-summary')).toHaveText(/跑赢 2\/4 个指数/)
    const row300 = page.getByTestId('index-compare-row-000300')
    await expect(row300).toContainText('↓ 跑输')
    const row905 = page.getByTestId('index-compare-row-000905')
    await expect(row905).toContainText('↑ 跑赢')
    const row006 = page.getByTestId('index-compare-row-399006')
    await expect(row006).toContainText('无数据')
  })

  test('跨度偏好决定请求参数', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('fa_track_prefs', JSON.stringify({ timeSpan: '3m', benchmark: 'none', drawdownThreshold: 0.2, navChartForm: 'cumulative' }))
    })
    const spanReq = page.waitForRequest(r => r.url().includes('/api/v1/track-record/index-compare') && r.url().includes('span=3m'))
    await page.goto('/track-record')
    await expect(spanReq).toPass()
  })
})
```

**注意**(实现者核对):① serial 模式下第一个「空态」用例依赖库内无 curve 数据——若本地测试库残留数据,先删 `data/test-e2e-sessions.db*` 再跑;② `/track-record` 在无会话数据时的其余空态已由 decisions.spec.ts 覆盖,本 spec 不重复;③ 断言稳定的终态文本,不用 waitForTimeout。

- [ ] **Step 2: Run E2E**

Run: `cd tests/e2e/playwright && npx playwright test track-record-index-compare.spec.ts`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/playwright/tests/track-record-index-compare.spec.ts
git commit -m "test(e2e): 跑赢指数对比卡片门禁 spec (add-index-performance-compare)"
```

---

### Task 11: 全量验证与收口

**Files:**
- Create: `tests/validation/2026-10-02-add-index-performance-compare-validation.md`

**Interfaces:**
- Consumes: 前 10 个任务的全部产物
- Produces: 验证证据 + 人工验证报告草稿

- [ ] **Step 1: 后端静态与测试**

Run: `uv run ruff check && uv run mypy && uv run pytest tests/outcome/test_index_compare.py tests/test_api_track_record.py -v`
Expected: 全绿、0 error。随后跑全量 `uv run pytest`(Langfuse Docker 需在线;若卡住先查容器状态,见 AGENTS.md)。

- [ ] **Step 2: 前端测试**

Run: `cd frontend && npm test`
Expected: 全绿

- [ ] **Step 3: E2E 门禁(全量 stub 套件)**

Run: `cd tests/e2e/playwright && npx playwright test`
Expected: 全绿(新增 spec 已入门禁;既有 spec 无回归)。报告路径记入验证材料。

- [ ] **Step 4: 生产环境冒烟**

Docker 重建后端(`docker compose up -d --build backend`),执行 Task 4 Step 3 的回填(若尚未执行),curl 冒烟:
`curl -s "http://127.0.0.1:8000/api/v1/track-record/index-compare?span=3m" | python -m json.tool`
Expected: 200,indices 五条,真实指数读数与行情软件同期数字抽验一致(±0.1pct)。

- [ ] **Step 5: 人工验证报告落盘**

写 `tests/validation/2026-10-02-add-index-performance-compare-validation.md`,按 project-workflow §5 模板:卡片视觉抽查、真实读数抽验(与行情源核对)、E2E 报告路径、异常记录;结论栏留待人工勾选。

- [ ] **Step 6: 收尾提交**

```bash
git add tests/validation/2026-10-02-add-index-performance-compare-validation.md
git commit -m "test(validation): 跑赢指数对比人工验证报告 (add-index-performance-compare)"
```

---

## Self-Review

1. **Spec coverage**:index-comparison 两需求(读数 6 场景→Task 5/6 全覆盖含基期回退/中段起算/全缺/净值不足/跨度截断;落库 3 场景→Task 2/3/4);track-record-metrics MODIFIED(盯市不受影响→Task 3 Step 5 回归);frontend 4 场景→Task 8/9/10。✔ 无缺口。
2. **Placeholder scan**:Task 9 Step 1 的测试代码标注「按该文件既有 helper 真实名字改写」——这是有意的适配说明,断言与 testid 已写死,不算占位符。Task 1 Step 1 测试代码完整。✔
3. **Type consistency**:`upsert_index_closes(list[tuple[str,str,float]]) -> int`、`list_index_closes(code, end, db_path)`、`sync_index_closes(*, client, db_path, days) -> {stored, failed}`、`build_index_compare(span, db_path) -> {span, window, agent_return, indices}` 在 Task 1/2/5/6/7 间签名一致;前端 `IndexCompareResponse` 字段与端点响应一一对应。✔
