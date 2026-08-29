# update-file-export-entry 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将文件导出入口从报告卡标题区迁移为会话级双横幅（报告名横幅 + 全部文件横幅）+ 全局顶部栏按钮，抽屉只列表已生成文件，报告名补齐股票名称与代码，导出文件名含股票名称。

**Architecture:** 后端 3 处小改（report_ready 增发 stock_code、导出文件名含名称、sessions 表持久化 file_paths）；前端 4 处（类型/状态链、ReportFileDrawer 列表改造、新组件 ReportEntryBanners 三入口、App 接线与头部标题）。E2E 重写 report-export.spec.ts。

**Tech Stack:** FastAPI/Python3.12、React18/TS/Vitest、Playwright（tests/e2e/playwright）。

**需求来源（唯一真相）:** `openspec/changes/update-file-export-entry/specs/frontend/spec.md`

## Global Constraints

- 「可导出报告」判定（口径 B）：`type='report'`、`streaming` 为假、`filePaths` 含至少一个非空值（`Object.values(fp).some(Boolean)`）
- 组合标题「股票名称（股票代码）」；`stockName` 缺失或等于 `stockCode` 时仅显示代码，不显示「600519（600519）」
- 历史会话恢复：报告消息无 `stockCode` → 用会话元数据 `stock_code` 兜底；恢复消息 SHALL 携带会话持久化的 `filePaths`
- 报告名横幅紧随报告产出轮次（报告消息及其后「分析完成」系统消息）之后，位次先于「全部文件」横幅
- 全部文件横幅位于对话尾部最后一条消息之后；点击 `setDrawerMessage(该报告)`
- 全局顶部栏「查看全部文件」按钮显示于设置按钮旁，会话无可导出报告/空状态时隐藏
- 抽屉：自上而下仅列出 `filePaths` 已生成文件（图标按扩展名、文件名、下载到 `/api/files/<basename>`）；无 pdf/docx/markdown 三格式行、无现场生成（不再 `POST /api/export`）；`filePaths` 空 → 显示「暂无已生成文件」；预览/关闭（X/遮罩/Esc）行为不变
- 报告卡头部标题（h3）同组合标题；报告卡头部无任何导出按钮（移除 `open-files-banner`）
- 导出文件名 `{名称}_{代码}_{日期}_report.ext`，名称缺失或等于代码时回退仅 `{代码}_{日期}_report`
- `report_ready` 载荷不可省略既有字段（非破坏），仅新增 `stock_code`
- 测试纪律：TDD 先红后绿；commit 信息 `feat: xxx` / `fix: xxx`；变量 camelCase、注释中文
- 验证命令：后端 `uv run pytest <file> -v`、`uv run ruff check`、`uv run mypy`；前端 `cd frontend && npx vitest run <file>`；E2E `cd tests/e2e/playwright && npx playwright test --config=playwright.timeline.config.ts <spec>`

---

### Task 1: 后端 report_ready 事件增发 stock_code

**Files:**
- Modify: `src/finance_agent/api.py` — 在 `_run_graph_streaming` 上方新增 `_report_ready_event` 辅助函数；`api.py:1018-1030` 的 report_ready 内联字典改用该辅助
- Test: Create `tests/test_report_ready_event.py`

**Interfaces:**
- Produces: `_report_ready_event(analysis_id: str, session_id: str, report_markdown: str, chart_data: dict, file_paths: dict, stock_code: str, stock_name: str, duration_ms: int) -> dict`，返回 report_ready 事件载荷（含 `stock_code`，字段与现状一致 + 新增）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_report_ready_event.py
"""report_ready SSE 事件载荷契约测试（update-file-export-entry Task 1）。"""

from finance_agent.api import _report_ready_event


