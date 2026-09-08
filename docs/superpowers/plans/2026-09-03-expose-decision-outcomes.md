# Expose Decision Outcomes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已落库的 `decision_log` 决策结算结果通过只读 API + 前端「决策战绩」页暴露给用户。

**Architecture:** 后端在 `outcome/store.py` 加两个只读查询函数（SQL 聚合），`api.py` 加两个端点；前端复用下载中心页面模式（pathname 条件渲染 + 折叠态侧边栏入口），新增 `pages/decisions/DecisionCenter.tsx`；决策行跳转来源会话走现有 `selectSession`。

**Tech Stack:** FastAPI / SQLite / React 18 / Tailwind / vitest / Playwright（`tests/e2e/playwright/`）

## Global Constraints

- 只读暴露：不改结算规则、不改落库挂点、不改 Langfuse 回传、无写入路径（delta spec）
- 状态枚举：`open / hit_stop / hit_target / expired`；非法 status 返回 422
- 胜率/均值只基于已结算记录（`status != 'open'`）；`decision_excess` 为 null 剔除出超额均值，不当作 0
- 空表/无已结算 → 计数 0、胜率与均值 null（前端显示「暂无数据」占位「—」）
- A 股红涨绿跌：正收益/正超额用涨色（红），负值用跌色（绿）
- 后端测试 `uv run pytest`；前端 `cd frontend && npm test`（vitest）；E2E `cd tests/e2e/playwright && npx playwright test`（stub 套件，禁止 mock 被测业务接口）
- 代码注释中文，camelCase 命名，commit 信息清晰

---

### Task 1: 后端只读查询函数（store.py）

**Files:**
- Modify: `src/finance_agent/outcome/store.py`（追加函数，不改现有）
- Test: `tests/outcome/test_decision_queries.py`（新建）

**Interfaces:**
- Consumes: 现有 `_connect(db_path)`、`_default_db_path()`
- Produces: `DECISION_STATUSES: tuple[str, ...]`、`list_decisions(ticker: str | None, status: str | None, limit: int, db_path) -> list[dict]`、`decision_stats(db_path) -> dict`（Task 2 的 API 端点使用，签名须一致）

- [ ] **Step 1: 写失败测试**

