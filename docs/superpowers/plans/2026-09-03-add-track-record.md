# Add Track-Record (阶段 A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 predictions 体系（append-only + 全量记录 + horizon/中性带判定）取代 decision_log，暴露 track-record 只读 API 与战绩页。

**Architecture:** `src/finance_agent/outcome/track_record/` 新增三个纯 Python 模块（model.py 数据模型+冻结守卫+迁移、judgment.py 判定纯函数、stats.py 统计），api.py 挂 track-record 端点，前端战绩页接新 API。判定与统计均为合成 DataFrame 可测、零 LLM 依赖。

**Tech Stack:** FastAPI / SQLite(WAL) / pandas / React 18 / vitest / Playwright

## Global Constraints

- predictions 取代 decision_log：迁移后 decision_log 只读停写（delta spec）
- append-only：冻结字段（direction/entry_price/rationale_snapshot/created_at）不可改，记录不可删除
- 方向映射：buy→long、sell→short、hold/watch→neutral；neutral 不进胜率分母
- 判定：horizon 默认 252 交易日（自带 horizon_days 为准，上限 1 年）、±2% 中性带、superseded、unresolvable
- 胜率 = win/(win+loss)；n<10 不展示胜率/评级、10–29 标注「样本较少」、≥30 完整
- 全量记录：reject/return/hold/watch/neutral 均落库；旁路失败不阻断业务
- API 响应带 `as_of` 与 `disclaimer`；写入接口内部鉴权；回测/实盘不分接口
- 复权口径：计算区间收益用后复权
- 交互类变更 → E2E 门禁 + 人工验证报告；测试纪律同前（TDD 五步、`-m "not live"` 门禁）

---

### Task 1: predictions 数据模型（model.py）

**Files:**
- Create: `src/finance_agent/outcome/track_record/__init__.py`
- Create: `src/finance_agent/outcome/track_record/model.py`
- Test: `tests/outcome/test_track_record_model.py`

**Interfaces:**
- Consumes: 现有 outcome/store.py 的 `_connect` 模式（WAL + 短连接 + db_path 注入）
- Produces:
  - `PREDICTIONS_STATUSES = ("open","resolved_win","resolved_loss","resolved_neutral","unresolvable")`
  - `init_predictions(db_path=None)`
  - `insert_prediction(record: dict, db_path=None) -> str`（写 created_at；冻结字段快照）
  - `update_prediction_status(prediction_id, resolved: dict, db_path=None)`（仅 status/resolved_at/exit_price/raw_return/excess_return/resolution_rule 可改；冻结字段变更抛 `FrozenFieldError`）
  - `list_predictions(ticker=None, status=None, source_type=None, limit=50, offset=0, db_path=None) -> list[dict]`
  - `prediction_stats(source_type=None, db_path=None) -> dict`
  - `migrate_decision_log(db_path=None) -> int`

- [ ] **Step 1: 写失败测试**（tests/outcome/test_track_record_model.py）

