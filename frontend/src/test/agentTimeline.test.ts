import { describe, it, expect } from 'vitest'
import type { SSEEvent, TimelineItem, UIMessage } from '../types'
import {
  applyChatStreamEvent,
  applyPipelineThinkingToken,
  applyPipelineNodeComplete,
  buildTimelineFromHistory,
} from '../timeline'

// 对话流事件 -> agentTimeline 的 reducer 行为测试（agent-turn-box-display Task 2）
// 覆盖：思考断开、搜索 item 生命周期、tool_call item 生命周期、chat_done 标题提取、
// 管线 node 分组、历史恢复重建。

const baseMsg = (overrides: Partial<UIMessage> = {}): UIMessage => ({
  id: 'm1',
  type: 'chat',
  content: '',
  streaming: true,
  ...overrides,
})

const ev = (e: Record<string, unknown>): SSEEvent => e as unknown as SSEEvent

describe('applyChatStreamEvent - thinking_token 断开逻辑', () => {
  it('timeline 为空时收到 thinking_token，新建 thinking item', () => {
    const next = applyChatStreamEvent(baseMsg(), ev({ type: 'thinking_token', token: '第一段' }))
    expect(next.agentTimeline).toHaveLength(1)
    const item = next.agentTimeline![0]
    expect(item.type).toBe('thinking')
    if (item.type === 'thinking') expect(item.content).toBe('第一段')
  })

  it('末尾是 thinking item 时累加 token', () => {
    const msg = baseMsg({ agentTimeline: [{ type: 'thinking', content: '思考' }] })
    const next = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '继续' }))
    expect(next.agentTimeline).toHaveLength(1)
    const item = next.agentTimeline![0]
    if (item.type === 'thinking') expect(item.content).toBe('思考继续')
  })

  it('tool_call 事件后再收 thinking_token，新建 thinking item（不累加到旧 item）', () => {
    let msg = baseMsg()
    msg = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '思考1' }))
    msg = applyChatStreamEvent(msg, ev({ type: 'tool_call', name: 'search_stock', args: { query: '茅台' }, iteration: 1 }))
    msg = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '思考2' }))
    const types = msg.agentTimeline!.map(i => i.type)
    expect(types).toEqual(['thinking', 'tool_call', 'thinking'])
    const t1 = msg.agentTimeline![0]
    const t2 = msg.agentTimeline![2]
    if (t1.type === 'thinking') expect(t1.content).toBe('思考1')
    if (t2.type === 'thinking') expect(t2.content).toBe('思考2')
  })

  it('search_start 事件后再收 thinking_token，新建 thinking item', () => {
    let msg = baseMsg()
    msg = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '思考1' }))
    msg = applyChatStreamEvent(msg, ev({ type: 'search_start', query: '茅台' }))
    msg = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '思考2' }))
    expect(msg.agentTimeline!.map(i => i.type)).toEqual(['thinking', 'search', 'thinking'])
  })

  it('thinking_replace 替换末尾 thinking item 内容', () => {
    const msg = baseMsg({ agentTimeline: [{ type: 'thinking', content: '旧内容' }] })
    const next = applyChatStreamEvent(msg, ev({ type: 'thinking_replace', token: '新内容' }))
    const item = next.agentTimeline![0]
    if (item.type === 'thinking') expect(item.content).toBe('新内容')
  })

  it('thinking_to_answer 将末尾 thinking item 与 answer 匹配的部分移至 chatResponse', () => {
    const msg = baseMsg({ agentTimeline: [{ type: 'thinking', content: '思考轨迹最终回答内容' }] })
    const next = applyChatStreamEvent(msg, ev({ type: 'thinking_to_answer', answer: '最终回答内容' }))
    const item = next.agentTimeline![0]
    if (item.type === 'thinking') expect(item.content).toBe('思考轨迹')
    expect(next.chatResponse).toBe('最终回答内容')
  })
})