```python
"""expose-decision-outcomes:store 层只读查询函数(list_decisions / decision_stats)。"""

import os

import pytest

from finance_agent.outcome.store import (
    DECISION_STATUSES,
    decision_stats,
    init_decision_log,
    insert_decision,
    list_decisions,
)

BASE = {
    "session_id": "sess-1",
    "timestamp": "2026-09-01T10:00:00",
    "ticker": "600519",
    "name": "贵州茅台",
    "action": "buy",
    "entry_price": 100.0,
    "stop_loss": 90.0,
    "target_price": 120.0,
    "confidence": 0.8,
    "position_size": 0.3,
}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "decisions.db"
    init_decision_log(path)
    return path


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_decision(rec, db_path=db)


def _settle(db, decision_id, **fields):
    from finance_agent.outcome.store import mark_settled

    settled = {
        "status": "hit_target",
        "settled_at": "2026-09-10T15:00:00",
        "settle_price": 115.0,
        "hold_days": 5,
        "decision_return": 0.15,
        "benchmark_return": 0.05,
        "decision_excess": 0.10,
    }
    settled.update(fields)
    mark_settled(decision_id, settled, db_path=db)


def test_list_decisions_empty(db):
    assert list_decisions(db_path=db) == []


def test_list_decisions_sorted_desc_by_timestamp(db):
    _insert(db, timestamp="2026-09-01T10:00:00", ticker="600519")
    _insert(db, timestamp="2026-09-02T10:00:00", ticker="300308")
    rows = list_decisions(db_path=db)
    assert [r["ticker"] for r in rows] == ["300308", "600519"]


def test_list_decisions_filter_ticker_and_status(db):
    _insert(db, ticker="600519")
    d2 = _insert(db, ticker="300308")
    _settle(db, d2)
    rows = list_decisions(ticker="600519", db_path=db)
    assert [r["ticker"] for r in rows] == ["600519"]
    rows = list_decisions(status="hit_target", db_path=db)
    assert [r["decision_id"] for r in rows] == [d2]
    rows = list_decisions(ticker="600519", status="hit_target", db_path=db)
    assert rows == []


def test_list_decisions_limit(db):
    for i in range(5):
        _insert(db, ticker=f"T{i}")
    assert len(list_decisions(limit=2, db_path=db)) == 2
    assert len(list_decisions(limit=0, db_path=db)) == 1  # 下限钳制为 1
    assert len(list_decisions(limit=9999, db_path=db)) == 5  # 上限钳制为 1000


def test_decision_statuses_enum():
    assert DECISION_STATUSES == ("open", "hit_stop", "hit_target", "expired")


def test_stats_empty_table(db):
    s = decision_stats(db_path=db)
    assert s["total"] == 0 and s["open"] == 0 and s["settled"] == 0
    assert s["win_rate"] is None and s["avg_return"] is None and s["avg_excess"] is None


def test_stats_all_open_no_settled(db):
    _insert(db)
    _insert(db)
    s = decision_stats(db_path=db)
    assert s["total"] == 2 and s["open"] == 2 and s["settled"] == 0
    assert s["win_rate"] is None and s["avg_return"] is None


def test_stats_settled_metrics_and_null_excess_excluded(db):
    _insert(db)  # open,不计入
    d1 = _insert(db, ticker="A")
    _settle(db, d1, decision_return=0.10, benchmark_return=0.05, decision_excess=0.05)
    d2 = _insert(db, ticker="B")
    _settle(db, d2, status="hit_stop", decision_return=-0.05, benchmark_return=None, decision_excess=None)
    s = decision_stats(db_path=db)
    assert s["total"] == 3 and s["open"] == 1 and s["settled"] == 2
    assert s["by_status"] == {"open": 1, "hit_target": 1, "hit_stop": 1}
    # 胜率 = 1/2；均值 = (0.10-0.05)/2；excess 只算 d1 → 0.05
    assert s["win_rate"] == 0.5
    assert s["avg_return"] == 0.025
    assert s["avg_excess"] == 0.05
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/outcome/test_decision_queries.py -q`
Expected: FAIL（ImportError，函数未定义）

- [ ] **Step 3: 最小实现（追加到 store.py）**

```python
DECISION_STATUSES = ("open", "hit_stop", "hit_target", "expired")


def list_decisions(
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 200,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """只读:按 ticker/status 过滤的决策列表,按 timestamp 倒序。limit 钳制 1..1000。"""
    limit = max(1, min(int(limit), 1000))
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM decision_log"
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def decision_stats(db_path: str | Path | None = None) -> dict[str, Any]:
    """只读:聚合战绩。胜率/均值只基于已结算(status!='open')记录,
    decision_excess 为 null 剔除出超额均值(不当作 0);无已结算时返回 null。"""
    conn = _connect(db_path)
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0])
        open_count = int(
            conn.execute("SELECT COUNT(*) FROM decision_log WHERE status='open'").fetchone()[0]
        )
        settled = total - open_count
        by_status = dict(
            conn.execute("SELECT status, COUNT(*) FROM decision_log GROUP BY status").fetchall()
        )
        win_rate: float | None = None
        avg_return: float | None = None
        avg_excess: float | None = None
        if settled:
            wins = int(
                conn.execute(
                    "SELECT COUNT(*) FROM decision_log WHERE status!='open' AND decision_return > 0"
                ).fetchone()[0]
            )
            win_rate = round(wins / settled, 4)
            avg_ret = conn.execute(
                "SELECT AVG(decision_return) FROM decision_log WHERE status!='open'"
            ).fetchone()[0]
            if avg_ret is not None:
                avg_return = round(float(avg_ret), 4)
            avg_exc = conn.execute(
                "SELECT AVG(decision_excess) FROM decision_log "
                "WHERE status!='open' AND decision_excess IS NOT NULL"
            ).fetchone()[0]
            if avg_exc is not None:
                avg_excess = round(float(avg_exc), 4)
        return {
            "total": total,
            "open": open_count,
            "settled": settled,
            "by_status": by_status,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "avg_excess": avg_excess,
        }
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/outcome/test_decision_queries.py -q`
Expected: PASS（6 个用例全绿）

