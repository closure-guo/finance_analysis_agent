# update-track-record-display-clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 战绩页展示治理七件套：窗口列、open 行浮动收益（接 daily_marks）、同日重复折叠、切片空态折叠、「已结算/带内中性」术语、口径披露 legacy_open、详情页中文化。

**Architecture:** 后端三处小改（overview 差值法加 legacy_open、list_predictions 注入 latest_mark、keyword 标签映射 + seed marks 通道），前端 TrackRecordPage 列/折叠/术语 + 新建 predictionDisplay.ts 单一真源 + 详情页接入。OpenSpec delta 见 `openspec/changes/update-track-record-display-clarity/`。

**Tech Stack:** FastAPI + sqlite3（窗口函数 ROW_NUMBER）、React 18 + TS + vitest、Playwright（track-record 专属套件 8004/5177）。

## Global Constraints

- **堆叠分支**：本分支基于 `add-current-stance-view`（PR #260）。TrackRecordPage.tsx 的修改以 #260 版本为基线（含当前观点区）；禁触碰主检出。
- E2E 红线：禁止 mock 业务接口；造数走 `POST /api/test/seed`（predictions 通道 + 本 delta 新增的 marks 子键）
- SQL 列名固定字面量、值参数化；commit 格式 `feat(track-record)/test(...): ...`
- 术语变更（已判定→已结算、中性→带内中性）会打红存量文本断言——逐个更新为预期新值，**在 commit message 与报告中注明**，禁止改弱断言绕过
- ruff/mypy 零新增告警；mypy 基线 83 errors（与 main/基线持平即可）

---

### Task 1: overview 新增 legacy_open（差值法）

**Files:**
- Modify: `src/finance_agent/api.py`（track_record_overview 响应组装处，约 2335 行 `"legacy_settled"` 旁）
- Test: `tests/test_api_track_record.py`（末尾追加）

**Interfaces:**
- Produces: overview 响应新增 `legacy_open: int`（旧口径 open 计数）——前端披露行消费

- [ ] **Step 1: Write the failing test**

`tests/test_api_track_record.py` 末尾追加：

```python
def test_overview_legacy_open_counts_non_headline_open(monkeypatch, tmp_path):
    """legacy_open=不在头条口径内的 open 计数（与 legacy_settled 对称的差值法）。"""
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, symbol="600015.SH", created_at="2026-10-01T10:00:00")  # T+20 open（头条）
    _insert(db, symbol="600016.SH", horizon_days=252, created_at="2026-08-01T10:00:00")
    _insert(db, symbol="600017.SH", horizon_days=252, created_at="2026-08-02T10:00:00")
    resp = TestClient(app).get("/api/v1/track-record/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["legacy_open"] == 2
    assert data["legacy_settled"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_track_record.py::test_overview_legacy_open_counts_non_headline_open -v`
Expected: FAIL with `KeyError: 'legacy_open'`（或 assert KeyError）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/api.py` 的 `track_record_overview` 返回 dict 中，`"legacy_settled": legacy_all["settled"] - stats["settled"],` 一行之后加：

```python
        # update-track-record-display-clarity：旧口径 open 计数（差值法，与 legacy_settled 对称；
        # 披露行双计数治「无存量」与全部 tab 内旧口径行的观感矛盾）
        "legacy_open": max(0, legacy_all["open"] - stats["open"]),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_track_record.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_track_record.py
git commit -m "feat(track-record): overview 新增 legacy_open 旧口径进行中计数 (update-track-record-display-clarity)"
```

---

### Task 2: list_predictions 注入 latest_mark

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`（list_predictions 尾部 + 新增 `_latest_marks_for` helper，放 list_predictions 之前）
- Test: `tests/outcome/test_track_record_model.py`（末尾追加；import 区加 `insert_daily_mark`）

**Interfaces:**
- Consumes: daily_marks 表（prediction_id/mark_date/cum_return/cum_excess）
- Produces: `list_predictions` 行新增 `latest_mark: {mark_date, cum_return, cum_excess} | None`（open 行=最新盯市，非 open 行=None）——前端 Task 5 消费

- [ ] **Step 1: Write the failing test**

import 区（`from finance_agent.outcome.track_record.model import (...)`）加入 `insert_daily_mark`，文件末尾追加：

