import { describe, it, expect } from 'vitest'
import type { SSEEvent, UIMessage, TimelineItem } from '../types'
import { applyPipelineThinkingToken } from '../timeline'

const baseMsg = (overrides: Partial<UIMessage> = {}): UIMessage => ({
  id: 'm1',
  type: 'chat',
  content: '',
  streaming: true,
  ...overrides,
})

const ev = (e: Record<string, unknown>): SSEEvent => e as unknown as SSEEvent

// 收窄到 thinking 变体：非 thinking 直接抛错（兼作断言），
// 使 .content/.done 访问通过严格类型检查（tsc -b）
const asThinking = (item: TimelineItem | undefined): Extract<TimelineItem, { type: 'thinking' }> => {
  if (!item || item.type !== 'thinking') throw new Error(`expected thinking item, got ${item?.type}`)
  return item
}

describe('applyPipelineThinkingToken - Send 扇出并行 agent 思考', () => {
  it('并行 agent 的 thinking 不互相收口(deep 模式 4 analyst 并行交错)', () => {
    // 模拟 Send 扇出:technical / fundamental token 交错到达
    let msg = baseMsg()
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'technical_analyst', token: 'T1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'fundamental_analyst', token: 'F1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'technical_analyst', token: 'T2' }))

    const tech = msg.nodeTimelines!['technical_analyst']
    const lastTech = asThinking(tech[tech.length - 1])
    expect(lastTech.type).toBe('thinking')
    // 不被 fundamental token 错误收口(修复前 done=true → UI 中途折叠思考)
    expect(lastTech.done).toBe(false)
    expect(lastTech.content).toBe('T1T2') // content 连续追加

    const fund = msg.nodeTimelines!['fundamental_analyst']
    expect(asThinking(fund[fund.length - 1]).done).toBe(false)
    expect(asThinking(fund[fund.length - 1]).content).toBe('F1')
  })

  it('同 node 连续 token 正常追加(单 agent 流式)', () => {
    let msg = baseMsg()
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'trader', token: 'A' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'trader', token: 'B' }))
    const trader = msg.nodeTimelines!['trader']
    expect(trader).toHaveLength(1)
    expect(asThinking(trader[0]).content).toBe('AB')
    expect(asThinking(trader[0]).done).toBe(false)
  })
})
