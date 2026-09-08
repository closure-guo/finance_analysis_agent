// add-collapsible-sidebar Task 2.2/2.3/3.1 组件测试：
// 折叠切换（按钮 + Ctrl/Cmd+B）、状态持久化、收起态新建会话可用、
// 会话项「···」菜单（重命名原地输入 / 删除二次确认）。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'

const SESSIONS = {
  s1: {
    meta: { session_id: 's1', stock_code: '600449', stock_name: '宁夏建材', display_name: '宁夏建材', status: 'completed', created_at: '2026-08-30T00:00:00Z', duration_ms: 1, session_type: 'chat' },
    detail: {
      session_id: 's1', stock_code: '600449', stock_name: '宁夏建材', display_name: '宁夏建材', status: 'completed',
      created_at: '2026-08-30T00:00:00Z', duration_ms: 1, report_markdown: '', chart_data: null,
      analyst_reports: {}, agent_process: {}, analyst_summaries: {},
      chat_history: [{ role: 'user', content: '你好', ts: '2026-08-30T00:00:00Z' }],
      pipeline_snapshot: null, last_seq: 0,
    },
  },
  s2: {
    meta: { session_id: 's2', stock_code: '600519', stock_name: '贵州茅台', display_name: '贵州茅台', status: 'completed', created_at: '2026-08-30T01:00:00Z', duration_ms: 1, session_type: 'chat' },
    detail: {
      session_id: 's2', stock_code: '600519', stock_name: '贵州茅台', display_name: '贵州茅台', status: 'completed',
      created_at: '2026-08-30T01:00:00Z', duration_ms: 1, report_markdown: '', chart_data: null,
      analyst_reports: {}, agent_process: {}, analyst_summaries: {},
      chat_history: [{ role: 'user', content: '你好', ts: '2026-08-30T01:00:00Z' }],
      pipeline_snapshot: null, last_seq: 0,
    },
  },
}

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'
    if (url === '/api/sessions' && method === 'GET') {
      return new Response(JSON.stringify({ sessions: [SESSIONS.s1.meta, SESSIONS.s2.meta] }), { status: 200 })
    }
    // PATCH：真实更新 stub 数据（renameSession 后 loadSessions 会重拉列表）
    if (url.startsWith('/api/sessions/') && method === 'GET') {
      const id = url.split('/').pop()
      const s = SESSIONS[id as keyof typeof SESSIONS]
      return new Response(JSON.stringify(s?.detail ?? {}), { status: 200 })
    }
    if (url.startsWith('/api/sessions/') && method === 'PATCH') {
      const id = url.split('/').pop()
      const body = JSON.parse((init?.body as string) || '{}')
      const s = SESSIONS[id as keyof typeof SESSIONS]
      if (s) (s.meta as { display_name: string }).display_name = body.display_name
      return new Response(JSON.stringify({ ok: true }), { status: 200 })
    }
    if (url.startsWith('/api/sessions/') && method === 'DELETE') {
      return new Response(JSON.stringify({ ok: true }), { status: 200 })
    }
    if (url === '/api/llm-config') {
      return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
    }
    return new Response('{}', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('移动端抽屉（add-collapsible-sidebar 窄视口补验）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    // 模拟 <768px 移动视口（组件读 window.matchMedia('(max-width: 767px)').matches）
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (q: string) => ({
        matches: q.includes('max-width: 767px'), media: q, onchange: null,
        addListener: () => {}, removeListener: () => {},
        addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
      }),
    })
  })

  afterEach(() => {
    delete (window as { matchMedia?: unknown }).matchMedia
  })

  it('收起态持久化时打开抽屉，仍渲染展开内容（会话列表可见）', async () => {
    // 收起态持久化 → AppSidebar 走收起分支传 expandedRail={null}，
    // 移动端抽屉渲染 expandedRail → 空抽屉（GUI 实测缺陷）
    localStorage.setItem('fa_sidebar_collapsed', '1')
    stubFetch()
    render(<App />)
    // 移动端抽屉关闭时不渲染侧边栏，先开抽屉
    fireEvent.click(screen.getByTestId('sidebar-trigger'))
    await waitFor(() => expect(screen.getByTestId('sidebar-overlay')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByTestId('session-list')).toBeInTheDocument())
    expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0)
  })
})