describe('applyChatStreamEvent - 搜索 item 生命周期', () => {
  it('search_start 新建 search item（status=searching）', () => {
    const next = applyChatStreamEvent(baseMsg(), ev({ type: 'search_start', query: '茅台' }))
    const item = next.agentTimeline![next.agentTimeline!.length - 1]
    expect(item.type).toBe('search')
    if (item.type === 'search') {
      expect(item.query).toBe('茅台')
      expect(item.status).toBe('searching')
    }
  })

  it('search_result 更新 search item 为 done 并写入 results', () => {
    let msg = applyChatStreamEvent(baseMsg(), ev({ type: 'search_start', query: '茅台' }))
    const results = [{ title: 't', url: 'https://a.com', content: 'c' }]
    msg = applyChatStreamEvent(msg, ev({ type: 'search_result', query: '茅台', results, count: 1 }))
    const item = msg.agentTimeline![0]
    if (item.type === 'search') {
      expect(item.status).toBe('done')
      expect(item.results).toHaveLength(1)
    }
  })

  it('search_error 更新 search item 为 error', () => {
    let msg = applyChatStreamEvent(baseMsg(), ev({ type: 'search_start', query: '茅台' }))
    msg = applyChatStreamEvent(msg, ev({ type: 'search_error', message: 'fail' }))
    const item = msg.agentTimeline![0]
    if (item.type === 'search') expect(item.status).toBe('error')
  })
})

describe('applyChatStreamEvent - tool_call item 生命周期', () => {
  it('tool_call（非搜索类）新建 tool_call item（done=false）', () => {
    const next = applyChatStreamEvent(baseMsg(), ev({ type: 'tool_call', name: 'search_stock', args: { query: '茅台' }, iteration: 1 }))
    const item = next.agentTimeline![0]
    expect(item.type).toBe('tool_call')
    if (item.type === 'tool_call') {
      expect(item.name).toBe('search_stock')
      expect(item.done).toBe(false)
    }
  })

  it('搜索类 tool_call 不生成 tool_call item', () => {
    const next = applyChatStreamEvent(baseMsg(), ev({ type: 'tool_call', name: 'web_search', args: { query: '茅台' }, iteration: 1 }))
    expect(next.agentTimeline ?? []).toHaveLength(0)
  })

  it('tool_result 优先更新同名且 done=false 的最近 item', () => {
    let msg = applyChatStreamEvent(baseMsg(), ev({ type: 'tool_call', name: 'search_stock', args: { query: '茅台' }, iteration: 1 }))
    msg = applyChatStreamEvent(msg, ev({ type: 'tool_result', name: 'search_stock', result: '已识别' }))
    const item = msg.agentTimeline![0]
    if (item.type === 'tool_call') {
      expect(item.done).toBe(true)
      expect(item.result).toBe('已识别')
    }
  })

  it('tool_result 无同名未完成时回退到最近未完成的任意 tool_call item', () => {
    let msg = applyChatStreamEvent(baseMsg(), ev({ type: 'tool_call', name: 'tool_a', args: {}, iteration: 1 }))
    msg = applyChatStreamEvent(msg, ev({ type: 'tool_result', name: 'tool_b', result: 'res' }))
    const item = msg.agentTimeline![0]
    if (item.type === 'tool_call') {
      expect(item.done).toBe(true)
      expect(item.result).toBe('res')
    }
  })

  it('tool_result 无任何匹配且结果非空时新建仅含结果的 item', () => {
    const msg = applyChatStreamEvent(baseMsg(), ev({ type: 'tool_result', name: 'search_stock', result: '已识别' }))
    const item = msg.agentTimeline![0]
    if (item.type === 'tool_call') {
      expect(item.done).toBe(true)
      expect(item.result).toBe('已识别')
    }
  })

  it('搜索类 tool_result 不更新/不新建 tool_call item', () => {
    const msg = applyChatStreamEvent(baseMsg(), ev({ type: 'tool_result', name: 'web_search', result: [] }))
    expect(msg.agentTimeline ?? []).toHaveLength(0)
  })
})

