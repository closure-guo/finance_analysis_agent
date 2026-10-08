# add-current-stance-view Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 战绩页新增「当前观点」区（每股最新一条 open 观点的立场视图）+ 只读接口 `GET /api/v1/track-record/current`，台账不动、统计口径零改动。

**Architecture:** 后端 model 层新增按标的收敛的查询函数（join 子查询取每股 `MAX(created_at)` 的 open 行），API 层新增只读端点（as_of + disclaimer 约定），前端在 IndexCompareCard 与观点日志之间插入独立区块（独立加载、显式失败文案）。OpenSpec delta 见 `openspec/changes/add-current-stance-view/`。

**Tech Stack:** FastAPI + sqlite3（同步短连接）、React 18 + TS + vitest + @testing-library、Playwright（专属 track-record 套件 `playwright.track-record.config.ts`，端口 8004/5177，独立测试库）。

## Global Constraints

- 在 `.worktrees/` 隔离 worktree 中实施（主检出被并发会话使用；主检出现有他人未提交改动 report.py/test_report.py，禁止触碰）
- `openspec/specs/` 主规范库禁手改；本变更只经 delta（已建）
- E2E 红线：禁止 route.fulfill/MSW mock 业务接口；造数只走 `TESTING=1` 的 `POST /api/test/seed`（`track_record.predictions` 通道）
- commit 格式 `feat(track-record): ...`；origin/main 禁 merge、须 PR
- 后端 lint/type 门禁：`uv run ruff check`、`uv run mypy` 零新增告警
- 排序列白名单模式：列名只能来自固定字面量，值参数化（防注入，与 `_SORT_WHITELIST` 同纪律）
- 本变更不涉及 prompts，无需 `scripts/deploy_prompts.py`

---

### Task 1: 后端查询函数 list_current_predictions

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`（在 `list_predictions` 之后追加）
- Test: `tests/outcome/test_track_record_model.py`（文件末尾追加）

**Interfaces:**
- Consumes: `model.py` 既有 `_connect(db_path)`（row_factory=sqlite3.Row）、`insert_prediction(record, db_path=)`、`update_prediction_status(prediction_id, resolved, db_path=)`、`init_predictions(path)`
- Produces: `list_current_predictions(source_type: str | None = None, db_path: str | Path | None = None) -> list[dict[str, Any]]`——Task 2 的端点调用它

- [ ] **Step 1: Write the failing test**

在 `tests/outcome/test_track_record_model.py` 末尾追加（import 区的 `from finance_agent.outcome.track_record.model import (...)` 中加入 `list_current_predictions`）：

```python
# ── add-current-stance-view:每股最新一条 open 的立场视图 ──

def test_list_current_latest_open_per_symbol(db):
    """同股多条 open 只返回 created_at 最新一条;多股各自一行,倒序。"""
    _insert(db, symbol="601058.SH", created_at="2026-10-05T10:00:00")
    _insert(db, symbol="601058.SH", created_at="2026-10-06T10:00:00")
    _insert(db, symbol="300033.SZ", created_at="2026-10-06T11:00:00")
    rows = list_current_predictions(db_path=db)
    assert [r["symbol"] for r in rows] == ["300033.SZ", "601058.SH"]
    assert [r["created_at"] for r in rows] == ["2026-10-06T11:00:00", "2026-10-06T10:00:00"]


def test_list_current_excludes_closed_and_dup(db):
    """dup/已结算/unresolvable 行不进入;该标的取其最新一条 open;仅剩关闭行的标的整体不出现。"""
    old = _insert(db, symbol="600519.SH", created_at="2026-10-01T10:00:00")
    dup = _insert(db, symbol="600519.SH", created_at="2026-10-02T10:00:00")
    update_prediction_status(
        dup, {"status": "duplicate_of_day", "resolution_rule": "duplicate_of_day"}, db_path=db
    )
    update_prediction_status(
        old,
        {"status": "resolved_neutral", "resolution_rule": "superseded", "resolved_at": "2026-10-03"},
        db_path=db,
    )
    keep = _insert(db, symbol="600519.SH", created_at="2026-10-04T10:00:00")
    only_closed = _insert(db, symbol="600026.SH", created_at="2026-10-01T09:00:00")
    update_prediction_status(
        only_closed, {"status": "unresolvable", "resolution_rule": "stale_no_market"}, db_path=db
    )
    rows = list_current_predictions(db_path=db)
    assert [r["prediction_id"] for r in rows] == [keep]


