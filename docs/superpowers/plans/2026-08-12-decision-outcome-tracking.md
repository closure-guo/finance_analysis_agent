# decision-outcome-tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 决策事后闭环:每个批准的 TradeDecision 落 `decision_log`(SQLite 旁路),日批结算(止损/目标/超期,A 股一字板/停牌规则),结算后按 `langfuse_trace_id` 反向上报 hit/return/excess 三个 Score。

**Architecture:** 新增 `src/finance_agent/outcome/` 包(store/settle/job/scheduler)。落库挂点:fund_manager 节点 approve 时捕获 `get_current_trace_id()` 入 state(节点内 OTel 上下文保证可用,复用 citation_node 同款模式),api.py 报告落库处同步插 decision_log(唯一同时持有 session_id/stock_code/quote 的位置);entry_price 由代码从 `stock_quote["price"]` 回填(kline 收盘兜底),不信 LLM。结算纯函数 + APScheduler in-process 日批(16:00 工作日,`_lifespan` 挂载,TESTING 禁用)。

**Tech Stack:** SQLite(复用 sessions.db 同库,WAL 短连接)、pandas(结算纯函数)、APScheduler(新依赖,design 决策 6)、langfuse 4.13 `create_score(trace_id=...)` 后置上报、AKShare 日 K(qfq)。

**Spec:** `openspec/changes/decision-outcome-tracking/specs/decision-outcome/spec.md`(5 个 ADDED Requirement)。

## Global Constraints

1. **旁路铁律**:decision_log 落库/结算/Score 上报任何失败 SHALL NOT 阻断业务管线(全 try/except + ERROR/WARN 日志)。spec「落库失败不阻断业务」「trace 不可查容错」。
2. **entry_price 代码回填**:`accumulated["stock_quote"]["price"]` 优先,`kline` 最后收盘兜底;SHALL NOT 用 LLM 填的 `final_trade_decision.entry_price`。无可靠价格 → WARN 跳过落库(entry_price NOT NULL)。
3. **幂等结算**:已 `settled_at` 非空的决策跳过,不重复结算/不重复上报 Score。
4. **配置**:`MAX_HOLD_DAYS`(默认 20)/`BENCHMARK_CODE`(默认 000300)/`DECISION_STALE_DAYS`(默认 5)/`DECISION_SETTLE_ENABLED`(默认开,"0" 关)——就近模块级 `os.getenv`,与项目惯例一致(session_store.py:27 等)。
5. **方向符号化**:buy 为正;sell/hold/watch 的 decision_return 与 benchmark_return 均取负(decision_excess 同步符号化)。
6. **结算优先级**:同日触及止损与目标 → 止损优先(保守);一字板(open==high==low==close)触及 → 递延至打开首日开盘价结算,hold_days 含等待日;停牌无 K 线行自然顺延(行驱动迭代),hold_days 只数有数据的交易日。
7. **评估起点**:扫描 decision_date 之后的 K 线行(T+1 起评),hold_days = 这些行的计数;超 MAX_HOLD_DAYS 未触发 → 第 MAX_HOLD_DAYS 行收盘价 expired 结算。
8. **新增依赖**:`uv add apscheduler`(design 决策 6;定时任务框架选型建议人工落 ADR,agent 不自建——验证报告注明)。
9. **测试纪律**:tmp_path DB + 显式 `db_path` 参数(store 不在 import 期读 env);mock 用 `unittest.mock.patch(..., return_value=X)`;结算测试全部合成 DataFrame,不调 LLM/网络;新测试只增不改。
10. **回归**:全量 `uv run pytest tests/ --ignore=tests/e2e --ignore=tests/scripts -m "not live" -q` 全绿(基线 715 passed / 3 deselected,main 分支口径);ruff 0;mypy 零新增(基线 75 错误)。
11. **data_stale 无状态判定**:ticker K 线最新日期落后基准 K 线最新日期 ≥ STALE_DAYS 个交易日 → WARN 告警(不加表列)。
12. **目录**:代码 `src/finance_agent/outcome/`;测试 `tests/outcome/`;验证报告 `tests/validation/`。

---

### Task 1: outcome/store.py — decision_log DDL + CRUD

**Files:**
- Create: `src/finance_agent/outcome/__init__.py`(空)
- Create: `src/finance_agent/outcome/store.py`
- Test: `tests/outcome/__init__.py`(空)、`tests/outcome/test_store.py`

**Interfaces:**
- Consumes: 无(自建连接,同 sessions.db)
- Produces:
  - `DECISION_LOG_DDL: str`(建表 + 索引 SQL)
  - `init_decision_log(db_path: str | Path | None = None) -> None`(幂等建表)
  - `insert_decision(record: dict, db_path=None) -> str`(返回 decision_id;record 键:decision_id/session_id/langfuse_trace_id/timestamp/ticker/name/action/entry_price/stop_loss/target_price/confidence/position_size)
  - `get_open_decisions(db_path=None) -> list[dict]`(status='open' 全字段行)
  - `mark_settled(decision_id: str, settled: dict, db_path=None) -> None`(settled 键:settled_at/settle_price/hold_days/decision_return/benchmark_return/decision_excess/status)

- [ ] **Step 1: Write the failing test**

```python
# tests/outcome/test_store.py
"""decision_log DDL + CRUD:幂等建表、插入、open 查询、结算更新。"""
import pytest

from finance_agent.outcome import store


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.db"
    store.init_decision_log(path)
    return path


def _record(**overrides):
    base = {
        "decision_id": "d_test001",
        "session_id": "sess-1",
        "langfuse_trace_id": "trace-abc",
        "timestamp": "2026-08-10T15:30:00",
        "ticker": "600519",
        "name": "贵州茅台",
        "action": "buy",
        "entry_price": 1700.0,
        "stop_loss": 1600.0,
        "target_price": 1900.0,
        "confidence": 0.8,
        "position_size": 0.3,
    }
    base.update(overrides)
    return base


class TestInit:
    def test_idempotent_init(self, db):
        # 重复执行不报错(幂等 DDL)
        store.init_decision_log(db)
        store.init_decision_log(db)

    def test_table_and_index_created(self, db):
        import sqlite3

        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        conn.close()
        assert "decision_log" in tables
        assert "idx_decision_log_status" in indexes


class TestInsertAndQuery:
    def test_insert_returns_id_and_open_query(self, db):
        decision_id = store.insert_decision(_record(), db)
        assert decision_id == "d_test001"
        rows = store.get_open_decisions(db)
        assert len(rows) == 1
        row = rows[0]
        assert row["ticker"] == "600519"
        assert row["action"] == "buy"
        assert row["entry_price"] == 1700.0
        assert row["status"] == "open"
        assert row["langfuse_trace_id"] == "trace-abc"

    def test_nullable_fields(self, db):
        store.insert_decision(_record(
            decision_id="d_test002", langfuse_trace_id=None, name=None,
            stop_loss=None, target_price=None, confidence=None, position_size=None,
        ), db)
        row = store.get_open_decisions(db)[0]
        assert row["stop_loss"] is None
        assert row["position_size"] is None


class TestMarkSettled:
    def test_settled_row_leaves_open_set(self, db):
        store.insert_decision(_record(), db)
        store.mark_settled("d_test001", {
            "status": "hit_target",
            "settled_at": "2026-08-12T16:00:00",
            "settle_price": 1900.0,
            "hold_days": 2,
            "decision_return": 0.1176,
            "benchmark_return": 0.01,
            "decision_excess": 0.1076,
        }, db)
        assert store.get_open_decisions(db) == []

    def test_settled_fields_persisted(self, db):
        import sqlite3

        store.insert_decision(_record(), db)
        store.mark_settled("d_test001", {
            "status": "hit_stop",
            "settled_at": "2026-08-12T16:00:00",
            "settle_price": 1600.0,
            "hold_days": 2,
            "decision_return": -0.0588,
            "benchmark_return": 0.005,
            "decision_excess": -0.0638,
        }, db)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM decision_log WHERE decision_id='d_test001'").fetchone()
        conn.close()
        assert row["status"] == "hit_stop"
        assert row["settle_price"] == 1600.0
        assert row["hold_days"] == 2
        assert abs(row["decision_return"] - (-0.0588)) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_store.py -v`