```python
# ── update-track-record-display-clarity:open 行最新盯市注入 ──

def test_list_predictions_injects_latest_mark_for_open(db):
    """open 行取 mark_date 最新的盯市；字段三元组完整。"""
    pid = _insert(db, symbol="600015.SH", created_at="2026-10-01T10:00:00")
    insert_daily_mark(pid, "2026-10-02", cum_return=0.01, cum_excess=0.005, db_path=db)
    insert_daily_mark(pid, "2026-10-03", cum_return=-0.012, cum_excess=-0.008, db_path=db)
    rows = list_predictions(status="open", db_path=db)
    row = next(r for r in rows if r["prediction_id"] == pid)
    assert row["latest_mark"] == {
        "mark_date": "2026-10-03",
        "cum_return": -0.012,
        "cum_excess": -0.008,
    }


def test_list_predictions_latest_mark_null_for_closed_and_unmarked(db):
    """非 open 行恒 None（即使有历史 marks）；无 marks 的 open 行也 None。"""
    unmarked = _insert(db, symbol="600016.SH", created_at="2026-10-01T11:00:00")
    closed = _insert(db, symbol="600017.SH", created_at="2026-10-01T12:00:00")
    insert_daily_mark(closed, "2026-10-02", cum_return=0.02, db_path=db)
    update_prediction_status(
        closed, {"status": "unresolvable", "resolution_rule": "stale_no_market"}, db_path=db
    )
    rows = {r["prediction_id"]: r for r in list_predictions(db_path=db)}
    assert rows[unmarked]["latest_mark"] is None
    assert rows[closed]["latest_mark"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_track_record_model.py -k latest_mark -v`
Expected: FAIL with `KeyError: 'latest_mark'`

- [ ] **Step 3: Write minimal implementation**

`model.py` 在 `list_predictions` 定义之前加 helper：

```python
def _latest_marks_for(
    prediction_ids: list[str], db_path: str | Path | None = None
) -> dict[str, dict[str, Any]]:
    """每观点最新一条盯市（update-track-record-display-clarity：open 行浮动收益展示用）。

    窗口函数取 mark_date 最大行；调用方保证 ids 非空切片。字段三元组与前端
    PredictionRecord.latest_mark 契约一致。
    """
    if not prediction_ids:
        return {}
    conn = _connect(db_path)
    try:
        placeholders = ",".join("?" for _ in prediction_ids)
        rows = conn.execute(
            f"""
            SELECT prediction_id, mark_date, cum_return, cum_excess FROM (
                SELECT prediction_id, mark_date, cum_return, cum_excess,
                       ROW_NUMBER() OVER (PARTITION BY prediction_id ORDER BY mark_date DESC) AS rn
                FROM daily_marks WHERE prediction_id IN ({placeholders})
            )
            WHERE rn = 1
            """,  # noqa: S608 — 占位符数量由 ids 长度生成，值全参数化
            prediction_ids,
        ).fetchall()
        return {
            r["prediction_id"]: {
                "mark_date": r["mark_date"],
                "cum_return": r["cum_return"],
                "cum_excess": r["cum_excess"],
            }
            for r in rows
        }
    finally:
        conn.close()
```

`list_predictions` 内 `return [dict(r) for r in rows]` 替换为：

```python
        result = [dict(r) for r in rows]
        # update-track-record-display-clarity:open 行注入最新盯市（浮动收益展示）；
        # 非 open 行恒 None——结算读数由 raw_return/excess_return 承载，语义不混
        open_ids = [d["prediction_id"] for d in result if d.get("status") == "open"]
        marks = _latest_marks_for(open_ids, db_path)
        for d in result:
            d["latest_mark"] = marks.get(d["prediction_id"]) if d.get("status") == "open" else None
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_track_record_model.py -v`
Expected: 全部 PASS（含既有 37+ 用例）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py tests/outcome/test_track_record_model.py
git commit -m "feat(track-record): list_predictions 注入 open 行最新盯市 latest_mark (update-track-record-display-clarity)"
```

---

### Task 3: keyword 标签更新 + seed marks 通道

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`（`_STATUS_LABELS`，约 862 行）
- Modify: `src/finance_agent/api.py`（`/api/test/seed` 的 predictions 循环内，约 762 行）
- Test: `tests/outcome/test_track_record_model.py`（末尾追加）

**Interfaces:**
- Produces: keyword=`带内中性` → status=resolved_neutral；seed 行 `marks` 子数组落 daily_marks——E2E Task 8 消费

- [ ] **Step 1: Write the failing test**

`tests/outcome/test_track_record_model.py` 末尾追加：