- [ ] **Step 5: 提交**

```bash
git add tests/outcome/test_decision_queries.py src/finance_agent/outcome/store.py
git commit -m "feat: decision_log 只读查询函数(list_decisions/decision_stats)"
```

---

### Task 2: 只读 API 端点

**Files:**
- Modify: `src/finance_agent/api.py`（import + 两个端点，追加在 `/api/files` 附近）
- Test: `tests/test_api_decisions.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `DECISION_STATUSES` / `list_decisions` / `decision_stats`（`db_path` 走默认，测试用 monkeypatch `finance_agent.outcome.store._default_db_path`）
- Produces: `GET /api/decisions`（query: ticker/status/limit，非法 status → 422）、`GET /api/decisions/stats`

- [ ] **Step 1: 写失败测试**

```python
"""expose-decision-outcomes:GET /api/decisions 与 /api/decisions/stats 端点测试。"""

from fastapi.testclient import TestClient

from finance_agent.api import app
from finance_agent.outcome.store import init_decision_log, insert_decision, mark_settled

BASE = {
    "session_id": "sess-1",
    "timestamp": "2026-09-01T10:00:00",
    "ticker": "600519",
    "name": "贵州茅台",
    "action": "buy",
    "entry_price": 100.0,
    "stop_loss": 90.0,
    "target_price": 120.0,
    "confidence": 0.8,
    "position_size": 0.3,
}


def _use_db(monkeypatch, tmp_path):
    db = tmp_path / "decisions.db"
    init_decision_log(db)
    monkeypatch.setattr(
        "finance_agent.outcome.store._default_db_path", lambda: db
    )
    return db


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_decision(rec, db_path=db)


def test_list_empty(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).get("/api/decisions")
    assert resp.status_code == 200 and resp.json() == []


def test_list_returns_records_with_fields(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db)
    items = TestClient(app).get("/api/decisions").json()
    assert len(items) == 1
    row = items[0]
    assert row["ticker"] == "600519" and row["action"] == "buy" and row["status"] == "open"
    for field in (
        "decision_id", "session_id", "timestamp", "ticker", "name", "action",
        "entry_price", "stop_loss", "target_price", "confidence", "status",
        "settled_at", "settle_price", "hold_days", "decision_return",
        "benchmark_return", "decision_excess",
    ):
        assert field in row


def test_filter_and_invalid_status(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, ticker="600519")
    _insert(db, ticker="300308")
    c = TestClient(app)
    assert len(c.get("/api/decisions", params={"ticker": "600519"}).json()) == 1
    assert len(c.get("/api/decisions", params={"ticker": "300308", "status": "open"}).json()) == 1
    assert c.get("/api/decisions", params={"status": "bogus"}).status_code == 422


def test_stats_endpoint(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db)
    d2 = _insert(db, ticker="300308")
    mark_settled(
        d2,
        {
            "status": "hit_target", "settled_at": "2026-09-10T15:00:00",
            "settle_price": 115.0, "hold_days": 5,
            "decision_return": 0.10, "benchmark_return": 0.05, "decision_excess": 0.05,
        },
        db_path=db,
    )
    s = TestClient(app).get("/api/decisions/stats").json()
    assert s["total"] == 2 and s["open"] == 1 and s["settled"] == 1
    assert s["win_rate"] == 1.0 and s["avg_return"] == 0.1 and s["avg_excess"] == 0.05


