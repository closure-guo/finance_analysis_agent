# add-download-center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增下载管理页（/downloads）与后端文件列表/删除接口，侧边栏入口，统一交互动效。

**Architecture:** 后端在现有 `/api/files/<file_name>` 命名空间上扩展 `GET /api/files`（列表）与 `DELETE /api/files/<file_name>`，三类文件接口共享路径安全工具函数；前端以轻量 pathname 路由（pushState + popstate，不引入 react-router）挂载 `pages/downloads/`，列表动效用 framer-motion（stagger 入场 + AnimatePresence 删除收起），toast 复用 Task refactor-ui-design-system 引入的 sonner。

**Tech Stack:** FastAPI TestClient（后端 TDD）、framer-motion、sonner、Tailwind 语义令牌、vitest + testing-library、Playwright（E2E 门禁）。

## Global Constraints

- 不改变 `POST /api/export` 契约与 `file_paths` 四键契约；不做预览/批量操作；不落库（实时扫描）
- 文件格式白名单：`.docx/.pptx/.pdf/.md`（大小写不敏感）；目录不存在/为空 → 空数组
- 路径安全：文件名接口（下载/删除）统一 `resolve_reports_path`，穿越请求返回 400/404 且无副作用
- 动效时长三档 150/200/300ms，ease-out 入场 / ease-in-out 切换；`prefers-reduced-motion` 全部禁用
- 删除为乐观 UI：确认 → 行收起动画 → 调接口；失败回滚 + toast 报错
- 列表首次进入 stagger（30ms 间隔，fade + translateY(8px)→0，200ms）；筛选切换不重播
- 前置依赖：refactor-ui-design-system 已实施（sonner/`components/ui/`/语义令牌可用）
- OpenSpec change：`openspec/changes/add-download-center/`（校验已通过）

---

### Task 1: 后端——路径安全工具 + 列表接口 + 删除接口（TDD）

**Files:**
- Modify: `src/finance_agent/api.py`（REPORTS_DIR 定义处 ~L99 附近加工具函数；文件接口区 ~L1973 改造）
- Test: `tests/test_api_files.py`（新建）

**Interfaces:**
- Consumes: `api.REPORTS_DIR`（`Path("reports")`，L99）
- Produces: `resolve_reports_path(file_name: str) -> Path`（越界抛 `HTTPException(400)`）；`GET /api/files` → `list[dict]`（键：`file_name: str, file_type: str, size_bytes: int, created_at: int` 毫秒时间戳，按 created_at 倒序）；`DELETE /api/files/{file_name}` → `{"deleted": "<name>"}`。

- [ ] **Step 1: 写失败测试 `tests/test_api_files.py`**

```python
"""add-download-center：文件列表/删除接口测试。"""
from fastapi.testclient import TestClient

from finance_agent.api import app


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr("finance_agent.api.REPORTS_DIR", tmp_path)
    return TestClient(app)


def test_list_files_empty_dir(monkeypatch, tmp_path):
    resp = _client(monkeypatch, tmp_path).get("/api/files")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_files_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("finance_agent.api.REPORTS_DIR", tmp_path / "nope")
    resp = TestClient(app).get("/api/files")
    assert resp.status_code == 200 and resp.json() == []


def test_list_files_sorted_and_meta(monkeypatch, tmp_path):
    (tmp_path / "a.docx").write_bytes(b"x" * 204800)
    (tmp_path / "b.pptx").write_bytes(b"y")
    import os
    past, recent = 1_000_000, 2_000_000
    os.utime(tmp_path / "a.docx", (past / 1000,) * 2)
    os.utime(tmp_path / "b.pptx", (recent / 1000,) * 2)
    (tmp_path / "chart.png").write_bytes(b"png")
    (tmp_path / "tmp.tmp").write_bytes(b"t")
    resp = _client(monkeypatch, tmp_path).get("/api/files")
    items = resp.json()
    assert [i["file_name"] for i in items] == ["b.pptx", "a.docx"]
    assert items[0] == {"file_name": "b.pptx", "file_type": "pptx",
                        "size_bytes": 1, "created_at": items[0]["created_at"]}
    assert isinstance(items[0]["created_at"], int) and items[0]["created_at"] > 0


def test_delete_existing_file(monkeypatch, tmp_path):
    (tmp_path / "a.docx").write_bytes(b"x")
    c = _client(monkeypatch, tmp_path)
    assert c.delete("/api/files/a.docx").status_code == 200
    assert c.get("/api/files").json() == []


def test_delete_missing_file_404(monkeypatch, tmp_path):
    assert _client(monkeypatch, tmp_path).delete("/api/files/nonexistent.docx").status_code == 404


def test_path_traversal_rejected(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    for url in ("/api/files/..%2F..%2F.env", "/api/files/%2e%2e%2fsecret.md"):
        assert c.delete(url).status_code in (400, 404)
    assert c.get("/api/files/..%2F..%2F.env").status_code in (400, 404)
```