Expected: FAIL(ModuleNotFoundError: finance_agent.outcome)

- [ ] **Step 3: Write minimal implementation**

```python
# src/finance_agent/outcome/__init__.py
```

```python
# tests/outcome/__init__.py
```

```python
# src/finance_agent/outcome/store.py
"""decision_log 存储(design 决策 1:与 session_store 同库 SQLite,幂等 DDL)。

旁路铁律:本模块任何失败由调用方(api.py 落库挂点 / outcome.job)try/except
兜底,不阻断业务。连接管理与 session_store 同款(WAL + busy_timeout 短连接),
但默认 DB 路径在调用期读取(不在 import 期),测试经 db_path 显式注入。
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DECISION_LOG_DDL = """
CREATE TABLE IF NOT EXISTS decision_log (
  decision_id    TEXT PRIMARY KEY,
  session_id     TEXT NOT NULL,
  langfuse_trace_id TEXT,
  timestamp      TEXT NOT NULL,
  ticker         TEXT NOT NULL,
  name           TEXT,
  action         TEXT NOT NULL,
  entry_price    REAL NOT NULL,
  stop_loss      REAL,
  target_price   REAL,
  confidence     REAL,
  position_size  REAL,
  status         TEXT NOT NULL DEFAULT 'open',
  settled_at     TEXT,
  settle_price   REAL,
  hold_days      INTEGER,
  decision_return REAL,
  benchmark_return REAL,
  decision_excess REAL,
  updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_log_status ON decision_log(status);
"""


def _default_db_path() -> Path:
    """默认与 session_store 同库;调用期读取(测试可 monkeypatch env)。"""
    return Path(os.getenv("SESSIONS_DB_PATH", "data/sessions.db"))


def _connect(db_path: str | Path | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_decision_log(db_path: str | Path | None = None) -> None:
    """幂等建表 + 索引(session_store 同款 CREATE IF NOT EXISTS 风格)。"""
    conn = _connect(db_path)
    try:
        conn.executescript(DECISION_LOG_DDL)
        conn.commit()
    finally:
        conn.close()


def insert_decision(record: dict[str, Any], db_path: str | Path | None = None) -> str:
    """插入 open 决策,返回 decision_id(未提供则生成 uuid)。"""
    decision_id = record.get("decision_id") or f"d_{uuid.uuid4().hex[:12]}"
    now = record.get("updated_at") or record["timestamp"]
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO decision_log (
                 decision_id, session_id, langfuse_trace_id, timestamp,
                 ticker, name, action, entry_price,
                 stop_loss, target_price, confidence, position_size,
                 status, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?)""",
            (
                decision_id, record["session_id"], record.get("langfuse_trace_id"),
                record["timestamp"], record["ticker"], record.get("name"),
                record["action"], record["entry_price"], record.get("stop_loss"),
                record.get("target_price"), record.get("confidence"),
                record.get("position_size"), now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return decision_id


def get_open_decisions(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """所有 status='open' 决策(结算 job 的输入)。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM decision_log WHERE status='open'"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_settled(
    decision_id: str, settled: dict[str, Any], db_path: str | Path | None = None
) -> None:
    """写入结算结果。幂等由调用方保证(settled_at IS NULL 才调)。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            """UPDATE decision_log SET
                 status=?, settled_at=?, settle_price=?, hold_days=?,
                 decision_return=?, benchmark_return=?, decision_excess=?,
                 updated_at=?
               WHERE decision_id=?""",
            (
                settled["status"], settled["settled_at"], settled["settle_price"],
                settled["hold_days"], settled["decision_return"],
                settled.get("benchmark_return"), settled.get("decision_excess"),
                settled["settled_at"], decision_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_store.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/__init__.py src/finance_agent/outcome/store.py tests/outcome/__init__.py tests/outcome/test_store.py
git commit -m "feat: [outcome] decision_log DDL + CRUD(Task 1)"
```

---

### Task 2: outcome/settle.py — 结算纯函数

**Files:**
- Create: `src/finance_agent/outcome/settle.py`
- Test: `tests/outcome/test_settle.py`

**Interfaces:**
- Consumes: pandas DataFrame(akshare_client 中文列:日期/开盘/收盘/最高/最低)
- Produces:
  - `MAX_HOLD_DAYS` / `STALE_DAYS` / `BENCHMARK_CODE`(模块级 env 配置)
  - `Settlement` dataclass:`status / settle_date / settle_price / hold_days / decision_return / benchmark_return / decision_excess / decision_hit`
  - `evaluate_decision(decision: dict, kline: pd.DataFrame, benchmark: pd.DataFrame | None, max_hold_days: int = MAX_HOLD_DAYS) -> Settlement | None`(未触发返回 None)

**结算算法**(Global Constraints 5/6/7 的精确化):
1. `sign = 1.0 if action == "buy" else -1.0`
2. `rows = kline[日期 > decision["timestamp"][:10]]` 按日期升序(T+1 起评)
3. 逐行迭代(i 从 0,hold_days = i+1):
   - `hit_stop = stop_loss is not None and 最低 <= stop_loss`
   - `hit_target = target_price is not None and 最高 >= target_price`
   - 两者同真 → 按 stop 处理(保守)
   - 触发时若一字板(`开盘==最高==最低==收盘`)→ 记 trigger,继续扫描**首个非一字板日**,以其**开盘价**为 settle_price 结算;hold_days 累计到该日;其后不再判新触发
   - 非一字板触发 → 以 `stop_loss` 或 `target_price` 为 settle_price 结算
   - 未触发且 `i+1 >= max_hold_days` → 以该行**收盘价** expired 结算
4. 全程未触发且行数不足 max_hold_days → 返回 None(继续 open)
5. `decision_return = sign * (settle_price - entry_price) / entry_price`
6. benchmark(benchmark 不为 None 且非空):`entry_bench = 决策日或之前最后收盘`,`settle_bench = 结算日或之前最后收盘`;`benchmark_return = sign * (settle_bench - entry_bench) / entry_bench`;`excess = decision_return - benchmark_return`;否则两者 None
7. `decision_hit = decision_return > 0`

- [ ] **Step 1: Write the failing test**

