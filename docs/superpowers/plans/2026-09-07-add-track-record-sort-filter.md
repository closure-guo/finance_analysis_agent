# Add Track-Record Sort & Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给历史战绩页「观点日志」增加服务端列排序、关键字/时间段过滤、建立日期列与分页。

**Architecture:** 后端 `list_predictions` 增加排序白名单 + 过滤子句，新增 `count_predictions` 提供过滤后总数；API `/predictions` 透传新查询参数；前端 `TrackRecordPage` 持有 `{sortBy,sortDir,keyword,dateFrom,dateTo,page}` 查询状态，任一变化重新拉取，表头可排序 + 过滤控件 + 分页。

**Tech Stack:** Python 3.12 / FastAPI / SQLite; React 18 / TS / Vitest + Testing Library.

## Global Constraints

- 红线：`openspec/specs/track-record/` 是行为唯一真相；改动只经 delta 合并，禁止手改主规范库。
- 红线：观点日志默认视图必须含 loss（不可隐藏），不做「只看好单」预设筛选。
- 后端 `list_predictions` 的 `ORDER BY` 只允许来自固定白名单的列名（防注入），绝不拼接用户输入。
- 过滤/排序在服务端执行；新增查询参数全部可选，缺省行为与现实现逐字节一致（`created_at DESC`、全状态、无过滤），无 BREAKING。
- `total` 必须反映过滤后的子集。
- 关键字大小写不敏感；方向/状态中文标签映射集中在一处（与前端 `DIRECTION_LABEL`/`STATUS_LABEL` 一致）。
- 时间段按 `created_at` 的日期部分过滤，含两端，最细到日。
- 注释用中文；变量命名 camelCase；commit 信息清晰。
- **E2E 门禁缺口**：`e2e/` Playwright 项目（§5.6 P1–P4）未落地，按 §4.5 本周期门禁不生效；交互覆盖走前端 RTL 单测 + 后端集成测试 + 人工验证，并在 tasks.md / 验证报告中如实标注，不虚构「E2E 全绿」。

---

### Task 1: 后端 model — 排序白名单 + 过滤子句 + count_predictions

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`
- Test: `tests/outcome/test_track_record_model.py`

**Interfaces:**
- Produces:
  - `list_predictions(ticker, status, source_type, limit, offset, db_path, sort_by=None, sort_dir=None, keyword=None, date_from=None, date_to=None) -> list[dict]`（新增 4 个可选参数）
  - `count_predictions(ticker=None, status=None, source_type=None, keyword=None, date_from=None, date_to=None, db_path=None) -> int`

- [ ] **Step 1: Write the failing tests**

在 `tests/outcome/test_track_record_model.py` 末尾追加：

```python
def test_list_sort_by_return_desc(db):
    _insert(db, symbol="a.SH", entry_price=100.0)
    _insert(db, symbol="b.SH", entry_price=100.0)
    # 需要不同 raw_return：直接经 status 更新写入
    from finance_agent.outcome.track_record.model import update_prediction_status

    rows = list_predictions(db_path=db)
    update_prediction_status(
        rows[0]["prediction_id"],
        {"status": "resolved_win", "raw_return": 0.05, "excess_return": 0.02},
        db_path=db,
    )
    update_prediction_status(
        rows[1]["prediction_id"],
        {"status": "resolved_win", "raw_return": 0.2, "excess_return": 0.1},
        db_path=db,
    )
    desc = list_predictions(sort_by="raw_return", sort_dir="desc", db_path=db)
    assert [r["raw_return"] for r in desc] == [0.2, 0.05]
    asc = list_predictions(sort_by="raw_return", sort_dir="asc", db_path=db)
    assert [r["raw_return"] for r in asc] == [0.05, 0.2]


def test_list_invalid_sort_falls_back_default(db):
    _insert(db, symbol="a.SH", created_at="2026-09-01T10:00:00")
    _insert(db, symbol="b.SH", created_at="2026-09-02T10:00:00")
    rows = list_predictions(sort_by="unknown_column", db_path=db)
    # 默认 created_at DESC → 后插入的 09-02 在前
    assert rows[0]["symbol"] == "b.SH"