```python
def test_keyword_band_neutral_label_matches_status_only(db):
    """「带内中性」匹配 resolved_neutral；「中性」只剩方向 neutral 语义（消歧）。"""
    neutral_dir = _insert(db, symbol="600015.SH", direction="neutral", created_at="2026-10-01T10:00:00")
    band = _insert(db, symbol="600016.SH", direction="short", created_at="2026-10-01T11:00:00")
    update_prediction_status(
        band, {"status": "resolved_neutral", "resolution_rule": "superseded"}, db_path=db
    )
    band_rows = list_predictions(keyword="带内中性", db_path=db)
    assert [r["prediction_id"] for r in band_rows] == [band]
    dir_rows = list_predictions(keyword="中性", db_path=db)
    assert {r["prediction_id"] for r in dir_rows} == {neutral_dir}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outcome/test_track_record_model.py -k band_neutral -v`
Expected: FAIL——`keyword=带内中性` 命中 0 行（映射里没有该词），`== [band]` 断言失败

- [ ] **Step 3: Write minimal implementation**

`model.py` `_STATUS_LABELS`：

```python
_STATUS_LABELS = {
    "进行中": "open",
    "命中": "resolved_win",
    "未中": "resolved_loss",
    # update-track-record-display-clarity:「中性」→「带内中性」——与方向「中性」(观望)消歧，
    # keyword=中性 现在只匹配 direction=neutral（_DIRECTION_LABELS）
    "带内中性": "resolved_neutral",
    "回避": "avoidance",
    "不可判定": "unresolvable",
    "同日重复": "duplicate_of_day",
}
```

`api.py` seed 的 predictions 循环（`for row in seed_predictions:` 内，`if row.get("status")...` 块之后）加：

```python
                    # update-track-record-display-clarity:行内 marks 子数组——浮动收益
                    # E2E 造数（prediction_id 服务端生成，顶层数组无法引用，按行携带）
                    for mk in row.get("marks") or []:
                        _seed_insert_mark(
                            pid,
                            mk["mark_date"],
                            mk.get("mark_price"),
                            mk.get("cum_return"),
                            mk.get("cum_excess"),
                            mk.get("benchmark_price"),
                        )
```

同函数上方局部 import 块（`from finance_agent.outcome.track_record.model import insert_prediction as _seed_insert_prediction` 处）加：

```python
                from finance_agent.outcome.track_record.model import (
                    insert_daily_mark as _seed_insert_mark,
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/outcome/test_track_record_model.py tests/test_api_track_record.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py src/finance_agent/api.py tests/outcome/test_track_record_model.py
git commit -m "feat(track-record): keyword 带内中性消歧 + seed 通道 marks 子数组 (update-track-record-display-clarity)"
```

---

### Task 4: 前端窗口列 + 副标题 + 类型

**Files:**
- Modify: `frontend/src/types.ts`（PredictionRecord 接口，latest_mark 字段——Task 5 也用，此处一并加）
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（COLUMNS、thead 渲染、行单元格、副标题）
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Produces: testid `sort-created_at` 等不变；窗口列无排序按钮（表头纯文本）；副标题文案变更——Task 8 E2E 断言

- [ ] **Step 1: Write the failing test**

`trackRecordPage.test.tsx`：现有 fixture `PREDICTIONS[1]`（p2, open, horizon 252）已可用于断言；`CURRENT` fixture 同样有 horizon_days。describe 内追加：

```tsx
  it('观点日志窗口列:T+N 逐行展示,表头无排序按钮', async () => {
    mockFetch({ current: [], predictions: PREDICTIONS })
    renderPage()
    const log = await screen.findByTestId('prediction-log')
    // p2 (open, h=252) 显示 T+252;p1 (resolved_win, h=252) 同
    const p2row = log.getByTestId('prediction-row-p2')
    expect(p2row).toContainText('T+252')
    // 窗口表头不可排序:无 sort-horizon_days 按钮
    expect(screen.queryByTestId('sort-horizon_days')).not.toBeInTheDocument()
    expect(screen.getByText('窗口')).toBeInTheDocument()
  })
```

注意：该项目 vitest 的 jest-dom v7 无 `toContainText`，用 `toHaveTextContent`（add-current-stance-view Task 3 已实证，简报误写 toContainText 的教训）。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: FAIL——窗口列不存在

- [ ] **Step 3: Write minimal implementation**

1. `types.ts` PredictionRecord 接口 `resolution_rule: string | null` 之后加：

```ts
  // update-track-record-display-clarity:open 行最新盯市（浮动收益展示）；非 open 行为 null
  latest_mark?: { mark_date: string; cum_return: number | null; cum_excess: number | null } | null
```

2. `TrackRecordPage.tsx`：

a. COLUMNS 加窗口列（状态之后）并支持非排序列：