```python
# tests/outcome/test_settle.py
"""结算纯函数:止损/目标/同日/超期/方向符号化/一字板递延/停牌顺延/基准缺失。"""
import pandas as pd

from finance_agent.outcome.settle import evaluate_decision


def _kline(rows: list[dict]) -> pd.DataFrame:
    """rows: {日期, 开盘, 收盘, 最高, 最低}"""
    return pd.DataFrame(rows)


def _decision(**overrides):
    base = {
        "decision_id": "d1", "action": "buy", "entry_price": 100.0,
        "stop_loss": 90.0, "target_price": 120.0,
        "timestamp": "2026-07-01T15:00:00",
    }
    base.update(overrides)
    return base


def _day(date, open_, close, high=None, low=None):
    return {"日期": date, "开盘": open_, "收盘": close,
            "最高": high if high is not None else max(open_, close),
            "最低": low if low is not None else min(open_, close)}


class TestStopAndTarget:
    def test_hit_stop(self):
        kline = _kline([_day("2026-07-02", 99, 98), _day("2026-07-03", 95, 94, low=89)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_stop"
        assert result.settle_price == 90.0
        assert result.hold_days == 2
        assert result.decision_return == -0.1
        assert result.decision_hit is False

    def test_hit_target(self):
        kline = _kline([_day("2026-07-02", 101, 110, high=121)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_target"
        assert result.settle_price == 120.0
        assert result.decision_return == 0.2
        assert result.decision_hit is True

    def test_same_day_stop_priority(self):
        # 同日触及止损和目标 → 止损优先(保守)
        kline = _kline([_day("2026-07-02", 100, 100, high=125, low=85)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_stop"
        assert result.settle_price == 90.0


class TestExpired:
    def test_expired_at_max_hold_days(self):
        kline = _kline([_day(f"2026-07-{d:02d}", 100, 101) for d in range(2, 22)])  # 20 行
        result = evaluate_decision(_decision(), kline, None, max_hold_days=20)
        assert result.status == "expired"
        assert result.hold_days == 20
        assert result.settle_price == 101.0

    def test_not_enough_rows_returns_none(self):
        kline = _kline([_day("2026-07-02", 100, 101)])
        assert evaluate_decision(_decision(), kline, None, max_hold_days=20) is None


class TestDirection:
    def test_sell_direction_negated(self):
        # sell 后跌为正
        kline = _kline([_day("2026-07-02", 99, 95)])
        result = evaluate_decision(
            _decision(action="sell", stop_loss=None, target_price=None),
            kline, None, max_hold_days=1)
        assert result.decision_return == 0.05
        assert result.decision_hit is True

    def test_hold_watch_same_as_sell(self):
        for action in ("hold", "watch"):
            kline = _kline([_day("2026-07-02", 99, 105)])
            result = evaluate_decision(
                _decision(action=action, stop_loss=None, target_price=None),
                kline, None, max_hold_days=1)
            assert result.decision_return == -0.05


class TestOneWordBoard:
    def test_limit_down_board_defers_settlement(self):
        # 一字跌停(开=高=低=收)触及止损但未成交 → 递延至打开首日开盘价
        kline = _kline([
            _day("2026-07-02", 95, 95),                    # 普通日,未触及
            _day("2026-07-03", 88, 88, high=88, low=88),   # 一字跌停,触及止损但未成交
            _day("2026-07-04", 88, 88, high=88, low=88),   # 继续一字
            _day("2026-07-05", 85, 86),                    # 打开,首个可成交价=开盘 85
        ])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_stop"
        assert result.settle_price == 85.0   # 实际可成交价,非 stop_loss 90
        assert result.hold_days == 4         # 含等待日
        assert abs(result.decision_return - (-0.15)) < 1e-9

    def test_board_unbroken_returns_none(self):
        # 一直一字板未打开 → 本批不结算
        kline = _kline([
            _day("2026-07-02", 88, 88, high=88, low=88),
            _day("2026-07-03", 88, 88, high=88, low=88),
        ])
        assert evaluate_decision(_decision(), kline, None) is None


class TestSuspension:
    def test_suspension_days_not_counted(self):
        # 停牌无 K 线行:hold_days 只数有数据的行,周期自然顺延
        kline = _kline([
            _day("2026-07-02", 99, 98),
            # 07-03 ~ 07-10 停牌,无行
            _day("2026-07-11", 97, 110, high=121),  # 复牌首日,触及目标
        ])
        result = evaluate_decision(_decision(), kline, None)
        assert result.status == "hit_target"
        assert result.hold_days == 2  # 停牌日不计入


class TestBenchmark:
    def _bench(self):
        return _kline([
            _day("2026-07-01", 4000, 4000),
            _day("2026-07-02", 4040, 4040),
        ])

    def test_excess_computed(self):
        kline = _kline([_day("2026-07-02", 101, 110, high=121)])
        result = evaluate_decision(_decision(), self._bench(), None if False else self._bench())
        assert result.benchmark_return == 0.01
        assert abs(result.decision_excess - (0.2 - 0.01)) < 1e-9

    def test_benchmark_missing_gives_none(self):
        kline = _kline([_day("2026-07-02", 101, 110, high=121)])
        result = evaluate_decision(_decision(), kline, None)
        assert result.benchmark_return is None
        assert result.decision_excess is None
        assert result.decision_return == 0.2  # 自身收益仍记

    def test_benchmark_also_negated_for_sell(self):
        kline = _kline([_day("2026-07-02", 99, 95)])
        result = evaluate_decision(
            _decision(action="sell", stop_loss=None, target_price=None),
            kline, self._bench(), max_hold_days=1)
        assert result.decision_return == 0.05
        assert result.benchmark_return == -0.01  # 基准也取负
        assert abs(result.decision_excess - 0.06) < 1e-9
```