def test_report_ready_event_contains_stock_code_and_preserves_fields():
    ev = _report_ready_event(
        "a1", "s1", "# 报告", {"k": 1}, {"docx": "/tmp/a.docx"},
        "600519", "贵州茅台", 1234,
    )
    assert ev["type"] == "report_ready"
    assert ev["stock_code"] == "600519"
    assert ev["stock_name"] == "贵州茅台"
    assert ev["report_markdown"] == "# 报告"
    assert ev["chart_data"] == {"k": 1}
    assert ev["file_paths"] == {"docx": "/tmp/a.docx"}
    assert ev["duration_ms"] == 1234
    assert ev["timestamp"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_report_ready_event.py -v`
Expected: FAIL（`_report_ready_event` 不存在，ImportError）→ 红

- [ ] **Step 3: 最小实现**

在 `src/finance_agent/api.py` 中（`_run_graph_streaming` 定义之前，`_sse` 已定义处）新增：

```python
def _report_ready_event(
    analysis_id: str,
    session_id: str,
    report_markdown: str,
    chart_data: dict,
    file_paths: dict,
    stock_code: str,
    stock_name: str,
    duration_ms: int,
) -> dict:
    """构造 report_ready SSE 事件载荷（供 _run_graph_streaming 下发）。"""
    return {
        "type": "report_ready",
        "analysis_id": analysis_id,
        "session_id": session_id,
        "report_markdown": report_markdown,
        "chart_data": chart_data,
        "file_paths": file_paths,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "duration_ms": duration_ms,
        "timestamp": _now(),
    }
```

把 `api.py:1018-1030` 的内联 `yield _sse({...})` 替换为：

```python
                yield _sse(
                    _report_ready_event(
                        analysis_id,
                        session_id,
                        report_md,
                        accumulated.get("chart_data") or {},
                        file_paths,
                        stock_code,
                        stock_name_final,
                        duration_ms,
                    )
                )
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/test_report_ready_event.py -v` → PASS
Run: `uv run pytest tests/test_export_api.py tests/test_pipeline_anchor.py -q` → 既有契约不回归

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/api.py tests/test_report_ready_event.py
git commit -m "feat(api): report_ready 事件增发 stock_code（文件导出入口数据链路）"
```

---

### Task 2: 后端导出文件名加入股票名称

**Files:**
- Modify: `src/finance_agent/export/service.py:69`（`export_report` 内 `base_name`）
- Test: Modify `tests/export/test_service.py`

**Interfaces:**
- Consumes: `export_report(markdown_text, stock_code, stock_name="", formats=EXPORT_FORMATS)` 既有签名不变
- Produces: 文件名 `{名称}_{代码}_{日期}_report.ext`；名称缺失或等于代码 → `{代码}_{日期}_report.ext`

- [ ] **Step 1: 写失败测试**（追加到 `tests/export/test_service.py`）

```python
def test_export_report_filename_contains_stock_name(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "贵州茅台", formats=["md"])
    assert result["md"] is not None
    name = Path(result["md"]).name
    assert name.startswith("贵州茅台_600519_")
    assert name.endswith("_report.md")


def test_export_report_filename_fallback_when_name_equals_code(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "600519", formats=["md"])
    assert result["md"] is not None
    name = Path(result["md"]).name
    assert name.startswith("600519_")
    assert "600519_600519" not in name
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/export/test_service.py -v`
Expected: FAIL（现文件名形如 `600519_<date>_report.md`，不含名称）→ 红

- [ ] **Step 3: 最小实现**

`src/finance_agent/export/service.py` 中：

```python
    name_part = (stock_name or "").strip()
    stem = f"{name_part}_{stock_code}" if name_part and name_part != stock_code else stock_code
    base_name = str(reports_dir / f"{stem}_{date_str}_report")
```

（替换原 `base_name = str(reports_dir / f"{stock_code}_{date_str}_report")`，其余 converter 循环不动。）

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/export/ -q` → PASS

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/export/service.py tests/export/test_service.py
git commit -m "feat(export): 导出文件名加入股票名称（含缺失回退）"
```

---

### Task 3: 会话持久化 file_paths（sessions 表 + API + 恢复链路）

**Files:**
- Modify: `src/finance_agent/session_store.py` — 迁移列表、`update_session_report`、`get_session`（JSON 解析）
- Modify: `src/finance_agent/api.py:1005-1014` — `update_session_report(...)` 调用传 `file_paths`
- Test: Create `tests/test_session_file_paths.py`

**Interfaces:**
- Consumes: `update_session_report(session_id, report_markdown="", chart_data=None, analyst_reports=None, agent_process=None, analyst_summaries=None, duration_ms=0, status="completed")` — 新增 `file_paths: dict | None = None` 参数
- Produces: `get_session(session_id)` 返回的 dict SHALL 含 `file_paths` 键（dict，占位 `{}`）；`GET /api/sessions/{id}` 返回 `"file_paths": {...}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_session_file_paths.py
"""sessions 表持久化报告文件产物（update-file-export-entry Task 3）。"""

import json

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


def test_update_session_report_persists_and_returns_file_paths(isolated_db):
    sid = session_store.create_session(
        stock_code="600519", stock_name="贵州茅台", status="running"
    )
    session_store.update_session_report(
        sid,
        report_markdown="# 报告",
        file_paths={"md": "/tmp/贵州茅台_600519_20260825_report.md", "docx": "/tmp/贵州茅台_600519_20260825_report.docx"},
        duration_ms=1234,
    )
    row = session_store.get_session(sid)
    assert row["file_paths"] == {
        "md": "/tmp/贵州茅台_600519_20260825_report.md",
        "docx": "/tmp/贵州茅台_600519_20260825_report.docx",
    }
    detail = TestClient(app).get(f"/api/sessions/{sid}").json()
    assert detail["file_paths"]["md"].endswith("_report.md")


def test_legacy_session_without_file_paths_returns_empty(isolated_db):
    sid = session_store.create_session(stock_code="600519", status="completed")
    row = session_store.get_session(sid)
    assert row["file_paths"] == {}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_session_file_paths.py -v`
Expected: FAIL（无 file_paths 列/字段）→ 红

- [ ] **Step 3: 最小实现**

`session_store.py`：
1. 迁移列表（`init_db` 中 ADD COLUMN 列表，约 96-104 行，与 `pipeline_snapshot` 同款）追加：`("file_paths", "ALTER TABLE sessions ADD COLUMN file_paths TEXT")`；注意 `CREATE TABLE` 初始列不用改（迁移兼容旧库）
2. `update_session_report` 签名新增 `file_paths: dict | None = None`，SQL 增列 `file_paths = ?`，参数 `json.dumps(file_paths or {}, ensure_ascii=False)`
3. `get_session` 中解析 `chart_data` 等 JSON 列的位置，同款解析 `file_paths`（`json.loads`，NULL/缺失 → `{}`）——按该函数现有的 JSON 列处理模式逐项复制

`api.py` `_run_graph_streaming` 完成分支的 `update_session_report(...)` 调用加参数：

```python
                update_session_report(
                    session_id,
                    report_markdown=report_md,
                    chart_data=accumulated.get("chart_data") or {},
                    analyst_reports=_safe_dump(accumulated.get("analyst_reports") or {}),
                    agent_process=agent_process,
                    analyst_summaries=analyst_summaries,
                    duration_ms=duration_ms,
                    file_paths=file_paths,
                    status="completed",
                )
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/test_session_file_paths.py -v` → PASS
Run: `uv run pytest tests/test_session_store*.py tests/test_pipeline_anchor.py tests/test_react_pipeline_snapshot.py -q` → 不回归

- [ ] **Step 5: 提交**

```bash
git add src/finance_agent/session_store.py src/finance_agent/api.py tests/test_session_file_paths.py
git commit -m "feat(session): 会话持久化报告 file_paths，刷新恢复可还原导出产物"
```

---

### Task 4: 前端类型与状态链（stockCode + filePaths 恢复）

**Files:**
- Modify: `frontend/src/types.ts` — `ReportReadyEvent` 增 `stock_code: string`（43-54 行附近）；`UIMessage` 增 `stockCode?: string`（372 行附近）；`SessionDetail` 增 `file_paths?: Record<string, string>`
- Modify: `frontend/src/stores/streamStore/reduce.ts:178-203` — `report_ready` updates 增 `stockCode: event.stock_code`
- Modify: `frontend/src/stores/streamStore/index.ts:451-463` — 恢复 reportMsg 增 `stockCode: data.stock_code` 与 `filePaths: data.file_paths || undefined`
- Test: Modify `frontend/src/test/streamStore/reduce.test.ts`

**Interfaces:**
- Consumes: Task 1（后端 `report_ready` 含 `stock_code`）、Task 3（`GET /api/sessions/{id}` 含 `file_paths`）
- Produces: `UIMessage.stockCode?: string`、`UIMessage.filePaths`（恢复路径也有值）、`SessionDetail.file_paths?`

- [ ] **Step 1: 写失败测试**（追加到 `frontend/src/test/streamStore/reduce.test.ts`，沿用文件头部现有 state 构造辅助；若无独立 helper 则按该文件既有模式内联构造含 `sessionId/phase/messages/lastSeq/status` 的初始 state）

```ts
describe('reduce - report_ready 携带股票代码', () => {
  it('report_ready 消息记录 stockCode 与既有字段', () => {
    const state = makeState({ messages: [] as UIMessage[] })
    const next = reduce(state, {
      type: 'report_ready',
      session_id: 's1',
      report_markdown: '# 报告',
      chart_data: {},
      file_paths: { md: '/tmp/贵州茅台_600519_x_report.md' },
      stock_name: '贵州茅台',
      stock_code: '600519',
      duration_ms: 1234,
      timestamp: 't',
    } as never)
    const report = next.messages.find((m) => m.type === 'report')
    expect(report?.stockCode).toBe('600519')
    expect(report?.stockName).toBe('贵州茅台')
    expect(report?.filePaths).toEqual({ md: '/tmp/贵州茅台_600519_x_report.md' })
  })
})
```

（`makeState` 若不存在，用该文件既有的最小 state 字面量代替；UIMessage 从 `../types` 导入。）

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/streamStore/reduce.test.ts`
Expected: FAIL（`report?.stockCode` undefined）→ 红

- [ ] **Step 3: 最小实现**

`types.ts`：
- `ReportReadyEvent`（43-54 行）在 `stock_name` 前加 `stock_code: string`
- `UIMessage`（372 行 `stockName?: string` 后）加 `stockCode?: string`
- `SessionDetail`（302 行 extends SessionMeta 的接口体）加 `file_paths?: Record<string, string>`

`reduce.ts` report_ready updates（181-189 行）加一行：

```ts
        stockName: event.stock_name,
        stockCode: event.stock_code,
```

`index.ts` 恢复 reportMsg（451-463 行）加两行：

```ts
            stockName: data.stock_name,
            stockCode: data.stock_code,
            filePaths: data.file_paths || undefined,
```

- [ ] **Step 4: 运行确认通过 + 类型检查**

Run: `cd frontend && npx vitest run src/test/streamStore/reduce.test.ts` → PASS
Run: `cd frontend && npx tsc --noEmit`（如项目有 tsc 脚本则用 `npm run build` 替代）→ 无类型错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/types.ts frontend/src/stores/streamStore/reduce.ts frontend/src/stores/streamStore/index.ts frontend/src/test/streamStore/reduce.test.ts
git commit -m "feat(frontend): 报告消息携带 stockCode，恢复路径还原 filePaths"
```

---

### Task 5: ReportFileDrawer 只列表已生成文件

**Files:**
- Modify: `frontend/src/ReportFileDrawer.tsx`（全量重写列表区）
- Test: Rewrite `frontend/src/test/reportFileDrawer.test.tsx`

**Interfaces:**
- Consumes: `UIMessage.filePaths`（key=格式, value=路径）、`UIMessage.reportMarkdown`（预览）
- Produces: testid `export-drawer` / `drawer-backdrop` / `drawer-close` / `preview-open` / `drawer-preview` / `file-row-<fmt>` / `download-file-<fmt>`；移除 `EXPORT_FORMATS`/`ExportFormatMeta`（先 grep 确认无其他引用再删）

- [ ] **Step 1: 写失败测试**（重写 `frontend/src/test/reportFileDrawer.test.tsx`）

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReportFileDrawer } from '../ReportFileDrawer'
import type { UIMessage } from '../types'

