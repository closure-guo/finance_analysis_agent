import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../../App'

// sonner mock：断言 toast 调用，且避免 Toaster 在 jsdom 中渲染
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

// framer-motion 依赖 matchMedia，jsdom 需兜底
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (q: string) => ({
        matches: false, media: q, onchange: null,
        addListener: () => {}, removeListener: () => {},
        addEventListener: () => {}, removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    })
  }
})

const DAY = 86_400_000
const yesterday = Date.now() - DAY
const files = [
  { file_name: '今日速览.docx', file_type: 'docx', size_bytes: 2048, created_at: Date.now() },
  { file_name: '茅台分析报告.docx', file_type: 'docx', size_bytes: 1_572_864, created_at: yesterday },
]

function pad(v: number) { return String(v).padStart(2, '0') }
const d = new Date(yesterday)
const yesterdayStr = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

function mockFetch(opts: { files?: unknown; status?: number } = {}) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/files' && (!init || !init.method || init.method === 'GET')) {
      const status = opts.status ?? 200
      return Promise.resolve(new Response(JSON.stringify(opts.status ? null : (opts.files ?? [])), { status }))
    }
    if (url === '/api/sessions') {
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 200 }))
  }))
}

function goDownloads() {
  window.history.pushState({}, '', '/downloads')
}

describe('下载中心页面（add-download-center Task 2）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    window.history.pushState({}, '', '/')
  })

  it('直达 /downloads 渲染文件列表（刷新保持路由语义）', async () => {
    goDownloads()
    mockFetch({ files })
    render(<App />)
    const rows = await screen.findAllByTestId('download-row')
    expect(rows).toHaveLength(2)
    expect(screen.getByText('茅台分析报告.docx')).toBeTruthy()
    expect(screen.getByText('1.5 MB')).toBeTruthy()
    // 昨日文件显示 YYYY-MM-DD；当日文件显示 HH:mm
    expect(screen.getByText(yesterdayStr)).toBeTruthy()
    expect(screen.getByText(`${pad(new Date(files[0].created_at).getHours())}:${pad(new Date(files[0].created_at).getMinutes())}`)).toBeTruthy()
  })

  it('空列表显示空态，点击「返回聊天」回会话页', async () => {
    goDownloads()
    mockFetch({ files: [] })
    render(<App />)
    const empty = await screen.findByTestId('downloads-empty')
    expect(empty.textContent).toContain('暂无导出文件')
    fireEvent.click(screen.getByText('返回聊天'))
    await waitFor(() => expect(window.location.pathname).toBe('/'))
    // 回到会话页（空态首屏）
    expect(await screen.findByText('今天想研究什么？')).toBeTruthy()
  })

  it('接口失败 toast 报错且不以空态冒充', async () => {
    goDownloads()
    mockFetch({ status: 500 })
    render(<App />)
    await screen.findByTestId('downloads-error')
    const { toast } = await import('sonner')
    expect(toast.error).toHaveBeenCalledWith('文件列表加载失败')
    expect(screen.queryByTestId('downloads-empty')).toBeNull()
  })

  it('侧边栏底部「下载管理」入口跳转 /downloads', async () => {
    mockFetch({ files })
    render(<App />)
    const entry = await screen.findByTestId('sidebar-downloads')
    fireEvent.click(entry)
    await waitFor(() => expect(window.location.pathname).toBe('/downloads'))
    expect(await screen.findAllByTestId('download-row')).toHaveLength(2)
  })
})