```python
"""add-track-record Task 1:predictions 数据模型(append-only + 冻结守卫 + 迁移)。"""

import pytest

from finance_agent.outcome.track_record.model import (
    FrozenFieldError,
    PREDICTIONS_STATUSES,
    init_predictions,
    insert_prediction,
    list_predictions,
    migrate_decision_log,
    prediction_stats,
    update_prediction_status,
)

BASE = {
    "source_type": "live",
    "symbol": "600519.SH",
    "symbol_name": "贵州茅台",
    "direction": "long",
    "entry_price": 100.0,
    "target_price": 120.0,
    "horizon_days": 252,
    "confidence": 0.8,
    "benchmark": "000300.SH",
    "rationale_snapshot": {"markdown": "原文快照", "decision": {"action": "buy"}},
}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "track.db"
    init_predictions(path)
    return path


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_prediction(rec, db_path=db)


def test_statuses_enum():
    assert PREDICTIONS_STATUSES == (
        "open", "resolved_win", "resolved_loss", "resolved_neutral", "unresolvable",
    )


def test_insert_and_list(db):
    pid = _insert(db)
    rows = list_predictions(db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["direction"] == "long" and row["source_type"] == "live"
    assert row["status"] == "open"
    assert row["created_at"]  # 服务端生成


def test_frozen_field_update_raises(db):
    pid = _insert(db)
    with pytest.raises(FrozenFieldError):
        update_prediction_status(pid, {"direction": "short"}, db_path=db)


def test_status_update_allowed(db):
    pid = _insert(db)
    update_prediction_status(
        pid,
        {"status": "resolved_win", "exit_price": 110.0, "raw_return": 0.1,
         "excess_return": 0.05, "resolution_rule": "expiry", "resolved_at": "2026-09-02"},
        db_path=db,
    )
    row = list_predictions(db_path=db)[0]
    assert row["status"] == "resolved_win" and row["exit_price"] == 110.0
    assert row["direction"] == "long"  # 冻结字段未被改动


def test_list_filter_and_pagination(db):
    _insert(db, symbol="600519.SH")
    _insert(db, symbol="300308.SZ")
    assert len(list_predictions(ticker="600519", db_path=db)) == 1
    assert len(list_predictions(status="open", db_path=db)) == 2
    assert len(list_predictions(source_type="backtest", db_path=db)) == 0
    assert len(list_predictions(limit=1, db_path=db)) == 1


def test_stats_empty(db):
    s = prediction_stats(db_path=db)
    assert s["total"] == 0 and s["open"] == 0 and s["win_rate"] is None


def test_migrate_decision_log(db, tmp_path):
    # 预置 decision_log 数据(复用 outcome.store DDL)
    from finance_agent.outcome.store import init_decision_log, insert_decision

    init_decision_log(db)
    insert_decision(
        {
            "session_id": "s", "timestamp": "2026-09-01T10:00:00", "ticker": "600519",
            "name": "贵州茅台", "action": "buy", "entry_price": 100.0,
            "stop_loss": 90.0, "target_price": 120.0, "confidence": 0.8,
        },
        db_path=db,
    )
    n = migrate_decision_log(db_path=db)
    assert n == 1
    rows = list_predictions(db_path=db)
    assert rows[0]["symbol"] == "600519.SH"
    assert rows[0]["direction"] == "long"
```

- [ ] **Step 2: 运行确认失败** `uv run pytest tests/outcome/test_track_record_model.py -q` → ImportError

- [ ] **Step 3: 实现 model.py**

