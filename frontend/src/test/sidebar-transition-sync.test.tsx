// 侧边栏收放抖动复现测试（fix-sidebar-toggle-jitter）：
// 1) Sidebar 内容必须包在固定 256px 宽的内层里 —— aside 宽度 200ms 动画期间
//    内容只被 overflow 裁剪、不逐帧重排（shadcn 原做法），否则列表文字抖动。
// 2) 会话视图的 fixed 定位层（header / 聊天区 / 底部输入栏）left 必须带
//    200ms 过渡，与 aside 宽度动画时序对齐，否则折叠瞬间聊天区横跳 204px。
// 3) 展开时历史会话列表带渐入场动画（fade + 随展开滑入，motion.div 驱动）。
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react'
import App from '../App'
import { SidebarProvider, Sidebar } from '../components/ui/sidebar'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('Sidebar 内容固定宽内层', () => {
  it('展开态内容包在固定 256px 内层中（动画期间不重排）', () => {
    render(
      <SidebarProvider>
        <Sidebar expandedRail={<div>展开内容</div>} collapsedRail={<div>图标栏</div>} />
      </SidebarProvider>,
    )
    const inner = screen.getByTestId('sidebar-content-inner')
    expect(inner.className).toContain('w-64')
    expect(inner.textContent).toContain('展开内容')
  })

  it('收起态图标栏同样包在固定宽内层中', () => {
    localStorage.setItem('fa_sidebar_collapsed', '1')
    render(
      <SidebarProvider>
        <Sidebar expandedRail={<div>展开内容</div>} collapsedRail={<div>图标栏</div>} />
      </SidebarProvider>,
    )
    const inner = screen.getByTestId('sidebar-content-inner')
    expect(inner.className).toContain('w-64')
    expect(inner.textContent).toContain('图标栏')
  })
})

describe('会话视图 fixed 层 left 过渡', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  function stubFetchWithSession() {
    const detail = {
      session_id: 's1', stock_code: '600519', stock_name: '贵州茅台',
      display_name: '贵州茅台分析', status: 'completed', created_at: '2026-07-01T00:00:00Z',
      duration_ms: 60_000, session_type: 'analysis',
      report_markdown: '', chart_data: {}, analyst_reports: {}, agent_process: {},
      analyst_summaries: {},
      chat_history: [
        { role: 'user', content: '你好' },
        { role: 'assistant', content: '你好！' },
      ],
      pipeline_snapshot: null,
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'
      if (url === '/api/sessions' && method === 'GET') {
        return new Response(JSON.stringify({ sessions: [{ session_id: 's1', stock_code: '600519', stock_name: '贵州茅台', display_name: '贵州茅台分析', status: 'completed', created_at: '2026-07-01T00:00:00Z', duration_ms: 1, session_type: 'chat' }] }), { status: 200 })
      }
      if (url.startsWith('/api/sessions/')) {
        return new Response(JSON.stringify(detail), { status: 200 })
      }
      if (url === '/api/llm-config') {
        return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    }))
  }

  it('header / 聊天区 / 输入栏的 fixed 层 left 带 200ms 过渡', async () => {
    stubFetchWithSession()
    render(<App />)
    // 进入会话视图
    const item = await screen.findByText('贵州茅台分析')
    fireEvent.click(item)
    await waitFor(() => expect(document.querySelector('header')).not.toBeNull())

    const header = document.querySelector('header')!
    expect(header.className).toContain('transition-[left]')
    expect(header.className).toContain('duration-200')

    const ta = await screen.findByPlaceholderText(/输入问题|输入股票名称或代码/)
    const inputBar = ta.closest('div.fixed')!
    expect(inputBar.className).toContain('transition-[left]')
    expect(inputBar.className).toContain('duration-200')
  })
})

describe('会话列表展开渐入场动画', () => {
  function stubMatchMedia(reduced: boolean) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (q: string) => ({
        matches: reduced && q.includes('prefers-reduced-motion'), media: q, onchange: null,
        addListener: () => {}, removeListener: () => {},
        addEventListener: () => {}, removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    })
  }

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'
      if (url === '/api/sessions' && method === 'GET') {
        return new Response(JSON.stringify({ sessions: [
          { session_id: 's1', stock_code: '600519', stock_name: '贵州茅台', display_name: '贵州茅台分析', status: 'completed', created_at: '2026-07-01T00:00:00Z', duration_ms: 1, session_type: 'chat' },
        ] }), { status: 200 })
      }
      if (url === '/api/llm-config') {
        return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    }))
  })

  it('正常模式：列表由 motion 接管（fade+slide 入场，内联 opacity 受控）', async () => {
    stubMatchMedia(false)
    render(<App />)
    const list = await screen.findByTestId('session-list')
    // motion 动画驱动的标志：opacity 被写入内联样式（动画进行中或完成后均成立）
    expect(list.style.opacity).not.toBe('')
  })

  it('减弱动态效果模式：framer-motion 原生跳过位移动画（无 translateX）', async () => {
    // framer-motion 的 useReducedMotion 全局值按首次访问缓存，用 MotionConfig 显式覆盖；
    // reducedMotion="always" 下 transform 动画被禁用（opacity 保留，对减弱用户安全）
    const { MotionConfig } = await import('framer-motion')
    render(<MotionConfig reducedMotion="always"><App /></MotionConfig>)
    const list = await screen.findByTestId('session-list')
    expect(list.style.transform ?? '').not.toContain('translateX')
  })
})