> 注:`test_excess_computed` 调用为 `evaluate_decision(_decision(), kline, self._bench())`(第三个位置参数是 benchmark;`None if False else` 是笔误,实现者按正确形参写)。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_settle.py -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/finance_agent/outcome/settle.py
"""结算纯函数(design 决策 2/3/4/5)。全部合成 DataFrame 可测,不调 LLM/网络。

结算优先级:止损 > 目标 > 超期(expired);同日触及两者按止损(保守)。
一字板(open==high==low==close)触及 → 递延至打开首日开盘价,hold_days 含等待日。
停牌无 K 线行 → 行驱动迭代自然顺延,hold_days 只数有数据的交易日。
评估起点:decision_date 之后的行(T+1 起评)。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

MAX_HOLD_DAYS = int(os.getenv("MAX_HOLD_DAYS", "20"))
STALE_DAYS = int(os.getenv("DECISION_STALE_DAYS", "5"))
BENCHMARK_CODE = os.getenv("BENCHMARK_CODE", "000300")


@dataclass
class Settlement:
    status: str            # hit_stop / hit_target / expired
    settle_date: str
    settle_price: float
    hold_days: int
    decision_return: float
    benchmark_return: float | None
    decision_excess: float | None
    decision_hit: bool


def _direction_sign(action: str) -> float:
    """buy 为正;sell/hold/watch 取负(建议不买/卖出后下跌为正)。"""
    return 1.0 if action == "buy" else -1.0


def _is_one_word_board(row: pd.Series) -> bool:
    """一字板:开=高=低=收(全天未打开)。"""
    return row["开盘"] == row["最高"] == row["最低"] == row["收盘"]


def _bench_close_on_or_before(benchmark: pd.DataFrame, date: str) -> float | None:
    """基准在 date 或之前最后一个收盘。"""
    eligible = benchmark[benchmark["日期"] <= date]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["收盘"])


def evaluate_decision(
    decision: dict,
    kline: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    max_hold_days: int = MAX_HOLD_DAYS,
) -> Settlement | None:
    """评估单个 open 决策是否结算。未触发返回 None。"""
    entry_price = float(decision["entry_price"])
    stop_loss = decision.get("stop_loss")
    target_price = decision.get("target_price")
    sign = _direction_sign(decision["action"])
    decision_date = str(decision["timestamp"])[:10]

    rows = kline[kline["日期"] > decision_date].sort_values("日期").reset_index(drop=True)
    if rows.empty:
        return None

    pending_trigger: str | None = None  # 一字板递延中的触发类型
    for i in range(len(rows)):
        row = rows.iloc[i]
        hold_days = i + 1

        if pending_trigger is not None:
            # 一字板递延中:等待打开首日,以开盘价结算
            if _is_one_word_board(row):
                continue
            return _settle(decision, pending_trigger, str(row["日期"]),
                           float(row["开盘"]), hold_days, entry_price, sign, benchmark)

        hit_stop = stop_loss is not None and float(row["最低"]) <= float(stop_loss)
        hit_target = target_price is not None and float(row["最高"]) >= float(target_price)

        if hit_stop or hit_target:
            trigger = "hit_stop" if hit_stop else "hit_target"  # 同日止损优先
            if _is_one_word_board(row):
                pending_trigger = trigger  # 未成交,递延
                continue
            price = float(stop_loss) if trigger == "hit_stop" else float(target_price)
            return _settle(decision, trigger, str(row["日期"]),
                           price, hold_days, entry_price, sign, benchmark)

        if hold_days >= max_hold_days:
            return _settle(decision, "expired", str(row["日期"]),
                           float(row["收盘"]), hold_days, entry_price, sign, benchmark)

    return None  # 行数不足或一字板未打开:继续 open


def _settle(
    decision: dict, status: str, settle_date: str, settle_price: float,
    hold_days: int, entry_price: float, sign: float,
    benchmark: pd.DataFrame | None,
) -> Settlement:
    decision_return = sign * (settle_price - entry_price) / entry_price
    benchmark_return: float | None = None
    decision_excess: float | None = None
    if benchmark is not None and not benchmark.empty:
        entry_bench = _bench_close_on_or_before(benchmark, str(decision["timestamp"])[:10])
        settle_bench = _bench_close_on_or_before(benchmark, settle_date)
        if entry_bench and settle_bench:
            benchmark_return = sign * (settle_bench - entry_bench) / entry_bench
            decision_excess = decision_return - benchmark_return
    return Settlement(
        status=status, settle_date=settle_date, settle_price=settle_price,
        hold_days=hold_days, decision_return=decision_return,
        benchmark_return=benchmark_return, decision_excess=decision_excess,
        decision_hit=decision_return > 0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_settle.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/settle.py tests/outcome/test_settle.py
git commit -m "feat: [outcome] 结算纯函数 — 止损/目标/超期 + 一字板递延 + 停牌顺延 + 方向符号化(Task 2)"
```

---

### Task 3: fetch_index_kline + outcome/job.py — 结算 job 与 Score 反向上报

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py:450-472`(fetch_benchmark_kline 泛化)
- Create: `src/finance_agent/outcome/job.py`
- Test: `tests/outcome/test_fetch_index.py`、`tests/outcome/test_job.py`

**Interfaces:**
- Consumes: Task 1 store CRUD、Task 2 settle、`AKShareClient.fetch_kline`、langfuse 4.13 `Langfuse.create_score(name=, value=, trace_id=, data_type=, comment=)`(client.py:1847 已探明)
- Produces:
  - `AKShareClient.fetch_index_kline(index_code: str, days: int = 250) -> pd.DataFrame`(`fetch_benchmark_kline` 改为其 000300 特化 wrapper,行为不变)
  - `settle_open_decisions(*, client=None, db_path=None, langfuse=None, kline_days: int | None = None) -> dict` 返回 `{"settled": int, "skipped": int, "stale": int, "scores_reported": int, "errors": int}`
  - `report_outcome_scores(langfuse, decision: dict, settlement: Settlement) -> int`(上报 3 score,返回成功数;任何失败 WARN 不阻断)

**job 流程**(per decision):
1. `rows_df = client.fetch_kline(ticker, days=kline_days or MAX_HOLD_DAYS+15)`
2. `bench_df = client.fetch_index_kline(BENCHMARK_CODE, days=...)`
3. 拉取异常 → 该决策本次跳过(errors += 1,继续下一个;spec「行情缺失重试」)
4. `rows_df` 决策日后无行 → skipped;若 ticker 最新行日期落后基准最新行日期 ≥ STALE_DAYS 个交易日(按基准行数计)→ WARN `data_stale`(stale += 1)
5. `settlement = evaluate_decision(...)`;None → skipped
6. `mark_settled(...)`(mark 前再查 `settled_at IS NULL` 防重;幂等,spec「幂等结算」)
7. `report_outcome_scores(...)`(trace_id 为 None → 直接跳过上报,不报错)

- [ ] **Step 1: Write the failing test**

```python
# tests/outcome/test_fetch_index.py
"""fetch_index_kline 泛化:任意指数代码;fetch_benchmark_kline 兼容。"""
from unittest.mock import MagicMock, patch

import pandas as pd

from finance_agent.data.akshare_client import AKShareClient


def test_fetch_index_kline_calls_akshare_with_code():
    client = AKShareClient()
    fake_df = pd.DataFrame({"日期": ["2026-08-01"], "收盘": [4000.0]})
    with patch("finance_agent.data.akshare_client.ak") as mock_ak:
        mock_ak.index_zh_a_hist.return_value = fake_df
        result = client.fetch_index_kline("000905", days=30)
    assert mock_ak.index_zh_a_hist.call_args.kwargs["symbol"] == "000905"
    assert result is fake_df


def test_fetch_benchmark_kline_still_000300():
    client = AKShareClient()
    fake_df = pd.DataFrame({"日期": ["2026-08-01"], "收盘": [4000.0]})
    with patch("finance_agent.data.akshare_client.ak") as mock_ak:
        mock_ak.index_zh_a_hist.return_value = fake_df
        client.fetch_benchmark_kline(days=30)
    assert mock_ak.index_zh_a_hist.call_args.kwargs["symbol"] == "000300"
```

```python
# tests/outcome/test_job.py
"""结算 job:结算+落库+上报、幂等、行情缺失跳过、data_stale、trace 不可查容错。"""
from unittest.mock import MagicMock, patch

import pandas as pd

from finance_agent.outcome import store
from finance_agent.outcome.job import report_outcome_scores, settle_open_decisions
from finance_agent.outcome.settle import Settlement


def _open_decision(**overrides):
    base = {
        "decision_id": "d1", "session_id": "s1", "langfuse_trace_id": "trace-1",
        "timestamp": "2026-07-01T15:00:00", "ticker": "600519", "name": "茅台",
        "action": "buy", "entry_price": 100.0, "stop_loss": 90.0,
        "target_price": 120.0, "confidence": 0.8, "position_size": 0.3,
    }
    base.update(overrides)
    return base


def _kline_hit_target():
    return pd.DataFrame([
        {"日期": "2026-07-02", "开盘": 101, "收盘": 110, "最高": 121, "最低": 100},
    ])


def _bench():
    return pd.DataFrame([
        {"日期": "2026-07-01", "开盘": 4000, "收盘": 4000, "最高": 4000, "最低": 4000},
        {"日期": "2026-07-02", "开盘": 4040, "收盘": 4040, "最高": 4040, "最低": 4040},
    ])


class TestSettleJob:
    def test_settles_and_reports(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)

        client = MagicMock()
        client.fetch_kline.return_value = _kline_hit_target()
        client.fetch_index_kline.return_value = _bench()
        langfuse = MagicMock()

        result = settle_open_decisions(client=client, db_path=db, langfuse=langfuse)
        assert result["settled"] == 1
        assert result["scores_reported"] == 3
        assert store.get_open_decisions(db) == []
        # 3 个 score 按 trace_id 反向上报
        names = {c.kwargs["name"] for c in langfuse.create_score.call_args_list}
        assert names == {"decision_hit", "decision_return", "decision_excess"}
        for c in langfuse.create_score.call_args_list:
            assert c.kwargs["trace_id"] == "trace-1"

    def test_idempotent_no_double_settle(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.return_value = _kline_hit_target()
        client.fetch_index_kline.return_value = _bench()
        langfuse = MagicMock()

        first = settle_open_decisions(client=client, db_path=db, langfuse=langfuse)
        second = settle_open_decisions(client=client, db_path=db, langfuse=langfuse)
        assert first["settled"] == 1
        assert second["settled"] == 0  # 不重复结算/上报
        assert langfuse.create_score.call_count == 3

    def test_unsettled_stays_open(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.return_value = pd.DataFrame(
            [{"日期": "2026-07-02", "开盘": 100, "收盘": 101, "最高": 102, "最低": 99}])
        client.fetch_index_kline.return_value = _bench()

        result = settle_open_decisions(client=client, db_path=db, langfuse=MagicMock())
        assert result["settled"] == 0
        assert len(store.get_open_decisions(db)) == 1

    def test_fetch_failure_skips_decision(self, tmp_path):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.side_effect = RuntimeError("network")

        result = settle_open_decisions(client=client, db_path=db, langfuse=MagicMock())
        assert result["settled"] == 0
        assert result["errors"] == 1
        assert len(store.get_open_decisions(db)) == 1  # 下次重试

    def test_data_stale_warned(self, tmp_path, caplog):
        db = tmp_path / "t.db"
        store.init_decision_log(db)
        # 决策日久远,K 线无新数据,但基准已到 07-30
        store.insert_decision(_open_decision(), db)
        client = MagicMock()
        client.fetch_kline.return_value = pd.DataFrame(
            [{"日期": "2026-06-01", "开盘": 100, "收盘": 100, "最高": 100, "最低": 100}])
        client.fetch_index_kline.return_value = pd.DataFrame(
            [{"日期": f"2026-07-{d:02d}", "开盘": 4000, "收盘": 4000,
              "最高": 4000, "最低": 4000} for d in range(1, 31)])

        import logging
        with caplog.at_level(logging.WARNING):
            result = settle_open_decisions(client=client, db_path=db, langfuse=MagicMock())
        assert result["stale"] == 1
        assert any("data_stale" in r.message for r in caplog.records)


class TestReportScores:
    def _settlement(self):
        return Settlement(
            status="hit_target", settle_date="2026-07-02", settle_price=120.0,
            hold_days=1, decision_return=0.2, benchmark_return=0.01,
            decision_excess=0.19, decision_hit=True,
        )

    def test_three_scores_with_comment(self):
        langfuse = MagicMock()
        count = report_outcome_scores(langfuse, _open_decision(), self._settlement())
        assert count == 3
        by_name = {c.kwargs["name"]: c.kwargs for c in langfuse.create_score.call_args_list}
        assert by_name["decision_hit"]["data_type"] == "BOOLEAN"
        assert by_name["decision_hit"]["value"] == 1.0
        assert by_name["decision_return"]["value"] == 0.2
        assert by_name["decision_excess"]["value"] == 0.19
        assert "120" in by_name["decision_return"]["comment"]  # 结算价在 comment

    def test_trace_missing_warns_not_raises(self, caplog):
        langfuse = MagicMock()
        langfuse.create_score.side_effect = RuntimeError("trace not found")
        import logging
        with caplog.at_level(logging.WARNING):
            count = report_outcome_scores(langfuse, _open_decision(), self._settlement())
        assert count == 0  # 不阻断,记 WARN

    def test_none_trace_id_skips(self):
        count = report_outcome_scores(
            MagicMock(), _open_decision(langfuse_trace_id=None), self._settlement())
        assert count == 0

    def test_excess_none_skips_excess_score(self):
        settlement = self._settlement()
        settlement.decision_excess = None
        settlement.benchmark_return = None
        langfuse = MagicMock()
        count = report_outcome_scores(langfuse, _open_decision(), settlement)
        assert count == 2  # excess 为 None 不上报
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_fetch_index.py tests/outcome/test_job.py -v`
Expected: FAIL(fetch_index_kline 不存在 / outcome.job 不存在)

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/data/akshare_client.py` — 把 `fetch_benchmark_kline`(450-472 区域)泛化(**实施时先读现有实现,保持其返回列与异常处理风格**):

```python
def fetch_index_kline(self, index_code: str, days: int = 250) -> pd.DataFrame:
    """拉指数日 K(ak.index_zh_a_hist,无 adjust)。列:日期/开盘/收盘/最高/最低/成交量。"""
    from datetime import datetime, timedelta

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=int(days * 1.6))).strftime("%Y%m%d")
    df = _call_ak(
        ak.index_zh_a_hist, symbol=index_code, period="daily",
        start_date=start, end_date=end,
    )
    return df

def fetch_benchmark_kline(self, days: int = 250) -> pd.DataFrame:
    """沪深 300 日 K(fetch_index_kline 的 000300 特化,行为与原来一致)。"""
    return self.fetch_index_kline("000300", days=days)
```

> 注意:现有 `fetch_benchmark_kline` 的 start_date 计算/列处理以实际代码为准,泛化时原样保留(只把 symbol 参数化),不要重写已有逻辑。

```python
# src/finance_agent/outcome/job.py
"""日批结算 job(design 决策 2/6/7):遍历 open 决策 → 拉行情 → 结算 → 落库 → 上报 Score。