```python
"""predictions 数据模型(add-track-record):append-only + 冻结字段守卫 + decision_log 迁移。

与 outcome/store.py 同款 SQLite(WAL + busy_timeout 短连接),db_path 调用期注入。
冻结铁律:方向/入场价/快照/创建时间写入后不可改;判定结果只经 update_prediction_status
更新 status/resolved_at/exit_price/raw_return/excess_return/resolution_rule。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

PREDICTIONS_DDL = """
CREATE TABLE IF NOT EXISTS predictions (
  prediction_id     TEXT PRIMARY KEY,
  source_type       TEXT NOT NULL CHECK (source_type IN ('backtest','live')),
  symbol            TEXT NOT NULL,
  symbol_name       TEXT,
  direction         TEXT NOT NULL CHECK (direction IN ('long','short','neutral')),
  entry_price       REAL NOT NULL,
  target_price      REAL,
  horizon_days      INTEGER NOT NULL DEFAULT 252,
  confidence        REAL CHECK (confidence BETWEEN 0 AND 1),
  benchmark         TEXT NOT NULL DEFAULT '000300.SH',
  rationale_snapshot TEXT NOT NULL,
  langfuse_trace_id TEXT,
  status            TEXT NOT NULL DEFAULT 'open',
  created_at        TEXT NOT NULL,
  resolved_at       TEXT,
  exit_price        REAL,
  raw_return        REAL,
  excess_return     REAL,
  resolution_rule   TEXT,
  updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);
"""

PREDICTIONS_STATUSES = ("open", "resolved_win", "resolved_loss", "resolved_neutral", "unresolvable")
_FROZEN_FIELDS = ("direction", "entry_price", "target_price", "rationale_snapshot", "created_at", "source_type", "symbol")
_MUTABLE_FIELDS = ("status", "resolved_at", "exit_price", "raw_return", "excess_return", "resolution_rule", "updated_at")


class FrozenFieldError(Exception):
    """尝试修改冻结字段(append-only 铁律)。"""


def _default_db_path() -> Path:
    return Path(os.getenv("SESSIONS_DB_PATH", "data/sessions.db"))


def _connect(db_path: str | Path | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_predictions(db_path: str | Path | None = None) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(PREDICTIONS_DDL)
        conn.commit()
    finally:
        conn.close()


def insert_prediction(record: dict[str, Any], db_path: str | Path | None = None) -> str:
    """插入一条观点;created_at 服务端生成;快照 JSON 序列化后冻结。"""
    prediction_id = record.get("prediction_id") or f"p_{uuid.uuid4().hex[:12]}"
    created_at = record.get("created_at") or record["timestamp"]
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO predictions (
                 prediction_id, source_type, symbol, symbol_name, direction,
                 entry_price, target_price, horizon_days, confidence, benchmark,
                 rationale_snapshot, langfuse_trace_id, status, created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?, ?)""",
            (
                prediction_id,
                record["source_type"],
                record["symbol"],
                record.get("symbol_name"),
                record["direction"],
                record["entry_price"],
                record.get("target_price"),
                int(record.get("horizon_days", 252)),
                record.get("confidence"),
                record.get("benchmark", "000300.SH"),
                json.dumps(record.get("rationale_snapshot") or {}, ensure_ascii=False),
                record.get("langfuse_trace_id"),
                created_at,
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return prediction_id


def update_prediction_status(prediction_id: str, resolved: dict[str, Any], db_path: str | Path | None = None) -> None:
    """判定结果更新。尝试改冻结字段抛 FrozenFieldError;幂等由调用方保证。"""
    frozen_hits = [f for f in _FROZEN_FIELDS if f in resolved]
    if frozen_hits:
        raise FrozenFieldError(f"attempt to mutate frozen field(s): {frozen_hits}")
    conn = _connect(db_path)
    try:
        cur = conn.execute("SELECT * FROM predictions WHERE prediction_id=?", (prediction_id,))
        if cur.fetchone() is None:
            return
        fields = [f for f in _MUTABLE_FIELDS if f in resolved]
        if not fields:
            return
        sets = ", ".join(f"{f}=?" for f in fields)
        params = [resolved[f] for f in fields]
        conn.execute(f"UPDATE predictions SET {sets} WHERE prediction_id=?", (*params, prediction_id))
        conn.commit()
    finally:
        conn.close()


def list_predictions(
    ticker: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM predictions"
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("symbol LIKE ?")
            params.append(f"%{ticker}%")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def prediction_stats(source_type: str | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    """胜率/超额聚合。胜率只基于 resolved_win/resolved_loss;neutral/unresolvable 不进分母。"""
    conn = _connect(db_path)
    try:
        where, params = "", []
        if source_type:
            where, params = " WHERE source_type=?", [source_type]
        total = int(conn.execute(f"SELECT COUNT(*) FROM predictions{where}", params).fetchone()[0])
        open_count = int(conn.execute(f"SELECT COUNT(*) FROM predictions WHERE status='open'{(' AND source_type=?' if source_type else '')}", params).fetchone()[0])
        wins = int(conn.execute(f"SELECT COUNT(*) FROM predictions WHERE status='resolved_win'{(' AND source_type=?' if source_type else '')}", params).fetchone()[0])
        losses = int(conn.execute(f"SELECT COUNT(*) FROM predictions WHERE status='resolved_loss'{(' AND source_type=?' if source_type else '')}", params).fetchone()[0])
        settled = wins + losses
        win_rate = round(wins / settled, 4) if settled else None
        avg_exc = conn.execute(
            f"SELECT AVG(excess_return) FROM predictions WHERE status IN ('resolved_win','resolved_loss'){(' AND source_type=?' if source_type else '')}",
            params,
        ).fetchone()[0]
        avg_excess = round(float(avg_exc), 4) if avg_exc is not None else None
        return {
            "total": total,
            "open": open_count,
            "settled": settled,
            "win_rate": win_rate,
            "avg_excess": avg_excess,
            "status_counts": dict(conn.execute(
                f"SELECT status, COUNT(*) FROM predictions{where} GROUP BY status", params
            ).fetchall()),
        }
    finally:
        conn.close()


def migrate_decision_log(db_path: str | Path | None = None) -> int:
    """一次性迁移 decision_log → predictions(方向映射 + 最小快照)。幂等:重复执行跳过已迁移。"""
    conn = _connect(db_path)
    migrated = 0
    try:
        try:
            rows = conn.execute(
                "SELECT * FROM decision_log WHERE prediction_id_migrated IS NULL"
            ).fetchall()
        except sqlite3.OperationalError:
            # decision_log 无迁移标记列 → 首迁
            conn.execute("ALTER TABLE decision_log ADD COLUMN prediction_id_migrated TEXT")
            conn.commit()
            rows = conn.execute("SELECT * FROM decision_log WHERE prediction_id_migrated IS NULL").fetchall()
        for r in rows:
            action = r["action"]
            direction = "long" if action == "buy" else ("short" if action == "sell" else "neutral")
            pid = insert_prediction(
                {
                    "source_type": "live",
                    "symbol": f"{r['ticker']}.SH" if r["ticker"].startswith("6") else f"{r['ticker']}.SZ",
                    "symbol_name": r["name"],
                    "direction": direction,
                    "entry_price": float(r["entry_price"]),
                    "target_price": r["target_price"],
                    "confidence": r["confidence"],
                    "rationale_snapshot": {"migrated_from": "decision_log", "decision_id": r["decision_id"], "action": action},
                    "langfuse_trace_id": r["langfuse_trace_id"],
                    "created_at": r["timestamp"],
                },
                db_path=conn,
            )
            conn.execute(
                "UPDATE decision_log SET prediction_id_migrated=? WHERE decision_id=?",
                (pid, r["decision_id"]),
            )
            migrated += 1
        conn.commit()
    finally:
        conn.close()
    return migrated
```