def test_stats_empty(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    s = TestClient(app).get("/api/decisions/stats").json()
    assert s["win_rate"] is None and s["avg_return"] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_api_decisions.py -q`
Expected: FAIL（404，端点不存在）

- [ ] **Step 3: 最小实现**

在 api.py 顶部 import 块加入（现有第 128 行是 `from finance_agent.outcome.store import init_decision_log, insert_decision`）：

```python
from finance_agent.outcome.store import (  # noqa: E402
    DECISION_STATUSES,
    decision_stats,
    init_decision_log,
    insert_decision,
    list_decisions,
)
```

在 `/api/files` 相关端点之后追加（读取决策库,与 /api/files 同为只读列表端点）：

```python
@app.get("/api/decisions")
async def get_decisions(
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """expose-decision-outcomes:只读决策列表(决策战绩页数据源)。非法 status 返回 422。"""
    if status is not None and status not in DECISION_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    return await asyncio.to_thread(list_decisions, ticker=ticker, status=status, limit=limit)


@app.get("/api/decisions/stats")
async def get_decision_stats() -> dict[str, Any]:
    """expose-decision-outcomes:聚合战绩统计(胜率/均值只基于已结算记录)。"""
    return await asyncio.to_thread(decision_stats)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_api_decisions.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_api_decisions.py src/finance_agent/api.py
git commit -m "feat: 决策战绩只读 API(GET /api/decisions 与 /api/decisions/stats)"
```

---

### Task 3: 前端类型与 DecisionCenter 页面组件

**Files:**
- Modify: `frontend/src/types.ts`（追加 DecisionStatus/DecisionRecord/DecisionStats）
- Create: `frontend/src/pages/decisions/DecisionCenter.tsx`
- Create: `frontend/src/test/decisions/decisionCenter.test.tsx`（新建目录）

**Interfaces:**
- Consumes: `GET /api/decisions`、`GET /api/decisions/stats`（Task 2）
- Produces: `<DecisionCenter onBack={() => void} onOpenSession={(sessionId: string) => void} />`（Task 4 在 App.tsx 使用；`data-testid="decision-center"`、`data-testid="decisions-empty"`）

- [ ] **Step 1: 写失败测试（types + 组件）**

types.ts 追加：

```ts
// 决策结算状态（expose-decision-outcomes：与后端 DECISION_STATUSES 一致）
export type DecisionStatus = 'open' | 'hit_stop' | 'hit_target' | 'expired'

// 决策记录（GET /api/decisions 返回项）
export interface DecisionRecord {
  decision_id: string
  session_id: string
  langfuse_trace_id: string | null
  timestamp: string
  ticker: string
  name: string | null
  action: string
  entry_price: number
  stop_loss: number | null
  target_price: number | null
  confidence: number
  position_size: number | null
  status: DecisionStatus
  settled_at: string | null
  settle_price: number | null
  hold_days: number | null
  decision_return: number | null
  benchmark_return: number | null
  decision_excess: number | null
  updated_at: string
}

// 聚合战绩（GET /api/decisions/stats 返回项）
export interface DecisionStats {
  total: number
  open: number
  settled: number
  by_status: Record<string, number>
  win_rate: number | null
  avg_return: number | null
  avg_excess: number | null
}
```

`frontend/src/test/decisions/decisionCenter.test.tsx`（沿用 downloadCenter.test.tsx 的 mock 模式，单独渲染 DecisionCenter，不整树渲染 App，隔离导航副作用）：

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DecisionCenter } from '../../pages/decisions/DecisionCenter'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

const open: Record<string, unknown> = {
  decision_id: 'd1', session_id: 's1', langfuse_trace_id: null,
  timestamp: '2026-09-01T10:00:00', ticker: '600519', name: '贵州茅台',
  action: 'buy', entry_price: 100, stop_loss: 90, target_price: 120,
  confidence: 0.8, position_size: 0.3, status: 'open',
  settled_at: null, settle_price: null, hold_days: null,
  decision_return: null, benchmark_return: null, decision_excess: null,
  updated_at: '2026-09-01T10:00:00',
}
const hit: Record<string, unknown> = {
  decision_id: 'd2', session_id: 's2', langfuse_trace_id: null,
  timestamp: '2026-09-02T10:00:00', ticker: '300308', name: '中际旭创',
  action: 'buy', entry_price: 100, stop_loss: null, target_price: 120,
  confidence: 0.7, position_size: 0.2, status: 'hit_target',
  settled_at: '2026-09-10T15:00:00', settle_price: 115, hold_days: 5,
  decision_return: 0.15, benchmark_return: 0.05, decision_excess: 0.10,
  updated_at: '2026-09-10T15:00:00',
}

function mockFetch(opts: { decisions?: unknown; stats?: unknown } = {}) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/decisions') {
      return Promise.resolve(new Response(JSON.stringify(opts.decisions ?? []), { status: 200 }))
    }
    if (url === '/api/decisions/stats') {
      return Promise.resolve(new Response(JSON.stringify(opts.stats ?? {
        total: 0, open: 0, settled: 0, by_status: {}, win_rate: null, avg_return: null, avg_excess: null,
      }), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 404 }))
  }))
}

function renderPage() {
  return render(<DecisionCenter onBack={vi.fn()} onOpenSession={vi.fn()} />)
}

describe('决策战绩页面（expose-decision-outcomes）', () => {
  beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('空态显示提示', async () => {
    mockFetch()
    renderPage()
    expect(await screen.findByTestId('decisions-empty')).toBeInTheDocument()
  })

  it('汇总卡与列表渲染、null 字段占位「—」', async () => {
    mockFetch({
      decisions: [hit, open],
      stats: { total: 2, open: 1, settled: 1, by_status: { open: 1, hit_target: 1 }, win_rate: 1, avg_return: 0.15, avg_excess: 0.1 },
    })
    renderPage()
    expect(await screen.findByText('贵州茅台')).toBeInTheDocument()
    expect(screen.getByText('中际旭创')).toBeInTheDocument()
    // 已结算行显示收益与超额；open 行收益显示「—」
    expect(screen.getByText('+15.00%')).toBeInTheDocument()
    expect(screen.getByText('+10.00%')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    // 状态中文标签
    expect(screen.getByText('达标')).toBeInTheDocument()
    expect(screen.getByText('持有中')).toBeInTheDocument()
  })

  it('正收益红涨、负收益绿跌', async () => {
    mockFetch({
      decisions: [hit, { ...hit, decision_id: 'd3', decision_return: -0.05, decision_excess: -0.02 }],
      stats: { total: 2, open: 0, settled: 2, by_status: { hit_target: 1, hit_stop: 1 }, win_rate: 0.5, avg_return: 0.05, avg_excess: 0.04 },
    })
    renderPage()
    const up = await screen.findByText('+15.00%')
    const down = await screen.findByText('-5.00%')
    expect(up.className).toContain('red')
    expect(down.className).toContain('green')
  })

  it('按状态与股票过滤调用带参数接口', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.startsWith('/api/decisions')) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
      }
      if (url === '/api/decisions/stats') {
        return Promise.resolve(new Response(JSON.stringify({ total: 0, open: 0, settled: 0, by_status: {}, win_rate: null, avg_return: null, avg_excess: null }), { status: 200 }))
      }
      return Promise.resolve(new Response('', { status: 404 }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    await screen.findByTestId('decisions-empty')
    fireEvent.change(screen.getByTestId('decisions-status-filter'), { target: { value: 'hit_target' } })
    fireEvent.change(screen.getByTestId('decisions-ticker-filter'), { target: { value: '600519' } })
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(c => String(c[0]))
      expect(calls.some(u => u.includes('status=hit_target') && u.includes('ticker=600519'))).toBe(true)
    })
  })

  it('点击决策行触发 onOpenSession', async () => {
    mockFetch({ decisions: [hit] })
    const onOpen = vi.fn()
    render(<DecisionCenter onBack={vi.fn()} onOpenSession={onOpen} />)
    const row = await screen.findByTestId('decision-row-d2')
    fireEvent.click(row)
    expect(onOpen).toHaveBeenCalledWith('s2')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/decisions/decisionCenter.test.tsx`
Expected: FAIL（组件/模块不存在）

- [ ] **Step 3: 实现 DecisionCenter.tsx**

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import type { DecisionRecord, DecisionStats, DecisionStatus } from '../../types'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'

const STATUS_LABEL: Record<DecisionStatus, string> = {
  open: '持有中',
  hit_stop: '止损',
  hit_target: '达标',
  expired: '超期',
}

const ACTION_LABEL: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  hold: '持有',
  watch: '观望',
}

const STATUS_OPTIONS: { key: DecisionStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'open', label: '持有中' },
  { key: 'hit_target', label: '达标' },
  { key: 'hit_stop', label: '止损' },
  { key: 'expired', label: '超期' },
]

