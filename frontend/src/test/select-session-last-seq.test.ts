import { describe, it, expect } from 'vitest'
import { StreamStore } from '../stores/streamStore'
import type { SessionDetail } from '../types'

// 刷新恢复架构修正：进行中会话走 journal full replay（rebuild 只保留 user 消息，
// lastSeq=0 让 resume 全量重放 journal）。本测试验证 lastSeq 续传游标的新语义。
//
// 历史：旧实现用 chat_history 快照重建 + last_seq 续传，后端 last_seq 是 journal
// 全量 max，用它做 after_seq 会跳过已 journal 但前端从未渲染的中间事件（流式文字
// 缺失根因）。现在 running/clarifying 强制 lastSeq=0，从第一个事件全量重放，
// 彻底消除「快照残缺 + 续传跳过」的丢失窗口。

function detail(status: string, lastSeq: number): SessionDetail {
  return {
    session_id: 's1', status, session_type: 'analysis', last_seq: lastSeq,
    chat_history: [{ role: 'user', content: 'q', ts: '2026-08-10T00:00:00' }],
  } as unknown as SessionDetail
}

describe('rebuildSession lastSeq 续传游标（journal replay 架构）', () => {
  it('running 会话 lastSeq=0（全量 replay，不跳过任何历史事件）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', detail('running', 100))
    expect(store.getSnapshot('s1').lastSeq).toBe(0)
  })

  it('clarifying 会话 lastSeq=0（同 running，全量 replay）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', detail('clarifying', 100))
    expect(store.getSnapshot('s1').lastSeq).toBe(0)
  })

  it('completed 会话 lastSeq=后端 last_seq（终态，不再 resume）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', detail('completed', 99))
    expect(store.getSnapshot('s1').lastSeq).toBe(99)
  })

  it('interrupted 会话 lastSeq=后端 last_seq（终态，不再 resume）', () => {
    const store = new StreamStore()
    store.rebuildSession('s1', detail('interrupted', 88))
    expect(store.getSnapshot('s1').lastSeq).toBe(88)
  })

  it('running 会话即使前端内存有旧 lastSeq 也强制归 0（刷新场景：内存已清空，但防御）', () => {
    // 刷新后 store 是新实例，existing.lastSeq 不存在；但即使切回一个内存中
    // 还有旧 lastSeq 的在途会话，rebuild 也应归 0（它要全量 replay 重建完整状态）
    const store = new StreamStore()
    store['streams'].set('s1', { phase: 'streaming', messages: [], lastSeq: 50, origin: 'live' })
    store.rebuildSession('s1', detail('running', 100))
    expect(store.getSnapshot('s1').lastSeq).toBe(0)
  })
})