def test_list_keyword_matches_symbol_name_and_labels(db):
    _insert(db, symbol="600519.SH", symbol_name="贵州茅台", direction="long")
    _insert(db, symbol="300308.SZ", symbol_name="中际旭创", direction="short")
    _insert(db, symbol="000001.SZ", symbol_name="平安银行", direction="long")
    assert len(list_predictions(keyword="茅台", db_path=db)) == 1
    assert len(list_predictions(keyword="看空", db_path=db)) == 1  # 方向标签
    assert len(list_predictions(keyword="平安", db_path=db)) == 1
    # 状态标签「命中」→ resolved_win
    from finance_agent.outcome.track_record.model import update_prediction_status

    rows = list_predictions(db_path=db)
    update_prediction_status(
        rows[0]["prediction_id"], {"status": "resolved_win"}, db_path=db
    )
    assert len(list_predictions(keyword="命中", db_path=db)) == 1


def test_list_date_range_inclusive(db):
    _insert(db, symbol="a.SH", created_at="2026-09-01T08:00:00")
    _insert(db, symbol="b.SH", created_at="2026-09-15T08:00:00")
    _insert(db, symbol="c.SH", created_at="2026-10-01T08:00:00")
    rows = list_predictions(date_from="2026-09-01", date_to="2026-09-30", db_path=db)
    assert sorted(r["symbol"] for r in rows) == ["a.SH", "b.SH"]  # 含两端