const baseMsg: UIMessage = {
  id: 'm1',
  type: 'report',
  content: '',
  reportMarkdown: '# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n',
  sessionId: 's1',
  filePaths: {
    docx: '/tmp/贵州茅台_600519_x_report.docx',
    pdf: '/tmp/贵州茅台_600519_x_report.pdf',
  },
}

describe('ReportFileDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('默认关闭：drawerMessage 为 null 时不渲染', () => {
    const { container } = render(<ReportFileDrawer drawerMessage={null} onClose={() => {}} />)
    expect(container.querySelector('[data-testid="export-drawer"]')).toBeNull()
  })

  it('打开后自上而下仅列出 filePaths 已生成的可下载文件', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    expect(screen.getByTestId('export-drawer')).toBeTruthy()
    expect(screen.getByText('贵州茅台_600519_x_report.docx')).toBeTruthy()
    expect(screen.getByText('贵州茅台_600519_x_report.pdf')).toBeTruthy()
    const pdfLink = screen.getByTestId('download-file-pdf')
    expect(pdfLink.getAttribute('href')).toBe('/api/files/贵州茅台_600519_x_report.pdf')
    expect(pdfLink.getAttribute('download')).toBe('贵州茅台_600519_x_report.pdf')
  })

  it('不再显示 PDF/Word/Markdown 三格式行，无现场生成按钮', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    expect(screen.queryByText('PDF')).toBeNull()
    expect(screen.queryByText('Word')).toBeNull()
    expect(screen.queryByText('Markdown')).toBeNull()
    expect(screen.queryByTestId('download-md')).toBeNull()
    expect(screen.queryByTestId('download-pdf')).toBeNull() // 旧 testid 已废弃
  })

  it('filePaths 为空时展示空态提示', () => {
    render(<ReportFileDrawer drawerMessage={{ ...baseMsg, filePaths: {} }} onClose={() => {}} />)
    expect(screen.getByText('暂无已生成文件')).toBeTruthy()
  })

  it('点击关闭按钮 / Esc / 遮罩可关闭', () => {
    const onClose = vi.fn()
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('drawer-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('预览面板渲染 Markdown 正文', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('preview-open'))
    expect(screen.getByTestId('drawer-preview')).toBeTruthy()
    expect(screen.getByText('测试报告')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/reportFileDrawer.test.tsx`
Expected: FAIL（新断言找不到 download-file-pdf、仍渲染三格式行）→ 红

- [ ] **Step 3: 最小实现**

`ReportFileDrawer.tsx` 全量重写：
- 删除 `EXPORT_FORMATS`/`ExportFormatMeta` 与 `handleDownload`（POST /api/export 逻辑整体移除）；grep 确认前端无其他引用（有则一并清理）
- 文件图标按扩展名映射：

```tsx
const FILE_ICONS: Record<string, string> = {
  pdf: 'fa-file-pdf',
  docx: 'fa-file-word',
  md: 'fa-file-code',
  pptx: 'fa-file-powerpoint',
}
const extIcon = (name: string) => {
  const ext = (name.split('.').pop() ?? '').toLowerCase()
  return FILE_ICONS[ext] || 'fa-file'
}
```

- 列表区（view === 'list'）替换为：

```tsx
        {view === 'list' ? (
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2" data-testid="drawer-file-list">
            {fileEntries.length === 0 ? (
              <p className="text-xs py-3 text-center" style={{ color: 'var(--text-tertiary)' }}>
                暂无已生成文件
              </p>
            ) : (
              fileEntries.map(({ fmt, name }) => (
                <div key={fmt} data-testid={`file-row-${fmt}`}
                  className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-base-secondary)' }}>
                  <i className={`fas ${extIcon(name)} text-sm`} style={{ color: 'var(--text-brand)' }}></i>
                  <span className="flex-1 text-sm font-medium truncate" style={{ color: 'var(--text-default)' }}>{name}</span>
                  <a href={`/api/files/${name}`} download={name} data-testid={`download-file-${fmt}`}
                    className="text-xs px-2 py-1 rounded no-underline"
                    style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}>
                    <i className="fas fa-download mr-1"></i>下载
                  </a>
                </div>
              ))
            )}
          </div>
        ) : (
          /* 预览视图保持现状不动 */
        )}
```

- 文件条目派生（组件内 `fileEntries`）：

```tsx
  const fileEntries = Object.entries(drawerMessage.filePaths || {})
    .map(([fmt, path]) => ({ fmt, name: basename(path) }))
    .filter((e) => e.name)
```

（`basename` 既有定义保留；Esc/遮罩/关闭/预览逻辑不动。）

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/reportFileDrawer.test.tsx` → PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/ReportFileDrawer.tsx frontend/src/test/reportFileDrawer.test.tsx
git commit -m "feat(drawer): 文件列表改为仅列出已生成可下载文件，移除三格式行与按需导出"
```

---

### Task 6: 报告卡头部标题 + 三入口组件 + App 接线

**Files:**
- Create: `frontend/src/ReportEntryBanners.tsx`（`formatReportTitle` / `isExportableReport` / `ReportNameBanner` / `AllFilesBanner`）
- Create: `frontend/src/test/reportEntryBanners.test.tsx`（纯组件/纯函数测试）
- Create: `frontend/src/test/fileExportEntries.test.tsx`（App 集成测试）
- Modify: `frontend/src/App.tsx` — 计算导出报告、消息容器尾追加横幅、顶部栏按钮、ReportCard 标题与移除按钮、MessageRenderer 去 onOpenFiles

**Interfaces:**
- Consumes: Task 4（`UIMessage.stockCode` / 恢复 `filePaths`）、Task 5（抽屉 testid）
- Produces: `formatReportTitle(msg: UIMessage): string`；`isExportableReport(msg: UIMessage): boolean`；`ReportNameBanner({ msg, onOpen }: { msg: UIMessage; onOpen: (msg: UIMessage) => void })`（testid `report-name-banner`）；`AllFilesBanner({ onOpen }: { onOpen: () => void })`（testid `conversation-files-banner`）

- [ ] **Step 1: 写失败测试**

`frontend/src/test/reportEntryBanners.test.tsx`：

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ReportNameBanner, AllFilesBanner, formatReportTitle, isExportableReport } from '../ReportEntryBanners'
import type { UIMessage } from '../types'

const reportMsg = (over: Partial<UIMessage>): UIMessage => ({
  id: 'r1',
  type: 'report',
  content: '',
  streaming: false,
  stockName: '贵州茅台',
  stockCode: '600519',
  filePaths: { md: '/tmp/贵州茅台_600519_x_report.md' },
  ...over,
})

describe('formatReportTitle', () => {
  it('名称+代码组合', () => {
    expect(formatReportTitle(reportMsg({}))).toBe('贵州茅台（600519）')
  })
  it('名称缺失时仅显示代码', () => {
    expect(formatReportTitle(reportMsg({ stockName: undefined }))).toBe('600519')
  })
  it('名称等于代码时不重复', () => {
    expect(formatReportTitle(reportMsg({ stockName: '600519' }))).toBe('600519')
  })
})

describe('isExportableReport', () => {
  it('已完成且 filePaths 有值 → true', () => {
    expect(isExportableReport(reportMsg({}))).toBe(true)
  })
  it('filePaths 为空对象 → false', () => {
    expect(isExportableReport(reportMsg({ filePaths: {} }))).toBe(false)
  })
  it('filePaths 值为空串 → false', () => {
    expect(isExportableReport(reportMsg({ filePaths: { md: '' } }))).toBe(false)
  })
  it('streaming 中 → false', () => {
    expect(isExportableReport(reportMsg({ streaming: true }))).toBe(false)
  })
  it('非 report 类型 → false', () => {
    expect(isExportableReport({ ...reportMsg({}), type: 'chat' } as UIMessage)).toBe(false)
  })
})

describe('ReportNameBanner / AllFilesBanner', () => {
  it('报告名横幅显示组合标题并可点击', () => {
    const msg = reportMsg({})
    const onOpen = vi.fn()
    render(<ReportNameBanner msg={msg} onOpen={onOpen} />)
    expect(screen.getByText('贵州茅台（600519）')).toBeTruthy()
    fireEvent.click(screen.getByTestId('report-name-banner'))
    expect(onOpen).toHaveBeenCalledWith(msg)
  })
  it('全部文件横幅可点击', () => {
    const onOpen = vi.fn()
    render(<AllFilesBanner onOpen={onOpen} />)
    expect(screen.getByText('全部文件')).toBeTruthy()
    fireEvent.click(screen.getByTestId('conversation-files-banner'))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})
```

`frontend/src/test/fileExportEntries.test.tsx`（App 集成，范式同 refresh-loading-skeleton.test.tsx / selectSession.test.tsx）：

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../App'

const session = {
  session_id: 's1',
  stock_code: '600519',
  stock_name: '贵州茅台',
  display_name: '贵州茅台分析',
  status: 'completed',
  created_at: '2026-07-01T00:00:00Z',
  duration_ms: 60000,
  session_type: 'analysis',
  report_markdown: '# 贵州茅台深度分析报告\n\n正文。',
  chart_data: {},
  analyst_reports: {},
  agent_process: {},
  analyst_summaries: {},
  chat_history: [{ role: 'user', content: '分析贵州茅台' }],
  pipeline_snapshot: null,
  file_paths: {
    md: '/tmp/贵州茅台_600519_20260825_report.md',
    docx: '/tmp/贵州茅台_600519_20260825_report.docx',
  },
}

function mockFetch() {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
      return Promise.resolve(new Response(JSON.stringify({ sessions: [session] }), { status: 200 }))
    }
    if (url.startsWith('/api/sessions/') && !url.endsWith('/stream')) {
      return Promise.resolve(new Response(JSON.stringify(session), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 200 }))
  }))
}

