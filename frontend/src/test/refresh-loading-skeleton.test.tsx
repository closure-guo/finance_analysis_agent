import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'

// 刷新空态闪感知：刷新页面后，/api/sessions 与 selectSession 恢复需要时间
// （后端 uvicorn 启动 / 分析运行期事件循环阻塞会进一步拉长）。
// 此窗口内：
//   - 侧边栏 sessions=[] 直接渲染「暂无历史会话」→ 用户感知「历史会话消失」
//   - 主区 currentSessionId 已从 localStorage 恢复但 messages 尚为空，
//     appState='empty' → 闪首页空态落地（特性卡片）→ 用户感知「会话内容消失」
//
// 修复标准（UX 骨架，不改变恢复逻辑）：
// 1. /api/sessions 首次成功前，侧边栏显示加载骨架（sidebar-skeleton），
//    不显示「暂无历史会话」。
// 2. 有持久化会话且恢复未完成时，主区显示「恢复会话中」（restoring-state），
//    不闪首页空态（特性卡片「AI 驱动的 A 股投研分析系统」）。
// 3. 加载/恢复完成后正常显示会话列表与内容（不回归）。

const runningSession = {
  session_id: 'sess-running',
  stock_code: '300308',
  stock_name: '中际旭创',
  display_name: '中际旭创 深度分析',
  status: 'running',
  session_type: 'analysis',
  created_at: '2026-08-03T10:00:00',
}

// 构造一个 /api/sessions 可手动控制 resolve 时机的 fetch mock，
// 其余端点立即返回空 200，制造「会话列表加载中」窗口
function buildDeferredFetchMock() {
  let resolveSessions: ((r: Response) => void) | null = null
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
      return new Promise<Response>((resolve) => { resolveSessions = resolve })
    }
    if (url.startsWith('/api/sessions/') && !url.endsWith('/stream')) {
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 200 }))
  })
  return {
    fetchMock,
    resolveSessions: (sessions: unknown[]) =>
      resolveSessions?.(new Response(JSON.stringify({ sessions }), { status: 200 })),
  }
}

describe('刷新加载骨架（消除空态闪感知）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('会话列表加载完成前，侧边栏显示骨架而非「暂无历史会话」', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    // 有持久化会话 → 触发恢复路径
    localStorage.setItem('fa_current_session_id', 'sess-running')
    const { fetchMock, resolveSessions } = buildDeferredFetchMock()
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 加载窗口内：显示骨架，不显示空态文案
    expect(screen.getByTestId('sidebar-skeleton')).toBeInTheDocument()
    expect(screen.queryByText('暂无历史会话')).not.toBeInTheDocument()

    // 列表返回后：骨架消失，会话出现
    resolveSessions([runningSession])
    await waitFor(() => {
      expect(screen.queryByTestId('sidebar-skeleton')).not.toBeInTheDocument()
    }, { timeout: 10000 })
    await waitFor(() => {
      expect(screen.getByText('中际旭创 深度分析')).toBeInTheDocument()
    }, { timeout: 10000 })
  })

  it('有持久化会话且恢复未完成时，主区显示「恢复会话中」而非闪首页空态', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    localStorage.setItem('fa_current_session_id', 'sess-running')
    const { fetchMock, resolveSessions } = buildDeferredFetchMock()
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 恢复未完成：主区显示恢复指示，不闪首页空态落地
    expect(screen.getByTestId('restoring-state')).toBeInTheDocument()
    expect(screen.queryByText('AI 驱动的 A 股投研分析系统')).not.toBeInTheDocument()

    // 恢复推进后（列表返回），不再停留恢复指示
    resolveSessions([runningSession])
    await waitFor(() => {
      expect(screen.queryByTestId('restoring-state')).not.toBeInTheDocument()
    }, { timeout: 10000 })
  })

  it('无持久化会话时，加载窗口内主区仍直接显示空态首页（不回归）', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    // 不设置 fa_current_session_id → bootRestoring=false
    const { fetchMock } = buildDeferredFetchMock()
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 即使会话列表仍在加载，主区也应直接是空态首页，而非恢复指示
    expect(screen.getByText('AI 驱动的 A 股投研分析系统')).toBeInTheDocument()
    expect(screen.queryByTestId('restoring-state')).not.toBeInTheDocument()
  })
})
