import { describe, it, expect } from 'vitest'
import type { TimelineItem } from '../types'
import { deserializeTimeline, deserializeNodeTimelines } from '../timeline'

// 持久化时序恢复（persist-full-session-timeline）：
// deserializeTimeline / deserializeNodeTimelines 为防御式反序列化——
// 后端落盘的 agentTimeline / pipeline_timelines 可能缺失、非法或含脏项，
// 恢复时逐项校验 type，合法项原样保留，非法输入整体回退空数组/空对象。

describe('deserializeTimeline', () => {
  it('合法 TimelineItem 数组原样返回（往返）', () => {
    const raw: TimelineItem[] = [
      { type: 'thinking', content: '第一段思考', title: '标题', done: true },
      { type: 'search', query: '茅台 财报', status: 'done', results: [{ title: 't', url: 'u', content: 'c' }] },
      { type: 'tool_call', name: 'get_stock_data', args: '{"code":"600519"}', result: 'ok', done: true },
    ]
    expect(deserializeTimeline(raw)).toEqual(raw)
  })

  it('非数组输入回退空数组', () => {
    expect(deserializeTimeline(undefined)).toEqual([])
    expect(deserializeTimeline(null)).toEqual([])
    expect(deserializeTimeline('not-an-array')).toEqual([])
    expect(deserializeTimeline(42)).toEqual([])
    expect(deserializeTimeline({ type: 'thinking' })).toEqual([])
  })

  it('含非法 type 的项被过滤，合法项保留', () => {
    const raw = [
      { type: 'thinking', content: '合法思考' },
      { type: 'unknown_type', foo: 1 },
      { type: 'tool_call', name: 't', args: '', done: true },
      { noType: true },
      'string-item',
      null,
    ]
    const result = deserializeTimeline(raw)
    expect(result).toEqual([
      { type: 'thinking', content: '合法思考' },
      { type: 'tool_call', name: 't', args: '', done: true },
    ])
  })

  it('type 合法但字段缺失的项按原样保留（渲染层容错）', () => {
    // 反序列化只校验 type 枚举，不做深度 schema 校验（字段缺失由渲染层防御）
    const raw = [{ type: 'thinking' }, { type: 'search' }, { type: 'tool_call' }]
    const result = deserializeTimeline(raw)
    expect(result).toHaveLength(3)
    expect(result.map((i) => i.type)).toEqual(['thinking', 'search', 'tool_call'])
  })

  it('空数组返回空数组', () => {
    expect(deserializeTimeline([])).toEqual([])
  })
})

describe('deserializeNodeTimelines', () => {
  it('合法 {node: [TimelineItem]} 对象逐 key 反序列化', () => {
    const raw = {
      bull_r1: [{ type: 'thinking', content: '多头思考', done: true }],
      trader: [
        { type: 'thinking', content: '决策思考' },
        { type: 'tool_call', name: 'get_stock_data', args: '', done: true },
      ],
    }
    expect(deserializeNodeTimelines(raw)).toEqual(raw)
  })

  it('非对象输入回退空对象', () => {
    expect(deserializeNodeTimelines(undefined)).toEqual({})
    expect(deserializeNodeTimelines(null)).toEqual({})
    expect(deserializeNodeTimelines('str')).toEqual({})
    expect(deserializeNodeTimelines(7)).toEqual({})
  })

  it('数组输入回退空对象（数组不是 node->timeline 映射）', () => {
    expect(deserializeNodeTimelines([{ type: 'thinking', content: 'x' }])).toEqual({})
  })

  it('节点值为非法时该节点回退空数组，其他节点不受影响', () => {
    const raw = {
      bull_r1: 'garbage',
      bear_r1: [{ type: 'thinking', content: '空头思考' }],
      trader: [null, { type: 'unknown' }],
    }
    expect(deserializeNodeTimelines(raw)).toEqual({
      bull_r1: [],
      bear_r1: [{ type: 'thinking', content: '空头思考' }],
      trader: [],
    })
  })

  it('空对象返回空对象', () => {
    expect(deserializeNodeTimelines({})).toEqual({})
  })
})