```tsx
const COLUMNS: Array<{ key: string; label: string; numeric?: boolean; sortable?: boolean }> = [
  { key: 'created_at', label: '建立日期' },
  { key: 'symbol', label: '标的' },
  { key: 'direction', label: '方向' },
  { key: 'status', label: '状态' },
  // update-track-record-display-clarity:窗口列——混合口径显式可见（T+20/T+252）；展示列不排序
  { key: 'horizon_days', label: '窗口', sortable: false },
  { key: 'entry_price', label: '入场价', numeric: true },
  { key: 'exit_price', label: '结算价', numeric: true },
  { key: 'raw_return', label: '区间收益', numeric: true },
  { key: 'excess_return', label: '基准超额', numeric: true },
]
```

b. thead 渲染改为条件排序按钮：

```tsx
                      {COLUMNS.map(c => (
                        <th key={c.key} className={`px-4 py-2 font-normal ${c.numeric ? 'text-right' : ''}`}>
                          {c.sortable === false ? (
                            c.label
                          ) : (
                            <button
                              type="button"
                              data-testid={`sort-${c.key}`}
                              onClick={() => onSort(c.key)}
                              className="inline-flex items-center gap-0.5 hover:opacity-80"
                              style={{ color: 'var(--text-tertiary)' }}
                            >
                              {c.label}{arrow(c.key)}
                            </button>
                          )}
                        </th>
                      ))}
```

c. 行内「状态」单元格之后、入场价之前加：

```tsx
                        <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>T+{r.horizon_days}</td>
```

d. 副标题（prediction-log-header 内）改为：

```tsx
                每条 = 一次分析结论;当前持有 = 仍在判定窗口内(长短见「窗口」列)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: 全部 PASS（存量断言不受影响——副标题无文本断言先例，如有按新文案更新并注明）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test/trackRecord/trackRecordPage.test.tsx
git commit -m "feat(track-record): 观点日志窗口列 T+N + 副标题去 20 日硬编码 (update-track-record-display-clarity)"
```

---

### Task 5: 前端 open 行浮动收益

**Files:**
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（观点日志行收益两格）
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `latest_mark` 行字段 + Task 4 的类型定义

- [ ] **Step 1: Write the failing test**

`trackRecordPage.test.tsx` describe 内追加（PREDICTIONS[1]=p2 open 无 latest_mark → 「—」；新造一条带 latest_mark 的 open 行 → 显示浮动车 + title）：

```tsx
  it('open 行浮动收益:有盯市显示浮动车并带盯市日期 title,无盯市显示 —', async () => {
    const withMark = {
      ...PREDICTIONS[1],
      prediction_id: 'p3', symbol: '600016.SH', symbol_name: '民生银行',
      latest_mark: { mark_date: '2026-10-08', cum_return: -0.012, cum_excess: -0.008 },
    }
    mockFetch({ current: [], predictions: [PREDICTIONS[0], PREDICTIONS[1], withMark] })
    renderPage()
    const p3row = await screen.findByTestId('prediction-row-p3')
    expect(p3row).toHaveTextContent('-1.20%')
    expect(p3row).toHaveTextContent('-0.80%')
    const markCell = p3row.getAllByTitle('盯市 2026-10-08（未结算浮动）')
    expect(markCell.length).toBeGreaterThanOrEqual(1)
    const p2row = screen.getByTestId('prediction-row-p2')
    expect(p2row).toHaveTextContent('—')
    expect(p2row.queryByTitle(/盯市/)).toBeNull()
  })
```

注意：`toHaveTextContent('-1.20%')` 子串匹配会同时命中区间收益格与其余格的风险不存在（-1.20% 唯一）；`getAllByTitle` 断言 count≥1（两个格子都带同 title）。p2 行的收益格此时显示「—」而非 0 值。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: FAIL——p3 行收益格显示「—」（latest_mark 未被消费）

- [ ] **Step 3: Write minimal implementation**

`TrackRecordPage.tsx` 观点日志 `rows.map(r => ...)` 内，收益两格替换为（map 回调开头先取值）：

```tsx
                        {(() => {
                          // update-track-record-display-clarity:open 行展示最新盯市浮动
                          // (latest_mark),已结算行展示结算读数;title 区分语义
                          const floating = r.status === 'open' ? r.latest_mark : undefined
                          const markTitle = floating ? `盯市 ${floating.mark_date}（未结算浮动）` : undefined
                          return (
                            <>
                              <td className="px-4 py-3 text-right" title={markTitle}>
                                <Delta value={floating ? floating.cum_return : r.raw_return} />
                              </td>
                              <td className="px-4 py-3 text-right" title={markTitle}>
                                <Delta value={floating ? floating.cum_excess : r.excess_return} />
                              </td>
                            </>
                          )
                        })()}
```

