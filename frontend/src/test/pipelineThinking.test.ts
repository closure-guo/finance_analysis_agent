import { describe, it, expect } from 'vitest'
import type { SSEEvent, UIMessage } from '../types'
import { applyPipelineThinkingToken } from '../timeline'

const baseMsg = (overrides: Partial<UIMessage> = {}): UIMessage => ({
  id: 'm1',
  type: 'chat',
  content: '',
  streaming: true,
  ...overrides,
})

const ev = (e: Record<string, unknown>): SSEEvent => e as unknown as SSEEvent

describe('applyPipelineThinkingToken - Send 扇出并行 agent 思考', () => {
  it('并行 agent 的 thinking 不互相收口(deep 模式 4 analyst 并行交错)', () => {
    // 模拟 Send 扇出:technical / fundamental token 交错到达
    let msg = baseMsg()
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'technical_analyst', token: 'T1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'fundamental_analyst', token: 'F1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'technical_analyst', token: 'T2' }))

    const tech = msg.nodeTimelines!['technical_analyst']
    const lastTech = tech[tech.length - 1]
    expect(lastTech.type).toBe('thinking')
    // 不被 fundamental token 错误收口(修复前 done=true → UI 中途折叠思考)
    expect(lastTech.done).toBe(false)
    expect(lastTech.content).toBe('T1T2') // content 连续追加

    const fund = msg.nodeTimelines!['fundamental_analyst']
    expect(fund[fund.length - 1].done).toBe(false)
    expect(fund[fund.length - 1].content).toBe('F1')
  })

  it('同 node 连续 token 正常追加(单 agent 流式)', () => {
    let msg = baseMsg()
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'trader', token: 'A' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', node: 'trader', token: 'B' }))
    const trader = msg.nodeTimelines!['trader']
    expect(trader).toHaveLength(1)
    expect(trader[0].content).toBe('AB')
    expect(trader[0].done).toBe(false)
  })
})