// 涨跌着色（A 股约定红涨绿跌）：收益与超额字段共用
function DeltaValue({ value }: { value: number | null }) {
  if (value === null) return <span className="text-txt-tertiary">—</span>
  const pct = value * 100
  const up = value >= 0
  const cls = up ? 'text-red-500' : 'text-green-600'
  return <span className={`${cls} font-medium`}>{up ? '+' : ''}{pct.toFixed(2)}%</span>
}

function fmt(value: number | null, digits = 2) {
  return value === null ? '—' : value.toFixed(digits)
}

export function DecisionCenter({ onBack, onOpenSession }: {
  onBack: () => void
  onOpenSession: (sessionId: string) => void
}) {
  // null = 加载中；error 与空态严格区分（与 DownloadCenter 同规）
  const [records, setRecords] = useState<DecisionRecord[] | null>(null)
  const [stats, setStats] = useState<DecisionStats | null>(null)
  const [error, setError] = useState(false)
  const [status, setStatus] = useState<DecisionStatus | 'all'>('all')
  const [ticker, setTicker] = useState('')

  const load = useCallback(async () => {
    setError(false)
    setRecords(null)
    setStats(null)
    try {
      const params = new URLSearchParams()
      if (status !== 'all') params.set('status', status)
      if (ticker.trim()) params.set('ticker', ticker.trim())
      const qs = params.toString()
      const [listResp, statsResp] = await Promise.all([
        fetch(`/api/decisions${qs ? `?${qs}` : ''}`),
        fetch('/api/decisions/stats'),
      ])
      if (!listResp.ok || !statsResp.ok) throw new Error(String(listResp.status))
      setRecords((await listResp.json()) as DecisionRecord[])
      setStats((await statsResp.json()) as DecisionStats)
    } catch {
      setError(true)
      toast.error('决策数据加载失败')
    }
  }, [status, ticker])

  useEffect(() => { void load() }, [load])

  // 列表过滤走后端参数；本组件内不再二次过滤（spec：列表通过 API 过滤参数刷新）
  const rows = records ?? []

  return (
    <div className="mx-auto max-w-5xl px-6 py-8" data-testid="decision-center">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--text-default)' }}>决策战绩</h1>
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="decisions-back">返回聊天</Button>
      </div>

      {error ? (
        <div className="text-sm py-16 text-center" style={{ color: 'var(--text-tertiary)' }}>数据加载失败，请刷新重试</div>
      ) : records === null ? (
        <div className="py-16 text-center text-sm" style={{ color: 'var(--text-tertiary)' }} data-testid="decisions-loading">加载中…</div>
      ) : rows.length === 0 ? (
        <div className="py-16 text-center" data-testid="decisions-empty">
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>暂无决策记录。完成一次深度分析并产生交易决策后，结算结果会出现在这里。</p>
          <Button variant="ghost" size="sm" className="mt-4" onClick={onBack}>返回聊天</Button>
        </div>
      ) : (
        <>
          {/* 汇总卡 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="decisions-summary">
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>总决策数</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }} data-testid="summary-total">{stats?.total ?? 0}</div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>胜率（已结算）</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }}>{stats?.win_rate === null || stats?.win_rate === undefined ? '—' : `${(stats.win_rate * 100).toFixed(1)}%`}</div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>平均收益</div>
              <div className="text-2xl font-semibold"><DeltaValue value={stats?.avg_return ?? null} /></div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>平均超额（沪深300）</div>
              <div className="text-2xl font-semibold"><DeltaValue value={stats?.avg_excess ?? null} /></div>
            </div>
          </div>

          {/* 过滤 */}
          <div className="flex gap-3 mb-4">
            <select
              data-testid="decisions-status-filter"
              value={status}
              onChange={e => setStatus(e.target.value as DecisionStatus | 'all')}
              className="h-9 rounded-lg px-3 text-sm border"
              style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', borderColor: 'var(--border-neutral-l1)' }}
            >
              {STATUS_OPTIONS.map(o => (
                <option key={o.key} value={o.key}>{o.label}</option>
              ))}
            </select>
            <Input
              type="text"
              data-testid="decisions-ticker-filter"
              value={ticker}
              onChange={e => setTicker(e.target.value)}
              placeholder="按股票代码过滤…"
              className="h-9 text-sm max-w-48"
            />
          </div>

          {/* 列表 */}
          <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-neutral-l1)' }}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  <th className="px-4 py-2 font-normal">标的</th>
                  <th className="px-4 py-2 font-normal">操作</th>
                  <th className="px-4 py-2 font-normal">状态</th>
                  <th className="px-4 py-2 font-normal text-right">入场价</th>
                  <th className="px-4 py-2 font-normal text-right">结算价</th>
                  <th className="px-4 py-2 font-normal text-right">持有天数</th>
                  <th className="px-4 py-2 font-normal text-right">收益</th>
                  <th className="px-4 py-2 font-normal text-right">基准超额</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr
                    key={r.decision_id}
                    data-testid={`decision-row-${r.decision_id}`}
                    onClick={() => onOpenSession(r.session_id)}
                    className="cursor-pointer transition-colors border-t"
                    style={{ borderColor: 'var(--border-neutral-l1)' }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium" style={{ color: 'var(--text-default)' }}>{r.name ?? r.ticker}</div>
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{r.ticker}</div>
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{ACTION_LABEL[r.action] ?? r.action}</td>
                    <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{STATUS_LABEL[r.status]}</td>
                    <td className="px-4 py-3 text-right">{fmt(r.entry_price)}</td>
                    <td className="px-4 py-3 text-right">{fmt(r.settle_price)}</td>
                    <td className="px-4 py-3 text-right">{fmt(r.hold_days, 0)}</td>
                    <td className="px-4 py-3 text-right"><DeltaValue value={r.decision_return} /></td>
                    <td className="px-4 py-3 text-right"><DeltaValue value={r.decision_excess} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/decisions/decisionCenter.test.tsx`
Expected: PASS（5 个用例全绿）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/types.ts frontend/src/pages/decisions/DecisionCenter.tsx frontend/src/test/decisions/decisionCenter.test.tsx
git commit -m "feat: 决策战绩页面(DecisionCenter)+ 类型 + 组件测试"
```

---

### Task 4: App.tsx 路由接入与侧边栏入口

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ui/sidebar.tsx`（无改动，侧边栏入口在 App.tsx 内）
- Test: `frontend/src/test/decisions/decisionCenter.test.tsx`（追加 2 个用例）

**Interfaces:**
- Consumes: Task 3 的 `<DecisionCenter onBack onOpenSession>`
- Produces: `/decisions` 路由渲染；折叠态侧边栏图标 `data-testid="sidebar-decisions-collapsed"`；跳转来源会话复用 `selectSession`

- [ ] **Step 1: 写失败测试（追加到 decisionCenter.test.tsx）**

```tsx
it('App 整树渲染:侧边栏折叠态入口直达 /decisions 渲染页面', async () => {
  mockFetch({ decisions: [hit] })
  window.history.pushState({}, '', '/decisions')
  const { default: App } = await import('../../App')
  const { render } = await import('@testing-library/react')
  render(<App />)
  expect(await screen.findByTestId('decision-center')).toBeInTheDocument()
  expect(screen.getByText('中际旭创')).toBeInTheDocument()
  window.history.pushState({}, '', '/')
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/decisions/decisionCenter.test.tsx`
Expected: FAIL（/decisions 路由未注册，渲染首页）

- [ ] **Step 3: 实现（App.tsx）**

顶部 import 追加：

```tsx
import { DecisionCenter } from './pages/decisions/DecisionCenter'
```

主内容区 pathname 条件渲染（放在 `/downloads` 分支之后）：

```tsx
{pathname === '/decisions' ? (
  <DecisionCenter
    onBack={() => navigate('/')}
    onOpenSession={(sessionId) => {
      navigate('/')
      void selectSession(sessionId)
    }}
  />
) : pathname === '/downloads' ? (
```

AppSidebar props 追加 `onOpenDecisions={() => navigate('/decisions')}`，并在折叠态图标栏 `sidebar-downloads-collapsed` 附近追加：

```tsx
<SidebarIcon label="决策战绩">
  <Button variant="ghost" size="icon" onClick={onOpenDecisions} aria-label="决策战绩" data-testid="sidebar-decisions-collapsed">
    <i className="fas fa-chart-line text-sm"></i>
  </Button>
</SidebarIcon>
```

（`selectSession` 已在 App.tsx 定义，签名不变；`navigate` 已在作用域内。）

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/decisions/decisionCenter.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.tsx frontend/src/test/decisions/decisionCenter.test.tsx
git commit -m "feat: /decisions 路由 + 折叠态侧边栏入口"
```

---

### Task 5: E2E spec（决策战绩页）

**Files:**
- Create: `tests/e2e/playwright/tests/decisions.spec.ts`

**Interfaces:**
- Consumes: 后端 webServer（TESTING=1, `REPORTS_DIR` 隔离）+ 前端 5173；`/api/decisions`（stub 后端为全新测试库，天然空态 → 需 seed 或用「直达 + 空态」断言）
- Produces: 门禁 spec（全绿）

- [ ] **Step 1: 写 E2E spec（真实浏览器，不 mock 业务接口）**

```ts
import { test, expect } from '@playwright/test'

/**
 * expose-decision-outcomes Task 5：/decisions 决策战绩页 E2E 门禁
 *
 * stub 后端使用独立测试库（SESSIONS_DB_PATH 隔离），decision_log 初始为空 → 天然空态。
 * 覆盖：
 * 1. 折叠态侧边栏「决策战绩」入口 → URL 变为 /decisions 且渲染页面
 * 2. 直达 /decisions → 渲染 + 空态提示 + 「返回聊天」回跳会话页
 *
 * 红线约束：不 mock /api/decisions 业务接口（E2E 禁止 route.fulfill 被测系统）；
 * 数据行渲染/过滤等细节由组件测试（frontend/src/test/decisions/）覆盖。
 */
test.describe('expose-decision-outcomes: 决策战绩页', () => {
  test.describe.configure({ retries: 2 })

  test('折叠态侧边栏「决策战绩」入口跳转 /decisions 并渲染页面', async ({ page }) => {
    await page.goto('/')
    const entry = page.getByTestId('sidebar-decisions-collapsed')
    await expect(entry).toBeVisible()
    await entry.click()
    await expect(page).toHaveURL(/\/decisions$/)
    await expect(page.getByTestId('decision-center')).toBeVisible()
  })

  test('直达 /decisions 渲染页面并显示空态，可返回聊天', async ({ page }) => {
    test.setTimeout(240_000)
    await page.goto('/decisions')
    await expect(page.getByTestId('decision-center')).toBeVisible()
    const empty = page.getByTestId('decisions-empty')
    const maxAttempts = 6
    let visible = false
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        await expect(empty).toBeVisible({ timeout: 20_000 })
        visible = true
        break
      } catch {
        if (attempt < maxAttempts - 1) {
          await page.reload({ timeout: 20_000 }).catch(() => {})
        }
      }
    }
    expect(visible, '轮询 6 次后空态仍未出现：/api/decisions 在全量套件负载下持续无响应窗口').toBe(true)
    await empty.getByRole('button', { name: '返回聊天' }).click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: '今天想研究什么？' })).toBeVisible()
  })
})
```

- [ ] **Step 2: 运行确认通过（可先单 spec）**

Run: `cd tests/e2e/playwright && npx playwright test tests/decisions.spec.ts --workers=1`
Expected: PASS（2 例全绿）

- [ ] **Step 3: 全量门禁回归**

Run: `cd tests/e2e/playwright && npx playwright test`
Expected: PASS（存量 spec 不受影响，新 spec 全绿）

- [ ] **Step 4: 提交**

```bash
git add tests/e2e/playwright/tests/decisions.spec.ts
git commit -m "test: 决策战绩页 E2E 门禁 spec"
```

---

### Task 6: 全量验证与人工验证报告

- [ ] **Step 1: 后端全量测试**

Run: `uv run pytest -q`
Expected: 0 failures

- [ ] **Step 2: 前端全量测试**

Run: `cd frontend && npm test`
Expected: 全部通过

- [ ] **Step 3: Lint / 类型检查**

Run: `uv run ruff check src/finance_agent/outcome/store.py src/finance_agent/api.py` 与 `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 人工验证报告**

Create: `tests/validation/2026-09-03-expose-decision-outcomes-validation.md`（含决策数字与 decision_log 直查核对、跳转会话体验）