describe('文件导出入口（update-file-export-entry Task 6）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('恢复已完成报告会话：头部标题「名称（代码）」、无 open-files-banner、双横幅与顶部按钮可见、点击弹出文件列表', async () => {
    mockFetch()
    render(<App />)
    fireEvent.click(await screen.findByText('贵州茅台分析'))
    // 报告卡 h3 与报告名横幅均显示「名称（代码）」（两处），用 findAllByText
    const titles = await screen.findAllByText('贵州茅台（600519）')
    expect(titles.length).toBeGreaterThanOrEqual(2)
    expect(screen.queryByTestId('open-files-banner')).toBeNull()
    expect(screen.getByTestId('report-name-banner')).toBeTruthy()
    expect(screen.getByTestId('conversation-files-banner')).toBeTruthy()
    expect(screen.getByTestId('topbar-files-button')).toBeTruthy()

    // 点击「全部文件」横幅 → 抽屉打开且列出已生成文件
    fireEvent.click(screen.getByTestId('conversation-files-banner'))
    expect(screen.getByTestId('export-drawer')).toBeTruthy()
    expect(screen.getByTestId('download-file-md')).toBeTruthy()
  })

  it('无可导出文件（快速对话会话）不显示横幅与顶部按钮', async () => {
    // 自包含 mock：直接用 chat 会话（session_type=chat、无报告产物）
    const chatSession = {
      ...session,
      session_id: 's2',
      session_type: 'chat',
      status: 'completed',
      display_name: '茅台对话',
      stock_code: '',
      stock_name: '',
      report_markdown: '',
      file_paths: {},
    }
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
        return Promise.resolve(new Response(JSON.stringify({ sessions: [chatSession] }), { status: 200 }))
      }
      if (url.startsWith('/api/sessions/') && !url.endsWith('/stream')) {
        return Promise.resolve(new Response(JSON.stringify(chatSession), { status: 200 }))
      }
      return Promise.resolve(new Response('', { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    fireEvent.click(await screen.findByText('茅台对话'))
    await waitFor(() => expect(screen.queryByTestId('topbar-files-button')).toBeNull())
    expect(screen.queryByTestId('report-name-banner')).toBeNull()
    expect(screen.queryByTestId('conversation-files-banner')).toBeNull()
  })
})
```

（若第二用例的 `display_name` 与第一用例重复导致选定冲突，将 chat 会话 display_name 改为「茅台对话」并在 findByText 中用该名；断言目标保持三入口不出现。）

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/reportEntryBanners.test.tsx src/test/fileExportEntries.test.tsx`
Expected: FAIL（`../ReportEntryBanners` 模块不存在 / App 无新入口）→ 红

