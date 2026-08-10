import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { SSEEvent, SessionDetail } from '../../types'
import { StreamStore, resetStreamStore } from '../../stores/streamStore'
import { IDLE_STATE } from '../../stores/streamStore/types'

// StreamStore 时序测试：不渲染 React，直接驱动 store
// 覆盖：双会话并发、切换续传、seq 去重、resume 204、单读取器保证

beforeEach(() => {
  resetStreamStore()
})

describe('StreamStore - 基础订阅', () => {
  it('getSnapshot 无会话时返回 IDLE_STATE', () => {
    const store = new StreamStore()
    expect(store.getSnapshot('nonexistent')).toBe(IDLE_STATE)
  })

  it('subscribe / emit 通知监听器', async () => {
    const store = new StreamStore()
    const listener = vi.fn()
    store.subscribe(listener)

    // 手动设置一个状态触发 emit
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 0 })
    store['emit']()

    await new Promise((r) => setTimeout(r, 0))
    expect(listener).toHaveBeenCalled()
  })
})

describe('StreamStore - seq 守门', () => {
  it('过期事件被丢弃（seq <= lastSeq）', () => {
    const store = new StreamStore()
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 5 })

    const listener = vi.fn()
    store.subscribe(listener)

    store['applyEvent']('s1', { type: 'chat_token', token: '旧', timestamp: '', seq: 3 } as SSEEvent)
    expect(store.getSnapshot('s1').messages).toHaveLength(0)
  })

  it('正常事件更新 lastSeq', () => {
    const store = new StreamStore()
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 5 })

    store['applyEvent']('s1', { type: 'chat_token', token: '新', timestamp: '', seq: 6 } as SSEEvent)
    expect(store.getSnapshot('s1').lastSeq).toBe(6)
    expect(store.getSnapshot('s1').messages).toHaveLength(1)
  })

  it('seq 空洞触发 resync', () => {
    const store = new StreamStore()
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 5 })

    const resumeSpy = vi.spyOn(store, 'resume').mockResolvedValue(undefined)

    store['applyEvent']('s1', { type: 'chat_token', token: '跳号', timestamp: '', seq: 8 } as SSEEvent)
    expect(resumeSpy).toHaveBeenCalledWith('s1')
  })
})

describe('StreamStore - 事件按 sessionId 分流', () => {
  it('双会话事件各自独立', () => {
    const store = new StreamStore()
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 0 })
    store['streams'].set('s2', { phase: 'streaming', messages: [], lastSeq: 0 })

    store['applyEvent']('s1', { type: 'chat_token', token: 'A', timestamp: '', seq: 1 } as SSEEvent)
    store['applyEvent']('s2', { type: 'chat_token', token: 'B', timestamp: '', seq: 1 } as SSEEvent)

    expect(store.getSnapshot('s1').messages[0].chatResponse).toBe('A')
    expect(store.getSnapshot('s2').messages[0].chatResponse).toBe('B')
  })

  it('迟到事件写入对应会话，不污染当前视图', () => {
    const store = new StreamStore()
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 0 })
    store['streams'].set('s2', { phase: 'streaming', messages: [], lastSeq: 0 })

    // 模拟 s1 的迟到事件在 s2 活跃时到达
    store['applyEvent']('s1', { type: 'chat_token', token: '迟到', timestamp: '', seq: 1 } as SSEEvent)
    store['applyEvent']('s2', { type: 'chat_token', token: '当前', timestamp: '', seq: 1 } as SSEEvent)

    expect(store.getSnapshot('s1').messages[0].chatResponse).toBe('迟到')
    expect(store.getSnapshot('s2').messages[0].chatResponse).toBe('当前')
  })
})

describe('StreamStore - 单读取器保证', () => {
  it('新 submit abort 旧 reader', async () => {
    const store = new StreamStore()
    const abort1 = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort: abort1 }

    // 模拟 fetch 立即 reject（abort 后触发）
    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    const submitPromise = store.submit({
      query: 'test', api_key: 'key', user_id: 'u1', analysis_type: 'comprehensive', session_id: 's2',
    })

    // 等待微任务让 submit 执行到 abort 逻辑
    await new Promise((r) => setTimeout(r, 10))

    expect(abort1.signal.aborted).toBe(true)

    globalThis.fetch = originalFetch
    await submitPromise.catch(() => {})
  })
})

