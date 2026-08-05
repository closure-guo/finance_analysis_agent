import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import App from '../App'

// 端到端复现：澄清回复是多行 markdown 列表（单 \n 分隔列表项，\n\n 分隔段落），
// 经 chat_token 流式下发。验证前端最终 chatResponse 保留换行、渲染为正常列表，
// 而非「列表挤成一段」（实时格式错乱，刷新后正常的 bug）。

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

// 模拟 DeepSeek 把多行列表拆成多个 chat_token（换行在 token 内部或边界）
const LIST_TOKENS = [
  '根据今日行情，当前热门标的有：\n\n',
  '1. 中大力德（002896）—— 机器人减速器\n',
  '2. 卧龙电驱（600580）—— 机器人电机\n',
  '5. 宁夏建材（600449）—— 算力网，受益算力网4万亿投资\n',
  '\n回复序号或股票名称，我将为你运行完整深度分析。',
]

describe('多行列表回复流式下发保留换行', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('chat_token 多行列表流后，最终渲染为 <ol> 列表而非一段', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    const events = [
      { type: 'session_created', session_id: 's1', seq: 1 },
      ...LIST_TOKENS.map((token, i) => ({ type: 'chat_token', token, seq: 2 + i })),
      { type: 'chat_done', seq: 10 },
      { type: 'awaiting_input', session_id: 's1', pending_intent: 'awaiting_focus', seq: 11 },
    ]

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions') {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
      }
      if (url === '/api/analyze') return sse(events)
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<App />)
    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '分析今日热门股票' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })

    // 等待回复渲染
    await waitFor(() => {
      expect(screen.getByText(/回复序号或股票名称/)).toBeInTheDocument()
    }, { timeout: 8000 })

    // 等待 streaming 结束（awaiting_input 置 streaming=false）
    await new Promise(r => setTimeout(r, 300))

    // 关键断言：列表被渲染为 <ol><li>（每项一行），而非折叠成一段
    const ol = container.querySelector('ol')
    console.log('=== OL 存在 ===', !!ol)
    if (ol) {
      console.log('li 数量:', ol.querySelectorAll('li').length)
      console.log('ol outerHTML:', ol.outerHTML.slice(0, 200))
    } else {
      // 折叠成段落时的实际文本
      const text = container.textContent || ''
      const idx = text.indexOf('中大力德')
      console.log('折叠文本片段:', text.slice(idx - 30, idx + 80))
    }
    expect(ol).not.toBeNull()
    expect(ol!.querySelectorAll('li').length).toBeGreaterThanOrEqual(3)
  })
})