幂等:mark_settled 前再查 settled_at IS NULL(spec「幂等结算」)。
失败隔离:单决策拉取异常仅跳过该决策(errors 计数),不中断整批(spec「行情缺失重试」)。
"""
from __future__ import annotations

import logging
from typing import Any

from finance_agent.outcome import store
from finance_agent.outcome.settle import (
    BENCHMARK_CODE, MAX_HOLD_DAYS, STALE_DAYS, Settlement, evaluate_decision,
)

logger = logging.getLogger(__name__)


def report_outcome_scores(langfuse, decision: dict, settlement: Settlement) -> int:
    """按 langfuse_trace_id 后置上报 3 个 Score,返回成功数。

    trace 不存在/已过期 → WARN 不阻断(spec「trace 不可查容错」);
    trace_id 为 None → 直接跳过;excess 为 None(基准缺失)→ 不上报 excess。
    """
    trace_id = decision.get("langfuse_trace_id")
    if not trace_id or langfuse is None:
        return 0
    comment = (
        f"settle_price={settlement.settle_price} hold_days={settlement.hold_days} "
        f"benchmark_return={settlement.benchmark_return}"
    )
    scores: list[tuple[str, float, str]] = [
        ("decision_hit", 1.0 if settlement.decision_hit else 0.0, "BOOLEAN"),
        ("decision_return", settlement.decision_return, "NUMERIC"),
    ]
    if settlement.decision_excess is not None:
        scores.append(("decision_excess", settlement.decision_excess, "NUMERIC"))
    reported = 0
    for name, value, data_type in scores:
        try:
            langfuse.create_score(
                name=name, value=value, trace_id=trace_id,
                data_type=data_type, comment=comment,
            )
            reported += 1
        except Exception as e:
            logger.warning("score 上报失败(trace 不可查?): %s %s", name, e)
    return reported


def _is_stale(kline, benchmark) -> bool:
    """ticker 最新行落后基准最新行 ≥ STALE_DAYS 个交易日(按基准行数,无状态判定)。"""
    if kline is None or kline.empty or benchmark is None or benchmark.empty:
        return False
    ticker_last = str(kline.iloc[-1]["日期"])
    bench_dates = [str(d) for d in benchmark["日期"]]
    later = [d for d in bench_dates if d > ticker_last]
    return len(later) >= STALE_DAYS


def settle_open_decisions(
    *, client=None, db_path=None, langfuse=None, kline_days: int | None = None
) -> dict[str, int]:
    """遍历 open 决策日批结算。返回 {settled, skipped, stale, scores_reported, errors}。"""
    if client is None:
        from finance_agent.data.akshare_client import AKShareClient

        client = AKShareClient()
    days = kline_days or MAX_HOLD_DAYS + 15
    result = {"settled": 0, "skipped": 0, "stale": 0, "scores_reported": 0, "errors": 0}

    for decision in store.get_open_decisions(db_path):
        try:
            kline = client.fetch_kline(decision["ticker"], days=days)
            benchmark = client.fetch_index_kline(BENCHMARK_CODE, days=days)
        except Exception as e:
            logger.warning("行情拉取失败,本次跳过 %s: %s", decision["decision_id"], e)
            result["errors"] += 1
            continue

        decision_date = str(decision["timestamp"])[:10]
        has_new_rows = kline is not None and not kline[kline["日期"] > decision_date].empty
        if not has_new_rows:
            if _is_stale(kline, benchmark):
                logger.warning(
                    "data_stale: %s(%s)K 线落后基准 ≥ %d 交易日",
                    decision["decision_id"], decision["ticker"], STALE_DAYS,
                )
                result["stale"] += 1
            result["skipped"] += 1
            continue

        settlement = evaluate_decision(decision, kline, benchmark)
        if settlement is None:
            result["skipped"] += 1
            continue

        # 幂等:落库前再查 settled_at(并发/重复执行防御)
        current = [d for d in store.get_open_decisions(db_path)
                   if d["decision_id"] == decision["decision_id"]]
        if not current:
            result["skipped"] += 1
            continue
        store.mark_settled(decision["decision_id"], {
            "status": settlement.status,
            "settled_at": settlement.settle_date,
            "settle_price": settlement.settle_price,
            "hold_days": settlement.hold_days,
            "decision_return": settlement.decision_return,
            "benchmark_return": settlement.benchmark_return,
            "decision_excess": settlement.decision_excess,
        }, db_path)
        result["settled"] += 1
        result["scores_reported"] += report_outcome_scores(langfuse, decision, settlement)

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_fetch_index.py tests/outcome/test_job.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/data/akshare_client.py src/finance_agent/outcome/job.py tests/outcome/test_fetch_index.py tests/outcome/test_job.py
git commit -m "feat: [outcome] fetch_index_kline 泛化 + 日批结算 job + Score 反向上报(Task 3)"
```

---

### Task 4: APScheduler 挂载(scheduler.py + lifespan + 依赖)

**Files:**
- Create: `src/finance_agent/outcome/scheduler.py`
- Modify: `pyproject.toml`(+apscheduler)、`uv.lock`(`uv lock` 刷新)
- Modify: `src/finance_agent/api.py:58-65`(_lifespan 挂 scheduler)
- Test: `tests/outcome/test_scheduler.py`

**Interfaces:**
- Consumes: Task 3 `settle_open_decisions`
- Produces:
  - `start_scheduler() -> BackgroundScheduler | None`(TESTING=1 或 `DECISION_SETTLE_ENABLED=0` → None;否则 BackgroundScheduler + CronTrigger(day_of_week="mon-fri", hour=16, minute=0) + `start()`)
  - `stop_scheduler(scheduler) -> None`(None 安全)

- [ ] **Step 1: Write the failing test**

```python
# tests/outcome/test_scheduler.py
"""scheduler 挂载:TESTING/env 禁用、cron 注册、启停、job 异常不传播。"""
import os
from unittest.mock import MagicMock, patch

from finance_agent.outcome.scheduler import start_scheduler, stop_scheduler


class TestStartGating:
    @patch.dict(os.environ, {"TESTING": "1"})
    def test_testing_disables(self):
        assert start_scheduler() is None

    @patch.dict(os.environ, {"DECISION_SETTLE_ENABLED": "0", "TESTING": ""})
    def test_env_disables(self):
        assert start_scheduler() is None

    @patch.dict(os.environ, {"TESTING": "", "DECISION_SETTLE_ENABLED": "1"})
    @patch("finance_agent.outcome.scheduler.BackgroundScheduler")
    def test_registers_weekday_1600_cron(self, mock_sched_cls):
        sched = MagicMock()
        mock_sched_cls.return_value = sched
        result = start_scheduler()
        assert result is sched
        _, kwargs = sched.add_job.call_args
        trigger = sched.add_job.call_args.args[1] if len(sched.add_job.call_args.args) > 1 else kwargs.get("trigger")
        # CronTrigger: 工作日 16:00
        assert "16" in str(trigger)
        assert "mon-fri" in str(trigger)
        sched.start.assert_called_once()


class TestStop:
    def test_stop_none_safe(self):
        stop_scheduler(None)  # 不抛异常

    def test_stop_calls_shutdown(self):
        sched = MagicMock()
        stop_scheduler(sched)
        sched.shutdown.assert_called_once_with(wait=False)


class TestJobIsolation:
    @patch.dict(os.environ, {"TESTING": "", "DECISION_SETTLE_ENABLED": "1"})
    @patch("finance_agent.outcome.scheduler.BackgroundScheduler")
    def test_job_wrapper_swallows_exceptions(self, mock_sched_cls):
        """job 内部异常不传播到 scheduler(旁路铁律)。"""
        sched = MagicMock()
        mock_sched_cls.return_value = sched
        start_scheduler()
        job_fn = sched.add_job.call_args.args[0]
        with patch("finance_agent.outcome.scheduler.settle_open_decisions",
                   side_effect=RuntimeError("boom")):
            job_fn()  # 不抛异常
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_scheduler.py -v`
Expected: FAIL(outcome.scheduler 不存在;apscheduler 未装)

- [ ] **Step 3: Write minimal implementation**

先加依赖:

```bash
uv add apscheduler
```

```python
# src/finance_agent/outcome/scheduler.py
"""日批结算定时任务(design 决策 6:APScheduler in-process,单 worker 无竞争)。

