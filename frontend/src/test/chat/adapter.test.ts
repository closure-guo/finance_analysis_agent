// adopt-assistant-ui-chat Task 2.2：SSE 事件适配层逐事件类型单测。
//
// 覆盖策略（delta spec: SSE 事件适配层 - 事件类型全覆盖 / 未知事件安全忽略）：
// 每个 SSE 事件类型构造事件序列 → streamStore reduce（既有归约，已有独立单测）
// → adapter translateMessage → 断言 assistant-ui 消息部件结构与映射表一致。
// 映射表见 docs/superpowers/plans/2026-08-30-adopt-assistant-ui-chat.md。
import { describe, it, expect } from 'vitest'
import type { SSEEvent, UIMessage, SessionDetail } from '../../types'
import { reduce } from '../../stores/streamStore/reduce'
import type { SessionStreamState } from '../../stores/streamStore/types'
import { IDLE_STATE } from '../../stores/streamStore/types'
import { translateMessage, translateMessages } from '../../chat/adapter'

// 事件序列 → reduce 归约 → 取最后一条消息翻译为 ThreadMessageLike
function applyEvents(events: object[]): { state: SessionStreamState; last: UIMessage } {
  let state: SessionStreamState = IDLE_STATE
  for (const ev of events as SSEEvent[]) {
    state = reduce(state, ev)
  }
  expect(state.messages.length).toBeGreaterThan(0)
  return { state, last: state.messages[state.messages.length - 1] }
}

// content 为 readonly 数组：测试断言用宽松视图
function partsOf(m: { content: unknown }): Array<Record<string, unknown>> {
  return (Array.isArray(m.content) ? m.content : []) as unknown as Array<Record<string, unknown>>
}

function lastPart(state: SessionStreamState) {
  const translated = translateMessage(state.messages[state.messages.length - 1])
  const parts = partsOf(translated)
  return { translated, part: parts[parts.length - 1] }
}

