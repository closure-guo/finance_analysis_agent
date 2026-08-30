import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { createRef } from 'react'
import QuickThread, { type QuickThreadHandle } from '../../chat/QuickThread'
import { installJsdomPolyfills } from './aguiTestSetup'

installJsdomPolyfills()

// add-assistant-ui-thread Task 3a：quick 模式 assistant-ui Thread 渲染接入 AG-UI 通道。
//
// 组件级测试：mock fetch 返回 EventEncoder 同款 SSE 线格式（`data: {json}\n\n`，
// camelCase 字段），脚本化 AG-UI 事件序列，验证：
//   1. 发送 → 用户消息 + 流式增量呈现（TEXT_MESSAGE_* 渲染进 Thread）
//   2. RUN_FINISHED 后流式指示器消失
//   3. RUN_STARTED.thread_id 经 onSessionCreated 回传（新会话绑定）
//   4. 请求体为 AG-UI RunAgentInput 形态（messages 含 user 消息）

function aguiSse(events: object[], holdUntil?: Promise<void>): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const ev of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}\n\n`))
      }
      if (holdUntil) await holdUntil
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

const NORMAL_EVENTS = [
  { type: 'RUN_STARTED', threadId: 'sess-1', runId: 'run-1' },
  { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' },
  { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: '贵州茅台今日' },
  { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: '上涨 1.2%。' },
  { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
  { type: 'RUN_FINISHED', threadId: 'sess-1', runId: 'run-1' },
]

describe('QuickThread（assistant-ui Thread + AG-UI 通道）', () => {
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('发送 → 流式增量渲染 → RUN_FINISHED 后指示器消失', async () => {
    // RUN_FINISHED 之前流保持打开，用于断言「流式中指示器存在」
    let releaseStream: (() => void) | undefined
    const hold = new Promise<void>((r) => { releaseStream = r })
    const preFinish = NORMAL_EVENTS.slice(0, -1)
    const finishEvent = NORMAL_EVENTS[NORMAL_EVENTS.length - 1]

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/agui/quick') {
        const enc = new TextEncoder()
        const stream = new ReadableStream<Uint8Array>({
          async start(controller) {
            for (const ev of preFinish) {
              controller.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`))
            }
            await hold
            controller.enqueue(enc.encode(`data: ${JSON.stringify(finishEvent)}\n\n`))
            controller.close()
          },
        })
        return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const ref = createRef<QuickThreadHandle>()
    render(<QuickThread ref={ref} apiKey="sk-test" />)

    await act(async () => {
      ref.current?.send('茅台怎么样')
    })

    // 用户消息呈现
    await waitFor(() => {
      expect(screen.getByText('茅台怎么样')).toBeInTheDocument()
    })

    // 流式增量呈现（拼接后完整文本）
    await waitFor(() => {
      expect(screen.getByText(/上涨 1\.2%/)).toBeInTheDocument()
    })

    // 流式中：流式指示器存在
    expect(screen.getByTestId('agui-stream-status')).toBeInTheDocument()

    // RUN_FINISHED 下发 → 指示器消失
    await act(async () => {
      releaseStream?.()
    })
    await waitFor(() => {
      expect(screen.queryByTestId('agui-stream-status')).toBeNull()
    })
  })

  it('请求体为 RunAgentInput 形态且 RUN_STARTED.thread_id 回传 onSessionCreated', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/agui/quick') return aguiSse(NORMAL_EVENTS)
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const onSessionCreated = vi.fn()
    const ref = createRef<QuickThreadHandle>()
    render(<QuickThread ref={ref} apiKey="sk-test" onSessionCreated={onSessionCreated} />)

    await act(async () => {
      ref.current?.send('茅台怎么样')
    })

    await waitFor(() => {
      expect(screen.getByText(/上涨 1\.2%/)).toBeInTheDocument()
    })

    // 请求 URL + body 形态
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [RequestInfo | URL, RequestInit | undefined]
    expect(String(url)).toBe('/api/agui/quick')
    const reqInit = (init ?? {}) as RequestInit
    expect(reqInit.method).toBe('POST')
    const body = JSON.parse(reqInit.body as string)
    expect(body.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '茅台怎么样' }),
      ]),
    )

    // 新会话绑定：RUN_STARTED.thread_id 回传
    await waitFor(() => {
      expect(onSessionCreated).toHaveBeenCalledWith('sess-1')
    })
  })
})