describe('applyChatStreamEvent - chat_token / chat_done / error', () => {
  it('chat_token 累加到 chatResponse', () => {
    const msg = baseMsg({ chatResponse: '前半' })
    const next = applyChatStreamEvent(msg, ev({ type: 'chat_token', token: '后半' }))
    expect(next.chatResponse).toBe('前半后半')
  })

  it('chat_done 时所有 thinking item 用 extractThinkingTitle 提取标题写入 title', () => {
    const msg = baseMsg({
      agentTimeline: [
        { type: 'thinking', content: '## 标题一\n内容一' },
        { type: 'search', query: 'q', status: 'done' },
        { type: 'thinking', content: '无标题内容' },
      ],
    })
    const next = applyChatStreamEvent(msg, ev({ type: 'chat_done' }))
    expect(next.streaming).toBe(false)
    const t1 = next.agentTimeline![0]
    const t2 = next.agentTimeline![2]
    if (t1.type === 'thinking') expect(t1.title).toBe('标题一')
    if (t2.type === 'thinking') expect(t2.title).toBeUndefined()
  })

  it('error 事件设置 chatResponse 并结束 streaming', () => {
    const next = applyChatStreamEvent(baseMsg(), ev({ type: 'error', message: '出错了' }))
    expect(next.streaming).toBe(false)
    expect(next.chatResponse).toContain('出错了')
  })
})

describe('applyChatStreamEvent - 思考横幅显式完成态（fix-pipeline-banner-and-eta）', () => {
  it('tool_call 事件将末尾未完成 thinking item 置 done=true', () => {
    let msg = baseMsg()
    msg = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '思考中' }))
    msg = applyChatStreamEvent(msg, ev({ type: 'tool_call', name: 'search_stock', args: { query: '茅台' }, iteration: 1 }))
    const thinking = msg.agentTimeline![0]
    if (thinking.type === 'thinking') expect(thinking.done).toBe(true)
  })

  it('首个 chat_token 将末尾未完成 thinking item 置 done=true', () => {
    let msg = baseMsg()
    msg = applyChatStreamEvent(msg, ev({ type: 'thinking_token', token: '思考中' }))
    msg = applyChatStreamEvent(msg, ev({ type: 'chat_token', token: '回答' }))
    const thinking = msg.agentTimeline![0]
    if (thinking.type === 'thinking') expect(thinking.done).toBe(true)
  })

  it('thinking_to_answer 将该 thinking item 置 done=true', () => {
    const msg = baseMsg({ agentTimeline: [{ type: 'thinking', content: '思考轨迹最终回答内容' }] })
    const next = applyChatStreamEvent(msg, ev({ type: 'thinking_to_answer', answer: '最终回答内容' }))
    const item = next.agentTimeline![0]
    if (item.type === 'thinking') expect(item.done).toBe(true)
  })

  it('chat_done 将所有 thinking item 置 done=true', () => {
    const msg = baseMsg({
      agentTimeline: [
        { type: 'thinking', content: '## 标题\n内容' },
        { type: 'search', query: 'q', status: 'done' },
        { type: 'thinking', content: '第二段' },
      ],
    })
    const next = applyChatStreamEvent(msg, ev({ type: 'chat_done' }))
    for (const item of next.agentTimeline!) {
      if (item.type === 'thinking') expect(item.done).toBe(true)
    }
  })

  it('error 将所有未完成 thinking item 置 done=true', () => {
    const msg = baseMsg({
      agentTimeline: [{ type: 'thinking', content: '思考中' }],
    })
    const next = applyChatStreamEvent(msg, ev({ type: 'error', message: 'fail' }))
    const item = next.agentTimeline![0]
    if (item.type === 'thinking') expect(item.done).toBe(true)
  })

  it('新建 thinking item 默认 done=false', () => {
    const next = applyChatStreamEvent(baseMsg(), ev({ type: 'thinking_token', token: '新思考' }))
    const item = next.agentTimeline![0]
    if (item.type === 'thinking') expect(item.done).toBe(false)
  })
})