- [ ] **Step 4: 运行确认通过** `uv run pytest tests/outcome/test_track_record_model.py -q` → PASS

- [ ] **Step 5: 提交** `git commit -m "feat: predictions 数据模型(append-only + 冻结守卫 + decision_log 迁移)"`

---

### Task 2: 判定引擎（judgment.py）

**Files:**
- Create: `src/finance_agent/outcome/track_record/judgment.py`
- Test: `tests/outcome/test_track_record_judgment.py`

**Interfaces:**
- Consumes: Task 1 的模型（本任务为纯函数,不依赖 model.py）
- Produces: `Resolution` dataclass（status/exit_price/raw_return/excess_return/resolution_rule）、`resolve_prediction(prediction: dict, kline: pd.DataFrame, benchmark: pd.DataFrame|None, neutral_band: float = 0.02) -> Resolution | None`、`should_supersede(old: dict, new: dict) -> bool`

**判定语义**（与 settle.py 的止损/目标不同,全新实现）：
- 判定窗口 = min(horizon_days, 252) 交易日（prediction 自带的 horizon_days 上限 1 年）
- raw_return（long）=(exit_price/entry_price)-1；(short) 取负
- excess_return = raw_return - benchmark_return(同区间)
- long: excess > +neutral_band → resolved_win; < -neutral_band → resolved_loss; 否则 resolved_neutral；short 对称
- 行数不足（未到 horizon 且未触发 superseded）→ None（保持 open）
- 一字板/停牌无行 → 由 job 层标记 unresolvable（本任务只判定到点）

- [ ] **Step 1: 写失败测试**