（原两格 `<td ...><Delta value={r.raw_return} /></td><td ...><Delta value={r.excess_return} /></td>` 删除。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test/trackRecord/trackRecordPage.test.tsx
git commit -m "feat(track-record): open 行浮动收益——区间收益/基准超额列接最新盯市 (update-track-record-display-clarity)"
```

---

### Task 6: 前端同日重复折叠

**Files:**
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（表格 body 渲染层）
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Produces: testid `dup-group-{symbol}-{date}`（汇总行，点击展开/收起）；明细行沿用 prediction-row-{id}

- [ ] **Step 1: Write the failing test**

fixture 追加三条同股同日 dup + 一条普通行，断言默认折叠、点击展开：

```tsx
  it('同日重复行默认折叠为汇总,点击展开明细,分页 total 不变', async () => {
    const dupBase = {
      ...PREDICTIONS[0], symbol: '000858.SH', symbol_name: '五粮液',
      status: 'duplicate_of_day' as const, resolution_rule: 'duplicate_of_day',
      exit_price: null, raw_return: null, excess_return: null,
    }
    const dupRows = [
      { ...dupBase, prediction_id: 'd1', created_at: '2026-10-05T11:00:00' },
      { ...dupBase, prediction_id: 'd2', created_at: '2026-10-05T12:00:00' },
      { ...dupBase, prediction_id: 'd3', created_at: '2026-10-05T13:00:00' },
    ]
    mockFetch({ current: [], predictions: dupRows, predictionsTotal: 7 })
    renderPage()
    // 默认折叠:1 行汇总,3 条明细不渲染
    expect(await screen.findByTestId('dup-group-000858.SH-2026-10-05')).toContainText('同日重复 ×3')
    expect(screen.queryByTestId('prediction-row-d1')).not.toBeInTheDocument()
    // 分页 total 不受折叠影响
    expect(screen.getByText(/共 7 条/)).toBeInTheDocument()
    // 点击展开
    fireEvent.click(screen.getByTestId('dup-group-000858.SH-2026-10-05'))
    expect(screen.getByTestId('prediction-row-d1')).toBeInTheDocument()
    expect(screen.getByTestId('prediction-row-d3')).toBeInTheDocument()
  })
```

注意：① `mockFetch` 需支持 `predictionsTotal`（分页 total 断言用，改造 mockFetch 的 predictions 分支：`total: opts.predictionsTotal ?? 0`）；② d2/d3 用对象展开语法展开完整 fixture（不能写「同上」——实现时逐字段展开 `dupRows[0]` 换 id/created_at）；③ fireEvent 已在该测试文件 import。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: FAIL——无 dup-group testid

- [ ] **Step 3: Write minimal implementation**

`TrackRecordPage.tsx`：

a. state 区加：

```tsx
  // update-track-record-display-clarity:同日重复折叠——展开组 key 集合(当前页前端作用域)
  const [expandedDups, setExpandedDups] = useState<Set<string>>(new Set())
```

b. 渲染前把 `rows` 组装为显示序列（`const rows = records ?? []` 之后）：

```tsx
  type DisplayRow =
    | { kind: 'single'; row: PredictionRecord }
    | { kind: 'dup-group'; key: string; rows: PredictionRecord[] }
  const displayRows: DisplayRow[] = []
  {
    let i = 0
    while (i < rows.length) {
      const r = rows[i]
      const date = r.created_at.slice(0, 10)
      if (
        r.status === 'duplicate_of_day' &&
        i + 1 < rows.length &&
        rows[i + 1].status === 'duplicate_of_day' &&
        rows[i + 1].symbol === r.symbol &&
        rows[i + 1].created_at.slice(0, 10) === date
      ) {
        const group: PredictionRecord[] = []
        while (
          i < rows.length &&
          rows[i].status === 'duplicate_of_day' &&
          rows[i].symbol === r.symbol &&
          rows[i].created_at.slice(0, 10) === date
        ) {
          group.push(rows[i])
          i += 1
        }
        displayRows.push({ kind: 'dup-group', key: `${r.symbol}|${date}`, rows: group })
      } else {
        displayRows.push({ kind: 'single', row: r })
        i += 1
      }
    }
  }