- [ ] **Step 3: 最小实现**

**创建 `frontend/src/ReportEntryBanners.tsx`：**

```tsx
import type { UIMessage } from './types'

// 报告名组合标题：名称缺失或等于代码时仅显示代码（不重复组合）
export function formatReportTitle(msg: UIMessage): string {
  const name = msg.stockName?.trim()
  const code = msg.stockCode?.trim()
  if (name && code && name !== code) return `${name}（${code}）`
  return name || code || ''
}

// 口径 B：已完成报告且 filePaths 含至少一个已生成文件
export function isExportableReport(msg: UIMessage): boolean {
  if (msg.type !== 'report' || msg.streaming) return false
  const fp = msg.filePaths || {}
  return Object.values(fp).some((p) => !!p)
}

const bannerClass =
  'w-full flex items-center gap-3 px-5 py-3 rounded-xl text-sm font-medium transition-colors hover:opacity-90'

export function ReportNameBanner({ msg, onOpen }: {
  msg: UIMessage
  onOpen: (msg: UIMessage) => void
}) {
  return (
    <button type="button" data-testid="report-name-banner" onClick={() => onOpen(msg)}
      className={bannerClass} style={{ background: 'var(--bg-base-secondary)', color: 'var(--text-default)' }}>
      <i className="fas fa-file-lines text-xs" style={{ color: 'var(--text-brand)' }}></i>
      <span className="flex-1 truncate">{formatReportTitle(msg)}</span>
      <i className="fas fa-chevron-right text-xs" style={{ color: 'var(--text-tertiary)' }}></i>
    </button>
  )
}

export function AllFilesBanner({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" data-testid="conversation-files-banner" onClick={onOpen}
      className={bannerClass} style={{ background: 'var(--bg-base-secondary)', color: 'var(--text-default)' }}>
      <i className="fas fa-folder-open text-xs" style={{ color: 'var(--text-brand)' }}></i>
      <span className="flex-1">全部文件</span>
      <i className="fas fa-chevron-right text-xs" style={{ color: 'var(--text-tertiary)' }}></i>
    </button>
  )
}
```

