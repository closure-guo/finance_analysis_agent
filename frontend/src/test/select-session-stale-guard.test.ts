import { describe, it, expect } from 'vitest'
import { StreamStore } from '../stores/streamStore'

// 回归：selectSession 是 async 函数，await fetch 期间用户可能已切换到其他会话。
// fetch 返回后若无 stale guard，会为已切走的会话启动 resumeStream，
// 导致两个 resumeStream reader 并发——它们竞争覆盖全局 streamingSessionIdRef.current，
// 使隔离检查使用错误的值，chat_token 等增量事件被误判为「非当前视图」丢弃 → 内容缺失。
//
// 迁移说明：stale guard（shouldProcessFetchedSession）与会话隔离（isCurrentViewEvent）
// 已随重构被结构性消除——
// 1. 事件按 sessionId 分流写入各自会话状态，无「当前视图」运行时判断；
// 2. switchSession 原子化：abort 旧 reader + 目标会话置 pending，交错调用无共享游标可竞争；
// 3. 单读取器不变量：任何时刻仅一条 reader，旧 reader 在新操作前必然被 abort。
// 本测试验证这些内化语义覆盖原守卫场景。

describe('selectSession 并发竞态防护（switchSession 原子协议）', () => {

  describe('切换原子性（stale guard 的结构性替代）', () => {
    it('切换时旧 reader 必然被 abort（fetch 挂起期间无并发 reader）', () => {
      const store = new StreamStore()
      const abortA = new AbortController()
      store['activeReader'] = { sessionId: 'A', abort: abortA }

      // 用户从 A 切到 B：A 的 reader 立即中断，B 置 pending
      store.switchSession('B')

      expect(abortA.signal.aborted).toBe(true)
      expect(store['activeReader']).toBeNull()
      expect(store.getSnapshot('B').origin).toBe('pending')
    })

    it('快速切换 A→B→A：每次切换都 abort 当前 reader，无交错 reader 存活', () => {
      const store = new StreamStore()
      const abortA = new AbortController()
      store['activeReader'] = { sessionId: 'A', abort: abortA }
      store.switchSession('B')

      const abortB = new AbortController()
      store['activeReader'] = { sessionId: 'B', abort: abortB }
      store.switchSession('A')

      expect(abortA.signal.aborted).toBe(true)
      expect(abortB.signal.aborted).toBe(true)
      expect(store['activeReader']).toBeNull()
    })

    it('切回 live 在途会话：状态原样保留（事件流持续写入，无需重建）', () => {
      const store = new StreamStore()
      store['streams'].set('A', {
        phase: 'streaming',
        messages: [{ id: 'm1', type: 'chat', content: '', chatResponse: '在途内容' }],
        lastSeq: 10,
        origin: 'live',
      })

      store.switchSession('A')

      const state = store.getSnapshot('A')
      expect(state.messages).toHaveLength(1)
      expect(state.lastSeq).toBe(10)
    })

    it('switchSession(null)（新建分析）仅断开订阅，不触碰会话状态', () => {
      const store = new StreamStore()
      const abortA = new AbortController()
      store['activeReader'] = { sessionId: 'A', abort: abortA }
      store['streams'].set('A', {
        phase: 'streaming',
        messages: [{ id: 'm1', type: 'chat', content: '', chatResponse: '在途内容' }],
        lastSeq: 10,
        origin: 'live',
      })

      store.switchSession(null)

      expect(abortA.signal.aborted).toBe(true)
      // A 的 live 状态保留：切回时直接展示
      expect(store.getSnapshot('A').messages).toHaveLength(1)
    })
  })

  describe('事件按 sessionId 分流（视图隔离的结构性替代）', () => {
    it('迟到事件写入其归属会话，与当前视图无关', () => {
      const store = new StreamStore()
      store['streams'].set('A', { phase: 'streaming', messages: [], lastSeq: 0 })
      store['streams'].set('B', { phase: 'streaming', messages: [], lastSeq: 0 })

      // 用户视图在 B，A 的迟到事件到达：写入 A，不污染 B，也不丢弃
      store['applyEvent']('A', { type: 'chat_token', token: 'A的内容', timestamp: '', seq: 1 } as never)
      store['applyEvent']('B', { type: 'chat_token', token: 'B的内容', timestamp: '', seq: 1 } as never)

      expect(store.getSnapshot('A').messages[0].chatResponse).toBe('A的内容')
      expect(store.getSnapshot('B').messages[0].chatResponse).toBe('B的内容')
    })

    it('关键回归：无共享 streamingSessionIdRef，交错 reader 不存在隔离误判', () => {
      // 旧根因：两个 resumeStream 并发，后启动者覆盖全局 streamingSessionIdRef，
      // 使先启动 reader 的事件被误判「非当前视图」丢弃。
      // 新结构：事件分流只依赖 applyEvent 的 sessionId 参数（reader 局部绑定），
      // 无任何全局游标参与路由判断。
      const store = new StreamStore()
      store['streams'].set('A', { phase: 'streaming', messages: [], lastSeq: 0 })

      // A 的完整 token 序列全部写入（旧结构下 seq 9+ 会被隔离丢弃）
      const tokens = ['这是', '一段', '测试用的', '固定回复。', '用于验证', '流式渲染', '的增量累积。']
      tokens.forEach((token, i) => {
        store['applyEvent']('A', { type: 'chat_token', token, timestamp: '', seq: i + 1 } as never)
      })

      expect(store.getSnapshot('A').messages[0].chatResponse).toBe(
        '这是一段测试用的固定回复。用于验证流式渲染的增量累积。',
      )
    })
  })
})
