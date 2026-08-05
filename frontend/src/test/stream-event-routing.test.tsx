import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import App from '../App'

// Bug 复现测试：深度模式流式事件按「pipelineMsgRef 是否存在」静态路由，
// 与事件真实归属不一致（delta spec: fix-stream-event-routing）。
//
// 根因：run_deep_analysis tool_call 创建 pipelineMsg 后，
// - thinking_token 被劫持进管线 UI（nodeTimelines['']），澄清思考从对话流消失；
// - thinking_replace / thinking_to_answer 被静默丢弃，DSML 清理不生效。
//
// 修复标准：
// - thinking_token 仅当携带 node 字段才进管线 UI，否则进对话流；
// - thinking_replace / thinking_to_answer 始终路由到对话流，不被丢弃。

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

describe('流式事件按归属路由（pipelineMsg 存在时澄清事件仍进对话流）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('管线触发后不带 node 的 thinking_token 仍进对话流（不错位）', { timeout: 20000 }, async () => {
    vi.useRealTimers()

    // run_deep_analysis 建管线 -> 后续澄清思考（不带 node）
    const events = [
      { type: 'session_created', session_id: 's1', seq: 1 },
      { type: 'tool_call', name: 'run_deep_analysis', args: { stock_code: '600449' }, seq: 2 },
      { type: 'thinking_token', token: '澄清阶段思考内容XYZ', seq: 3 },
      { type: 'done', seq: 4 },
    ]

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions') {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
      }
      if (url === '/api/analyze') {
        return sse(events)
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '宁夏建材' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })

    // 关键断言：澄清思考应渲染在对话流消息中
    // 修复前：被劫持进管线 nodeTimelines['']，从对话流消失
    // 修复后：按归属进对话流 agentTimeline，正常渲染
    await waitFor(() => {
      expect(screen.getByText(/澄清阶段思考内容XYZ/)).toBeInTheDocument()
    }, { timeout: 8000 })
  })

  it('pipelineMsg 存在时 thinking_replace 不被丢弃（DSML 清理生效）', { timeout: 20000 }, async () => {
    vi.useRealTimers()

    // 建管线 -> thinking_token(DSML 原文) -> thinking_replace(清理后)
    const events = [
      { type: 'session_created', session_id: 's1', seq: 1 },
      { type: 'tool_call', name: 'run_deep_analysis', args: { stock_code: '600449' }, seq: 2 },
      { type: 'thinking_token', token: 'DSML_RAW_原始文本ABC', seq: 3 },
      { type: 'thinking_replace', token: '清理后的思考内容DEF', seq: 4 },
      { type: 'done', seq: 5 },
    ]

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions') {
        return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
      }
      if (url === '/api/analyze') {
        return sse(events)
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '宁夏建材' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })

    // 关键断言：DSML 清理后文本生效，原始文本被替换
    // 修复前：thinking_replace 被丢弃，UI 残留 DSML_RAW_原始文本ABC
    // 修复后：显示清理后文本，不显示原始文本
    await waitFor(() => {
      expect(screen.getByText(/清理后的思考内容DEF/)).toBeInTheDocument()
    }, { timeout: 8000 })
    expect(screen.queryByText(/DSML_RAW_原始文本ABC/)).not.toBeInTheDocument()
  })
})
