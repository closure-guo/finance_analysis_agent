// replicate-chat-home Task 2.2/2.3 组件测试：
// 空态首页（问候语/提示/建议卡片）、卡片点击填入不发送、历史会话不显示空态、
// 首条消息发送后空态 200ms 淡出。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import App from '../App'

const COMPLETED_DETAIL = {
  session_id: 's1', stock_code: '600449', stock_name: '宁夏建材', display_name: '宁夏建材', status: 'completed',
  created_at: '2026-08-30T00:00:00Z', duration_ms: 1, report_markdown: '', chart_data: null,
  analyst_reports: {}, agent_process: {}, analyst_summaries: {},
  chat_history: [
    { role: 'user', content: '历史提问', ts: '2026-08-30T00:00:00Z' },
    { role: 'assistant', content: '历史回答', ts: '2026-08-30T00:01:00Z' },
  ],
  pipeline_snapshot: null, last_seq: 0,
}

function stubFetch(opts: { sessions?: unknown[] } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'
    if (url === '/api/sessions' && method === 'GET') {
      return new Response(JSON.stringify({ sessions: opts.sessions ?? [] }), { status: 200 })
    }
    if (url.startsWith('/api/sessions/') && method === 'GET') {
      return new Response(JSON.stringify(COMPLETED_DETAIL), { status: 200 })
    }
    if (url === '/api/llm-config') {
      return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
    }
    return new Response('{}', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('空态首页（replicate-chat-home）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('新会话显示空态：问候语 + 输入提示 + 4 张建议卡片', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('今天想研究什么？')).toBeInTheDocument())
    expect(screen.getByText('支持输入股票名称、代码或自然语言指令')).toBeInTheDocument()
    expect(screen.getByTestId('suggestion-深度分析')).toBeInTheDocument()
    expect(screen.getByTestId('suggestion-财报解读')).toBeInTheDocument()
    expect(screen.getByTestId('suggestion-最新消息')).toBeInTheDocument()
    expect(screen.getByTestId('suggestion-对比研究')).toBeInTheDocument()
  })

  it('点击建议卡片填入输入框，不发出分析请求', async () => {
    const fetchMock = stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('suggestion-深度分析')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('suggestion-深度分析'))

    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/) as HTMLTextAreaElement
    expect(input.value).toBe('分析宁德时代')
    // 未发出分析请求
    expect(fetchMock.mock.calls.some(([u]) => String(u) === '/api/analyze')).toBe(false)
  })

  it('历史会话不显示空态，直接显示消息流', async () => {
    stubFetch({ sessions: [{ session_id: 's1', stock_code: '600449', stock_name: '宁夏建材', display_name: '宁夏建材', status: 'completed', created_at: '2026-08-30T00:00:00Z', duration_ms: 1, session_type: 'chat' }] })
    render(<App />)
    // 空态先短暂出现（列表加载前），选中历史会话后必须退场
    await waitFor(() => expect(screen.getAllByText('宁夏建材').length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByText('宁夏建材')[0])
    await waitFor(() => expect(screen.getByTestId('stream-output')).toBeInTheDocument())
    await waitFor(() => {
      expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument()
    })
    expect(screen.queryByText('今天想研究什么？')).not.toBeInTheDocument()
  })

  it('发送首条消息后空态 200ms 淡出退场', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'
      if (url === '/api/sessions' && method === 'GET') {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
      }
      if (url === '/api/llm-config') {
        return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
      }
      if (url === '/api/analyze') {
        const events = [
          { type: 'session_created', session_id: 's9', seq: 1 },
          { type: 'chat_token', token: '测试回答', seq: 2 },
          { type: 'chat_done', seq: 3 },
          { type: 'done', seq: 4 },
        ]
        const encoder = new TextEncoder()
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            for (const ev of events) controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}\n\n`))
            controller.close()
          },
        })
        return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument())

    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    fireEvent.change(input, { target: { value: '分析宁德时代' } })
    fireEvent.click(screen.getByTestId('send-button'))

    // 空态进入退场（opacity-0）后卸载
    await waitFor(() => {
      const empty = screen.queryByTestId('empty-state')
      if (empty) {
        expect(empty.className).toContain('opacity-0')
      } else {
        expect(empty).toBeNull()
      }
    })
    // 消息流就位
    await waitFor(() => expect(screen.getByTestId('stream-output')).toBeInTheDocument())
  })
})
