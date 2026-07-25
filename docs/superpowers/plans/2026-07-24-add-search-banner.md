# add-search-banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 启用 Kimi-style 搜索横幅，使快速模式和深度模式澄清阶段的搜索状态与结果对用户可见且可展开。

**Architecture:** 提取 SearchBanner 为独立组件并支持 searching/done/error 三态；在 MessageRenderer 的 chat 分支中渲染 SearchBanner；深度模式 search_result 事件从 attachToolResult（ToolCallBanner 摘要）改为设置 searchStatus/searchResults（独立搜索横幅）。

**Tech Stack:** React 18, TypeScript, Vite, vitest + @testing-library/react（新增）, Playwright Python（E2E）

## Global Constraints

- 变量命名使用 camelCase
- 代码注释使用中文
- E2E 测试禁止使用 mock 数据，必须通过前端模拟用户真实输入
- 没有先写失败测试的代码，删除重写
- delta spec 来源：openspec/changes/add-search-banner/specs/frontend/spec.md

---

### Task 1: 搭建前端测试框架

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/package.json`
- Test: `frontend/src/test/smoke.test.tsx`

**Interfaces:**
- Produces: vitest 配置 + `npm run test` 脚本，供后续 Task 使用

- [ ] **Step 1: 安装测试依赖**

```bash
cd frontend && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @testing-library/user-event
```

- [ ] **Step 2: 创建 vitest 配置**

Create `frontend/vitest.config.ts`:

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
```

- [ ] **Step 3: 创建 setup 文件**

Create `frontend/src/test/setup.ts`:

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 4: 添加 test 脚本到 package.json**

Modify `frontend/package.json` scripts 部分添加:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 5: 写冒烟测试验证框架工作**

Create `frontend/src/test/smoke.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'

describe('vitest smoke test', () => {
  it('框架正常工作', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd frontend && npx vitest run`
Expected: 1 passed

- [ ] **Step 7: 提交**

```bash
git add frontend/vitest.config.ts frontend/src/test/ frontend/package.json frontend/package-lock.json
git commit -m "test: 搭建前端 vitest + @testing-library/react 测试框架 (#add-search-banner)"
```

---

### Task 2: 提取并重写 SearchBanner 组件（TDD）

**Files:**
- Create: `frontend/src/SearchBanner.tsx`
- Create: `frontend/src/test/SearchBanner.test.tsx`
- Modify: `frontend/src/App.tsx`（移除旧 SearchBanner 定义，导入新的）
- Modify: `frontend/src/App.tsx`（MessageRenderer chat 分支渲染 SearchBanner）

**Interfaces:**
- Produces: `SearchBanner` 组件，props: `{ status: 'searching' | 'done' | 'error'; query?: string; results?: Array<{ title: string; url: string; content: string }> }`

- [ ] **Step 1: 写失败测试 - 搜索中状态**

Create `frontend/src/test/SearchBanner.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SearchBanner } from '../SearchBanner'

describe('SearchBanner', () => {
  it('搜索中状态显示"正在搜索：{query}"', () => {
    render(<SearchBanner status="searching" query="茅台 财报" />)
    expect(screen.getByText(/正在搜索/)).toBeInTheDocument()
    expect(screen.getByText(/茅台 财报/)).toBeInTheDocument()
  })

  it('搜索完成显示"搜索了 N 个网页"', () => {
    const results = [
      { title: '茅台年报', url: 'https://example.com/1', content: '摘要1' },
      { title: '茅台季报', url: 'https://example.com/2', content: '摘要2' },
    ]
    render(<SearchBanner status="done" results={results} />)
    expect(screen.getByText(/搜索了/)).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText(/个网页/)).toBeInTheDocument()
  })

  it('搜索完成可展开查看结果列表', () => {
    const results = [
      { title: '茅台年报', url: 'https://example.com/1', content: '摘要内容' },
    ]
    render(<SearchBanner status="done" results={results} />)
    // 折叠状态下结果不可见
    expect(screen.getByText('茅台年报')).not.toBeVisible()
    // 点击展开
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText('茅台年报')).toBeVisible()
    expect(screen.getByText('摘要内容')).toBeVisible()
  })

  it('搜索失败显示错误状态', () => {
    render(<SearchBanner status="error" />)
    expect(screen.getByText(/搜索失败/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd frontend && npx vitest run src/test/SearchBanner.test.tsx`