**`App.tsx` 修改：**

1. import：`import { ReportNameBanner, AllFilesBanner, isExportableReport, formatReportTitle } from './ReportEntryBanners'`
2. 主组件 render 前（`const messages = stream.messages` 之后）计算：

```tsx
  // 会话级导出入口：口径 B（已完成报告且 filePaths 含已生成文件）
  const exportableReports = messages.filter(isExportableReport)
  const lastExportableReport = exportableReports[exportableReports.length - 1] ?? null
```

3. 消息容器（约 700-714 行 `<div className="w-full max-w-3xl ...">`）在 `.map` 结束后、容器闭合前追加：

```tsx
              {exportableReports.map((msg) => (
                <ReportNameBanner key={`rb-${msg.id}`} msg={msg} onOpen={setDrawerMessage} />
              ))}
              {lastExportableReport && (
                <AllFilesBanner onOpen={() => setDrawerMessage(lastExportableReport!)} />
              )}
```

4. 全局顶部栏（约 691-696 行 `设置` 按钮前）追加：

```tsx
                {lastExportableReport && (
                  <button data-testid="topbar-files-button"
                    onClick={() => setDrawerMessage(lastExportableReport!)}
                    className="text-[var(--icon-secondary)] hover:text-[var(--text-default)] transition-colors text-sm">
                    <i className="fas fa-folder-open mr-1"></i>查看全部文件
                  </button>
                )}
```