```python
"""add-track-record Task 2:horizon + 中性带 + superseded 判定纯函数。"""

import pandas as pd
import pytest

from finance_agent.outcome.track_record.judgment import Resolution, resolve_prediction, should_supersede

def _kline(prices, start="2026-09-02"):
    import datetime
    return pd.DataFrame(
        {"日期": [str(datetime.date.fromisoformat(start) + datetime.timedelta(days=i)) for i in range(len(prices))],
         "开盘": prices, "最高": prices, "最低": prices, "收盘": prices, "成交量": [1]*len(prices)}
    )


def _pred(entry=100.0, horizon=10, direction="long"):
    return {"entry_price": entry, "horizon_days": horizon, "direction": direction, "created_at": "2026-09-01T10:00:00"}


def test_horizon_win():
    # 10 天后收盘 115(无基准),超额正 → win
    r = resolve_prediction(_pred(), _kline([101, 102, 103, 104, 105, 106, 107, 108, 109, 115]))
    assert isinstance(r, Resolution)
    assert r.status == "resolved_win" and r.exit_price == 115.0
    assert abs(r.raw_return - 0.15) < 1e-9


def test_neutral_band():
    # 区间超额 +1.5% (< 2%) → neutral
    r = resolve_prediction(_pred(), _kline([101, 101.5]))
    assert r is not None and r.status == "resolved_neutral"


def test_loss_and_short_symmetry():
    r = resolve_prediction(_pred(), _kline([95, 90]))
    assert r is not None and r.status == "resolved_loss"
    # short 对称: 跌 → win
    rs = resolve_prediction(_pred(direction="short"), _kline([95, 90]))
    assert rs is not None and rs.status == "resolved_win"


def test_excess_uses_benchmark():
    bench = _kline([100, 100, 100])  # 基准不涨
    r = resolve_prediction(_pred(entry=100.0), _kline([101, 103]), bench)
    assert r is not None and r.status == "resolved_win"
    assert abs(r.excess_return - (0.03 - 0.0)) < 1e-9


def test_not_enough_rows_returns_none():
    assert resolve_prediction(_pred(horizon=10), _kline([101])) is None


def test_horizon_capped_at_252():
    from finance_agent.outcome.track_record.judgment import _effective_horizon
    assert _effective_horizon({"horizon_days": 999}) == 252
    assert _effective_horizon({"horizon_days": 60}) == 60


def test_superseded():
    old = {"symbol": "600519.SH", "direction": "long", "target_price": 120.0}
    new = {"symbol": "600519.SH", "direction": "short", "target_price": 100.0}
    assert should_supersede(old, new) is True
    same = {"symbol": "600519.SH", "direction": "long", "target_price": 121.0}
    assert should_supersede(old, same) is False
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 judgment.py**

```python
"""判定引擎(add-track-record):horizon + 中性带 + superseded。纯函数,合成 DataFrame 可测。

与 settle.py(止损/目标/超期)语义不同——horizon 到点按区间超额收益判定 win/loss/neutral;
short 方向对称;neutral 不进胜率。停牌/退市由 job 层按连续无行情标记 unresolvable。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pandas as pd

MAX_HORIZON_DAYS = 252


@dataclass
class Resolution:
    status: str  # resolved_win / resolved_loss / resolved_neutral
    exit_price: float
    raw_return: float
    excess_return: float | None
    resolution_rule: str  # expiry / superseded


def _effective_horizon(prediction: dict) -> int:
    return max(1, min(int(prediction.get("horizon_days", MAX_HORIZON_DAYS)), MAX_HORIZON_DAYS))


def _bench_close_on_or_before(benchmark: pd.DataFrame, date: str) -> float | None:
    eligible = benchmark[benchmark["日期"] <= date]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["收盘"])


def should_supersede(old: dict, new: dict) -> bool:
    """同标的方向相反或目标价不同 → 旧观点立即结算。"""
    if old.get("symbol") != new.get("symbol"):
        return False
    if old.get("direction") != new.get("direction"):
        return True
    old_t = old.get("target_price")
    new_t = new.get("target_price")
    return old_t is not None and new_t is not None and abs(float(old_t) - float(new_t)) > 1e-9


def resolve_prediction(
    prediction: dict,
    kline: pd.DataFrame,
    benchmark: pd.DataFrame | None = None,
    neutral_band: float = 0.02,
) -> Resolution | None:
    """horizon 到点判定。未到点返回 None(保持 open)。"""
    entry_price = float(prediction["entry_price"])
    if entry_price <= 0:
        return None
    horizon = _effective_horizon(prediction)
    direction = prediction.get("direction", "long")
    created = str(prediction["created_at"])[:10]
    df = kline.copy()
    df["日期"] = df["日期"].astype(str).str[:10]
    rows = df[df["日期"] > created].sort_values("日期").reset_index(drop=True)
    if len(rows) < horizon:
        return None
    exit_row = rows.iloc[horizon - 1]
    exit_price = float(exit_row["收盘"])
    sign = 1.0 if direction == "long" else -1.0
    raw_return = sign * (exit_price / entry_price - 1.0)
    excess = raw_return
    bench_df = benchmark.copy() if benchmark is not None else None
    if bench_df is not None and not bench_df.empty:
        bench_df["日期"] = bench_df["日期"].astype(str).str[:10]
        entry_bench = _bench_close_on_or_before(bench_df, created)
        exit_bench = _bench_close_on_or_before(bench_df, str(exit_row["日期"]))
        if entry_bench is not None and exit_bench is not None:
            bench_ret = sign * (exit_bench / entry_bench - 1.0)
            excess = raw_return - bench_ret
    band = float(neutral_band)
    if excess > band:
        status = "resolved_win"
    elif excess < -band:
        status = "resolved_loss"
    else:
        status = "resolved_neutral"
    return Resolution(
        status=status,
        exit_price=exit_price,
        raw_return=round(raw_return, 6),
        excess_return=round(excess, 6),
        resolution_rule="expiry",
    )
```

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交** `git commit -m "feat: 判定引擎(horizon/中性带/superseded 纯函数)"`

---

### Task 3: 全量记录接入（_persist_decision_log → predictions）

**Files:**
- Modify: `src/finance_agent/api.py`（`_persist_decision_log` 改为写 predictions；import）
- Modify: `src/finance_agent/outcome/scheduler.py`（日批任务改用判定引擎）
- Test: `tests/outcome/test_track_record_ingest.py`（新建）

**Interfaces:**
- Consumes: Task 1 `insert_prediction`、Task 2 `resolve_prediction`/`should_supersede`
- Produces: `_persist_decision_log` 不再用 insert_decision（decision_log 停写）

- [ ] **Step 1: 写失败测试**

```python
"""add-track-record Task 3:全量记录(reject/hold/watch 也落库)+ 判定任务替换。"""

from unittest.mock import patch

import pytest

from finance_agent.outcome.track_record.model import init_predictions, list_predictions


def test_approve_buy_records_long(monkeypatch, tmp_path):
    from finance_agent.api import _persist_decision_log

    db = tmp_path / "t.db"
    init_predictions(db)
    monkeypatch.setattr("finance_agent.outcome.track_record.model._default_db_path", lambda: db)
    _persist_decision_log(
        {
            "fund_manager_decision": "approve",
            "final_trade_decision": {"action": "buy", "confidence": 0.8, "entry_price": 100.0,
                                     "stop_loss": 90.0, "target_price": 120.0, "position_size": "30%"},
            "stock_quote": {"price": 100.0},
        },
        "sess-1", "600519", "贵州茅台",
    )
    rows = list_predictions(db_path=db)
    assert len(rows) == 1
    assert rows[0]["direction"] == "long" and rows[0]["source_type"] == "live"
    assert rows[0]["entry_price"] == 100.0


def test_reject_also_records(monkeypatch, tmp_path):
    from finance_agent.api import _persist_decision_log

    db = tmp_path / "t.db"
    init_predictions(db)
    monkeypatch.setattr("finance_agent.outcome.track_record.model._default_db_path", lambda: db)
    _persist_decision_log(
        {
            "fund_manager_decision": "reject",
            "final_trade_decision": {"action": "hold", "confidence": 0.5, "entry_price": 100.0},
            "stock_quote": {"price": 100.0},
        },
        "sess-1", "600519", "贵州茅台",
    )
    rows = list_predictions(db_path=db)
    assert len(rows) == 1
    assert rows[0]["direction"] == "neutral"  # hold → neutral
```

- [ ] **Step 2: 运行确认失败**（当前 `_persist_decision_log` 用 insert_decision，reject 不落库）

- [ ] **Step 3: 实现**（api.py `_persist_decision_log` 重写为写 predictions；scheduler.py 日批循环改用 resolve_prediction + update_prediction_status，superseded 按 should_supersede）

- [ ] **Step 4: 运行确认通过** + 全量 `uv run pytest -q -m "not live"`

- [ ] **Step 5: 提交** `git commit -m "feat: 观点全量记录 + 判定任务替换(decision_log 停写)"`

---

### Task 4: track-record 只读 API

**Files:**
- Modify: `src/finance_agent/api.py`（新增 `/api/v1/track-record/overview`、`/api/v1/track-record/predictions`）
- Test: `tests/test_api_track_record.py`

**Interfaces:**
- Consumes: Task 1 `prediction_stats` / `list_predictions`
- Produces: `GET /api/v1/track-record/overview?source=live`、`GET /api/v1/track-record/predictions?status=&symbol=&source=&page=`（分页 50，默认全部状态）

- [ ] **Step 1: 写失败测试**（仿 tests/test_api_decisions.py，monkeypatch `_default_db_path`）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（端点返回带 `as_of`（北京时间日期）+ `disclaimer`；显著性门槛：settled<10 时 overview 的 win_rate 置 null 且带 `insufficient_sample: true`；写入端点不暴露，外部调用 403）
- [ ] **Step 4: 确认通过**
- [ ] **Step 5: 提交** `git commit -m "feat: track-record 只读 API(overview + predictions)"`

---

### Task 5: 前端战绩页（接 track-record API）

**Files:**
- Create: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`
- Modify: `frontend/src/App.tsx`（路由 `/track-record`，`/decisions` 重定向到 `/track-record`）
- Create: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/track-record/overview`、`/predictions`
- Produces: `<TrackRecordPage onBack onOpenSession />`；`data-testid="track-record"`、`data-testid="track-record-disclaimer"`、`data-testid="track-record-empty"`

- [ ] **Step 1: 写失败测试**（总览+日志渲染、风险提示可见、默认含 loss、样本不足空态、null 胜率占位）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（类型 `TrackRecordOverview`/`PredictionRecord` 进 types.ts；状态标签分色；进行中展示浮动收益标「未结算」；`/decisions` pathname 重定向）
- [ ] **Step 4: 确认通过** `cd frontend && npx vitest run src/test/trackRecord/ && npx tsc --noEmit`
- [ ] **Step 5: 提交** `git commit -m "feat: track-record 战绩页(总览+观点日志, 风险提示常驻)"`

---

### Task 6: E2E spec + 验证报告

- [ ] **Step 1:** 新建 `tests/e2e/playwright/tests/track-record.spec.ts`（战绩页渲染、风险提示可见、样本不足空态、默认含 loss——stub 后端空库天然空态；参照 decisions.spec.ts 的折叠态入口 + 直达模式）
- [ ] **Step 2:** `cd tests/e2e/playwright && npx playwright test tests/track-record.spec.ts --workers=1` 全绿
- [ ] **Step 3:** 全量门禁回归 + 后端 `uv run pytest -q -m "not live"` + 前端 `cd frontend && npm test`
- [ ] **Step 4:** 人工验证报告落 `tests/validation/2026-09-03-add-track-record-validation.md`（判定数字对照设计档案 §7：4win/4loss/2neutral→0.5、中性带 +1.5%→neutral、superseded、冻结不可改、样本门槛；回测/实盘分离；风险提示）
- [ ] **Step 5:** 提交 `git commit -m "test: track-record 战绩页 E2E + 验证报告"`