```

c. tbody 渲染改为双层（单行分支沿用现有行 JSX；dup-group 分支渲染汇总行，展开时追加组内明细行——明细行 JSX 抽为局部函数 `renderPredictionRow(r)` 复用）：

```tsx
                    {displayRows.map(d => {
                      if (d.kind === 'single') return renderPredictionRow(d.row)
                      const expanded = expandedDups.has(d.key)
                      const first = d.rows[0]
                      return (
                        <Fragment key={d.key}>
                          <tr
                            data-testid={`dup-group-${d.key.replace('|', '-')}`}
                            className="border-t cursor-pointer hover:opacity-80"
                            style={{ borderColor: 'var(--border-neutral-l1)' }}
                            onClick={() =>
                              setExpandedDups(prev => {
                                const next = new Set(prev)
                                if (next.has(d.key)) next.delete(d.key)
                                else next.add(d.key)
                                return next
                              })
                            }
                          >
                            <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{first.created_at.slice(0, 10)}</td>
                            <td className="px-4 py-3">
                              <div className="font-medium" style={{ color: 'var(--text-default)' }}>{first.symbol_name ?? first.symbol}</div>
                              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{first.symbol}</div>
                            </td>
                            <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>—</td>
                            <td className="px-4 py-3"><span className={STATUS_CLS.duplicate_of_day}>同日重复 ×{d.rows.length}</span></td>
                            <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>T+{first.horizon_days}</td>
                            <td className="px-4 py-3 text-right">—</td>
                            <td className="px-4 py-3 text-right">—</td>
                            <td className="px-4 py-3 text-right">—</td>
                            <td className="px-4 py-3 text-right">—</td>
                          </tr>
                          {expanded && d.rows.map(r => renderPredictionRow(r))}
                        </Fragment>
                      )
                    })}
```

（需 `import { Fragment } from 'react'`；`renderPredictionRow(r: PredictionRecord)` 为现有 `<tr key={r.prediction_id} ...>` JSX 抽出的局部渲染函数，onClick 导航逻辑不变。注意汇总行方向格显示「—」（组内方向可能混合），窗口格取首行窗口。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test/trackRecord/trackRecordPage.test.tsx
git commit -m "feat(track-record): 同日重复行当前页折叠汇总+点击展开 (update-track-record-display-clarity)"
```

---

### Task 7: 切片空态折叠 + 术语 + predictionDisplay + 详情中文化

**Files:**
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（切片区条件渲染；三处「已判定」术语；DIRECTION_LABEL 改 import）
- Create: `frontend/src/pages/trackRecord/predictionDisplay.ts`
- Modify: `frontend/src/pages/trackRecord/predictionStatus.ts`（resolved_neutral 标签）
- Modify: `frontend/src/pages/trackRecord/PredictionDetailPage.tsx`（方向/判定规则中文化）
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx` + 详情页测试（如存在，同目录 grep）

**Interfaces:**
- Produces: `predictionDisplay.ts` 的 `DIRECTION_LABEL`/`RESOLUTION_RULE_LABEL`——列表与详情共用单一真源

- [ ] **Step 1: Write the failing test**

`trackRecordPage.test.tsx` 追加：

```tsx
  it('切片空态:settled=0 时折叠为一行说明,不渲染分桶表格', async () => {
    mockFetch({ current: [], predictions: [] })
    renderPage()
    expect(await screen.findByTestId('track-record-segments-empty')).toHaveTextContent('切片指标将在首批观点结算后可用')
    expect(screen.queryByTestId('track-record-segments')).not.toBeInTheDocument()
  })

  it('术语消歧:横幅用已结算,带内中性标签替换中性', async () => {
    mockFetch({ current: [], predictions: [
      { ...PREDICTIONS[0], status: 'resolved_neutral', resolution_rule: 'superseded' },
    ] })
    renderPage()
    // 横幅:已结算(原「已判定 0 条」)
    expect(await screen.findByTestId('track-record-insufficient')).toHaveTextContent('已结算 0 条')
    expect(screen.getByTestId('track-record-insufficient').textContent).not.toContain('已判定 0 条')
    // 状态标签:带内中性
    expect(screen.getByTestId('prediction-log')).toHaveTextContent('带内中性')
  })
```

（若现有用例断言「已判定 0 条」或「中性」状态文本——实现时逐个改为新值并在 commit 注明；`/样本积累中/` 部分匹配的用例不受影响。）

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run trackRecordPage`
Expected: FAIL——segments-empty 不存在；横幅仍是「已判定」

- [ ] **Step 3: Write minimal implementation**

1. 新建 `frontend/src/pages/trackRecord/predictionDisplay.ts`：

```ts
// 方向/判定规则中文映射单一真源（update-track-record-display-clarity）：
// 列表与详情共用，避免两处漂移；原始英文值由调用方以 title 辅助保留供排查。
export const DIRECTION_LABEL: Record<string, string> = {
  long: '看多',
  short: '看空',
  neutral: '中性',
}

export const RESOLUTION_RULE_LABEL: Record<string, string> = {
  expiry: '到期结算',
  superseded: '被新观点替代·提前结算',
  duplicate_of_day: '同日重复关闭',
  stale_no_market: '长期无行情',
}
```

