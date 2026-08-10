import { describe, it, expect } from 'vitest'
import { StreamStore } from '../stores/streamStore'
import type { SSEEvent } from '../types'

// 回归：两会话并发流式输出时，后启动会话的文本后半段整段丢失。
//
// 根因（E2E concurrent-streaming-integrity.spec.ts 复现 + SSE 轨迹定位）：
// startAnalysis/quickChat 处理 session_created 事件时只调 setAndPersistSession()，
// 它触发 React setState，但 currentSessionIdRef.current 要等 useEffect 才异步同步。
// 在这个同步窗口内到达的 chat_token 被会话隔离分支误判为「非当前视图」丢弃 → 整段缺失。
//
// E2E 实测轨迹（修复前）：seq 5-8 渲染成功，seq 9/10/11 全部丢失。
//
// 迁移说明：会话隔离检查已随重构被结构性消除——
// session_created 在 store 内完成 key 迁移（临时 key '' → 实际 sessionId），
// 后续事件经 reader 局部绑定的 sessionId 分流写入，不经过任何「当前视图」运行时判断，
// 也不依赖 React ref 的同步时序。本测试验证迁移后 seq 序列完整无丢失。

describe('session_created key 迁移（并发流式文本完整性）', () => {

  it('session_created 把临时 key 的状态迁移到实际 sessionId', () => {
    const store = new StreamStore()
    // submit 预提交的用户消息挂在临时 key '' 上
    store['streams'].set('', {
      phase: 'connecting',
      messages: [{ id: 'm1', type: 'user', content: '分析平安银行' }],
      lastSeq: 0,
      origin: 'live',
    })

    store['applyEvent']('', { type: 'session_created', session_id: 'session-B', display_name: '平安银行', timestamp: '', seq: 1 } as SSEEvent)

    expect(store['streams'].has('')).toBe(false)
    const state = store.getSnapshot('session-B')
    expect(state.messages[0].content).toBe('分析平安银行')
    expect(state.lastSeq).toBe(1)
  })

  it('reader 绑定随 key 迁移更新，后续事件写入实际 sessionId', () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: '', abort }
    store['streams'].set('', { phase: 'connecting', messages: [], lastSeq: 0, origin: 'live' })

    store['applyEvent']('', { type: 'session_created', session_id: 'session-B', display_name: '', timestamp: '', seq: 1 } as SSEEvent)

    expect(store['activeReader']?.sessionId).toBe('session-B')
  })

  it('迁移后完整 seq 序列全部写入（旧结构下 seq 9+ 会被隔离丢弃）', () => {
    const store = new StreamStore()
    store['streams'].set('', { phase: 'connecting', messages: [], lastSeq: 0, origin: 'live' })

    // seq 连续序列（含 session_created seq=1）：seq 空洞检测只在跳号时触发 resync
    const events: SSEEvent[] = [
      { type: 'session_created', session_id: 'session-B', display_name: '', timestamp: '', seq: 1 } as SSEEvent,
      { type: 'chat_token', token: '这是', timestamp: '', seq: 2 } as SSEEvent,
      { type: 'chat_token', token: '一段', timestamp: '', seq: 3 } as SSEEvent,
      { type: 'chat_token', token: '测试用的', timestamp: '', seq: 4 } as SSEEvent,
      { type: 'chat_token', token: '固定回复。', timestamp: '', seq: 5 } as SSEEvent,
      { type: 'chat_token', token: '用于验证', timestamp: '', seq: 6 } as SSEEvent,
      { type: 'chat_token', token: '流式渲染', timestamp: '', seq: 7 } as SSEEvent,
      { type: 'chat_token', token: '的增量累积。', timestamp: '', seq: 8 } as SSEEvent,
    ]
    let key = ''
    for (const event of events) {
      store['applyEvent'](key, event)
      if (event.type === 'session_created') key = event.session_id
    }

    expect(store.getSnapshot('session-B').messages[0].chatResponse).toBe(
      '这是一段测试用的固定回复。用于验证流式渲染的增量累积。',
    )
  })

  it('并发场景：两会话各自绑定后事件互不干扰', () => {
    const store = new StreamStore()
    store['streams'].set('session-A', { phase: 'streaming', messages: [], lastSeq: 0 })
    store['streams'].set('session-B', { phase: 'streaming', messages: [], lastSeq: 0 })

    store['applyEvent']('session-A', { type: 'chat_token', token: 'A', timestamp: '', seq: 1 } as SSEEvent)
    store['applyEvent']('session-B', { type: 'chat_token', token: 'B', timestamp: '', seq: 1 } as SSEEvent)

    expect(store.getSnapshot('session-A').messages[0].chatResponse).toBe('A')
    expect(store.getSnapshot('session-B').messages[0].chatResponse).toBe('B')
  })
})