describe('StreamStore - switchSession', () => {
  it('切换会话 abort 当前 reader 并清空 messages', () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort }
    store['streams'].set('s1', { phase: 'streaming', messages: [{ id: 'm1', type: 'chat', content: '' }], lastSeq: 5 })
    // 目标会话 s2 也需要有状态，才能触发 messages 清空逻辑
    store['streams'].set('s2', { phase: 'idle', messages: [], lastSeq: 0 })

    store.switchSession('s2')

    expect(abort.signal.aborted).toBe(true)
    // s2 的 messages 被清空（从后端重建）
    const s2State = store['streams'].get('s2')
    expect(s2State?.messages).toHaveLength(0)
    // s1 的状态保留（lastSeq 用于续传）
    const s1State = store['streams'].get('s1')
    expect(s1State?.lastSeq).toBe(5)
  })

  it('switchSession(null) 仅 abort reader', () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort }

    store.switchSession(null)

    expect(abort.signal.aborted).toBe(true)
    expect(store['activeReader']).toBeNull()
  })
})

describe('StreamStore - cancel', () => {
  it('cancel abort 本地 reader 并设置 interrupted', async () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort }
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 0 })

    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true })

    await store.cancel('s1')

    expect(abort.signal.aborted).toBe(true)
    expect(store.getSnapshot('s1').phase).toBe('interrupted')

    globalThis.fetch = originalFetch
  })
})

describe('StreamStore - rebuild 进行中会话走 journal replay', () => {
  // 刷新恢复架构修正：进行中（running/clarifying）会话刷新后，
  // 不再用 chat_history 快照重建 assistant 部分 + last_seq 续传（会丢失中间流式事件）。
  // 改为：rebuild 只保留 user 消息（journal 不含 user_message 事件，须从 chat_history 补），
  // lastSeq=0 让 resume 全量 replay journal（从第一个事件重放，逐条累积完整状态）。
  // 终态会话（completed/failed/interrupted）仍走完整快照重建（chat_history 已是最终结果）。
  const runningDetail = {
    session_id: 's1', status: 'running', session_type: 'analysis', last_seq: 50,
    chat_history: [
      { role: 'user', content: '分析热门股票', ts: '2026-08-10T00:00:00' },
      {
        role: 'assistant', content: '', ts: '2026-08-10T00:00:05',
        thinking: '历史思考快照',
        tool_calls: [{ name: 'web_search', args: '{}', result_text: 'r', done: true }],
      },
    ],
  } as unknown as SessionDetail

  it('running 会话 rebuild 只保留 user 消息（assistant 交给 journal replay）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', runningDetail)
    const msgs = store.getSnapshot('s1').messages
    // 只有 user 消息，不含 assistant chat（将被 replay 重建）
    expect(msgs).toHaveLength(1)
    expect(msgs[0].type).toBe('user')
    expect(msgs[0].content).toBe('分析热门股票')
  })

  it('running 会话 rebuild 的 lastSeq=0（让 resume 从头全量 replay）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', runningDetail)
    expect(store.getSnapshot('s1').lastSeq).toBe(0)
  })

  it('clarifying 会话同样走 replay（只留 user 消息 + lastSeq=0）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', { ...runningDetail, status: 'clarifying' } as never)
    const snap = store.getSnapshot('s1')
    expect(snap.lastSeq).toBe(0)
    expect(snap.messages.filter((m) => m.type === 'user')).toHaveLength(1)
    expect(snap.messages.some((m) => m.type === 'chat')).toBe(false)
  })

  it('completed 会话仍走完整快照重建（chat_history 是最终结果，无需 replay）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', {
      ...runningDetail, status: 'completed', last_seq: 99,
      report_markdown: '# 报告', chart_data: {},
    } as unknown as SessionDetail)
    const snap = store.getSnapshot('s1')
    // completed：lastSeq 用后端 last_seq（终态，不再 resume）
    expect(snap.lastSeq).toBe(99)
    // assistant chat 保留（快照重建）
    expect(snap.messages.some((m) => m.type === 'chat')).toBe(true)
  })

  it('running 多轮会话 rebuild 只保留所有 user 消息（多轮 user 都从 chat_history 补）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', {
      ...runningDetail,
      chat_history: [
        { role: 'user', content: '第一问', ts: '2026-08-10T00:00:00' },
        { role: 'assistant', content: '第一答', ts: '2026-08-10T00:00:05', thinking: '', tool_calls: [] },
        { role: 'user', content: '第二问', ts: '2026-08-10T00:01:00' },
        { role: 'assistant', content: '', ts: '2026-08-10T00:01:05', thinking: '正在思考', tool_calls: [] },
      ],
    } as unknown as SessionDetail)
    const msgs = store.getSnapshot('s1').messages
    expect(msgs.filter((m) => m.type === 'user').map((m) => m.content)).toEqual(['第一问', '第二问'])
    expect(msgs.some((m) => m.type === 'chat')).toBe(false)
  })

  it('replay 后 journal 事件重建完整 assistant：reduce 从空累积出思考+工具+文本', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', runningDetail)
    // 模拟 resume(after_seq=0) 收到的 journal 事件（全量重放）
    store['applyEvent']('s1', { type: 'thinking_token', token: '日志里的完整思考', timestamp: '', seq: 1 } as SSEEvent)
    store['applyEvent']('s1', { type: 'tool_call', name: 'web_search', args: {}, iteration: 0, timestamp: '', seq: 2 } as SSEEvent)
    store['applyEvent']('s1', { type: 'chat_token', token: '完整回答', timestamp: '', seq: 3 } as SSEEvent)

    const msgs = store.getSnapshot('s1').messages
    // user + replay 重建的 chat
    expect(msgs).toHaveLength(2)
    expect(msgs[1].type).toBe('chat')
    // 思考、工具、文本都完整（来自 journal 全量重放，非残缺快照）
    const timeline = msgs[1].agentTimeline ?? []
    const thinkingTexts = timeline.filter((t) => t.type === 'thinking').map((t) => t.content)
    expect(thinkingTexts.join('')).toContain('日志里的完整思考')
    expect(msgs[1].chatResponse).toBe('完整回答')
  })
})