2. `TrackRecordPage.tsx`：删除本地 `DIRECTION_LABEL` 常量，改 `import { DIRECTION_LABEL } from './predictionDisplay'`（引用处不变）。

3. 术语三处：胜率卡 label「胜率（已结算）」；回避卡 label「回避正确率（中性观点已结算）」与其空态「样本积累中（已结算 N 条，满 10 条解锁）」；横幅「样本积累中（已结算 {overview.settled} 条，满 10 条解锁胜率）」。

4. 切片区条件渲染（`{/* 切片指标 ... */}` 区块外包）：

```tsx
          {overview.settled === 0 ? (
            <div className="rounded-xl p-4 mb-6" data-testid="track-record-segments-empty" style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-tertiary)' }}>
              切片指标将在首批观点结算后可用
            </div>
          ) : (
            <div className="rounded-xl p-4 mb-6" style={{ background: 'var(--bg-overlay-l1)' }} data-testid="track-record-segments">
              ……现有切片 JSX 原样……
            </div>
          )}
```

5. `predictionStatus.ts`：`resolved_neutral: '带内中性',`（注释注明与方向「中性」消歧、后端 `_STATUS_LABELS` 已同步）。

6. `PredictionDetailPage.tsx`：import 区加 `import { DIRECTION_LABEL, RESOLUTION_RULE_LABEL } from './predictionDisplay'`；L89 方向格：

```tsx
            <Field label="方向"><span title={p.direction}>{DIRECTION_LABEL[p.direction] ?? p.direction}</span></Field>
```

L96 判定规则格：

```tsx
            <Field label="判定规则">{p.resolution_rule ? <span title={p.resolution_rule}>{RESOLUTION_RULE_LABEL[p.resolution_rule] ?? p.resolution_rule}</span> : '—'}</Field>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: 全量 PASS（存量断言按预期变更更新处，在 commit message 注明清单）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/trackRecord/ frontend/src/test/trackRecord/
git commit -m "feat(track-record): 切片空态折叠 + 已结算/带内中性术语 + 详情页中文化 (update-track-record-display-clarity)"
```

---

### Task 8: E2E spec

**Files:**
- Create: `tests/e2e/playwright/tests/track-record-ux-clarity.spec.ts`

**Interfaces:**
- Consumes: `/api/test/seed`（predictions + 行内 marks）；Task 4-7 的 testid 与文案
- 命名约束：`ux-clarity` 字母序排在本套件现有全部 spec（含 stance-view）之后——前置种子不破坏本 spec 前提，本 spec 用独立 symbol（601318/000858/600015 之 600015 可能与既有 spec 撞、改用 601288 农业银行）

- [ ] **Step 1: 写 spec**