每个工作日 16:00(收盘后)触发 settle_open_decisions。
TESTING=1 或 DECISION_SETTLE_ENABLED=0 时禁用;job 异常不传播(旁路)。
注:定时任务框架选型建议人工落 ADR(design 决策 6 注),agent 不自建 ADR。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _settle_job() -> None:
    """scheduler 入口:全部异常吞掉(旁路铁律)。"""
    from finance_agent.outcome.job import settle_open_decisions

    try:
        result = settle_open_decisions()
        logger.info("decision settle job 完成: %s", result)
    except Exception:
        logger.exception("decision settle job 失败(下交易日重试)")


def start_scheduler():
    """启动日批 scheduler;TESTING/禁用时返回 None。"""
    if os.getenv("TESTING") == "1" or os.getenv("DECISION_SETTLE_ENABLED") == "0":
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _settle_job,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0),
        id="decision_settle_daily",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("decision settle scheduler 已启动(工作日 16:00)")
    return scheduler


def stop_scheduler(scheduler) -> None:
    """关闭 scheduler(None 安全)。"""
    if scheduler is not None:
        scheduler.shutdown(wait=False)
```

`src/finance_agent/api.py` 的 `_lifespan`(58-65 区域,**先读现有实现**):

```python
@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    PipelineRunner.mark_swept_failed()
    # 决策结算日批 scheduler(旁路;TESTING/禁用返回 None)
    from finance_agent.outcome.scheduler import start_scheduler, stop_scheduler

    _scheduler = start_scheduler()
    yield
    stop_scheduler(_scheduler)
```

同时 api.py 模块级 `init_db()`(api.py:86)后加:

```python
from finance_agent.outcome.store import init_decision_log

init_decision_log()  # 幂等建表,decision_log 与 sessions 同库
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_scheduler.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/scheduler.py src/finance_agent/api.py pyproject.toml uv.lock tests/outcome/test_scheduler.py
git commit -m "feat: [outcome] APScheduler 日批挂载(lifespan 启停,TESTING 禁用)(Task 4)"
```

---

### Task 5: trace_id 捕获(fund_manager)+ 决策落库挂点(api.py)

**Files:**
- Modify: `src/finance_agent/state.py`(加 `langfuse_trace_id: str`)
- Modify: `src/finance_agent/nodes/fund_manager.py`(approve 时捕获 trace_id)
- Modify: `src/finance_agent/api.py`(报告落库处加 `_persist_decision_log` 调用)
- Test: `tests/outcome/test_trace_capture.py`、`tests/outcome/test_decision_logging.py`

**Interfaces:**
- Consumes: langfuse 4.13 `Langfuse.get_current_trace_id()`(client.py:2271,OTel context,图节点内可用——citation_node 同款);Task 1 `insert_decision`
- Produces:
  - state 新键 `langfuse_trace_id: str`(fund_manager approve 时写入)
  - `api._persist_decision_log(accumulated: dict, session_id: str, stock_code: str, stock_name: str) -> None`(全 try/except)

**挂点逻辑**(api.py 报告落库处,约 api.py:878-909 `update_session_report` 之后,**实施时先读该段代码定位**):

条件(全部满足才落库):
1. `accumulated.get("fund_manager_decision") == "approve"`
2. `accumulated.get("final_trade_decision")` 非空
3. entry_price 可解析:`(accumulated.get("stock_quote") or {}).get("price")` 优先;否则 `accumulated.get("kline")` 最后一行收盘价(DataFrame 则 `.iloc[-1]["收盘"]`,list[dict] 则 `[-1]["收盘"]`);都无 → WARN 跳过(Global Constraint 2)

record 字段:decision_id=None(store 生成)/session_id/langfuse_trace_id=accumulated.get("langfuse_trace_id")/timestamp=datetime.now().isoformat()/ticker=stock_code/name=stock_name/action=decision["action"]/entry_price=回填价/stop_loss/target_price/confidence=decision 同名字段/position_size=`float(decision["position_size"]) if isinstance(decision.get("position_size"), (int, float)) else None`(模型里是 str|None,非数值给 None)

- [ ] **Step 1: Write the failing test**

```python
# tests/outcome/test_trace_capture.py
"""fund_manager approve 时捕获 langfuse trace_id 入 state。"""
from unittest.mock import MagicMock, patch

import finance_agent.nodes.fund_manager as fm_mod