def test_count_predictions_reflects_filters(db):
    _insert(db, symbol="a.SH", symbol_name="茅台", created_at="2026-09-01T08:00:00")
    _insert(db, symbol="b.SH", symbol_name="茅台", created_at="2026-09-15T08:00:00")
    _insert(db, symbol="c.SH", symbol_name="平安", created_at="2026-10-01T08:00:00")
    assert count_predictions(keyword="茅台", db_path=db) == 2
    assert (
        count_predictions(keyword="茅台", date_from="2026-09-01", date_to="2026-09-30", db_path=db)
        == 2
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/outcome/test_track_record_model.py -k "sort or keyword or date_range or count_predictions" -v`
Expected: FAIL（`list_predictions` 无 `sort_by` 参数 / `count_predictions` 未定义）

- [ ] **Step 3: Write minimal implementation**

在 `model.py` 的 `list_predictions` 之前插入白名单与映射常量，并新增 `_prediction_filters` 与 `count_predictions`，重写 `list_predictions`：

```python
# 排序白名单：仅允许这些列参与 ORDER BY（防注入）
_SORT_WHITELIST = {
    "created_at": "created_at",
    "symbol": "symbol",
    "direction": "direction",
    "status": "status",
    "entry_price": "entry_price",
    "exit_price": "exit_price",
    "raw_return": "raw_return",
    "excess_return": "excess_return",
}

# 关键字 → 方向/状态映射（与前端 DIRECTION_LABEL/STATUS_LABEL 一致）
_DIRECTION_LABELS = {"看多": "long", "看空": "short", "中性": "neutral"}
_STATUS_LABELS = {
    "进行中": "open",
    "命中": "resolved_win",
    "未中": "resolved_loss",
    "中性": "resolved_neutral",
    "不可判定": "unresolvable",
}


def _prediction_filters(
    ticker: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[list[str], list[Any]]:
    """构造 predictions 查询的 WHERE 子句与参数（list/count 共用）。"""
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
    if keyword:
        kw = f"%{keyword}%"
        label_parts = ["(symbol LIKE ? OR symbol_name LIKE ?)"]
        params += [kw, kw]
        if keyword in _DIRECTION_LABELS:
            label_parts.append("direction = ?")
            params.append(_DIRECTION_LABELS[keyword])
        if keyword in _STATUS_LABELS:
            label_parts.append("status = ?")
            params.append(_STATUS_LABELS[keyword])
        clauses.append("(" + " OR ".join(label_parts) + ")")
    if date_from or date_to:
        date_parts: list[str] = []
        if date_from:
            date_parts.append("date(created_at) >= ?")
            params.append(date_from)
        if date_to:
            date_parts.append("date(created_at) <= ?")
            params.append(date_to)
        clauses.append("(" + " AND ".join(date_parts) + ")")
    return clauses, params


def list_predictions(
    ticker: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db_path: str | Path | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    conn = _connect(db_path)
    try:
        clauses, params = _prediction_filters(
            ticker, status, source_type, keyword, date_from, date_to
        )
        sql = "SELECT * FROM predictions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        col = _SORT_WHITELIST.get(sort_by or "created_at", "created_at")
        direction = "ASC" if (sort_dir or "desc").lower() == "asc" else "DESC"
        sql += f" ORDER BY {col} {direction} LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_predictions(
    ticker: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """返回过滤后观点总数（供 API 分页 total 使用）。"""
    conn = _connect(db_path)
    try:
        clauses, params = _prediction_filters(
            ticker, status, source_type, keyword, date_from, date_to
        )
        sql = "SELECT COUNT(*) FROM predictions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/outcome/test_track_record_model.py -q`
Expected: PASS（含旧用例，确认无回归）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py tests/outcome/test_track_record_model.py
git commit -m "feat(track-record): list_predictions 排序白名单 + 关键字/时间段过滤 + count_predictions"
```

---

### Task 2: 后端 API — 透传排序/过滤参数，total 反映子集

**Files:**
- Modify: `src/finance_agent/api.py`（`track_record_predictions` 端点 + import）
- Test: `tests/test_api_track_record.py`

**Interfaces:**
- Consumes: Task 1 的 `list_predictions(..., sort_by, sort_dir, keyword, date_from, date_to)` 与 `count_predictions(...)`。
- Produces: `GET /api/v1/track-record/predictions` 支持 `sort_by/sort_dir/keyword/date_from/date_to` 查询参数。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_api_track_record.py` 顶部 import 增加 `count_predictions`（本任务用不到，仅确保不破坏；实际测试走 HTTP）。在文件末尾追加：

```python
# ── add-track-record-sort-filter：排序/关键字/时间段/过滤后 total ──


def test_predictions_sort_api(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, symbol="a.SH", entry_price=100.0, created_at="2026-09-01T10:00:00")
    _insert(db, symbol="b.SH", entry_price=100.0, created_at="2026-09-02T10:00:00")
    c = TestClient(app)
    items = c.get(
        "/api/v1/track-record/predictions", params={"sort_by": "created_at", "sort_dir": "asc"}
    ).json()["predictions"]
    assert [r["symbol"] for r in items] == ["a.SH", "b.SH"]
    # 非法 sort_by 回退默认 created_at DESC
    items2 = c.get("/api/v1/track-record/predictions", params={"sort_by": "bogus"}).json()[
        "predictions"
    ]
    assert items2[0]["symbol"] == "b.SH"


def test_predictions_keyword_api(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, symbol="600519.SH", symbol_name="贵州茅台", direction="long")
    _insert(db, symbol="300308.SZ", symbol_name="中际旭创", direction="short")
    c = TestClient(app)
    assert len(c.get("/api/v1/track-record/predictions", params={"keyword": "茅台"}).json()["predictions"]) == 1
    assert len(c.get("/api/v1/track-record/predictions", params={"keyword": "看空"}).json()["predictions"]) == 1


def test_predictions_date_range_api(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, symbol="a.SH", created_at="2026-09-01T10:00:00")
    _insert(db, symbol="b.SH", created_at="2026-09-30T10:00:00")
    _insert(db, symbol="c.SH", created_at="2026-10-02T10:00:00")
    data = TestClient(app).get(
        "/api/v1/track-record/predictions",
        params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    ).json()
    assert sorted(r["symbol"] for r in data["predictions"]) == ["a.SH", "b.SH"]
    assert data["total"] == 2  # total 反映过滤后子集


def test_predictions_filtered_total(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    for i in range(6):
        _insert(db, symbol=f"{i}.SH", symbol_name="茅台" if i < 2 else "平安", created_at=f"2026-09-0{i+1}T10:00:00")
    data = TestClient(app).get(
        "/api/v1/track-record/predictions", params={"keyword": "茅台", "page_size": 1}
    ).json()
    assert len(data["predictions"]) == 1 and data["total"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_track_record.py -k "sort_api or keyword_api or date_range_api or filtered_total" -v`
Expected: FAIL（端点不识别新参数，total 未过滤）

- [ ] **Step 3: Write minimal implementation**

在 `api.py` 中把 `from finance_agent.outcome.track_record.model import (...)` 加入 `count_predictions`（找到现有 import 行），并替换 `track_record_predictions` 端点：

```python
@app.get("/api/v1/track-record/predictions")
async def track_record_predictions(
    status: str | None = None,
    symbol: str | None = None,
    source: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """add-track-record:观点日志列表(默认全部状态,含 loss)。
    add-track-record-sort-filter:可选 sort_by/sort_dir/keyword/date_from/date_to,
    缺省回退 created_at DESC;total 反映过滤后子集。分页上限 50。"""
    page = max(1, page)
    limit = max(1, min(page_size, 50))
    offset = (page - 1) * limit
    items = await asyncio.to_thread(
        list_predictions,
        ticker=symbol,
        status=status,
        source_type=source,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    total = await asyncio.to_thread(
        count_predictions,
        ticker=symbol,
        status=status,
        source_type=source,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "predictions": items,
        "page": page,
        "page_size": limit,
        "total": total,
        "as_of": _track_as_of(),
        "disclaimer": _DISCLAIMER,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_track_record.py -q`
Expected: PASS（含旧用例）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_track_record.py
git commit -m "feat(track-record): predictions 端点透传排序/关键字/时间段, total 反映过滤子集"
```

---

### Task 3: 前端 TrackRecordPage — 日期列 + 排序 + 过滤 + 分页

**Files:**
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Consumes: `PredictionsResponse`（`frontend/src/types.ts`，已含 `page/page_size/total`，无需改动类型）。
- Produces: 页面新增「建立日期」列、可排序表头、关键字/起止日期过滤控件、分页。

- [ ] **Step 1: Write the failing tests**

在 `frontend/src/test/trackRecord/trackRecordPage.test.tsx` 末尾追加一个 describe（复用文件顶部已有的 `mockFetch`/`PREDICTIONS`/`renderPage` 辅助与 `OVERVIEW`）：

```tsx
describe('观点日志排序/过滤/日期列/分页（add-track-record-sort-filter）', () => {
  beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('渲染建立日期列（created_at 日期部分）', async () => {
    mockFetch({ overview: OVERVIEW, predictions: PREDICTIONS })
    renderPage()
    await screen.findByText('贵州茅台')
    expect(screen.getByText('2026-09-01')).toBeInTheDocument()
    expect(screen.getByText('2026-09-02')).toBeInTheDocument()
  })

  it('点击「区间收益」表头请求 sort_by=raw_return 并显示排序指示', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      calls.push(url)
      if (url.includes('/predictions')) {
        return Promise.resolve(new Response(JSON.stringify({
          predictions: PREDICTIONS, page: 1, page_size: 50, total: 2,
          as_of: 'x', disclaimer: 'x',
        }), { status: 200 }))
      }
      if (url.includes('/overview')) {
        return Promise.resolve(new Response(JSON.stringify(OVERVIEW), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify({ points: [], dimensions: [] }), { status: 200 }))
    }))
    renderPage()
    await screen.findByText('贵州茅台')
    fireEvent.click(screen.getByTestId('sort-raw_return'))
    await waitFor(() => expect(calls.some(u => u.includes('sort_by=raw_return'))).toBe(true))
    // 再次点击切换为 desc
    fireEvent.click(screen.getByTestId('sort-raw_return'))
    await waitFor(() => expect(calls.some(u => u.includes('sort_by=raw_return') && u.includes('sort_dir=desc'))).toBe(true))
  })

  it('关键字 + 查询按钮请求 keyword 参数', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      calls.push(url)
      if (url.includes('/predictions')) {
        return Promise.resolve(new Response(JSON.stringify({
          predictions: [PREDICTIONS[0]], page: 1, page_size: 50, total: 1, as_of: 'x', disclaimer: 'x',
        }), { status: 200 }))
      }
      if (url.includes('/overview')) {
        return Promise.resolve(new Response(JSON.stringify(OVERVIEW), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify({ points: [], dimensions: [] }), { status: 200 }))
    }))
    renderPage()
    await screen.findByText('贵州茅台')
    fireEvent.change(screen.getByTestId('track-record-keyword'), { target: { value: '茅台' } })
    fireEvent.click(screen.getByTestId('track-record-apply'))
    await waitFor(() => expect(calls.some(u => u.includes('keyword=%E8%8C%85%E5%8F%B0'))).toBe(true))
  })

  it('起止日期 + 查询请求 date_from/date_to', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      calls.push(url)
      if (url.includes('/predictions')) {
        return Promise.resolve(new Response(JSON.stringify({ predictions: [], page: 1, page_size: 50, total: 0, as_of: 'x', disclaimer: 'x' }), { status: 200 }))
      }
      if (url.includes('/overview')) {
        return Promise.resolve(new Response(JSON.stringify(OVERVIEW), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify({ points: [], dimensions: [] }), { status: 200 }))
    }))
    renderPage()
    await screen.findByText('贵州茅台')
    fireEvent.change(screen.getByTestId('track-record-date-from'), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByTestId('track-record-date-to'), { target: { value: '2026-09-30' } })
    fireEvent.click(screen.getByTestId('track-record-apply'))
    await waitFor(() => expect(calls.some(u => u.includes('date_from=2026-09-01') && u.includes('date_to=2026-09-30'))).toBe(true))
  })

  it('total 超过单页时渲染分页，下一页请求 page=2', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      calls.push(url)
      if (url.includes('/predictions')) {
        return Promise.resolve(new Response(JSON.stringify({ predictions: PREDICTIONS, page: 1, page_size: 50, total: 120, as_of: 'x', disclaimer: 'x' }), { status: 200 }))
      }
      if (url.includes('/overview')) {
        return Promise.resolve(new Response(JSON.stringify(OVERVIEW), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify({ points: [], dimensions: [] }), { status: 200 }))
    }))
    renderPage()
    await screen.findByText('贵州茅台')
    const next = screen.getByTestId('track-record-next')
    expect(next).toBeInTheDocument()
    fireEvent.click(next)
    await waitFor(() => expect(calls.some(u => u.includes('page=2'))).toBe(true))
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/test/trackRecord/trackRecordPage.test.tsx`
Expected: FAIL（`sort-raw_return`/`track-record-keyword`/`track-record-apply`/`track-record-next` 等 testid 不存在，或日期列缺失）

- [ ] **Step 3: Write minimal implementation**

重构 `TrackRecordPage.tsx`：

1. 顶部新增常量与 state：

```tsx
const COLUMNS: Array<{ key: string; label: string; numeric?: boolean }> = [
  { key: 'created_at', label: '建立日期' },
  { key: 'symbol', label: '标的' },
  { key: 'direction', label: '方向' },
  { key: 'status', label: '状态' },
  { key: 'entry_price', label: '入场价', numeric: true },
  { key: 'exit_price', label: '结算价', numeric: true },
  { key: 'raw_return', label: '区间收益', numeric: true },
  { key: 'excess_return', label: '基准超额', numeric: true },
]
const PAGE_SIZE = 50
```

在组件内 `useState` 区新增：

```tsx
const [sortBy, setSortBy] = useState<string>('created_at')
const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
const [keywordInput, setKeywordInput] = useState('')
const [dateFrom, setDateFrom] = useState('')
const [dateTo, setDateTo] = useState('')
const [applied, setApplied] = useState({ keyword: '', dateFrom: '', dateTo: '' })
const [page, setPage] = useState(1)
const [total, setTotal] = useState(0)
```

2. predictions URL 与独立拉取 effect（把 predictions 从 `load` 中拆出）：

```tsx
const predictionsUrl = useCallback(() => {
  const p = new URLSearchParams()
  if (sortBy !== 'created_at') p.set('sort_by', sortBy)
  if (sortDir !== 'desc') p.set('sort_dir', sortDir)
  if (applied.keyword) p.set('keyword', applied.keyword)
  if (applied.dateFrom) p.set('date_from', applied.dateFrom)
  if (applied.dateTo) p.set('date_to', applied.dateTo)
  if (page > 1) p.set('page', String(page))
  p.set('page_size', String(PAGE_SIZE))
  const q = p.toString()
  return `/api/v1/track-record/predictions${q ? `?${q}` : ''}`
}, [sortBy, sortDir, applied, page])