5. `MessageRenderer`（1139 行）：签名去掉 `onOpenFiles`，`msg.type === 'report'` 分支改为 `return <ReportCard msg={msg} />`；主组件 712 行改为 `<MessageRenderer key={msg.id} msg={msg} />`
6. `ReportCard`（1591 行）：签名改为 `function ReportCard({ msg }: { msg: UIMessage })`；h3（1618 行）改为 `{formatReportTitle(msg)}`；删除 1623-1636 行的 `<div className="flex gap-2">…全部文件…</div>` 按钮块（header 右侧容器若因此为空则一并删除该 wrapper）

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/reportEntryBanners.test.tsx src/test/fileExportEntries.test.tsx` → PASS
Run: `cd frontend && npx vitest run src/test/reportFileDrawer.test.tsx src/test/selectSession.test.tsx src/test/refresh-loading-skeleton.test.tsx` → 既有不回退

- [ ] **Step 5: 提交**

```bash
git add frontend/src/ReportEntryBanners.tsx frontend/src/test/reportEntryBanners.test.tsx frontend/src/test/fileExportEntries.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): 文件导出改为报告名横幅+全部文件横幅+顶部栏按钮，报告头部标题含名称代码"
```

---

### Task 7: E2E report-export.spec.ts 重写并跑通

**Files:**
- Modify: `tests/e2e/playwright/tests/report-export.spec.ts`
- 参考：`tests/e2e/playwright/playwright.config.ts` 与 `playwright.timeline.config.ts`（管线 spec 由 timeline config 拉起 5175→8002 STUB_SCENARIO=pipeline 端口对；默认 config 的 testIgnore 已排除本 spec，无需改）

**Interfaces:**
- Consumes: 前端三入口 testid（`report-name-banner` / `conversation-files-banner` / `topbar-files-button` / `export-drawer` / `download-file-<fmt>`）
- Produces: 全绿 E2E（stub 管线报告完成后断言新入口与文件列表）

- [ ] **Step 1: 先运行旧 spec 确认当前基线（红/绿皆可，用于对照）**

Run: `cd tests/e2e/playwright && npx playwright test --config=playwright.timeline.config.ts report-export`
（若 config 名/命令不符，读 `package.json` scripts 与 config 文件确认管线 spec 的拉起方式）

- [ ] **Step 2: 重写 spec**

以既有 `report-export.spec.ts` 为基础重写核心流程（保留进入应用/选模式/发送的既有步骤与 240s 超时），断言改为新 UX：

```ts
    // 4. 报告完成后的稳定终态：报告卡标题出现「贵州茅台（600519）」组合
    await expect(page.getByText('贵州茅台（600519）')).toBeVisible({ timeout: 150_000 })

    // 5. 报告卡头部不再有「全部文件」导出按钮
    await expect(page.getByTestId('open-files-banner')).toHaveCount(0)

    // 6. 会话级入口：报告名横幅、全部文件横幅、顶部栏按钮均可见
    await expect(page.getByTestId('report-name-banner')).toBeVisible()
    await expect(page.getByTestId('conversation-files-banner')).toBeVisible()
    await expect(page.getByTestId('topbar-files-button')).toBeVisible()

    // 7. 点击顶部栏按钮打开抽屉，文件列表包含已生成文件（文件名含 名称_代码 前缀 + _report.md/.docx 后缀，时间戳不可固定）
    await page.getByTestId('topbar-files-button').click()
    await expect(page.getByTestId('export-drawer')).toBeVisible()
    await expect(page.getByTestId('drawer-file-list')).toBeVisible()
    await expect(page.locator('[data-testid^="download-file-"]').first()).toBeVisible()

    // 8. 关闭抽屉后经「全部文件」横幅再开一次（双入口等价）
    await page.getByTestId('drawer-close').click()
    await expect(page.getByTestId('export-drawer')).toHaveCount(0)
    await page.getByTestId('conversation-files-banner').click()
    await expect(page.getByTestId('export-drawer')).toBeVisible()