- [ ] **Step 2: 运行确认失败** `uv run pytest tests/test_api_files.py -v`（列表 404、删除 405/404）。
- [ ] **Step 3: 实现**——`api.py` 在 `REPORTS_DIR` 定义后加：

```python
EXPORT_EXTENSIONS = {".docx", ".pptx", ".pdf", ".md"}


def resolve_reports_path(file_name: str) -> Path:
    """将文件名解析到 REPORTS_DIR 内的绝对路径；越界（路径穿越）抛 400。

    三类文件接口（下载/列表/删除）共用：取 basename 剥离目录成分后，
    resolve 并校验父目录必须是 REPORTS_DIR 本身。
    """
    safe_name = Path(file_name).name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="非法文件名")
    reports_root = REPORTS_DIR.resolve()
    file_path = (reports_root / safe_name).resolve()
    if file_path.parent != reports_root:
        raise HTTPException(status_code=400, detail="非法文件名")
    return file_path
```

  并新增两条路由（**必须声明在 `GET /api/files/{filename}` 之前**）：

```python
@app.get("/api/files")
async def list_export_files():
    """扫描 REPORTS_DIR 返回导出文件元信息，按创建时间倒序。"""
    if not REPORTS_DIR.exists():
        return []
    items = []
    for entry in REPORTS_DIR.iterdir():
        if not entry.is_file() or entry.suffix.lower() not in EXPORT_EXTENSIONS:
            continue
        st = entry.stat()
        items.append({
            "file_name": entry.name,
            "file_type": entry.suffix.lower().lstrip("."),
            "size_bytes": st.st_size,
            "created_at": int(st.st_ctime * 1000),
        })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items


@app.delete("/api/files/{filename}")
async def delete_export_file(filename: str):
    file_path = resolve_reports_path(filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"deleted": file_path.name}
```

  并把既有 `download_file` 的 safe_name/file_path 两行替换为 `file_path = resolve_reports_path(filename)`（下载对穿越现在返回 400，符合 spec「400 或 404」）。

- [ ] **Step 4:** `uv run pytest tests/test_api_files.py tests/test_session_file_paths.py tests/export/ -v` 全绿；`uv run ruff check && uv run mypy` 通过。
- [ ] **Step 5:** Commit `feat(api): 文件列表/删除接口 + 三类文件接口统一路径安全（add-download-center 1.1-1.3）`

### Task 2: 前端——路由与下载管理页骨架 + 列表行

**Files:**
- Create: `frontend/src/route.ts`（`usePathname()` + `navigate()`）
- Create: `frontend/src/pages/downloads/DownloadCenter.tsx`、`FileRow.tsx`
- Modify: `frontend/src/App.tsx`（pathname 分流）、`frontend/src/types.ts`（`ExportFileInfo`）

**Interfaces:**
- Produces: `usePathname(): string`、`navigate(to: string): void`（pushState + PopStateEvent）；`type ExportFileInfo = { file_name: string; file_type: 'docx'|'pptx'|'pdf'|'md'; size_bytes: number; created_at: number }`；`DownloadCenter({ onBack }: { onBack: () => void })`；`FileRow({ file, onDownload, onDelete }: ...)`。
- 约束：`/downloads` 直达/刷新可渲染（nginx `try_files` 已就绪，vite dev 自带 fallback）；侧边栏在下载页照常显示，折叠状态保持。

- [ ] **Step 1: 写失败测试 `frontend/src/test/downloads/downloadCenter.test.tsx`**——mock fetch 返回两条记录，断言：渲染行数/图标/大小「1.5 MB」/昨日文件显示 `YYYY-MM-DD`、当日文件显示 `HH:mm`；侧边栏入口存在且点击后 `window.location.pathname === '/downloads'`（沿用 `renderApp()` 模式，参考 `frontend/src/test/fileExportEntries.test.tsx` 的 App 级渲染 + fetch stub 写法）。
- [ ] **Step 2: 运行确认失败**（模块不存在）。
- [ ] **Step 3: 实现 `route.ts`**：

```ts
import { useEffect, useState } from 'react'

export function usePathname(): string {
  const [pathname, setPathname] = useState(() => window.location.pathname)
  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  return pathname
}

export function navigate(to: string): void {
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
```

  `DownloadCenter` 骨架：`useEffect` 内 `fetch('/api/files')`；loading→骨架屏（`animate-pulse` 行）；非 2xx→`toast.error('文件列表加载失败')` 且**不**显示空态；`[]`→空态（占位图形 + 「暂无导出文件」+ 「返回聊天」按钮调 `onBack`）；标题栏固定，列表区内部滚动（`flex-1 overflow-y-auto`）。`FileRow`：`formatBytes`（<1MB 显 KB 一位小数，否则 MB）、`formatFileTime`（当日 HH:mm，否则 YYYY-MM-DD）、`FILE_ICONS` 映射四格式不同配色（lucide `FileText/FilePresentation?`——用 fa 图标沿用 ReportFileDrawer 的 `fa-file-word` 系保持一致）、删除按钮 `opacity-0 group-hover:opacity-100 transition-opacity`。