describe('侧边栏折叠（add-collapsible-sidebar）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    // jsdom 无 matchMedia（桌面态）
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('点击折叠按钮收起，localStorage 持久化；重渲染后保持收起态', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0))

    // 展开 → 折叠
    fireEvent.click(screen.getByTestId('sidebar-trigger'))
    await waitFor(() => expect(screen.getByTestId('sidebar-rail')).toHaveAttribute('data-state', 'collapsed'))
    expect(localStorage.getItem('fa_sidebar_collapsed')).toBe('1')

    // 重渲染（模拟刷新）：保持收起态
    cleanup()
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('sidebar-rail')).toHaveAttribute('data-state', 'collapsed'))
  })

  it('Ctrl/Cmd + B 快捷键切换折叠', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0))

    await act(async () => {
      fireEvent.keyDown(window, { key: 'b', ctrlKey: true })
    })
    expect(screen.getByTestId('sidebar-rail')).toHaveAttribute('data-state', 'collapsed')

    await act(async () => {
      fireEvent.keyDown(window, { key: 'b', metaKey: true })
    })
    expect(screen.getByTestId('sidebar-rail')).toHaveAttribute('data-state', 'expanded')
  })

  it('收起态：新建会话图标可用、展开按钮、下载管理图标', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0))

    fireEvent.click(screen.getByTestId('sidebar-trigger'))
    await waitFor(() => expect(screen.getByTestId('sidebar-new-collapsed')).toBeInTheDocument())

    // 收起态新建会话可用（点击不抛错，行为与展开态一致：switchSession(null)）
    fireEvent.click(screen.getByTestId('sidebar-new-collapsed'))
    // 下载管理入口存在（图标化）
    expect(screen.getByTestId('sidebar-downloads-collapsed')).toBeInTheDocument()

    // 展开按钮恢复
    fireEvent.click(screen.getByRole('button', { name: '展开侧边栏' }))
    expect(screen.getByTestId('sidebar-rail')).toHaveAttribute('data-state', 'expanded')
  })

  it('会话项「···」菜单：重命名原地输入生效（PATCH 请求）', async () => {
    const fetchMock = stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0))

    // hover 会话项出现菜单（DOM 常驻，直接点击触发按钮）
    await userEvent.click(screen.getByTestId('session-menu-s1'))
    const renameItem = await screen.findByText('重命名')
    await userEvent.click(renameItem)

    // 原地输入框出现，编辑后 Enter 提交
    const input = screen.getByDisplayValue('宁夏建材')
    fireEvent.change(input, { target: { value: '宁夏建材新名' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([u, init]) => String(u).includes('/api/sessions/s1') && (init as RequestInit | undefined)?.method === 'PATCH')
      expect(patch).toBeDefined()
      expect(JSON.parse((patch![1] as RequestInit).body as string)).toEqual({ display_name: '宁夏建材新名' })
    })
    await waitFor(() => expect(screen.getAllByText('宁夏建材新名').length).toBeGreaterThan(0))
  })

  it('会话项「···」菜单：删除二次确认后才发 DELETE', async () => {
    const fetchMock = stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0))

    await userEvent.click(screen.getByTestId('session-menu-s1'))
    await userEvent.click(await screen.findByText('删除'))

    // 二次确认弹窗出现
    expect(screen.getByText(/确定删除/)).toBeInTheDocument()
    // 确认前未发 DELETE
    expect(fetchMock.mock.calls.some(([u, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(false)

    fireEvent.click(screen.getByTestId('confirm-delete'))
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u, init]) => String(u).includes('/api/sessions/s1') && (init as RequestInit | undefined)?.method === 'DELETE')).toBe(true)
    })
  })
})
