import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { createRef } from 'react'
import QuickThread, { type QuickThreadHandle } from '../../chat/QuickThread'
import { installJsdomPolyfills } from './aguiTestSetup'

installJsdomPolyfills()

// 回归测试（systematic-debugging）：quick 通道多步交互的两处根因修复。
//
// 根因 1（后端 translator）：TOOL_CALL 段只发 START+ARGS+RESULT、不发 END。
// 客户端 HttpAgent 校验状态机中 END 是唯一闭合 active tool call 的事件，
// RUN_FINISHED 时 active 非空抛 AGUIError → 整个 run 判错、内容实时丢弃
// （思考/工具动作条不显示，刷新后走 MessageItem 快照才恢复）。
//
// 根因 2（前端 QuickThread.send）：append 用 parentId=null，追问被挂成新的
// 兄弟分支——第一轮对话脱离当前视图，多步交互的输出/action 序列错乱。

function aguiSse(events: object[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
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

// 一次多步 run：思考 → 工具 → 思考 → 回答（与修复后 translator 产出一致）
const MULTISTEP_RUN1 = [
  { type: 'RUN_STARTED', threadId: 'sess-1', runId: 'run-1' },
  { type: 'REASONING_MESSAGE_START', messageId: 'r1', role: 'reasoning' },
  { type: 'REASONING_MESSAGE_CONTENT', messageId: 'r1', delta: '第一段思考：需要先搜索' },
  { type: 'REASONING_MESSAGE_END', messageId: 'r1' },
  { type: 'TOOL_CALL_START', toolCallId: 't1', toolCallName: 'web_search' },
  { type: 'TOOL_CALL_ARGS', toolCallId: 't1', delta: '{"query":"茅台股价"}' },
  { type: 'TOOL_CALL_END', toolCallId: 't1' },
  {
    type: 'TOOL_CALL_RESULT',
    toolCallId: 't1',
    messageId: 'tr1',
    content: '搜索结果：茅台 1600 元',
  },
  { type: 'REASONING_MESSAGE_START', messageId: 'r2', role: 'reasoning' },
  { type: 'REASONING_MESSAGE_CONTENT', messageId: 'r2', delta: '第二段思考：整合结果' },
  { type: 'REASONING_MESSAGE_END', messageId: 'r2' },
  { type: 'TEXT_MESSAGE_START', messageId: 'a1', role: 'assistant' },
  { type: 'TEXT_MESSAGE_CONTENT', messageId: 'a1', delta: '第一轮回答文本' },
  { type: 'TEXT_MESSAGE_END', messageId: 'a1' },
  { type: 'RUN_FINISHED', threadId: 'sess-1', runId: 'run-1' },
]

const RUN2 = [
  { type: 'RUN_STARTED', threadId: 'sess-1', runId: 'run-2' },
  { type: 'TEXT_MESSAGE_START', messageId: 'a2', role: 'assistant' },
  { type: 'TEXT_MESSAGE_CONTENT', messageId: 'a2', delta: '第二轮回答文本' },
  { type: 'TEXT_MESSAGE_END', messageId: 'a2' },
  { type: 'RUN_FINISHED', threadId: 'sess-1', runId: 'run-2' },
]

describe('QuickThread 多步交互回归（动作条 + 分轮时序）', () => {
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('多步 run：思考与工具动作横幅实时可见（根因1：TOOL_CALL_END 缺失致 run 判错）', async () => {
    const fetchMock = vi.fn(async () => aguiSse(MULTISTEP_RUN1))
    vi.stubGlobal('fetch', fetchMock)

    const ref = createRef<QuickThreadHandle>()
    render(<QuickThread ref={ref} apiKey="sk-test" />)

    await act(async () => {
      ref.current?.send('多步问题')
    })

    await waitFor(() => {
      expect(screen.getByText('第一轮回答文本')).toBeInTheDocument()
    })

    // 按时间序列依次呈现：思考 → 工具 → 思考 → 回答（同一气泡内有序 parts）
    expect(screen.getByText('第一段思考：需要先搜索')).toBeInTheDocument()
    expect(screen.getByText('第二段思考：整合结果')).toBeInTheDocument()
    expect(screen.getByText(/调用工具 · web_search/)).toBeInTheDocument()
    // run 正常结束（不被 AGUIError 判错）
    expect(screen.queryByTestId('agui-stream-status')).toBeNull()
  })

  it('多轮追问：两轮消息按时间序列独立排列，第二轮请求携带历史上下文（根因2：parentId=null）', async () => {
    const bodies: Array<{ messages: Array<{ role: string; content: string }> }> = []
    let call = 0
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      call += 1
      bodies.push(JSON.parse((init?.body as string) ?? '{}'))
      return aguiSse(call === 1 ? MULTISTEP_RUN1 : RUN2)
    })
    vi.stubGlobal('fetch', fetchMock)

    const ref = createRef<QuickThreadHandle>()
    render(<QuickThread ref={ref} apiKey="sk-test" />)

    await act(async () => {
      ref.current?.send('第一问')
    })
    await waitFor(() => {
      expect(screen.getByText('第一轮回答文本')).toBeInTheDocument()
    })

    await act(async () => {
      ref.current?.send('第二问')
    })
    await waitFor(() => {
      expect(screen.getByText('第二轮回答文本')).toBeInTheDocument()
    })

    // 两轮 → 两条独立 assistant 消息，各含本轮内容、互不串轮
    const assistantMsgs = screen.getAllByTestId('agui-assistant-message')
    expect(assistantMsgs.length).toBe(2)
    expect(assistantMsgs[0]).toHaveTextContent('第一轮回答文本')
    expect(assistantMsgs[0]).not.toHaveTextContent('第二轮回答文本')
    expect(assistantMsgs[1]).toHaveTextContent('第二轮回答文本')
    expect(assistantMsgs[1]).not.toHaveTextContent('第一轮回答文本')

    // 第二轮 RunAgentInput 携带完整历史（agent 不丢上下文）
    expect(bodies[1]?.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '第一问' }),
        expect.objectContaining({ role: 'user', content: '第二问' }),
      ]),
    )
  })
})
