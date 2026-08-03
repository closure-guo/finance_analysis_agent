import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import App from '../App'

// Bug 复现测试：追问（follow-up）时 POST /api/analyze 的 _subscribe_sse 重放全量历史事件，
// 但前端 streamingSessionIdRef 为 null（无 session_created 事件）导致 seq 去重失效，
// 旧事件触发 setMessages 风暴冻结 UI。

function sse(events: object[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const ev of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}\n\n`))
      }
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('追问时 SSE 重放不冻结 UI（seq 去重生效）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('追问时重放的历史事件被 seq 去重跳过，不产生重复消息', { timeout: 15000 }, async () => {
    vi.useRealTimers()
    // 第一轮 SSE：session_created → chat_token "你好" → done
    const round1 = [
      { type: 'session_created', session_id: 's1', seq: 1 },
      { type: 'chat_token', token: '你好', seq: 2 },
      { type: 'done', seq: 3 },
    ]

    // 第二轮：后端 _subscribe_sse(after_seq=0) 重放全部事件 + 新事件
    const round2 = [
      { type: 'session_created', session_id: 's1', seq: 1 },     // 旧事件（重放）
      { type: 'chat_token', token: '你好', seq: 2 },              // 旧事件（重放）
      { type: 'done', seq: 3 },                                    // 旧事件（重放）
      { type: 'chat_token', token: '世界', seq: 4 },              // 新事件
      { type: 'done', seq: 5 },                                    // 新终态
    ]

    let analyzeCallCount = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions') {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
      }
      if (url === '/api/analyze') {
        analyzeCallCount += 1
        return sse(analyzeCallCount === 1 ? round1 : round2)
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 第一轮：发送消息
    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '你好' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })

    // 等待第一轮：用户消息 + assistant 回复出现
    await waitFor(() => expect(screen.getByTestId('stream-output')).toBeInTheDocument(), { timeout: 8000 })
    // "你好" 出现 2 次：用户消息 + assistant 回复
    expect(screen.getAllByText('你好').length).toBe(2)

    // 第二轮：追问
    await act(async () => {
      fireEvent.change(input, { target: { value: '世界' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })

    // 等待第二轮 assistant 回复出现
    await waitFor(() => expect(screen.getByTestId('stream-output')).toBeInTheDocument(), { timeout: 8000 })

    // 关键断言：重放的旧 chat_token "你好"（seq=2）不应创建额外消息
    // 修复前：seq 去重失效，重放的 chat_token "你好" 会追加到已有消息或创建新消息
    // 修复后：seq 去重跳过旧事件，"你好" 仍为 2 次
    expect(screen.getAllByText('你好').length).toBe(2)
  })
})