class TestTraceCapture:
    def _run_fund_manager(self, decision: str):
        """驱动 fund_manager 节点,返回 state update。"""
        state = {
            "stock_code": "600519",
            "final_trade_decision": {"action": "buy", "confidence": 0.8,
                                     "reasoning": "x", "entry_price": None,
                                     "stop_loss": 90.0, "target_price": 120.0,
                                     "position_size": None},
            "research_manager_conclusion": "rm",
            "risk_debate_history": [],
            "debate_history": [],
            "analyst_reports": {},
        }
        return fm_mod.fund_manager(state)

    @patch.object(fm_mod, "call_llm_streaming")
    def test_approve_captures_trace_id(self, mock_llm):
        mock_llm.return_value = '{"decision": "approve", "feedback": "ok"}'
        mock_client = MagicMock()
        mock_client.get_current_trace_id.return_value = "trace-xyz"
        with patch.object(fm_mod, "get_langfuse", return_value=mock_client):
            update = self._run_fund_manager("approve")
        assert update["fund_manager_decision"] == "approve"
        assert update["langfuse_trace_id"] == "trace-xyz"

    @patch.object(fm_mod, "call_llm_streaming")
    def test_reject_no_trace_capture(self, mock_llm):
        mock_llm.return_value = '{"decision": "reject", "feedback": "no"}'
        with patch.object(fm_mod, "get_langfuse") as mock_get:
            update = self._run_fund_manager("reject")
        assert update["fund_manager_decision"] == "reject"
        assert "langfuse_trace_id" not in update
        mock_get.assert_not_called()

    @patch.object(fm_mod, "call_llm_streaming")
    def test_langfuse_unconfigured_no_key(self, mock_llm):
        mock_llm.return_value = '{"decision": "approve", "feedback": "ok"}'
        with patch.object(fm_mod, "get_langfuse", return_value=None):
            update = self._run_fund_manager("approve")
        assert "langfuse_trace_id" not in update  # 降级:不写键
```

> 实施说明:`call_llm_streaming` 的真实签名/mock 形态以 `nodes/fund_manager.py` 现状为准(**先读文件**);若其返回不是 JSON 字符串而是结构化产出,相应调整 mock 与断言,但三场景语义(approve 捕获 / reject 不捕获 / 未配置不写键)必须保持。`get_langfuse` 若 fund_manager.py 未 import,则实现里新增 `from finance_agent.langfuse_tracing import get_langfuse`,patch 路径用 `finance_agent.nodes.fund_manager.get_langfuse`。

```python
# tests/outcome/test_decision_logging.py
"""api._persist_decision_log:approve 落库、entry_price 回填、非 approve 跳过、失败不阻断。"""
from unittest.mock import MagicMock, patch

import pandas as pd

from finance_agent.api import _persist_decision_log


def _accumulated(**overrides):
    base = {
        "fund_manager_decision": "approve",
        "final_trade_decision": {
            "action": "buy", "confidence": 0.8, "reasoning": "x",
            "entry_price": None, "stop_loss": 90.0, "target_price": 120.0,
            "position_size": "30%",
        },
        "langfuse_trace_id": "trace-1",
        "stock_quote": {"price": 100.0},
    }
    base.update(overrides)
    return base


class TestPersistDecisionLog:
    @patch("finance_agent.api.insert_decision")
    def test_approve_inserts_with_quote_price(self, mock_insert):
        _persist_decision_log(_accumulated(), "sess-1", "600519", "贵州茅台")
        record = mock_insert.call_args.args[0]
        assert record["action"] == "buy"
        assert record["entry_price"] == 100.0          # quote 回填,非 LLM 的 None
        assert record["stop_loss"] == 90.0
        assert record["langfuse_trace_id"] == "trace-1"
        assert record["session_id"] == "sess-1"
        assert record["position_size"] is None          # "30%" 非数值 → None

    @patch("finance_agent.api.insert_decision")
    def test_kline_close_fallback(self, mock_insert):
        acc = _accumulated(stock_quote=None)
        acc["kline"] = pd.DataFrame([{"日期": "2026-08-01", "收盘": 99.5}])
        _persist_decision_log(acc, "sess-1", "600519", "茅台")
        assert mock_insert.call_args.args[0]["entry_price"] == 99.5

    @patch("finance_agent.api.insert_decision")
    def test_non_approve_skips(self, mock_insert):
        _persist_decision_log(
            _accumulated(fund_manager_decision="reject"), "s", "600519", "茅台")
        mock_insert.assert_not_called()
        _persist_decision_log(
            _accumulated(final_trade_decision=None), "s", "600519", "茅台")
        mock_insert.assert_not_called()

    @patch("finance_agent.api.insert_decision")
    def test_no_price_skips_with_warn(self, mock_insert, caplog):
        import logging
        acc = _accumulated(stock_quote=None, kline=None)
        with caplog.at_level(logging.WARNING):
            _persist_decision_log(acc, "s", "600519", "茅台")
        mock_insert.assert_not_called()
        assert any("entry_price" in r.message or "价格" in r.message
                   for r in caplog.records)

    @patch("finance_agent.api.insert_decision", side_effect=RuntimeError("db down"))
    def test_failure_does_not_raise(self, mock_insert):
        # spec「落库失败不阻断业务」:异常吞掉记 ERROR
        _persist_decision_log(_accumulated(), "s", "600519", "茅台")  # 不抛
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_trace_capture.py tests/outcome/test_decision_logging.py -v`
Expected: FAIL(langfuse_trace_id 不在 state / _persist_decision_log 不存在)

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/state.py`(total=False,追加一行):

```python
langfuse_trace_id: str  # fund_manager approve 时捕获,decision_log 反向上报用
```

`src/finance_agent/nodes/fund_manager.py`(**先读现有 12-34 行实现**,在 return 前加):

```python
from finance_agent.langfuse_tracing import get_langfuse

# fund_manager() 内,decision 计算后:
result: dict = {"fund_manager_decision": decision}
if decision == "return":
    result["return_count"] = return_count + 1
if decision == "approve":
    # 决策落库需要 trace 关联:节点内 OTel 上下文可用(citation_node 同款)
    try:
        _client = get_langfuse()
        _trace_id = _client.get_current_trace_id() if _client else None
        if _trace_id:
            result["langfuse_trace_id"] = _trace_id
    except Exception:
        logger.warning("trace_id 捕获失败,decision_log 将无 trace 关联", exc_info=True)
return result
```

`src/finance_agent/api.py`(**先读报告落库段 878-909 定位调用点**):

```python
from finance_agent.outcome.store import insert_decision  # 模块顶部 import 区


def _persist_decision_log(
    accumulated: dict, session_id: str, stock_code: str, stock_name: str
) -> None:
    """批准的 TradeDecision 落 decision_log(旁路:任何失败仅 ERROR,不阻断)。"""
    try:
        if accumulated.get("fund_manager_decision") != "approve":
            return
        decision = accumulated.get("final_trade_decision") or {}
        if not decision.get("action"):
            return
        # entry_price 代码回填:quote 优先,kline 收盘兜底(Global Constraint 2)
        entry_price = (accumulated.get("stock_quote") or {}).get("price")
        if entry_price is None:
            kline = accumulated.get("kline")
            if kline is not None and len(kline) > 0:
                last = kline.iloc[-1] if hasattr(kline, "iloc") else kline[-1]
                entry_price = float(last["收盘"])
        if entry_price is None:
            logger.warning("decision_log 跳过: %s 无可靠 entry_price", stock_code)
            return
        position_size = decision.get("position_size")
        insert_decision({
            "decision_id": None,
            "session_id": session_id,
            "langfuse_trace_id": accumulated.get("langfuse_trace_id"),
            "timestamp": datetime.now().isoformat(),
            "ticker": stock_code,
            "name": stock_name,
            "action": decision["action"],
            "entry_price": float(entry_price),
            "stop_loss": decision.get("stop_loss"),
            "target_price": decision.get("target_price"),
            "confidence": decision.get("confidence"),
            "position_size": float(position_size)
            if isinstance(position_size, (int, float)) else None,
        })
        logger.info("decision_log 已落库: %s %s", stock_code, decision["action"])
    except Exception:
        logger.exception("decision_log 落库失败(不阻断业务)")
```

调用点:`update_session_report(...)` 成功后(报告落库段末尾)加:

```python
_persist_decision_log(accumulated, session_id, stock_code, stock_name)
```