describe('StreamStore - rebuild completed 会话追问新建 chat', () => {
  it('completed 会话 rebuild 的 chat 不标 streaming（追问应新建）', () => {
    // 对照：已完成会话的最后一条 chat 不标 streaming，
    // 追问时 applyChatEventToLastChat 新建新一轮回复（不串字）
    const store = new StreamStore()
    store.rebuildSession('s1', {
      session_id: 's1',
      status: 'completed',
      session_type: 'chat',
      last_seq: 5,
      report_markdown: '',
      chart_data: {},
      chat_history: [
        { role: 'user', content: 'q', ts: '2026-08-10T00:00:00' },
        { role: 'assistant', content: '第一轮完整回复', ts: '2026-08-10T00:00:05', thinking: '', tool_calls: [] },
      ],
    } as never)

    const chat = store.getSnapshot('s1').messages.filter((m) => m.type === 'chat')
    expect(chat[0].streaming).toBeFalsy()

    // 追问续传 thinking_token 应新建第二条 chat
    store['applyEvent']('s1', { type: 'thinking_token', token: '第二轮思考', timestamp: '', seq: 6 } as SSEEvent)
    const chats = store.getSnapshot('s1').messages.filter((m) => m.type === 'chat')
    expect(chats).toHaveLength(2)
    expect(chats[0].chatResponse).toBe('第一轮完整回复') // 第一轮不被污染
  })
})

describe('StreamStore - 防御性清理', () => {
  it('pump 结束后清除 streaming 标志', async () => {
    const store = new StreamStore()
    store['streams'].set('s1', {
      phase: 'streaming',
      messages: [{ id: 'm1', type: 'chat', content: '', chatResponse: 'test', streaming: true }],
      lastSeq: 0,
    })

    // 模拟一个立即结束的 Response
    const mockResp = {
      body: {
        getReader: () => ({
          read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
          releaseLock: vi.fn(),
        }),
      },
    } as unknown as Response

    await store['pump']('s1', mockResp)

    const state = store.getSnapshot('s1')
    expect(state.messages[0].streaming).toBe(false)
    expect(state.phase).toBe('idle')
  })
})