Expected: FAIL - "Cannot find module '../SearchBanner'"

- [ ] **Step 3: 实现 SearchBanner 组件**

Create `frontend/src/SearchBanner.tsx`:

```tsx
import { useState } from 'react'

// 搜索结果条目
interface SearchResult {
  title: string
  url: string
  content: string
}

// SearchBanner 组件支持三态：搜索中 / 完成 / 失败
interface SearchBannerProps {
  status: 'searching' | 'done' | 'error'
  query?: string
  results?: SearchResult[]
}

// 从 URL 提取域名
function getDomain(url: string): string {
  try {
    return new URL(url).hostname.replace('www.', '')
  } catch {
    return url
  }
}

// 从 URL 生成 favicon 地址
function getFavicon(url: string): string {
  try {
    const domain = new URL(url).hostname
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
  } catch {
    return ''
  }
}

export function SearchBanner({ status, query, results = [] }: SearchBannerProps) {
  const [expanded, setExpanded] = useState(false)

  // 搜索中：脉冲动画 + "正在搜索：{query}"
  if (status === 'searching') {
    return (
      <div className="mb-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'var(--bg-overlay-l1)' }}>
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }}></span>
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }}></span>
          </span>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            正在搜索
            {query && <span className="ml-1.5" style={{ color: 'var(--text-tertiary)' }}>：{query}</span>}
          </span>
        </div>
      </div>
    )
  }

  // 搜索失败
  if (status === 'error') {
    return (
      <div className="mb-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'var(--bg-overlay-l1)' }}>
          <i className="fas fa-exclamation-circle text-xs flex-shrink-0" style={{ color: 'var(--status-error-default)' }}></i>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>搜索失败</span>
        </div>
      </div>
    )
  }

  // 搜索完成：可折叠的结果列表
  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left"
        style={{ background: 'var(--bg-overlay-l1)' }}
      >
        <i className="fas fa-search text-xs flex-shrink-0" style={{ color: 'var(--status-success-default)' }}></i>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          搜索了
          <span className="mx-1 font-medium" style={{ color: 'var(--text-default)' }}>{results.length}</span>
          个网页
          {query && <span className="ml-1.5" style={{ color: 'var(--text-tertiary)' }}>· {query}</span>}
        </span>
        <i className={`fas fa-chevron-${expanded ? 'down' : 'right'} text-[10px] ml-auto transition-transform`} style={{ color: 'var(--text-tertiary)' }}></i>
      </button>
      <div
        className="overflow-hidden transition-all duration-300 ease-out"
        style={{ maxHeight: expanded ? '400px' : '0px', opacity: expanded ? 1 : 0 }}
      >
        <div className="space-y-2 mt-1 max-h-[400px] overflow-y-auto pr-1">
          {results.map((r, i) => (
            <a
              key={i}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block px-3 py-2 rounded-lg border transition-all"
              style={{ background: 'var(--bg-base-secondary)', borderColor: 'var(--border-neutral-l1)' }}
            >
              <div className="flex items-start gap-2">
                <img
                  src={getFavicon(r.url)}
                  alt=""
                  className="w-4 h-4 rounded-sm flex-shrink-0 mt-0.5"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>{i + 1}</span>
                    <span className="text-xs truncate font-medium" style={{ color: 'var(--text-default)' }}>{r.title}</span>
                  </div>
                  <p className="text-[11px] mt-1 line-clamp-2 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{r.content}</p>
                  <span className="text-[10px] truncate block mt-1" style={{ color: 'var(--text-tertiary)' }}>{getDomain(r.url)}</span>
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd frontend && npx vitest run src/test/SearchBanner.test.tsx`
Expected: 4 passed

- [ ] **Step 5: 从 App.tsx 移除旧 SearchBanner，导入新组件**