```ts
import { expect, test } from '@playwright/test'

/**
 * update-track-record-display-clarity Task 8:展示治理 E2E 门禁。
 * 红线:不 mock 业务接口——造数走 TESTING=1 的 /api/test/seed(predictions + 行内 marks)。
 * 套件序:字母序排本套件末位(ux > stance);断言只认本 spec 造的 symbol(601318/000858/601288)。
 * 覆盖:窗口列混合口径 / open 行浮动收益(盯市 title) / 同日重复折叠展开(total 不变) /
 * 切片空态折叠 / 详情页方向+判定规则中文映射。
 */
test.describe('战绩页:展示治理(add-track-record-display-clarity)', () => {
  let seeded = false

  test.beforeEach(async ({ request }) => {
    if (seeded) return
    const resp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            {
              symbol: '601318.SH', symbol_name: '中国平安', direction: 'short',
              created_at: '2026-10-01T10:00:00',
              marks: [{ mark_date: '2026-10-08', cum_return: -0.012, cum_excess: -0.008 }],
            },
            {
              symbol: '601318.SH', symbol_name: '中国平安', direction: 'neutral',
              created_at: '2026-10-02T10:00:00', horizon_days: 252,
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T10:00:00',
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T11:00:00', status: 'duplicate_of_day', resolution_rule: 'duplicate_of_day',
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T12:00:00', status: 'duplicate_of_day', resolution_rule: 'duplicate_of_day',
            },
            {
              symbol: '601288.SH', symbol_name: '农业银行', direction: 'short',
              created_at: '2026-10-04T10:00:00', status: 'resolved_neutral', resolution_rule: 'superseded',
            },
          ],
        },
      },
    })
    expect(resp.ok()).toBeTruthy()
    seeded = true
  })

  test('窗口列混合口径 + open 行浮动收益 + 无盯市显示 —', async ({ page }) => {
    await page.goto('/track-record')
    const log = page.getByTestId('prediction-log')
    // 601318 short open(有盯市):T+20 + 浮动收益 + 盯市日期 title
    const peace = log.getByRole('row').filter({ hasText: '中国平安' }).filter({ hasText: '看空' })
    await expect(peace).toHaveCount(1)
    await expect(peace).toContainText('T+20')
    await expect(peace).toContainText('-1.20%')
    await expect(peace).toContainText('-0.80%')
    await expect(peace.getByTitle('盯市 2026-10-08（未结算浮动）').first()).toBeAttached()
    // 601318 neutral open(无盯市,T+252):收益格 —
    const peaceNeutral = log.getByRole('row').filter({ hasText: '中国平安' }).filter({ hasText: '中性' })
    await expect(peaceNeutral).toHaveCount(1)
    await expect(peaceNeutral).toContainText('T+252')
    // 副标题不再含「20 日」
    await expect(page.getByTestId('prediction-log-header')).not.toContainText('20 日')
  })

  test('同日重复折叠:默认汇总 ×3,展开后明细可见,total 不变', async ({ page }) => {
    await page.goto('/track-record')
    await page.getByTestId('prediction-tab-all').click()
    const log = page.getByTestId('prediction-log')
    const group = page.getByTestId('dup-group-000858.SH-2026-10-05')
    await expect(group).toContainText('同日重复 ×3')
    const pagBefore = await page.getByTestId('track-record-pagination').innerText()
    await group.click()
    await expect(log.getByRole('row', { name: /五粮液/ })).toHaveCount(4) // 1 open + 3 dup 明细
    expect(await page.getByTestId('track-record-pagination').innerText()).toEqual(pagBefore)
    await group.click()
    await expect(log.getByRole('row', { name: /五粮液/ })).toHaveCount(2) // 收起:1 open + 1 汇总
  })

  test('已判定 tab:带内中性标签;详情页方向/判定规则中文', async ({ page }) => {
    await page.goto('/track-record')
    await page.getByTestId('prediction-tab-resolved').click()
    const abc = page.getByTestId('prediction-log').getByRole('row').filter({ hasText: '农业银行' })
    await expect(abc).toContainText('带内中性')
    await abc.click()
    await expect(page).toHaveURL(/\/track-record\/predictions\//)
    await expect(page.getByText('看空', { exact: true })).toBeVisible()
    await expect(page.getByText('被新观点替代·提前结算')).toBeVisible()
  })

  test('切片空态折叠:settled=0 不渲染分桶表格', async ({ page }) => {
    await page.goto('/track-record')
    await expect(page.getByTestId('track-record-segments-empty')).toContainText('切片指标将在首批观点结算后可用')
    await expect(page.getByTestId('track-record-segments')).toHaveCount(0)
  })
})
```

（实施时若「已判定 tab 内先前 spec 种子的 resolved 行使 settled>0」——settled=win+loss，前位 spec 无 resolved_win/loss 种子，settled 恒 0，切片空态前提成立；若实证不符，把切片断言移入第 2 个 test 前提下重验并在报告注明。）

- [ ] **Step 2: scan.sh 快扫**

Run: `bash .trae/skills/e2e-reviewer/scripts/scan.sh tests/e2e/playwright/tests/track-record-ux-clarity.spec.ts`
Expected: P0 = 0

- [ ] **Step 3: 跑专属套件**

Run: `cd tests/e2e/playwright && rm -f ../../../data/test-e2e-track-record.db* && npx playwright test --config=playwright.track-record.config.ts`
Expected: 全绿（若存量 spec 因「中性→带内中性」文案变红——按预期变更更新对应断言文本，commit 注明）

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/playwright/tests/track-record-ux-clarity.spec.ts
git commit -m "test(track-record): 展示治理 E2E 门禁 spec (update-track-record-display-clarity)"
```

---

### Task 9: 全量验证 + final review

- [ ] **Step 1:** `uv run ruff check && uv run mypy src`（mypy ≤83 基线）；`uv run pytest`（对照基线：本分支基线失败集与 main 失败集一致 + 0 新增）
- [ ] **Step 2:** `cd frontend && npm test` 全绿；`npx tsc --noEmit` 零错误
- [ ] **Step 3:** E2E 专属套件全绿（Task 8 已跑，此处复跑确认最终态）
- [ ] **Step 4:** 对照 delta spec 每个 Scenario 列证据清单；dispatch final code reviewer（全分支 diff 包）