useEffect(() => {
  let cancelled = false
  ;(async () => {
    try {
      const resp = await fetch(predictionsUrl())
      if (!resp.ok) throw new Error(String(resp.status))
      const data = (await resp.json()) as PredictionsResponse
      if (cancelled) return
      setRecords(data.predictions)
      setTotal(data.total)
    } catch {
      if (!cancelled) setError(true)
    }
  })()
  return () => { cancelled = true }
}, [predictionsUrl])
```

并把 `load` 改为只拉 overview/equity-curve/segments（去掉 predictions fetch 与 `setRecords`）：

```tsx
const load = useCallback(async (ver: number | null) => {
  setError(false)
  try {
    const [ovResp, cvResp, sgResp] = await Promise.all([
      fetch(`/api/v1/track-record/overview${ver !== null ? `?version=${ver}` : ''}`),
      fetch('/api/v1/track-record/equity-curve'),
      fetch('/api/v1/track-record/segments'),
    ])
    if (!ovResp.ok || !cvResp.ok || !sgResp.ok) throw new Error(String(ovResp.status))
    setOverview((await ovResp.json()) as TrackRecordOverview)
    const cv = (await cvResp.json()) as { points: EquityCurvePoint[] }
    setCurve(cv.points)
    const sg = (await sgResp.json()) as { dimensions: SegmentDimension[] }
    setSegments(sg.dimensions)
  } catch {
    setError(true)
    toast.error('战绩数据加载失败')
  }
}, [])
```

3. 处理器：

```tsx
const onSort = (col: string) => {
  if (sortBy === col) {
    setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
  } else {
    setSortBy(col)
    setSortDir(col === 'created_at' ? 'desc' : 'asc')
  }
  setPage(1)
}
const applyFilters = () => {
  setApplied({ keyword: keywordInput.trim(), dateFrom, dateTo })
  setPage(1)
}
const resetFilters = () => {
  setKeywordInput(''); setDateFrom(''); setDateTo('')
  setApplied({ keyword: '', dateFrom: '', dateTo: '' })
  setSortBy('created_at'); setSortDir('desc'); setPage(1)
}
const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
const arrow = (col: string) => (sortBy === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '')
```

4. JSX：在观点日志表格上方插入过滤工具栏，替换 thead/tbody 以支持排序与日期列、加分页：

```tsx
{/* 过滤工具栏（add-track-record-sort-filter） */}
<div className="flex flex-wrap items-center gap-2 mb-3" data-testid="track-record-filters">
  <input
    data-testid="track-record-keyword"
    value={keywordInput}
    onChange={e => setKeywordInput(e.target.value)}
    placeholder="输入代码/名称/方向/状态"
    className="text-xs rounded-lg px-2 py-1 border"
    style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', borderColor: 'var(--border-neutral-l1)' }}
  />
  <input type="date" data-testid="track-record-date-from" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="text-xs rounded-lg px-2 py-1 border" style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', borderColor: 'var(--border-neutral-l1)' }} />
  <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>至</span>
  <input type="date" data-testid="track-record-date-to" value={dateTo} onChange={e => setDateTo(e.target.value)} className="text-xs rounded-lg px-2 py-1 border" style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', borderColor: 'var(--border-neutral-l1)' }} />
  <Button size="sm" onClick={applyFilters} data-testid="track-record-apply">查询</Button>
  <Button size="sm" variant="ghost" onClick={resetFilters} data-testid="track-record-reset">重置</Button>