在 `frontend/src/App.tsx` 顶部添加导入:

```tsx
import { SearchBanner } from './SearchBanner'
```

删除 App.tsx 中的旧 `SearchBanner` 函数定义（约 1543-1610 行）和顶部的 `getDomain`、`getFavicon` 工具函数（如果仅被 SearchBanner 使用则移除，若 ReportCard 也使用则保留）。

**注意**：`getDomain` 和 `getFavicon` 在 ReportCard 的信源卡片中也使用了（约 1937-1975 行），所以保留 App.tsx 中的这两个函数，SearchBanner.tsx 中有自己独立的副本。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/SearchBanner.tsx frontend/src/test/SearchBanner.test.tsx frontend/src/App.tsx
git commit -m "refactor: 提取 SearchBanner 为独立组件，支持 searching/done/error 三态 (#add-search-banner)"
```

---

### Task 3: 快速模式渲染 SearchBanner

**Files:**
- Modify: `frontend/src/App.tsx` - MessageRenderer 的 chat 分支（约 1340-1382 行）

**Interfaces:**
- Consumes: `SearchBanner` 组件（Task 2 产出）
- Consumes: `UIMessage.searchStatus` / `searchResults` / `searchQuery`（types.ts 已定义）

- [ ] **Step 1: 在 MessageRenderer chat 分支渲染 SearchBanner**

在 `frontend/src/App.tsx` 的 `MessageRenderer` 函数中，`msg.type === 'chat'` 分支内，在 `ToolCallBanner` 之前添加 SearchBanner 渲染:

```tsx
// 在 {msg.toolCalls && msg.toolCalls.length > 0 && (<ToolCallBanner ... />)} 之前添加：
{msg.searchStatus && (
  <SearchBanner
    status={msg.searchStatus}
    query={msg.searchQuery}
    results={msg.searchResults}
  />
)}
```

- [ ] **Step 2: 验证快速模式搜索横幅渲染**

前置条件：后端运行在 `http://localhost:8000`，前端运行在 `http://localhost:5173`，已配置有效 API Key。

Run: `cd frontend && npx vitest run`（确认组件测试仍通过）
Then 手动验证：打开 `http://localhost:5173`，切换到快速模式，输入"茅台怎么样"并发送，观察搜索横幅是否显示"正在搜索"然后变为"搜索了 N 个网页"。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.tsx
git commit -m "feat: 快速模式渲染 SearchBanner，搜索状态和结果对用户可见 (#add-search-banner)"
```

---

### Task 4: 深度模式搜索横幅

**Files:**
- Modify: `frontend/src/App.tsx` - startAnalysis 中的 search_result 事件处理（约 443-448 行）
- Modify: `frontend/src/App.tsx` - startAnalysis 中添加 search_start 事件处理

**Interfaces:**
- Consumes: `ensureAssistantMsg()` 函数（startAnalysis 内部）
- Produces: 深度模式澄清阶段的搜索以独立搜索横幅展示

- [ ] **Step 1: 修改 search_result 事件处理**

在 `frontend/src/App.tsx` 的 `startAnalysis` 函数中，找到 search_result 事件处理（约 443 行）:

旧代码:
```tsx
if (event.type === 'search_result') {
  const results = event.results || []
  const count = event.count || results.length
  const summary = results.slice(0, 3).map((r: any) => r?.title).filter(Boolean).join('、')
  attachToolResult(ensureAssistantMsg(), ['web_search', 'batch_web_search'], `找到 ${count} 条结果：${summary}`)
  continue
}
```

新代码:
```tsx
if (event.type === 'search_result') {
  const results = event.results || []
  const chatId = ensureAssistantMsg()
  setMessages(prev => prev.map(m =>
    m.id === chatId
      ? { ...m, searchStatus: 'done' as const, searchResults: results }
      : m
  ))
  continue
}
```

- [ ] **Step 2: 添加 search_start 事件处理**

在 search_result 事件处理之前，添加 search_start 处理:

```tsx
if (event.type === 'search_start') {
  const chatId = ensureAssistantMsg()
  setMessages(prev => prev.map(m =>
    m.id === chatId
      ? { ...m, searchStatus: 'searching' as const, searchQuery: event.query }
      : m
  ))
  continue
}
```

- [ ] **Step 3: 验证深度模式搜索横幅**

前置条件：后端运行在 `http://localhost:8000`，前端运行在 `http://localhost:5173`，已配置有效 API Key。