describe('对话流事件 → 消息部件', () => {
  it('chat_token：assistant text 部件，流式 running', () => {
    const { state } = applyEvents([{ type: 'chat_token', token: '你好' }])
    const { translated, part } = lastPart(state)
    expect(translated.role).toBe('assistant')
    expect(translated.status).toEqual({ type: 'running' })
    expect(part.type).toBe('text')
    expect(part.text).toBe('你好')
    expect(part.status).toEqual({ type: 'running' })
  })

  it('chat_done：text 部件与消息均收口 complete', () => {
    const { state } = applyEvents([
      { type: 'chat_token', token: '答案' },
      { type: 'chat_done' },
    ])
    const { translated, part } = lastPart(state)
    expect(part.type).toBe('text')
    expect(part.text).toBe('答案')
    expect(part.status).toBeUndefined()
    expect(translated.status).toEqual({ type: 'complete', reason: 'unknown' })
  })

  it('thinking_token（无 node）：reasoning 部件，流式中 status running', () => {
    const { state } = applyEvents([{ type: 'thinking_token', token: '思考中片段' }])
    const { part } = lastPart(state)
    expect(part.type).toBe('reasoning')
    expect(part.text).toBe('思考中片段')
    expect(part.status).toEqual({ type: 'running' })
  })

  it('thinking_token（带 node）：管线思考 → data-pipeline 部件', () => {
    const { state } = applyEvents([
      { type: 'analysis_start', analysis_id: 'a1', stock_code: '600449', stock_name: '宁夏建材' },
      { type: 'thinking_token', token: '多头思考', node: 'bull_r1' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-pipeline')
    const data = part.data as UIMessage
    expect(data.type).toBe('pipeline')
    expect(data.nodeTimelines?.['bull_r1']?.[0]).toMatchObject({ type: 'thinking', content: '多头思考' })
  })

  it('thinking_replace：替换末尾 reasoning 部件内容（DSML 清理）', () => {
    const { state } = applyEvents([
      { type: 'thinking_token', token: 'DSML_RAW_原始文本ABC' },
      { type: 'thinking_replace', token: '清理后的思考内容DEF' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('reasoning')
    expect(part.text).toBe('清理后的思考内容DEF')
  })

  it('thinking_to_answer：reasoning 收口 + answer 转 text 部件', () => {
    const { state } = applyEvents([
      { type: 'thinking_token', token: '前缀思考，最终答案XYZ' },
      { type: 'thinking_to_answer', answer: '最终答案XYZ' },
    ])
    const translated = translateMessage(state.messages[state.messages.length - 1])
    const parts = partsOf(translated)
    expect(parts.some((p) => p.type === 'reasoning' && p.text === '前缀思考，')).toBe(true)
    const text = parts.find((p) => p.type === 'text')
    expect(text?.text).toBe('最终答案XYZ')
  })
})

describe('工具调用事件 → tool-call 部件', () => {
  it('tool_call：tool-call 部件 loading 语义（无 result、artifact.done=false）', () => {
    const { state } = applyEvents([
      { type: 'tool_call', name: 'get_stock_data', args: { stock_code: '600449' }, iteration: 1 },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('tool-call')
    expect(part.toolName).toBe('get_stock_data')
    expect(part.argsText).toContain('stock_code')
    expect(part.result).toBeUndefined()
    expect((part.artifact as { done: boolean }).done).toBe(false)
  })

  it('tool_result：result 填充 + artifact.done=true（完成态）', () => {
    const { state } = applyEvents([
      { type: 'tool_call', name: 'get_stock_data', args: { stock_code: '600449' }, iteration: 1 },
      { type: 'tool_result', name: 'get_stock_data', result: '股价数据OK' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('tool-call')
    expect(part.result).toBe('股价数据OK')
    expect((part.artifact as { done: boolean }).done).toBe(true)
  })

  it('搜索类工具不产生 tool-call 部件（由 search_* 事件承载）', () => {
    const { state } = applyEvents([
      { type: 'tool_call', name: 'web_search', args: { query: '茅台' }, iteration: 1 },
      { type: 'search_start', query: '茅台' },
    ])
    const translated = translateMessage(state.messages[state.messages.length - 1])
    const parts = partsOf(translated)
    expect(parts.filter((p) => p.type === 'tool-call')).toHaveLength(0)
    expect(parts.some((p) => p.type === 'data-search')).toBe(true)
  })

  it('tool_call(run_deep_analysis)：触发管线 → data-pipeline 部件', () => {
    const { state } = applyEvents([
      { type: 'tool_call', name: 'run_deep_analysis', args: { stock_code: '600449' }, iteration: 1 },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-pipeline')
  })

  it('stock_resolved（澄清阶段）：search_stock 工具结果 → tool-call 部件完成态', () => {
    const { state } = applyEvents([
      { type: 'stock_resolved', stock_code: '600449', stock_name: '宁夏建材' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('tool-call')
    expect(part.toolName).toBe('search_stock')
    expect(part.result).toContain('宁夏建材')
    expect((part.artifact as { done: boolean }).done).toBe(true)
  })
})

describe('时序排列（bug 复现）：正文/思考/工具调用按到达顺序渲染', () => {
  // 真实 SSE 到达序（ReAct 单轮可先吐文字再调工具）：
  //   thinking → 正文「我先查一下」 → tool_call → 正文「结果如下」
  // 渲染部件顺序 MUST 与到达序一致；当前 adapter 把 text 一律排到 timeline 之后 → 复现失败。
  it('正文先于工具调用时,text 部件应插在 tool-call 之前', () => {
    const { state } = applyEvents([
      { type: 'thinking_token', token: '思考一' },
      { type: 'chat_token', token: '我先查一下' },
      { type: 'tool_call', name: 'get_stock_data', args: { stock_code: '600519' }, iteration: 1 },
      { type: 'chat_token', token: '结果如下' },
      { type: 'chat_done' },
    ])
    const translated = translateMessage(state.messages[state.messages.length - 1])
    const parts = partsOf(translated)
    const types = parts.map((p) => p.type)
    // 到达序:reasoning, text(我先查一下), tool-call, text(结果如下)
    const textIdx = types.findIndex((t) => t === 'text')
    const toolIdx = types.findIndex((t) => t === 'tool-call')
    expect(textIdx).toBeGreaterThanOrEqual(0)
    expect(toolIdx).toBeGreaterThanOrEqual(0)
    // 关键断言:第一段正文必须先于 tool-call 渲染(时间序)
    expect(textIdx).toBeLessThan(toolIdx)
  })
})

describe('搜索事件 → data-search 部件', () => {
  it('search_start：searching 状态', () => {
    const { state } = applyEvents([{ type: 'search_start', query: '茅台 股价' }])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-search')
    expect(part.data).toMatchObject({ status: 'searching', query: '茅台 股价' })
  })

  it('search_result：done 状态 + results', () => {
    const { state } = applyEvents([
      { type: 'search_start', query: '茅台 股价' },
      { type: 'search_result', query: '茅台 股价', results: [{ title: 'T1', url: 'https://a', content: 'C1' }], count: 1 },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-search')
    expect(part.data).toMatchObject({ status: 'done', results: [{ title: 'T1' }] })
  })

  it('search_error：error 状态', () => {
    const { state } = applyEvents([
      { type: 'search_start', query: '茅台 股价' },
      { type: 'search_error', message: '超时' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-search')
    expect(part.data).toMatchObject({ status: 'error' })
  })
})

describe('管线事件 → data-pipeline 部件', () => {
  const PIPELINE_EVENTS = [
    { ev: { type: 'parsing', query: '宁夏建材' }, assert: (d: UIMessage) => expect(d.content).toContain('识别') },
    { ev: { type: 'resolved', stock_code: '600449', stock_name: '宁夏建材' }, assert: (d: UIMessage) => expect(d.content).toContain('已识别') },
    { ev: { type: 'analysis_start', analysis_id: 'a1', stock_code: '600449', stock_name: '宁夏建材' }, assert: (d: UIMessage) => expect(d.progress).toBe(0) },
    { ev: { type: 'node_start', node_id: 'fetch_data', layer: 'L1', desc: '获取数据', icon: 'db' }, assert: (d: UIMessage) => expect(d.currentNode).toBe('fetch_data') },
    { ev: { type: 'node_timing', node_id: 'fetch_data', server_duration_ms: 100 }, assert: (d: UIMessage) => expect(d.layerTree).toBeDefined() },
    {
      ev: { type: 'node_complete', node_id: 'fetch_data', layer: 'L1', desc: '获取数据', completed: ['fetch_data'], progress: 0.2, output: { summary: 'ok' } },
      assert: (d: UIMessage) => expect(d.completedNodes).toContain('fetch_data'),
    },
  ] as const

  for (const { ev, assert } of PIPELINE_EVENTS) {
    it(`${ev.type}：映射为 data-pipeline 部件`, () => {
      const { state } = applyEvents([ev])
      const { part } = lastPart(state)
      expect(part.type).toBe('data-pipeline')
      assert(part.data as UIMessage)
    })
  }
})

describe('报告事件 → data-report 部件', () => {
  it('report_chunk：data-report 部件，流式内容累加', () => {
    const { state } = applyEvents([
      { type: 'report_chunk', chunk_index: 0, total_chunks: 2, text: '# 报告标题' },
      { type: 'report_chunk', chunk_index: 1, total_chunks: 2, text: '\n正文' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-report')
    const data = part.data as UIMessage
    expect(data.type).toBe('report')
    expect(data.reportMarkdown).toBe('# 报告标题\n正文')
    expect(data.streaming).toBe(true)
  })

  it('report_ready：完整报告数据挂载（chartData/filePaths/webSources）', () => {
    const { state } = applyEvents([
      { type: 'report_ready', analysis_id: 'a1', session_id: 's1', report_markdown: '# 报告', chart_data: { stock_code: '600449', stock_name: '宁夏建材', annual: [], growth: { years: [], revenue_growth: [], profit_growth: [] }, price: { daily: [], earnings_dates: [] }, kpi: {}, market_share: null }, file_paths: { md: 'report.md' }, stock_code: '600449', stock_name: '宁夏建材', duration_ms: 1000, web_sources: [{ query: 'q', title: 'T', url: 'https://a', content: 'C' }] },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-report')
    const data = part.data as UIMessage
    expect(data.reportMarkdown).toBe('# 报告')
    expect(data.filePaths).toEqual({ md: 'report.md' })
    expect(data.webSources).toHaveLength(1)
    expect(data.streaming).toBe(false)
  })
})

describe('状态转换与错误事件', () => {
  it('user_message：user text 部件', () => {
    const { state } = applyEvents([{ type: 'user_message', content: '用户提问' }])
    const { translated, part } = lastPart(state)
    expect(translated.role).toBe('user')
    expect(part.type).toBe('text')
    expect(part.text).toBe('用户提问')
  })

  it('error（无管线）：data-error 部件', () => {
    const { state } = applyEvents([{ type: 'error', node_id: '', message: ' boom' }])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-error')
    expect((part.data as { content: string }).content).toContain('boom')
  })

  it('error（管线中）：管线消息 type 改写为 error → data-error 部件（既有 reduce 行为）', () => {
    const { state } = applyEvents([
      { type: 'analysis_start', analysis_id: 'a1', stock_code: '600449', stock_name: '宁夏建材' },
      { type: 'error', node_id: 'fetch_data', message: '数据源不可用' },
    ])
    const { part } = lastPart(state)
    expect(part.type).toBe('data-error')
    expect((part.data as { content: string }).content).toContain('数据源不可用')
  })

  it('awaiting_input / done / interrupted：不产生新部件，消息流式收口', () => {
    for (const ev of [{ type: 'awaiting_input', session_id: 's1', pending_intent: 'clarify' }, { type: 'done', analysis_id: 'a1', duration_ms: 1 }, { type: 'interrupted' }]) {
      const { state } = applyEvents([
        { type: 'chat_token', token: '部分回答' },
        ev,
      ])
      const translated = translateMessage(state.messages[state.messages.length - 1])
      expect(translated.status).toEqual({ type: 'complete', reason: 'unknown' })
      const parts = partsOf(translated)
      expect(parts.every((p) => p.status === undefined)).toBe(true)
    }
  })

  it('session_created：不产生消息部件（store 层绑定）', () => {
    let state: SessionStreamState = IDLE_STATE
    state = reduce(state, { type: 'session_created', session_id: 's1', display_name: '新会话' } as SSEEvent)
    expect(state.messages).toHaveLength(0)
  })

  it('未知事件类型：安全忽略，不抛错、不产生部件', () => {
    const { state } = applyEvents([
      { type: 'chat_token', token: '前文' },
      { type: 'totally_unknown_event', foo: 'bar' },
    ])
    const translated = translateMessage(state.messages[state.messages.length - 1])
    const parts = partsOf(translated)
    expect(parts).toHaveLength(1)
    expect(parts[0].text).toBe('前文')
  })
})

describe('translateMessages / 边界', () => {
  it('空 agentTimeline 且无 chatResponse：parts 为空数组（Empty 渲染兜底）', () => {
    const msg: UIMessage = { id: 'm1', type: 'chat', content: '', chatResponse: '', agentTimeline: [] }
    const translated = translateMessage(msg)
    expect(translated.content).toEqual([])
  })

  it('translateMessages 批量翻译保序', () => {
    const msgs: UIMessage[] = [
      { id: 'm1', type: 'user', content: 'Q' },
      { id: 'm2', type: 'chat', content: '', chatResponse: 'A' },
      { id: 'm3', type: 'report', content: '', reportMarkdown: '# R' },
    ]
    const translated = translateMessages(msgs)
    expect(translated.map((m) => m.role)).toEqual(['user', 'assistant', 'assistant'])
  })

  it('历史会话重建（rebuildMessagesFromDetail）产物可完整翻译', () => {
    // 终态会话经 chat_history 重建 → translate，验证重建路径（Task 2.3 刷新重建路径的前置）
    const detail: SessionDetail = {
      session_id: 's1', stock_code: '600449', stock_name: '宁夏建材', display_name: '宁夏建材', status: 'completed',
      created_at: '2026-08-30T00:00:00Z', duration_ms: 100, report_markdown: '', chart_data: { stock_code: '', stock_name: '', annual: [], growth: { years: [], revenue_growth: [], profit_growth: [] }, price: { daily: [], earnings_dates: [] }, kpi: {}, market_share: null },
      analyst_reports: {}, agent_process: {}, analyst_summaries: {}, chat_history: [],
      pipeline_snapshot: null,
    }
    // 直接用 chat 消息（含 thinking/tool_call 拍平字段）验证翻译
    const msg: UIMessage = {
      id: 'm2', type: 'chat', content: '', chatResponse: '最终回答',
      agentTimeline: [
        { type: 'thinking', content: '思考A', done: true },
        { type: 'tool_call', name: 'get_stock_data', args: '', result: 'ok', done: true },
        { type: 'thinking', content: '思考B', done: true },
      ],
    }
    expect(detail.chat_history).toEqual([])
    const translated = translateMessage(msg)
    const parts = partsOf(translated)
    expect(parts.map((p) => p.type)).toEqual(['reasoning', 'tool-call', 'reasoning', 'text'])
  })
})
