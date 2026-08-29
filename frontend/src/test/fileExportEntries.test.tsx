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