- [ ] **Step 4:** `App.tsx` 根组件加 `const pathname = usePathname()`，`pathname === '/downloads'` 时主区域渲染 `<DownloadCenter onBack={() => navigate('/')} />`（Sidebar 与折叠逻辑不动）；Sidebar 底部加「下载管理」入口（`fa-download` 图标 + 文字，`data-testid="sidebar-downloads"`，onClick `navigate('/downloads')`）。
- [ ] **Step 5:** `npm test` 全绿（新测试过 + 旧测试无修改）；Commit `feat(frontend): /downloads 页面骨架与列表行 + 侧边栏入口（add-download-center 2.1/2.2/2.6）`

### Task 3: 搜索/筛选 + 下载/删除交互

**Files:**
- Modify: `frontend/src/pages/downloads/DownloadCenter.tsx`、`frontend/src/pages/downloads/FileRow.tsx`
- Test: `frontend/src/test/downloads/interactions.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `DELETE /api/files/<name>`；Task 3(refactor) 的 `Button/Dialog/Sonner`。
- Produces: 过滤状态 `search: string`、`typeTab: 'all'|'docx'|'pptx'|'pdf'|'md'`（叠加过滤）；`handleDownload(file)`（`<a download>` 触发 + loading 态 + `toast.success('已开始下载')`）；`handleDelete(file)`（确认 Dialog → 乐观移除 → `fetch(DELETE)` → 4xx/5xx 回滚该行 + `toast.error('删除失败')`）。

- [ ] **Step 1: 写失败测试**——搜索「茅台」+ Word tab 只剩 `茅台分析报告.docx`；删除取消不发请求（fetch mock 计数为 0）；确认 + 500 → 行恢复 + 错误 toast（`toast` 用 vi.mock('sonner') 断言）；确认 + 200 → 行消失。
- [ ] **Step 2: 确认失败后实现**：搜索框用 `Input`；类型 tab 用一排 `Button variant={active?'secondary':'ghost'} size="sm"`；下载按钮 loading 态（图标换 `fa-circle-notch fa-spin` + disabled）；删除确认用 `Dialog`（`data-testid="delete-confirm"`，确认/取消钮）。乐观删除：`setFiles(prev => prev.filter(...))`，失败时以原 `files` 引用恢复该项并按 `created_at` 重新插入正确位置。
- [ ] **Step 3:** `npm test` 全绿；Commit `feat(frontend): 下载管理搜索筛选与下载/删除交互（add-download-center 2.3/2.4）`

### Task 4: 动效（framer-motion）

**Files:**
- Modify: `frontend/package.json`（`npm install framer-motion`）、`DownloadCenter.tsx`、`FileRow.tsx`
- Test: `frontend/src/test/downloads/motion.test.tsx`

- [ ] **Step 1: 写失败测试**——mock `useReducedMotion` 返回 true 时，行元素不带 framer-motion 动画 props（`initial` 为 false）；列表容器 `data-testid="file-list"` 首挂载存在。
- [ ] **Step 2: 实现**：容器 `<motion.ul initial="hidden" animate="show" variants={{show:{transition:{staggerChildren:0.03}}}}>`；行 `variants={{hidden:{opacity:0,y:8},show:{opacity:1,y:0,transition:{duration:0.2,ease:'easeOut'}}}}`；**stagger 只在首挂载播放**：把 variants 放在首挂载后条件渲染的外层（`const [entered, setEntered] = useState(false)` + `useEffect(()=>setEntered(true),[])`，筛选后的重渲染不再以 `initial="hidden"` 播放——用 `key` 不变 + `initial={entered ? false : 'hidden'}`）；删除行用 `<AnimatePresence>` + `exit={{height:0,opacity:0,transition:{duration:0.2,easeInOut}}}`（行外层包 `overflow-hidden` 的 motion.div）；全部动效包 `useReducedMotion()` 分支（true 时 `initial={false}` 且 exit 用无动画即时移除）。
- [ ] **Step 3:** `npm test` 全绿；Commit `feat(frontend): 下载管理 stagger 入场/删除收起动效 + reduced-motion 降级（add-download-center 3.1-3.3）`

### Task 5: 验证与门禁

- [ ] **Step 1:** 后端 `uv run pytest && uv run ruff check && uv run mypy`；前端 `cd frontend && npm test && npm run build`。
- [ ] **Step 2:** E2E：新建 `tests/e2e/playwright/tests/downloads.spec.ts`——覆盖：侧边栏入口跳转 `/downloads`、刷新保持路由、空态显示与「返回聊天」回跳（stub 后端 `REPORTS_DIR` 为空仓目录，天然空态；删除回滚等副作用路径由组件测试覆盖，E2E 不做文件预埋）。运行默认门禁全绿。
- [ ] **Step 3:** 前后端重建，人工验证（中文文件名下载、删除回滚、空态、动效降级），报告落 `tests/validation/2026-08-29-add-download-center-validation.md`。
- [ ] **Step 4:** 勾选 `openspec/changes/add-download-center/tasks.md`；archive 走 openspec-archive-change（人工验证签字后）。
