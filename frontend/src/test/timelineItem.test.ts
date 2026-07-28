import { describe, it, expect } from 'vitest'
import type { TimelineItem, UIMessage } from '../types'

// TimelineItem 联合类型结构校验（types.ts 新增 agentTimeline 的前置契约）
describe('TimelineItem 联合类型', () => {
  it('thinking 片段：content 必填，title 可选', () => {
    const item: TimelineItem = { type: 'thinking', content: '## 分析\n内容' }
    expect(item.type).toBe('thinking')
    if (item.type === 'thinking') {
      expect(item.content).toContain('分析')
      expect(item.title).toBeUndefined()
    }
    const titled: TimelineItem = { type: 'thinking', content: '内容', title: '标题' }
    if (titled.type === 'thinking') {
      expect(titled.title).toBe('标题')
    }
  })

  it('search 片段：query/status 必填，results 可选，status 为三态', () => {
    const searching: TimelineItem = { type: 'search', query: '茅台', status: 'searching' }
    if (searching.type === 'search') {
      expect(searching.status).toBe('searching')
      expect(searching.results).toBeUndefined()
    }
    const done: TimelineItem = {
      type: 'search',
      query: '茅台',
      status: 'done',
      results: [{ title: 't', url: 'https://a.com', content: 'c' }],
    }
    if (done.type === 'search') {
      expect(done.results).toHaveLength(1)
    }
    const error: TimelineItem = { type: 'search', query: 'q', status: 'error' }
    expect(error.type).toBe('search')
  })

  it('tool_call 片段：name/args/done 必填，result 可选', () => {
    const pending: TimelineItem = { type: 'tool_call', name: 'search_stock', args: '茅台', done: false }
    if (pending.type === 'tool_call') {
      expect(pending.done).toBe(false)
      expect(pending.result).toBeUndefined()
    }
    const finished: TimelineItem = {
      type: 'tool_call',
      name: 'search_stock',
      args: '茅台',
      result: '已识别：贵州茅台 (600519)',
      done: true,
    }
    if (finished.type === 'tool_call') {
      expect(finished.done).toBe(true)
      expect(finished.result).toContain('600519')
    }
  })

  it('UIMessage 包含 agentTimeline: TimelineItem[]', () => {
    const msg: UIMessage = {
      id: 'm1',
      type: 'chat',
      content: '',
      agentTimeline: [
        { type: 'thinking', content: '思考1' },
        { type: 'search', query: 'q', status: 'searching' },
        { type: 'thinking', content: '思考2' },
      ],
    }
    expect(msg.agentTimeline).toHaveLength(3)
    expect(msg.agentTimeline?.map(i => i.type)).toEqual(['thinking', 'search', 'thinking'])
  })
})