describe('applyPipelineThinkingToken - 管线按 node 分组', () => {
  it('thinking_token 按 node 字段写入对应 node 的 timeline', () => {
    let msg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '多头观点', node: 'bull_r1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '空头观点', node: 'bear_r1' }))
    expect(msg.nodeTimelines!['bull_r1']).toHaveLength(1)
    expect(msg.nodeTimelines!['bear_r1']).toHaveLength(1)
    const bull = msg.nodeTimelines!['bull_r1'][0]
    if (bull.type === 'thinking') expect(bull.content).toBe('多头观点')
  })

  it('同 node 连续 thinking_token 累加，不换 node 不断开', () => {
    let msg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: 'A', node: 'bull_r1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: 'B', node: 'bull_r1' }))
    const bull = msg.nodeTimelines!['bull_r1']
    expect(bull).toHaveLength(1)
    if (bull[0].type === 'thinking') expect(bull[0].content).toBe('AB')
  })

  it('收到其他节点 thinking_token 时，不收口其他节点（由 node_complete 显式收口，支持 Send 并行）', () => {
    let msg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '多头思考', node: 'bull_r1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '空头思考', node: 'bear_r1' }))
    const bull = msg.nodeTimelines!['bull_r1'][0]
    // 不被 bear token 收口——并行 agent(Send 扇出)与串行辩论均由 node_complete 收口
    if (bull.type === 'thinking') expect(bull.done).toBe(false)
    const bear = msg.nodeTimelines!['bear_r1'][0]
    if (bear.type === 'thinking') expect(bear.done).toBe(false)
  })
})

describe('applyPipelineNodeComplete - 节点完成收口思考横幅（fix-pipeline-banner-and-eta）', () => {
  it('node_complete 将该节点末尾 thinking item 置 done=true', () => {
    let msg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '多头思考', node: 'bull_r1' }))
    msg = applyPipelineNodeComplete(msg, 'bull_r1')
    const bull = msg.nodeTimelines!['bull_r1'][0]
    if (bull.type === 'thinking') expect(bull.done).toBe(true)
  })

  it('node_complete 不影响其他节点的 thinking item', () => {
    let msg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '多头', node: 'bull_r1' }))
    msg = applyPipelineThinkingToken(msg, ev({ type: 'thinking_token', token: '空头', node: 'bear_r1' }))
    msg = applyPipelineNodeComplete(msg, 'bull_r1')
    const bear = msg.nodeTimelines!['bear_r1'][0]
    if (bear.type === 'thinking') expect(bear.done).toBe(false)
  })

  it('节点无 timeline 时 node_complete 不报错', () => {
    const msg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const next = applyPipelineNodeComplete(msg, 'bull_r1')
    expect(next).toEqual(msg)
  })
})

describe('buildTimelineFromHistory - 历史恢复重建', () => {
  it('从 thinking + tool_calls 重建 agentTimeline（思考在前、工具调用在后）', () => {
    const timeline = buildTimelineFromHistory('## 复盘\n思考内容', [
      { name: 'search_stock', args: { query: '茅台' }, result_text: '已识别', done: true },
    ])
    expect(timeline.map(i => i.type)).toEqual(['thinking', 'tool_call'])
    const t = timeline[0]
    if (t.type === 'thinking') expect(t.title).toBe('复盘')
    const tc = timeline[1]
    if (tc.type === 'tool_call') {
      expect(tc.name).toBe('search_stock')
      expect(tc.done).toBe(true)
    }
  })

  it('搜索类工具不还原为 tool_call item', () => {
    const timeline = buildTimelineFromHistory(undefined, [
      { name: 'web_search', args: { query: '茅台' }, done: true },
    ])
    expect(timeline.filter(i => i.type === 'tool_call')).toHaveLength(0)
  })

  it('thinking 为空时不生成 thinking item', () => {
    const timeline = buildTimelineFromHistory('', [])
    expect(timeline).toHaveLength(0)
  })
})
