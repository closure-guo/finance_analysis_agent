# 结算价格同口径展示 Implementation Plan

> **For agentic workers:** 本计划在会话内直接以 TDD 五步执行（任务粒度小、改动点已全部勘察定位，不派发 subagent）。

**Goal:** 战绩页观点日志与详情页把盘面口径参考价与 hfq 结算价的可比性补齐：新增结算入场价列、口径列头标注、详情页三价。

**Architecture:** 纯前端展示 + TESTING-only seed 通道透传。后端生产代码零改动（列表 API `SELECT *` 已返回 `settle_entry_price`，`_MUTABLE_FIELDS` 已含该列）。

**Tech Stack:** React 18 + TS + vitest（前端）；FastAPI TESTING=1 seed 端点（后端）；Playwright track-record 专属套件（E2E）。

## Global Constraints

- E2E 红线：禁止 mock 业务接口；造数一律走 `/api/test/seed` 的 `track_record.predictions` 通道
- 新列不参与排序：后端 `_SORT_WHITELIST` 不动；列头渲染为纯 th（无 sort 按钮）
- 禁止将结算价折算回盘面口径展示
- Playwright 套件按文件名字母序串行共享持久库：本变更 spec 命名 `track-record-settle-price-display.spec.ts`（"s" 排 pred-* 之后，不污染 pred-tabs 空态前提）
- 本地跑 track-record 套件前删 `data/test-e2e-track-record.db*`

---

### Task 1: seed 通道结算字段透传（后端 TESTING-only）

**Files:**
- Modify: `src/finance_agent/api.py`（test_seed 的 predictions 循环，约 :775-785）
- Test: `tests/test_api_track_record.py`（追加）

**Interfaces:**
- Consumes: `update_prediction_status(pid, resolved)`（`_MUTABLE_FIELDS` 已含 settle_entry_price/exit_price/raw_return/excess_return）
- Produces: seed 行可带 `settle_entry_price`/`exit_price`/`raw_return`/`excess_return`（存在才透传）

- [ ] **Step 1: 写失败测试**

```python
async def test_seed_predictions_settle_fields_passthrough(client):
    """update-track-record-settle-price-display:seed 终态行透传结算字段，
    供 E2E 造带 settle_entry_price 的已结算观点。"""
    resp = await client.post("/api/test/seed", json={"track_record": {"predictions": [
        {"symbol": "601818.SH", "direction": "short", "created_at": "2026-10-09T18:00:00",
         "status": "resolved_loss", "resolution_rule": "horizon",
         "settle_entry_price": 6.39, "exit_price": 6.5, "raw_return": -0.0172},
    ]}})
    assert resp.status_code == 200
    rows = await client.get("/api/v1/track-record/predictions?keyword=601818")
    items = rows.json()["predictions"]
    assert len(items) == 1
    assert items[0]["settle_entry_price"] == 6.39
    assert items[0]["exit_price"] == 6.5
```

- [ ] **Step 2: 运行确认失败**：`uv run pytest tests/test_api_track_record.py -k seed_settle -q` → FAIL（字段被丢弃，None）
- [ ] **Step 3: 最小实现**：api.py seed 循环 resolved dict 构造后追加：

```python
                        for _fld in ("settle_entry_price", "exit_price", "raw_return", "excess_return"):
                            if row.get(_fld) is not None:
                                resolved[_fld] = row[_fld]
```

- [ ] **Step 4: 运行确认通过**：同 Step 2 命令 → PASS；`uv run pytest tests/test_api_track_record.py -q` 全绿
- [ ] **Step 5: Commit**：`test(api): seed 终态行透传结算字段 (update-track-record-settle-price-display)`

---

### Task 2: 列表页结算入场价列 + 口径列头

**Files:**
- Modify: `frontend/src/types.ts`（PredictionRecord 增 `settle_entry_price: number | null`）
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（:19-28 COLUMNS；thead 渲染块 :498-511；tbody :534-535）
- Test: `frontend/src/pages/trackRecord/__tests__/trackRecordPage.test.tsx`（追加）

- [ ] **Step 1: 写失败测试**（列头文案三断言；resolved 行渲染 settle 值；open 行 '—'；新列头无 sort 按钮 `sort-settle_entry_price` 不存在）
- [ ] **Step 2: 运行确认失败**：`cd frontend && npx vitest run src/pages/trackRecord/__tests__/trackRecordPage.test.tsx`
- [ ] **Step 3: 最小实现**

```ts
const COLUMNS: Array<{ key: string; label: string; numeric?: boolean; sortable?: boolean }> = [
  { key: 'created_at', label: '建立日期' },
  { key: 'symbol', label: '标的' },
  { key: 'direction', label: '方向' },
  { key: 'status', label: '状态' },
  { key: 'entry_price', label: '参考价（盘面）', numeric: true },
  { key: 'settle_entry_price', label: '结算入场价（后复权）', numeric: true, sortable: false },
  { key: 'exit_price', label: '结算价（后复权）', numeric: true },
  { key: 'raw_return', label: '区间收益', numeric: true },
  { key: 'excess_return', label: '基准超额', numeric: true },
]
```

thead 中 `sortable === false` 的列渲染纯文本 th（无 button）；tbody 在 entry/exit 两 td 之间插 `{fmt(r.settle_entry_price)}`。

- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**：`feat(frontend): 观点日志结算入场价列+口径列头 (update-track-record-settle-price-display)`

---

### Task 3: 详情页三价展示

**Files:**
- Modify: `frontend/src/pages/trackRecord/PredictionDetailPage.tsx`（:91-93 Field 区）
- Test: `frontend/src/pages/trackRecord/__tests__/predictionDetailPage.test.tsx`（追加）

- [ ] **Step 1-5:** 失败测试（三 Field 标签与值）→ 改为 参考价（盘面）/ 结算入场价（后复权）/ 结算价（后复权）三格 → 绿 → commit `feat(frontend): 详情页三价口径展示`

---

### Task 4: E2E 用例

**Files:**
- Create: `tests/e2e/playwright/tests/track-record-settle-price-display.spec.ts`

- [ ] seed：同股两行（open + resolved_loss 带 settle_entry_price=6.39/exit_price=6.5）+ 断言：
  - 列头三口径文案存在
  - resolved 行同时含 6.39 与 6.50（同口径可比）且含参考价 3.00
  - open 行结算两列为 '—'
  - 点 resolved 行进详情页，三 Field 标签+值可见
- [ ] 门禁：`cd tests/e2e/playwright && npx playwright test --config playwright.track-record.config.ts` 全绿；默认套件回归 `npx playwright test --workers=1`
- [ ] Commit：`test(e2e): 已结算行同口径价格展示用例 (update-track-record-settle-price-display)`

---

### Task 5: 验证与收尾

- [ ] `uv run pytest tests/test_api_track_record.py -q` + `cd frontend && npx vitest run` 全绿
- [ ] 验证报告落 `tests/validation/2026-10-07-update-track-record-settle-price-display-validation.md`
- [ ] 推分支 + 开 PR（基点 origin/main dc4d3af5）