</div>
```

替换表格 thead/tbody（在原来的 `<table>` 内）：

```tsx
<thead>
  <tr className="text-left text-xs" style={{ color: 'var(--text-tertiary)' }}>
    {COLUMNS.map(c => (
      <th key={c.key} className={`px-4 py-2 font-normal ${c.numeric ? 'text-right' : ''}`}>
        <button
          type="button"
          data-testid={`sort-${c.key}`}
          onClick={() => onSort(c.key)}
          className="inline-flex items-center gap-0.5 hover:opacity-80"
          style={{ color: 'var(--text-tertiary)' }}
        >
          {c.label}{arrow(c.key)}
        </button>
      </th>
    ))}
  </tr>
</thead>
<tbody>
  {rows.map(r => (
    <tr key={r.prediction_id} className="border-t cursor-pointer hover:opacity-80"
        style={{ borderColor: 'var(--border-neutral-l1)' }}
        onClick={() => navigate(`/track-record/predictions/${r.prediction_id}`)}
        data-testid={`prediction-row-${r.prediction_id}`}>
      <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{r.created_at.slice(0, 10)}</td>
      <td className="px-4 py-3">
        <div className="font-medium" style={{ color: 'var(--text-default)' }}>{r.symbol_name ?? r.symbol}</div>
        <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{r.symbol}</div>
      </td>
      <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{DIRECTION_LABEL[r.direction]}</td>
      <td className="px-4 py-3">
        <span className={STATUS_CLS[r.status]}>{STATUS_LABEL[r.status]}</span>
        {r.status === 'open' && <span className="ml-1 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>未结算</span>}
      </td>
      <td className="px-4 py-3 text-right">{fmt(r.entry_price)}</td>
      <td className="px-4 py-3 text-right">{fmt(r.exit_price)}</td>
      <td className="px-4 py-3 text-right"><Delta value={r.raw_return} /></td>
      <td className="px-4 py-3 text-right"><Delta value={r.excess_return} /></td>
    </tr>
  ))}
</tbody>
```

在表格容器后追加分页（`rows.length > 0` 时显示）：

```tsx
{rows.length > 0 && (
  <div className="flex items-center justify-end gap-3 mt-3 text-xs" data-testid="track-record-pagination">
    <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)} data-testid="track-record-prev">上一页</Button>
    <span style={{ color: 'var(--text-tertiary)' }}>第 {page} / {pageCount} 页 · 共 {total} 条</span>
    <Button size="sm" variant="ghost" disabled={page >= pageCount} onClick={() => setPage(p => p + 1)} data-testid="track-record-next">下一页</Button>
  </div>
)}
```

需要确保 import 增加 `PredictionsResponse` 类型（`from '../../types'` 中已含，确认加入）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/test/trackRecord/trackRecordPage.test.tsx`
Expected: PASS（新增 + 既有用例）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test/trackRecord/trackRecordPage.test.tsx
git commit -m "feat(track-record): 观点日志排序/关键字与时间段过滤/日期列/分页"
```

---

### Task 4: 验证 + 人工验证报告 + sync + archive

**Files:**
- Create: `tests/validation/2026-09-07-add-track-record-sort-filter-validation.md`
- Modify: `openspec/changes/add-track-record-sort-filter/tasks.md`（勾选 1.x/2.x/4.x，并对 E2E 门禁如实标注缺口）

- [ ] **Step 1: 全量验证命令并读取输出**

```bash
uv run pytest -q
uv run ruff check src tests
cd frontend && npx tsc -b && npm test
```

Expected: 全绿；若有失败，先修复再继续（不得带病声称完成）。

- [ ] **Step 2: 手动浏览器抽查交互**

用浏览器自动化打开 `http://127.0.0.1:5173/track-record`，抽查：日期列展示、点击表头排序、关键字/日期过滤、分页翻页。

- [ ] **Step 3: 落人工验证报告**

按 §5 模板写 `tests/validation/2026-09-07-add-track-record-sort-filter-validation.md`，含表格（场景/预期/实际/通过）+ 异常记录 + 结论；异常记录中注明 E2E 门禁缺口（e2e/ 基建未落地，覆盖由单测+集成+人工验证承担）。

- [ ] **Step 4: 更新 tasks.md**

勾选已完成项；把「3.1 E2E spec 已覆盖」「3.2 npx playwright test 全绿」标记为「不适用（e2e/ 基建未落地，见验证报告异常记录）」。

- [ ] **Step 5: 校验 delta 并 commit**

```bash
openspec validate add-track-record-sort-filter --strict
git add tests/validation/2026-09-07-add-track-record-sort-filter-validation.md openspec/changes/add-track-record-sort-filter/tasks.md
git commit -m "test(track-record): 排序/过滤人工验证报告 + tasks 勾选"
```

- [ ] **Step 6: sync + archive**

按 §3 Step 6：`openspec sync`（delta 合并进 `openspec/specs/track-record/`）→ archive 前置条件满足后移入 `openspec/changes/archive/2026-09-07-add-track-record-sort-filter/` → `openspec validate --strict` 复核。
