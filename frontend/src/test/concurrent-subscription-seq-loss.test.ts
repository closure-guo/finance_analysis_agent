/**
 * 回归：并发 SSE 订阅共享 state.lastSeq 会互相误判「旧事件」丢弃整个 token。
 *
 * 根因（后端日志实证 token 完整、前端随机丢整 token）：
 * startAnalysis 的实时流（App.tsx seq 去重）与 resumeStream 共享同一 sessionId 的
 * StreamState.lastSeq。两条订阅同时活跃时各自字节流进度不同步：实时流处理 seq=8
 * 置 lastSeq=8 后，resume 流的 seq=2..7 被判为旧事件丢弃 —— 而这些 token 实时流
 * 尚未处理，于是永久丢失。
 *
 * 症状：thinking/chat 两条流都概率性错乱（随机缺整个 token，如「中环海陆（301040）」
 * 变成「中陆301040」），刷新后走 chat_history 落库文本恢复正常。
 *
 * 修复：resumeStream 启动前中断已有活跃订阅（state.abort.abort()），保证同一会话
 * 同一时刻只有一条订阅消费 lastSeq。
 */
import { describe, it, expect } from 'vitest'

class SharedStreamState {
  lastSeq = 0
  abort: AbortController | null = null
}

/** 一条 SSE 订阅：按 seq 去重消费（与 App.tsx 去重逻辑同构）。 */
function consumeEvents(
  state: SharedStreamState,
  abort: AbortController,
  events: Array<{ seq: number; token: string }>,
): string[] {
  const accepted: string[] = []
  for (const ev of events) {
    // abort 后停止消费（与 App.tsx 的 signal.aborted 检查同构）
    if (abort.signal.aborted) break
    if (ev.seq <= state.lastSeq) continue
    state.lastSeq = ev.seq
    accepted.push(ev.token)
  }
  return accepted
}

/** 模拟 resumeStream 的启动：中断已有活跃订阅后再建立自己的订阅。 */
function startResumeSubscription(state: SharedStreamState): AbortController {
  if (state.abort && !state.abort.signal.aborted) {
    state.abort.abort()
  }
  const ctrl = new AbortController()
  state.abort = ctrl
  return ctrl
}

const ALL_EVENTS = [
  { seq: 1, token: '中' },
  { seq: 2, token: '环' },
  { seq: 3, token: '海' },
  { seq: 4, token: '陆' },
  { seq: 5, token: '（' },
  { seq: 6, token: '301' },
  { seq: 7, token: '040' },
  { seq: 8, token: '）' },
]
const EXPECTED = '中环海陆（301040）'

describe('SSE 订阅并发与 lastSeq', () => {
  it('resumeStream 启动前中断旧订阅：单一活跃订阅消费全部 token 不丢失', () => {
    const state = new SharedStreamState()

    // 实时流建立订阅并消费前 4 个事件（seq 1..4）
    const realtimeCtrl = new AbortController()
    state.abort = realtimeCtrl
    const fromRealtime = consumeEvents(state, realtimeCtrl, ALL_EVENTS.slice(0, 4))
    expect(fromRealtime.join('')).toBe('中环海陆')

    // resume 启动：中断旧订阅（关键修复），从 after_seq=lastSeq 续传剩余事件
    const resumeCtrl = startResumeSubscription(state)
    expect(realtimeCtrl.signal.aborted).toBe(true)

    const remaining = ALL_EVENTS.filter(e => e.seq > state.lastSeq)
    const fromResume = consumeEvents(state, resumeCtrl, remaining)

    const rendered = [...fromRealtime, ...fromResume].join('')
    expect(rendered).toBe(EXPECTED)
  })

  it('旧订阅被中断后不再消费事件，不会与新订阅争抢 lastSeq', () => {
    const state = new SharedStreamState()
    const realtimeCtrl = new AbortController()
    state.abort = realtimeCtrl

    // resume 启动即中断实时流
    const resumeCtrl = startResumeSubscription(state)

    // 被中断的实时流即使还有事件到达，也不再消费（不推进 lastSeq）
    const fromAbortedRealtime = consumeEvents(state, realtimeCtrl, ALL_EVENTS)
    expect(fromAbortedRealtime).toEqual([])
    expect(state.lastSeq).toBe(0)

    // 新订阅完整消费全部 token
    const fromResume = consumeEvents(state, resumeCtrl, ALL_EVENTS)
    expect(fromResume.join('')).toBe(EXPECTED)
  })
})