手动验证：打开 `http://localhost:5173`，深度模式下输入含"推荐"或"热点"等词的查询（触发 web_search），观察澄清阶段是否显示独立搜索横幅（而非 ToolCallBanner 中的"找到 N 条结果"摘要）。

- [ ] **Step 4: 运行全部前端测试**

Run: `cd frontend && npx vitest run`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.tsx
git commit -m "feat: 深度模式澄清阶段搜索结果以独立搜索横幅展示 (#add-search-banner)"
```

---

### Task 5: E2E 验证与人工验证报告

**Files:**
- Create: `tests/e2e/test_search_banner.py`
- Create: `tests/validation/search-banner-validation.md`

- [ ] **Step 1: 写 E2E 测试**

Create `tests/e2e/test_search_banner.py`:

```python
"""E2E 测试：搜索横幅在快速模式中的渲染。

前置条件：后端运行在 http://localhost:8000，前端运行在 http://localhost:5173。
禁止使用 mock 数据，通过前端模拟用户真实输入验证完整链路。
"""
import pytest


def test_quick_mode_search_banner(page):
    """快速模式下搜索横幅可见且可展开。"""
    page.goto("http://localhost:5173")
    page.wait_for_selector("textarea")

    # 通过 localStorage 设置 API Key（避免每次手动配置）
    page.evaluate("localStorage.setItem('fa_api_key', document.querySelector('[data-api-key]')?.value || '')")

    # 切换到快速模式
    page.click("button:has-text('模式')")
    page.click("button:has-text('快速模式')")

    # 输入问题并发送
    page.fill("textarea", "茅台怎么样")
    page.press("textarea", "Enter")

    # 等待搜索横幅出现（正在搜索 或 搜索了 N 个网页）
    page.wait_for_selector("text=/正在搜索|搜索了/", timeout=30000)

    # 验证搜索横幅可见
    banner = page.locator("text=/正在搜索|搜索了/")
    assert banner.is_visible()
```

- [ ] **Step 2: 运行 E2E 测试**

前置条件：启动前后端服务（`docker compose up -d` 或分别启动）。

Run: `uv run pytest tests/e2e/test_search_banner.py -v -s`
Expected: PASSED

- [ ] **Step 3: 写人工验证报告**

Create `tests/validation/search-banner-validation.md`:

```markdown
# 搜索横幅人工验证报告

**日期**: 2026-07-25
**Delta 提案**: add-search-banner
**验证人**: [填写]

## 验证项

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | 快速模式：搜索中显示"正在搜索：{query}"脉冲动画 | □ 通过 □ 不通过 |
| 2 | 快速模式：搜索完成显示"搜索了 N 个网页" | □ 通过 □ 不通过 |
| 3 | 快速模式：点击展开查看网页列表（标题+摘要+域名+favicon） | □ 通过 □ 不通过 |
| 4 | 快速模式：搜索失败显示错误状态 | □ 通过 □ 不通过 |
| 5 | 深度模式：澄清阶段搜索以独立搜索横幅展示（非 ToolCallBanner 摘要） | □ 通过 □ 不通过 |
| 6 | 搜索横幅与思考横幅/工具调用横幅视觉协调，不重叠 | □ 通过 □ 不通过 |

## 备注

[填写观察到的异常或建议]
```

- [ ] **Step 4: 回填 tasks.md 勾选**

Modify `openspec/changes/add-search-banner/tasks.md`，将所有 `- [ ]` 改为 `- [x]`。

- [ ] **Step 5: 提交**

```bash
git add tests/e2e/test_search_banner.py tests/validation/search-banner-validation.md openspec/changes/add-search-banner/tasks.md
git commit -m "test: 添加搜索横幅 E2E 测试与人工验证报告 (#add-search-banner)"
```