```

（保留顶部注释块并更新描述：入口从「报告头部全部文件横幅」改为「会话级报告名横幅/全部文件横幅/顶部栏按钮」；删除旧的三格式下载行断言 `download-pdf/download-docx/download-md`。）

- [ ] **Step 3: 跑通本 spec**

Run: `cd tests/e2e/playwright && npx playwright test --config=playwright.timeline.config.ts report-export`
Expected: PASS

若 stub 管线 `file_paths` 为空（报告无文件 → 口径 B 下横幅不出现）导致红：在 `src/finance_agent/export/service.py` 无问题前提下，检查 stub 场景下 `generate_file` 节点是否执行（`STUB_SCENARIO=pipeline` 的 stub 只吐 `run_deep_analysis` 工具调用，`generate_file` 是真实图节点、md 必然成功写盘）——若仍空，记录 evidence 并升级处理，不盲改断言。

- [ ] **Step 4: 提交**

```bash
git add tests/e2e/playwright/tests/report-export.spec.ts
git commit -m "test(e2e): report-export spec 重写为新三入口与文件列表行为"
```

---

### Task 8: 全量回归 + lint/类型 + 人工验证报告

**Files:**
- Create: `tests/validation/2026-08-25-update-file-export-entry-validation.md`
- 无代码改动（若回归发现缺陷，走 fix 循环）

- [ ] **Step 1: 后端全量回归**

Run: `uv run pytest -q`
Expected: 全绿（README 描述既有失败用例除外，逐条记录）

Run: `uv run ruff check` → 0 issues
Run: `uv run mypy` → 无新增错误

- [ ] **Step 2: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全绿

- [ ] **Step 3: E2E 门禁抽查**

Run: `cd tests/e2e/playwright && npx playwright test --config=playwright.timeline.config.ts report-export smoke`
Expected: 本 delta 相关 spec 全绿（其余 spec 若因基建/平台失败，记录 evidence 不记为本次回归）

- [ ] **Step 4: 人工验证报告**

按 `project-workflow.md` §3 Step 5 模板落 `tests/validation/2026-08-25-update-file-export-entry-validation.md`，覆盖：
- 报告卡头部标题显示「股票名称（股票代码）」，无导出按钮
- 分析完成后对话尾部出现报告名横幅（标题=报告名，位次在全部文件之上）与全部文件横幅
- 顶部栏出现「查看全部文件」按钮
- 点击任一入口弹出右侧文件列表（仅已生成文件，无三格式行）
- 无文件/快速对话/空状态下三入口均不出现
- 刷新后恢复会话，导出入口仍可用（file_paths 持久化生效）
- 下载文件名含「名称_代码」

- [ ] **Step 5: 提交验证报告并收尾检查**

```bash
git add tests/validation/2026-08-25-update-file-export-entry-validation.md
git commit -m "docs(validation): update-file-export-entry 人工验证报告"
```

（提交后按 `finishing-a-development-branch` 决策合并方式，交回用户定夺，不擅自 push/merge。）