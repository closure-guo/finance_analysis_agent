// fix-analysis-ux-polish Task 2.3/3.3 组件测试：
// 1) 深模式追问流存活期间运行中拦截：composer 切换为停止按钮、Enter 不发新请求
//    （adopt-assistant-ui-chat 迁移后主拦截层 = runtime 状态判定；App 内 guard 为兜底）
// 2) quick 模式兜底 guard：run 进行中从首页再次发送 → 「该会话正在生成中」
//    以 fixed 顶部 toast 呈现（z-index 高于 header/输入栏），不发新请求，3 秒自动消失
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react'
import App from '../App'

function sse(events: object[], keepOpen = false): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const ev of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}\n\n`))
      }
      if (!keepOpen) controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('运行中拦截（fix-analysis-ux-polish）', () => {
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

  it('深模式追问流存活期间：发送入口切为停止按钮，Enter 不发新请求', { timeout: 20000 }, async () => {
    let analyzeCount = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions') return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
      if (url === '/api/llm-config') return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
      if (url === '/api/analyze') {
        analyzeCount += 1
        if (analyzeCount === 1) {
          return sse([
            { type: 'session_created', session_id: 's1', seq: 1 },
            { type: 'chat_token', token: '你好', seq: 2 },
            { type: 'done', seq: 3 },
          ])
        }
        // 第二轮（追问）：管线事件后流保持打开 → 会话保持运行中
        return sse([
          { type: 'session_created', session_id: 's1', seq: 4 },
          { type: 'tool_call', name: 'run_deep_analysis', args: {}, seq: 5 },
          { type: 'node_start', node: 'PREP', label: '准备', seq: 6 },
        ], true)
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 第一轮：发起分析并完成
    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '你好' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })
    await waitFor(() => expect(screen.getByTestId('stream-output')).toBeInTheDocument(), { timeout: 8000 })

    // 第二轮：追问发起，流保持打开（运行中）
    const input2 = await screen.findByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input2, { target: { value: '继续' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })
    await waitFor(() => expect(screen.getByTestId('composer-stop')).toBeInTheDocument(), { timeout: 8000 })

    // 关键断言 1：运行中发送入口被移除（runtime 状态判定拦截）
    expect(screen.queryByTestId('send-button')).toBeNull()
    // 关键断言 2：Enter 不发出新请求
    const ta = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(ta, { target: { value: '不该发出去' } })
      fireEvent.keyDown(ta, { key: 'Enter' })
    })
    await new Promise((r) => setTimeout(r, 500))
    expect(analyzeCount).toBe(2)
  })
})

describe('quick 模式警告 toast（fix-analysis-ux-polish）', () => {
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

  it('toast 以 fixed 顶部呈现（z-index 高于 header/输入栏）且 3 秒自动消失', { timeout: 20000 }, async () => {
    // 经可驱动的 409 路径触发 showWarning（与「该会话正在生成中」共用同一 toast 容器/样式；
    // 运行中拦截主层 = runtime 状态判定，见上一组用例与 quickThreadGuards.test.tsx）
    const s1Meta = { session_id: 's1', stock_code: '', stock_name: '', display_name: '会话一', status: 'completed', created_at: '2026-07-01T00:00:00Z', duration_ms: 0 }
    const s1Detail = { ...s1Meta, session_type: 'chat', report_markdown: '', chart_data: {}, analyst_reports: {}, agent_process: {}, analyst_summaries: {}, chat_history: [], pipeline_snapshot: null }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions' && (!init || !init.method)) {
        return new Response(JSON.stringify({ sessions: [s1Meta] }), { status: 200 })
      }
      if (url === '/api/sessions/s1') return new Response(JSON.stringify(s1Detail), { status: 200 })
      if (url === '/api/llm-config') return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
      if (url === '/api/agui/quick') return new Response(JSON.stringify({ detail: 'session_busy' }), { status: 409 })
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText('会话一')).toBeInTheDocument())
    await act(async () => { fireEvent.click(screen.getByText('会话一')) })
    await waitFor(() => expect(screen.getByPlaceholderText(/输入问题/)).toBeInTheDocument())

    const input = screen.getByPlaceholderText(/输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '触发 409' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })

    // toast 呈现：fixed 顶部、z-index 高于 header(z-50)/输入栏(z-40)
    await waitFor(() => {
      const toast = screen.getByText(/HTTP 409/)
      expect(toast.className).toContain('fixed')
      expect(toast.className).toContain('top-16')
      expect(toast.className).toContain('z-[60]')
    })

    // 3 秒后自动消失
    await waitFor(
      () => expect(screen.queryByText(/HTTP 409/)).not.toBeInTheDocument(),
      { timeout: 4500 },
    )
  })
})
