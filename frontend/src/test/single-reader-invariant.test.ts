import { describe, it, expect, vi } from 'vitest'
import { StreamStore } from '../stores/streamStore'

// 回归：两个会话同时流式输出时文字错乱/丢失。
//
// 根因（用户实测确认后端跨会话隔离正常，问题在前端）：
// 旧结构的 abortRef/assistantMsgIdRef 是页面级单例，三个 SSE 入口都直接
// `abortRef.current = newController` 覆盖旧值而不先 abort 它——旧 reader 失控，
// 继续运行并写全局 assistantMsgIdRef → 两条流的 token 交叉写入 → 必然串字。
//
// 迁移说明：ensureSingleReader 已随重构内化为 StreamStore 的单读取器结构——
// activeReader 单例字段，submit/resume/switchSession/cancel 任一写路径
// 都先 abort 现存 reader 再建立新绑定，结构性保证同一时刻仅一条 reader。
// 本测试验证该内化语义。

describe('单读取器不变量（StreamStore 结构性保证）', () => {

  it('submit 前存在活跃 reader 时应 abort 它', async () => {
    const store = new StreamStore()
    const oldAbort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort: oldAbort }

    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    const promise = store.submit({
      query: 'test', api_key: 'key', user_id: 'u1', analysis_type: 'comprehensive', session_id: 's2',
    })
    await new Promise((r) => setTimeout(r, 10))

    expect(oldAbort.signal.aborted).toBe(true)

    globalThis.fetch = originalFetch
    await promise.catch(() => {})
  })

  it('resume 前存在活跃 reader 时应 abort 它', async () => {
    const store = new StreamStore()
    const oldAbort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort: oldAbort }
    store['streams'].set('s2', { phase: 'idle', messages: [], lastSeq: 0 })

    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    await store.resume('s2')

    expect(oldAbort.signal.aborted).toBe(true)
    globalThis.fetch = originalFetch
  })

  it('switchSession abort 当前 reader', () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort }

    store.switchSession('s2')

    expect(abort.signal.aborted).toBe(true)
    expect(store['activeReader']).toBeNull()
  })

  it('cancel abort 目标会话的 reader', async () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort }
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 0 })

    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true })

    await store.cancel('s1')

    expect(abort.signal.aborted).toBe(true)
    expect(store['activeReader']).toBeNull()
    globalThis.fetch = originalFetch
  })

  it('关键回归：连续触发多条 reader 路径时旧 reader 全部被中断', async () => {
    // 模拟旧根因场景：A 流式中用户切到 B（resume），再从 B 发起新提交
    const store = new StreamStore()
    const readerA = new AbortController()
    store['activeReader'] = { sessionId: 'A', abort: readerA }
    store['streams'].set('B', { phase: 'idle', messages: [], lastSeq: 0 })

    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    // 切到 B：A 被中断
    const resumePromise = store.resume('B')
    const readerB = store['activeReader']?.abort
    expect(readerB).toBeDefined()
    await resumePromise
    expect(readerA.signal.aborted).toBe(true)
    // resume 的 fetch 已 reject（AbortError），reader 引用已释放
    expect(store['activeReader']).toBeNull()

    // 从 B 发起新提交：入口 abort 残留 reader（幂等，旧 readerB 已 abort）并建立新 reader
    const submitPromise = store.submit({
      message: '追问', api_key: 'key', user_id: 'u1', session_id: 'B',
    })
    const readerB2 = store['activeReader']?.abort
    expect(readerB2).toBeDefined()
    expect(readerB2!.signal.aborted).toBe(false)
    await submitPromise

    globalThis.fetch = originalFetch
  })

  it('abortAll（页面卸载）中断当前 reader', () => {
    const store = new StreamStore()
    const abort = new AbortController()
    store['activeReader'] = { sessionId: 's1', abort }

    store.abortAll()

    expect(abort.signal.aborted).toBe(true)
    expect(store['activeReader']).toBeNull()
  })
})