> `datetime` import 与 `session_id`/`stock_name` 在该作用域的实际变量名以 api.py 现状为准(**先读代码**,变量名不同时用现状名)。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_trace_capture.py tests/outcome/test_decision_logging.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/state.py src/finance_agent/nodes/fund_manager.py src/finance_agent/api.py tests/outcome/test_trace_capture.py tests/outcome/test_decision_logging.py
git commit -m "feat: [outcome] fund_manager trace_id 捕获 + 决策落库挂点(Task 5)"
```

---

### Task 6: @live 用例 + 验证报告 + 质量门禁

**Files:**
- Create: `tests/outcome/test_outcome_live.py`(`@live`)
- Create: `tests/validation/2026-08-12-decision-outcome-tracking-validation.md`

- [ ] **Step 1: Write the @live test**

```python
# tests/outcome/test_outcome_live.py
"""@live 用例:真实 AKShare 行情跑结算逻辑(不调 LLM),nightly 防 AKShare 漂移。"""
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="需 DEEPSEEK_API_KEY(与 nightly 同开关)"),
]


def test_live_settle_with_real_kline():
    """真实 600519 日 K + 合成决策,结算逻辑产出合法结果(防 AKShare 列名/接口漂移)。"""
    from finance_agent.data.akshare_client import AKShareClient
    from finance_agent.outcome.settle import evaluate_decision

    client = AKShareClient()
    kline = client.fetch_kline("600519", days=60)
    benchmark = client.fetch_index_kline("000300", days=60)
    assert not kline.empty and not benchmark.empty
    for col in ("日期", "开盘", "收盘", "最高", "最低"):
        assert col in kline.columns, f"AKShare 列名漂移: 缺 {col}"

    # 决策日 = 倒数第 10 个交易日的上一日;stop/target 设在远离现价处必走 expired
    decision_date = str(kline.iloc[-11]["日期"])
    last_close = float(kline.iloc[-11]["收盘"])
    decision = {
        "decision_id": "live", "action": "buy", "entry_price": last_close,
        "stop_loss": last_close * 0.5, "target_price": last_close * 2.0,
        "timestamp": f"{decision_date}T15:00:00",
    }
    result = evaluate_decision(decision, kline, benchmark, max_hold_days=20)
    # 10 行 < 20:可能 None(行不足)或 expired(不会 hit);两类都合法,但类型必须正确
    if result is not None:
        assert result.status in ("hit_stop", "hit_target", "expired")
        assert isinstance(result.hold_days, int) and result.hold_days >= 1
        assert result.benchmark_return is not None  # 基准给了就不应为 None


def test_live_fetch_index_kline_columns():
    """真实指数 K 线列名(防 index_zh_a_hist 漂移)。"""
    from finance_agent.data.akshare_client import AKShareClient

    df = AKShareClient().fetch_index_kline("000300", days=10)
    assert not df.empty
    assert "日期" in df.columns and "收盘" in df.columns
```

- [ ] **Step 2: collect 验证(本环境不跑 live)**

Run: `uv run pytest tests/outcome/test_outcome_live.py --collect-only -m live -q`
Expected: 2 tests collected

- [ ] **Step 3: 人工验证报告**

写 `tests/validation/2026-08-12-decision-outcome-tracking-validation.md`:

```markdown
# 人工验证报告: decision-outcome-tracking

**日期**: 2026-08-12
**验证人**: [待填]
**关联 delta**: openspec/changes/decision-outcome-tracking/
**E2E 门禁**: 不适用(纯后端旁路,非交互类变更,§2 判别)

## 验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| decision_log 建表 | init_decision_log 幂等建表 + 索引 | 单测锁定(test_idempotent_init/test_table_and_index_created) | ✅ |
| 结算规则正确 | 止损/目标/同日/超期/一字板/停牌/方向/基准 13 场景 | 单测锁定(test_settle.py 13 例) | ✅ |
| 幂等结算 | 重复 job 不重复结算/上报 | 单测锁定(test_idempotent_no_double_settle) | ✅ |
| 落库失败不阻断 | DB 异常业务正常 | 单测锁定(test_failure_does_not_raise) | ✅ |
| trace 不可查容错 | score 失败仅 WARN | 单测锁定(test_trace_missing_warns_not_raises) | ✅ |
| 真实决策落库 | 跑一次真实 deep 分析(approve),decision_log 有新行且 entry_price 为真实现价 | [待人工:approve 案例需真 LLM;可查 `sqlite3 data/sessions.db "SELECT * FROM decision_log"`] | ⬜ |
| langfuse_trace_id 关联 | 落库行 trace_id 可在 Langfuse UI 打开对应 trace | [待人工:UI 核对] | ⬜ |
| 日批 job 真实结算 | 手动触发 settle_open_decisions() 对 open 行结算 + Langfuse 出现 3 个 score | [待人工:需真实行情 + open 决策] | ⬜ |
| scheduler 启动 | uvicorn 启动日志含「decision settle scheduler 已启动」;TESTING=1 不启动 | [待人工:启动后端核对日志] | ⬜ |

## 异常记录
[待填]

## 结论
[x] 存在待人工确认项(真实落库/trace 关联/日批结算/scheduler)
[ ] 全部通过,可 archive

## 备注
- 定时任务框架选型(APScheduler in-process,design 决策 6)**建议人工落 ADR 确认**——agent 不自建 ADR(AGENTS.md 红线)。
- 历史 TradeDecision 不回溯补录(design Migration Plan,Non-Goal)。
```

- [ ] **Step 4: 质量门禁**

```bash
uv run pytest tests/ --ignore=tests/e2e --ignore=tests/scripts -m "not live" -x -q
uv run ruff check
uv run mypy src/   # 与基线 75 错误对比(HEAD vs 430b004 worktree),零新增
openspec validate decision-outcome-tracking --strict
```

Expected: 全绿(715 基线 + 新增 ≈ 46);ruff 0;mypy 零新增;validate 通过。

- [ ] **Step 5: Commit**

```bash
git add tests/outcome/test_outcome_live.py tests/validation/2026-08-12-decision-outcome-tracking-validation.md
git commit -m "test: [outcome] @live 用例 + 人工验证报告骨架(Task 6)"
```

---

## Self-Review

**1. Spec coverage**(对照 spec 5 个 ADDED Requirement):
- ✅ 决策落库(3 Scenario)→ Task 5(产出即落库 / 失败不阻断 / trace 关联)+ Task 1(store)
- ✅ 事后行情追踪(6 Scenario)→ Task 2(止损/目标/同日/超期)+ Task 3(幂等/行情缺失重试/data_stale)+ Task 4(日批)
- ✅ Score 反向上报(4 Scenario)→ Task 3(结算即上报 / 方向符号化 / 基准超额 / trace 不可查容错)
- ✅ A 股异常结算规则(3 Scenario)→ Task 2(一字板递延 / 停牌顺延 / qfq——fetch_kline 默认 adjust="qfq" 已探明 akshare_client.py:405)
- ✅ 基准对比(3 Scenario)→ Task 3(fetch_index_kline + 基准收益)+ Task 2(配置覆盖 max_hold_days 参数 / 基准缺失 None)

**2. Placeholder scan**:无 TBD/TODO。Task 3/4/5 标注了「先读现有实现」的点(fetch_benchmark_kline 原逻辑保留、fund_manager mock 形态、api.py 变量名),均有明确的现状锚点(行号)与必须保持的语义,非占位符。

**3. Type consistency**:`Settlement` dataclass 字段跨 Task 2/3 一致;`insert_decision` record 键跨 Task 1/5 一致;`settle_open_decisions` 返回 dict 键跨 Task 3/4 一致;`_persist_decision_log(accumulated, session_id, stock_code, stock_name)` 签名 Task 5 内部一致。

**4. 已知实施风险**(brief 中提示):
- fund_manager 的 call_llm_streaming mock 形态 → Task 5 测试按现状调整,三场景语义必须保持
- api.py 报告落库段变量名(session_id/stock_name)→ Task 5 先读 878-909 定位
- apscheduler 新依赖 `uv add` → Task 4 一并提交 uv.lock
- accumulated 里 kline 是 DataFrame 还是 list[dict] → Task 5 helper 双兼容(hasattr iloc)
