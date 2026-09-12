// streamStore 迭代计数测试（add-pipeline-graph-view Task 2，TDD 先行）
// node_start 重复到达同一 node_id 时，管线消息的 nodeStartCounts[node_id] 累计，
// 供 graphModel 迭代徽标使用；node_timing/node_complete 不累计。
import { describe, expect, it } from 'vitest'
import { reduce } from '../stores/streamStore/reduce'
import { IDLE_STATE, resetMsgIdCounter, type SessionStreamState } from '../stores/streamStore/types'
import type { SSEEvent, UIMessage } from '../types'

function stateWithPipeline(): SessionStreamState {
  resetMsgIdCounter()
  const msg: UIMessage = {
    id: 'msg-1',
    type: 'pipeline',
    content: '',
    completedNodes: [],
    currentNode: '',
    nodeOutputs: {},
    progress: 0,
    startedAt: 1000,
  }
  return { ...IDLE_STATE, phase: 'streaming' as const, messages: [msg] }
}

function nodeStart(nodeId: string): SSEEvent {
  return { type: 'node_start', node_id: nodeId, layer: 'Layer I', desc: nodeId, seq: 1 } as unknown as SSEEvent
}

function lastMsg(state: { messages: UIMessage[] }): UIMessage {
  return state.messages[state.messages.length - 1]
}

describe('streamStore node_start 迭代计数', () => {
  it('首次 node_start 计数为 1，重跑累计为 2', () => {
    let state = stateWithPipeline()
    state = reduce(state, nodeStart('trader'))
    expect(lastMsg(state).nodeStartCounts?.['trader']).toBe(1)
    state = reduce(state, nodeStart('trader'))
    expect(lastMsg(state).nodeStartCounts?.['trader']).toBe(2)
  })

  it('不同节点计数互不影响；node_timing/node_complete 不累计', () => {
    let state = stateWithPipeline()
    state = reduce(state, nodeStart('trader'))
    state = reduce(state, nodeStart('fund_manager'))
    state = reduce(state, { type: 'node_timing', node_id: 'trader' } as unknown as SSEEvent)
    state = reduce(state, { type: 'node_complete', node_id: 'trader', layer: 'Trader', desc: '', completed: [], progress: 0.5 } as unknown as SSEEvent)
    const msg = lastMsg(state)
    expect(msg.nodeStartCounts).toEqual({ trader: 1, fund_manager: 1 })
  })

  it('nodeStartCounts 为可选字段：无重跑场景不产生 undefined 噪声', () => {
    let state = stateWithPipeline()
    state = reduce(state, nodeStart('trader'))
    const counts = lastMsg(state).nodeStartCounts!
    expect(Object.keys(counts)).toEqual(['trader'])
  })
})