def test_list_current_empty_db(db):
    assert list_current_predictions(db_path=db) == []


def test_list_current_source_filter(db):
    """source 过滤;缺省行内携带 source_type 供区分。"""
    _insert(db, symbol="600015.SH", source_type="live", created_at="2026-10-05T10:00:00")
    _insert(db, symbol="600016.SH", source_type="backtest", created_at="2026-10-05T11:00:00")
    assert [r["symbol"] for r in list_current_predictions("live", db_path=db)] == ["600015.SH"]
    assert [r["symbol"] for r in list_current_predictions("backtest", db_path=db)] == ["600016.SH"]
    assert len(list_current_predictions(db_path=db)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_track_record_model.py -k list_current -v`
Expected: FAIL with `ImportError: cannot import name 'list_current_predictions'`

- [ ] **Step 3: Write minimal implementation**

在 `src/finance_agent/outcome/track_record/model.py` 的 `count_predictions` 函数之后追加：

```python
def list_current_predictions(
    source_type: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """当前立场视图(add-current-stance-view):每股最新一条 status='open' 的观点。

    立场语义 = 最新一条仍在窗口内的活跃主张:dup/superseded/已结算行不代表当前
    立场,一律排除;跨日多条 open 由 MAX(created_at) 收敛为每股一行。日主机制
    保证同股同日至多一条 open,本函数不改变任何统计口径,纯展示查询。
    """
    conn = _connect(db_path)
    try:
        cond = ""
        params: list[Any] = []
        if source_type:
            cond = " AND source_type=?"
            params.append(source_type)
        # 列名固定字面量、值参数化;created_at 并列时 prediction_id 作确定性 tiebreak,
        # Python 层按 symbol 去重保首行(防御同秒双 open 的理论并列)
        rows = conn.execute(
            f"""
            SELECT p.* FROM predictions p
            JOIN (
                SELECT symbol, MAX(created_at) AS max_created
                FROM predictions WHERE status='open'{cond}
                GROUP BY symbol
            ) m ON p.symbol = m.symbol AND p.created_at = m.max_created
            WHERE p.status='open'{" AND p.source_type=?" if source_type else ""}
            ORDER BY p.created_at DESC, p.prediction_id DESC
            """,  # noqa: S608
            params + ([source_type] if source_type else []),
        ).fetchall()
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if d["symbol"] in seen:
                continue
            seen.add(d["symbol"])
            out.append(d)
        return out
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_track_record_model.py -v`
Expected: 全部 PASS（含既有用例，确认无回归）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py tests/outcome/test_track_record_model.py
git commit -m "feat(track-record): list_current_predictions 每股最新一条 open 立场查询 (add-current-stance-view)"
```

---

### Task 2: 只读端点 GET /api/v1/track-record/current

**Files:**
- Modify: `src/finance_agent/api.py`（在 `track_record_predictions` 端点之后追加）
- Test: `tests/test_api_track_record.py`（文件末尾追加）

**Interfaces:**
- Consumes: Task 1 的 `list_current_predictions(source_type, db_path)`、api.py 既有 `_track_as_of()`、`_DISCLAIMER`
- Produces: `GET /api/v1/track-record/current?source=` → `{"current": [PredictionRecord...], "total": int, "as_of": str, "disclaimer": str}`——Task 3 前端消费

- [ ] **Step 1: Write the failing test**

在 `tests/test_api_track_record.py` 末尾追加（import 区加入 `list_current_predictions` 无需——端点测试只用 HTTP；`from finance_agent.api import app` 已有）：

```python
def test_current_endpoint_latest_open_per_symbol(monkeypatch, tmp_path):
    """立场视图:每股仅最新 open;dup/已结算不进入;as_of+disclaimer 必带。"""
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, symbol="601058.SH", direction="neutral", created_at="2026-10-05T10:00:00")
    _insert(db, symbol="601058.SH", direction="neutral", created_at="2026-10-06T10:00:00")
    dup = _insert(db, symbol="300033.SZ", created_at="2026-10-06T11:00:00")
    update_prediction_status(
        dup, {"status": "duplicate_of_day", "resolution_rule": "duplicate_of_day"}, db_path=db
    )
    resp = TestClient(app).get("/api/v1/track-record/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["current"][0]["symbol"] == "601058.SH"
    assert data["current"][0]["created_at"] == "2026-10-06T10:00:00"
    assert data["current"][0]["source_type"] == "live"
    assert data["as_of"] and data["disclaimer"]


def test_current_endpoint_source_filter(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, symbol="600015.SH", source_type="live", created_at="2026-10-05T10:00:00")
    _insert(db, symbol="600016.SH", source_type="backtest", created_at="2026-10-05T11:00:00")
    resp = TestClient(app).get("/api/v1/track-record/current?source=live")
    assert resp.status_code == 200
    assert [r["symbol"] for r in resp.json()["current"]] == ["600015.SH"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_track_record.py -k current -v`
Expected: FAIL with `assert 404 == 200`

- [ ] **Step 3: Write minimal implementation**

在 `src/finance_agent/api.py` 的 `track_record_predictions` 端点之后追加（同文件 import 区 `from finance_agent.outcome.track_record.model import (...)` 中加入 `list_current_predictions`）：

```python
@app.get("/api/v1/track-record/current")
async def track_record_current(source: str | None = None) -> dict[str, Any]:
    """add-current-stance-view:当前立场视图——每股最新一条 open 观点。

    纯展示收敛,不改变任何统计口径(分母仍按日主规则);dup/已结算/unresolvable
    不代表当前立场,一律排除。行内携带 source_type 供回测/实盘区分,可选 source
    参数过滤,不产出无法区分口径的合并视图。
    """
    rows = await asyncio.to_thread(list_current_predictions, source)
    return {
        "current": rows,
        "total": len(rows),
        "as_of": _track_as_of(),
        "disclaimer": _DISCLAIMER,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_track_record.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_track_record.py
git commit -m "feat(track-record): GET /track-record/current 当前立场只读端点 (add-current-stance-view)"
```

---

### Task 3: 前端「当前观点」区块

**Files:**
- Modify: `frontend/src/types.ts`（`PredictionsResponse` 接口附近追加）
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `GET /api/v1/track-record/current` 响应；页面既有 `DIRECTION_LABEL`/`STATUS_CLS`/`STATUS_LABEL`/`fmt`/`navigate`/`PredictionRecord` 类型
- Produces: testid `current-stance`（区块容器）、`current-stance-row-{prediction_id}`（行）、`current-stance-empty`（空态）——Task 4 E2E 依赖

- [ ] **Step 1: Write the failing test**

`frontend/src/test/trackRecord/trackRecordPage.test.tsx`：

1. `mockFetch` 的 opts 参数类型加入 `current?: unknown`，并在 `/api/v1/track-record/segments` 分支之后加入（注意放在 `/predictions` 分支之前，includes 判定互不冲突）：

```tsx
    if (url.includes('/api/v1/track-record/current')) {
      return Promise.resolve(new Response(JSON.stringify({
        current: opts.current ?? [], total: (opts.current as unknown[])?.length ?? 0,
        as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
      }), { status: 200 }))
    }
```

2. 文件顶部常量区加入测试数据：

```tsx
const CURRENT = [
  {
    prediction_id: 'p2', source_type: 'live', symbol: '300308.SZ', symbol_name: '中际旭创',
    direction: 'neutral', entry_price: 100, target_price: null, horizon_days: 20,
    confidence: 0.5, benchmark: '000300.SH', langfuse_trace_id: null,
    status: 'open', created_at: '2026-09-02T10:00:00', resolved_at: null,
    exit_price: null, raw_return: null, excess_return: null, resolution_rule: null,
  },
]
```

3. describe 块内追加用例：

```tsx
  it('当前观点区:每股最新一条 open,含判定窗口与状态', async () => {
    mockFetch({ current: CURRENT, predictions: [] })
    renderPage()
    const stance = await screen.findByTestId('current-stance')
    expect(stance).toBeInTheDocument()
    expect(screen.getByText(/每股仅显示最新一条进行中观点/)).toBeInTheDocument()
    expect(screen.getByTestId('current-stance-row-p2')).toContainText('中际旭创')
    expect(screen.getByTestId('current-stance-row-p2')).toContainText('T+20')
    expect(screen.getByTestId('current-stance-row-p2')).toContainText('进行中')
  })

  it('当前观点区空态:显示空态文案而非隐藏区块', async () => {
    mockFetch({ current: [] })
    renderPage()
    expect(await screen.findByTestId('current-stance-empty')).toHaveTextContent('暂无进行中观点')
  })

  it('当前观点区加载失败:显式失败文案,不冒充空态', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/api/v1/track-record/current')) {
        return Promise.resolve(new Response('', { status: 500 }))
      }
      if (url.includes('/api/v1/track-record/overview')) {
        return Promise.resolve(new Response(JSON.stringify({
          total: 0, open: 0, settled: 0, win_rate: null, avg_excess: null,
          status_counts: {}, source_type: null, insufficient_sample: true,
          as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
          portfolio: { available: false, annual_return: null, volatility: null,
            sharpe: null, max_drawdown: null, risk_score: null, risk_label: null, as_of: null },
        }), { status: 200 }))
      }
      if (url.includes('/api/v1/track-record/equity-curve')) {
        return Promise.resolve(new Response(JSON.stringify({ points: [] }), { status: 200 }))
      }
      if (url.includes('/api/v1/track-record/segments')) {
        return Promise.resolve(new Response(JSON.stringify({ dimensions: [] }), { status: 200 }))
      }
      if (url.includes('/api/v1/track-record/predictions')) {
        return Promise.resolve(new Response(JSON.stringify({
          predictions: [], page: 1, page_size: 50, total: 0,
        }), { status: 200 }))
      }
      if (url.includes('/api/v1/track-record/index-compare')) {
        return Promise.resolve(new Response(JSON.stringify(INDEX_COMPARE), { status: 200 }))
      }
      return Promise.resolve(new Response('', { status: 404 }))
    }))
    renderPage()
    expect(await screen.findByText('当前观点加载失败')).toBeInTheDocument()
    expect(screen.queryByTestId('current-stance-empty')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- trackRecordPage`
Expected: FAIL——`Unable to find [data-testid="current-stance"]`（区块不存在）

- [ ] **Step 3: Write minimal implementation**

1. `frontend/src/types.ts` 在 `PredictionsResponse` 接口后追加：

```ts
// 当前立场视图（GET /api/v1/track-record/current，add-current-stance-view）：
// 每股最新一条 open 观点，行结构与观点日志一致
export interface CurrentStanceResponse {
  current: PredictionRecord[]
  total: number
  as_of: string
  disclaimer: string
}
```

2. `frontend/src/pages/trackRecord/TrackRecordPage.tsx`：

a. import 区：types 行加入 `CurrentStanceResponse`：

```tsx
import type { CurrentStanceResponse, EquityCurvePoint, PredictionRecord, PredictionsResponse, SegmentDimension, TrackRecordOverview } from '../../types'
```

b. state 区（`const [segments, setSegments] = ...` 之后）加入：

```tsx
  const [currentStance, setCurrentStance] = useState<PredictionRecord[] | null>(null)
  const [currentStanceError, setCurrentStanceError] = useState(false)
```

c. `load` useCallback 内，主 `Promise.all` 的 try/catch 之后追加独立加载（不与总览绑死成败）：

```tsx
      // 当前立场视图独立加载(add-current-stance-view):失败显示显式失败文案,
      // 不静默降级为空态冒充「无观点」
      try {
        const csResp = await fetch('/api/v1/track-record/current')
        if (!csResp.ok) throw new Error(String(csResp.status))
        const cs = (await csResp.json()) as CurrentStanceResponse
        setCurrentStance(cs.current)
        setCurrentStanceError(false)
      } catch {
        setCurrentStanceError(true)
      }
```

d. 渲染区：在 `<IndexCompareCard span={prefs.timeSpan} />` 与观点日志 header `<div className="flex items-center justify-between mb-3" data-testid="prediction-log-header">` 之间插入：

```tsx
          {/* 当前观点区（add-current-stance-view）：每股最新一条 open 的立场视图。
              纯展示收敛：台账不受影响，统计口径零改动（delta spec 战绩页面 MODIFIED） */}
          <div data-testid="current-stance" className="rounded-xl p-4 mb-6" style={{ background: 'var(--bg-overlay-l1)' }}>
            <div className="flex flex-wrap items-baseline justify-between gap-1 mb-2">
              <div className="text-sm font-medium">当前观点</div>
              <div className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                每股仅显示最新一条进行中观点;历史逐条记录见下方观点日志
              </div>
            </div>
            {currentStanceError ? (
              <div className="text-xs py-2" style={{ color: 'var(--text-secondary)' }}>当前观点加载失败</div>
            ) : currentStance === null ? (
              <div className="text-xs py-2" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>
            ) : currentStance.length === 0 ? (
              <div className="text-xs py-2" data-testid="current-stance-empty" style={{ color: 'var(--text-tertiary)' }}>暂无进行中观点</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    <th className="px-2 py-2 font-normal">建立日期</th>
                    <th className="px-2 py-2 font-normal">标的</th>
                    <th className="px-2 py-2 font-normal">方向</th>
                    <th className="px-2 py-2 font-normal text-right">入场价</th>
                    <th className="px-2 py-2 font-normal">判定窗口</th>
                    <th className="px-2 py-2 font-normal">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {currentStance.map(r => (
                    <tr
                      key={r.prediction_id}
                      data-testid={`current-stance-row-${r.prediction_id}`}
                      className="border-t cursor-pointer hover:opacity-80"
                      style={{ borderColor: 'var(--border-neutral-l1)' }}
                      onClick={() => navigate(`/track-record/predictions/${r.prediction_id}`)}
                    >
                      <td className="px-2 py-3" style={{ color: 'var(--text-secondary)' }}>{r.created_at.slice(0, 10)}</td>
                      <td className="px-2 py-3">
                        <div className="font-medium" style={{ color: 'var(--text-default)' }}>{r.symbol_name ?? r.symbol}</div>
                        <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{r.symbol}</div>
                      </td>
                      <td className="px-2 py-3" style={{ color: 'var(--text-secondary)' }}>{DIRECTION_LABEL[r.direction]}</td>
                      <td className="px-2 py-3 text-right">{fmt(r.entry_price)}</td>
                      <td className="px-2 py-3" style={{ color: 'var(--text-secondary)' }}>T+{r.horizon_days}</td>
                      <td className="px-2 py-3">
                        <span className={STATUS_CLS[r.status]}>{STATUS_LABEL[r.status]}</span>
                        <span className="ml-1 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>未结算</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: 全部 PASS（含既有用例；既有用例未 mock `/current` 会走 404 → 显式失败文案，不撞既有断言）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test/trackRecord/trackRecordPage.test.tsx
git commit -m "feat(track-record): 战绩页当前观点区——每股最新一条 open 立场视图 (add-current-stance-view)"
```

---

### Task 4: E2E spec（track-record 专属套件）

**Files:**
- Create: `tests/e2e/playwright/tests/track-record-stance-view.spec.ts`

**Interfaces:**
- Consumes: `POST /api/test/seed`（`track_record.predictions` 造数通道）；Task 3 的 testid；`playwright.track-record.config.ts`（端口 8004/5177、独立库 `data/test-e2e-track-record.db`、workers=1 串行、testMatch `track-record-*.spec.ts` 按文件名字母序执行）
- Produces: 门禁 spec；命名 `track-record-stance-view` 保证字母序排在 `track-record-prediction-duplicates` 之后（其种子不污染本 spec 前提；本 spec 种子之后无依赖空库的用例）

- [ ] **Step 1: 写 spec（selector 来自 Task 3 真实 testid，非盲写）**

```ts
import { expect, test } from '@playwright/test'

/**
 * add-current-stance-view Task 4:当前观点区 E2E 门禁。
 * 红线:不 mock 业务接口——数据经 TESTING=1 的 /api/test/seed 的 track_record
 * .predictions 通道写入独立测试库(与生产同一 insert_prediction 路径)。
 *
 * 套件序:字母序排在本套件末位(前位 prediction-duplicates 的种子不影响本
 * spec 前提——断言只认本 spec 造的 symbol;本 spec 种子之后无依赖空库用例)。
 * 本地重跑前删 data/test-e2e-track-record.db*(config 头注释同款纪律)。
 *
 * 空态场景不在本套件覆盖:串行共享持久库且无清库端点,无法可靠构造
 * 「无任何 open」前提;空态由 vitest 单测层覆盖(trackRecordPage.test.tsx)。
 *
 * selector 来源:TrackRecordPage.tsx 真实 testid——current-stance /
 * current-stance-row-* / prediction-log / prediction-tab-*。
 */
test.describe('战绩页:当前观点区(add-current-stance-view)', () => {
  test('每股仅显示最新一条 open;台账不受影响;行点击进详情', async ({ page, request }) => {
    const seedResp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            { symbol: '601058.SH', symbol_name: '渝农商行', direction: 'neutral', created_at: '2026-10-05T10:00:00' },
            { symbol: '601058.SH', symbol_name: '渝农商行', direction: 'neutral', created_at: '2026-10-06T10:00:00' },
            { symbol: '300033.SZ', symbol_name: '同花顺', direction: 'long', created_at: '2026-10-06T11:00:00' },
          ],
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto('/track-record')
    const stance = page.getByTestId('current-stance')
    await expect(stance).toBeVisible()
    // 口径说明常驻(立场视图与台账的语义边界)
    await expect(stance).toContainText('每股仅显示最新一条进行中观点')
    // 每股一行:601058 两条 open 收敛为最新一条(10-06),300033 一行
    const row601058 = stance.getByTestId(/^current-stance-row-/).filter({ hasText: '渝农商行' })
    await expect(stance.getByTestId(/^current-stance-row-/)).toHaveCount(2)
    await expect(row601058).toHaveCount(1)
    await expect(row601058).toContainText('2026-10-06')
    await expect(row601058).toContainText('T+20')

    // 台账不受立场视图影响:缺省「当前持有」tab 下 601058 仍两条 open
    const log = page.getByTestId('prediction-log')
    await expect(log.getByRole('row', { name: /渝农商行/ })).toHaveCount(2)

    // 行点击进入观点详情页(与观点日志行同一详情路由)
    await row601058.click()
    await expect(page).toHaveURL(/\/track-record\/predictions\//)
  })
})
```

- [ ] **Step 2: scan.sh 快扫（零 token 抓 P0）**

Run: `bash .trae/skills/e2e-reviewer/scripts/scan.sh tests/e2e/playwright/tests/track-record-stance-view.spec.ts`（worktree 内相对路径；scan.sh 由 e2e-reviewer 技能携带）
Expected: P0 = 0（无恒真断言、无缺 await、无 route.fulfill 业务接口 mock）

- [ ] **Step 3: 跑专属套件验证**

Run: `cd tests/e2e/playwright && rm -f ../../../data/test-e2e-track-record.db* && npx playwright test --config=playwright.track-record.config.ts`
Expected: 全绿（整个 track-record 套件，含本 spec 与既有 specs）

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/playwright/tests/track-record-stance-view.spec.ts
git commit -m "test(track-record): 当前观点区 E2E 门禁 spec (add-current-stance-view)"
```

---

### Task 5: 全量验证（verification-before-completion）

**Files:** 无新增（只跑门禁）

- [ ] **Step 1: 后端全量**

Run: `uv run ruff check && uv run mypy && uv run pytest`
Expected: 三者全绿（pytest 若因 Langfuse 未起卡住，先 `docker compose up -d langfuse-web`——全量套件依赖见 memory）

- [ ] **Step 2: 前端全量**

Run: `cd frontend && npm test`
Expected: 全绿

- [ ] **Step 3: E2E stub 门禁（track-record 套件 + 默认套件冒烟）**

Run: `cd tests/e2e/playwright && npx playwright test --config=playwright.track-record.config.ts && npx playwright test tests/smoke.spec.ts`
Expected: 全绿

- [ ] **Step 4: 对照 delta spec 逐条核对**

对照 `openspec/changes/add-current-stance-view/specs/track-record/spec.md` 的每个 Scenario，逐条指出对应测试/实现证据，记录进 verification 结论。
