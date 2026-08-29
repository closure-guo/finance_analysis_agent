import { describe, it, expect, beforeEach } from 'vitest'
import type { SSEEvent, UIMessage } from '../../types'
import type { SessionStreamState } from '../../stores/streamStore/types'
import { IDLE_STATE, resetMsgIdCounter } from '../../stores/streamStore/types'
import { reduce } from '../../stores/streamStore/reduce'

// reduce 纯函数行为测试：覆盖全部 24 种 SSE 事件
// 基于 App.tsx 现有事件处理逻辑搬运，验证行为等价

const baseState = (overrides: Partial<SessionStreamState> = {}): SessionStreamState => ({
  ...IDLE_STATE,
  ...overrides,
})

const stateWithMessages = (messages: UIMessage[], overrides: Partial<SessionStreamState> = {}): SessionStreamState =>
  baseState({ messages, ...overrides })

const ev = (e: Record<string, unknown>): SSEEvent => e as unknown as SSEEvent

beforeEach(() => {
  resetMsgIdCounter()
})

describe('reduce - session_created', () => {
  it('session_created 不修改状态（store 层处理）', () => {
    const state = baseState()
    const next = reduce(state, ev({ type: 'session_created', session_id: 's1', display_name: '测试', timestamp: '' }))
    expect(next).toBe(state)
  })
})

describe('reduce - parsing / resolved / stock_resolved', () => {
  it('parsing 更新管线消息内容', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({ type: 'parsing', query: '茅台', timestamp: '' }))
    expect(next.messages[0].content).toBe('正在识别：茅台...')
  })

  it('resolved 更新管线消息内容', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({ type: 'resolved', stock_code: '600519', stock_name: '贵州茅台', timestamp: '' }))
    expect(next.messages[0].content).toBe('已识别：贵州茅台 (600519)')
  })

  it('stock_resolved 在管线模式下更新管线消息', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({ type: 'stock_resolved', stock_code: '600519', stock_name: '贵州茅台', timestamp: '' }))
    expect(next.messages[0].content).toBe('已识别：贵州茅台 (600519)')
  })

  it('stock_resolved 在澄清阶段写入对话流 timeline', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'stock_resolved', stock_code: '600519', stock_name: '贵州茅台', timestamp: '' }))
    const timeline = next.messages[0].agentTimeline
    expect(timeline).toBeDefined()
    expect(timeline!.some((i) => i.type === 'tool_call' && i.name === 'search_stock')).toBe(true)
  })
})

describe('reduce - analysis_start / node_start / node_complete / node_timing', () => {
  it('analysis_start 创建管线消息并进入 streaming', () => {
    const state = baseState()
    const next = reduce(state, ev({ type: 'analysis_start', analysis_id: 'a1', stock_code: '600519', stock_name: '贵州茅台', timestamp: '' }))
    expect(next.phase).toBe('streaming')
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].type).toBe('pipeline')
    expect(next.messages[0].content).toBe('开始分析 贵州茅台 (600519)')
  })

  it('node_start 更新管线消息当前节点和 layerTree', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({
      type: 'node_start', node_id: 'technical_analyst', layer: 'Layer I', desc: '技术面分析', icon: '📊', timestamp: '',
    }))
    expect(next.messages[0].currentNode).toBe('technical_analyst')
    expect(next.messages[0].content).toBe('Layer I: 技术面分析...')
    expect(next.messages[0].layerTree).toBeDefined()
  })

  it('node_complete 更新进度和节点输出', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({
      type: 'node_complete', node_id: 'technical_analyst', layer: 'Layer I', desc: '技术面分析',
      completed: ['technical_analyst'], progress: 0.5, output: { summary: '完成' }, timestamp: '',
    }))
    expect(next.messages[0].completedNodes).toEqual(['technical_analyst'])
    expect(next.messages[0].progress).toBe(0.5)
    expect(next.messages[0].content).toBe('Layer I: 技术面分析 ✓')
  })

  it('node_timing 更新节点真实耗时', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({
      type: 'node_timing', node_id: 'technical_analyst',
      server_start_ts: 1000, server_end_ts: 2000, server_duration_ms: 1000, timestamp: '',
    }))
    expect(next.messages[0].layerTree).toBeDefined()
  })
})

describe('reduce - thinking_token / thinking_replace / thinking_to_answer', () => {
  it('thinking_token 无 node 且无 chat 消息时自动创建对话流消息', () => {
    // 真实流中 thinking_token 可能在 chat_token 之前到达（管线已建、澄清思考），
    // 不自动建消息会导致思考内容静默丢失（stream-event-routing 回归）
    const state = stateWithMessages([{ id: 'p1', type: 'pipeline', content: '' }])
    const next = reduce(state, ev({ type: 'thinking_token', token: '思考中', timestamp: '' }))
    const chat = next.messages.find((m) => m.type === 'chat')
    expect(chat).toBeDefined()
    expect(chat!.agentTimeline![0].type).toBe('thinking')
  })

  it('thinking_replace 无 chat 消息时自动创建对话流消息', () => {
    const state = stateWithMessages([{ id: 'p1', type: 'pipeline', content: '' }])
    const next = reduce(state, ev({ type: 'thinking_replace', token: '清理后', timestamp: '' }))
    expect(next.messages.some((m) => m.type === 'chat')).toBe(true)
  })

  it('thinking_token 无 node 时写入对话流', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'thinking_token', token: '思考中', timestamp: '' }))
    const timeline = next.messages[0].agentTimeline
    expect(timeline).toHaveLength(1)
    expect(timeline![0].type).toBe('thinking')
    if (timeline![0].type === 'thinking') expect(timeline![0].content).toBe('思考中')
  })

  it('thinking_token 有 node 时写入管线 nodeTimelines', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({ type: 'thinking_token', token: '分析中', node: 'technical_analyst', timestamp: '' }))
    const nodeTimelines = next.messages[0].nodeTimelines
    expect(nodeTimelines).toBeDefined()
    expect(nodeTimelines!['technical_analyst']).toHaveLength(1)
  })

  it('thinking_replace 替换末尾 thinking item', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true,
      agentTimeline: [{ type: 'thinking', content: '原始' }],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'thinking_replace', token: '替换后', timestamp: '' }))
    const item = next.messages[0].agentTimeline![0]
    if (item.type === 'thinking') expect(item.content).toBe('替换后')
  })

  it('thinking_to_answer 将回答移至 chatResponse', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true,
      agentTimeline: [{ type: 'thinking', content: '思考过程最终回答' }],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'thinking_to_answer', answer: '最终回答', timestamp: '' }))
    expect(next.messages[0].chatResponse).toBe('最终回答')
    const item = next.messages[0].agentTimeline![0]
    if (item.type === 'thinking') expect(item.content).toBe('思考过程')
  })
})

describe('reduce - tool_call / tool_result', () => {
  it('tool_call 非 run_deep_analysis 写入对话流', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'tool_call', name: 'search_stock', args: { query: '茅台' }, iteration: 1, timestamp: '' }))
    const timeline = next.messages[0].agentTimeline
    expect(timeline!.some((i) => i.type === 'tool_call' && i.name === 'search_stock')).toBe(true)
  })

  it('tool_call run_deep_analysis 创建管线消息', () => {
    const state = baseState()
    const next = reduce(state, ev({ type: 'tool_call', name: 'run_deep_analysis', args: {}, iteration: 1, timestamp: '' }))
    expect(next.phase).toBe('streaming')
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].type).toBe('pipeline')
    expect(next.messages[0].content).toBe('开始深度分析...')
  })

  it('tool_call 搜索类工具不生成 tool_call item', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true,
      agentTimeline: [],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'tool_call', name: 'web_search', args: { query: '茅台' }, iteration: 1, timestamp: '' }))
    const timeline = next.messages[0].agentTimeline
    expect(timeline).toBeDefined()
    expect(timeline!.every((i) => i.type !== 'tool_call')).toBe(true)
  })

  it('tool_result 更新对应 tool_call item', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true,
      agentTimeline: [{ type: 'tool_call', name: 'search_stock', args: '茅台', done: false }],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'tool_result', name: 'search_stock', result: '找到 600519', timestamp: '' }))
    const item = next.messages[0].agentTimeline![0]
    if (item.type === 'tool_call') {
      expect(item.done).toBe(true)
      expect(item.result).toBe('找到 600519')
    }
  })
})

describe('reduce - search_start / search_result / search_error', () => {
  it('search_start 创建 search item', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'search_start', query: '茅台股价', timestamp: '' }))
    const timeline = next.messages[0].agentTimeline
    expect(timeline).toHaveLength(1)
    expect(timeline![0].type).toBe('search')
    if (timeline![0].type === 'search') {
      expect(timeline![0].query).toBe('茅台股价')
      expect(timeline![0].status).toBe('searching')
    }
  })

  it('search_result 更新 search item 为 done', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true,
      agentTimeline: [{ type: 'search', query: '茅台', status: 'searching' }],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({
      type: 'search_result', query: '茅台', results: [{ title: 't', url: 'u', content: 'c' }], count: 1, timestamp: '',
    }))
    const item = next.messages[0].agentTimeline![0]
    if (item.type === 'search') {
      expect(item.status).toBe('done')
      expect(item.results).toHaveLength(1)
    }
  })

  it('search_error 更新 search item 为 error', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true,
      agentTimeline: [{ type: 'search', query: '茅台', status: 'searching' }],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'search_error', message: '网络错误', timestamp: '' }))
    const item = next.messages[0].agentTimeline![0]
    if (item.type === 'search') expect(item.status).toBe('error')
  })
})

describe('reduce - report_chunk / report_ready', () => {
  it('report_chunk 创建流式报告消息', () => {
    const state = baseState()
    const next = reduce(state, ev({ type: 'report_chunk', chunk_index: 0, total_chunks: 2, text: '# 报告', timestamp: '' }))
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].type).toBe('report')
    expect(next.messages[0].reportMarkdown).toBe('# 报告')
    expect(next.messages[0].streaming).toBe(true)
  })

  it('report_chunk 累加到现有报告消息', () => {
    const reportMsg: UIMessage = { id: 'r1', type: 'report', content: '', reportMarkdown: '# 报告', streaming: true }
    const state = stateWithMessages([reportMsg])
    const next = reduce(state, ev({ type: 'report_chunk', chunk_index: 1, total_chunks: 2, text: '正文', timestamp: '' }))
    expect(next.messages[0].reportMarkdown).toBe('# 报告正文')
  })

  it('report_ready 定型报告消息', () => {
    const reportMsg: UIMessage = { id: 'r1', type: 'report', content: '', reportMarkdown: '流式内容', streaming: true }
    const state = stateWithMessages([reportMsg])
    const next = reduce(state, ev({
      type: 'report_ready', analysis_id: 'a1', session_id: 's1',
      report_markdown: '最终报告', chart_data: {}, file_paths: { docx: 'f.docx' },
      stock_name: '贵州茅台', duration_ms: 5000, timestamp: '',
    }))
    expect(next.messages[0].reportMarkdown).toBe('最终报告')
    expect(next.messages[0].streaming).toBe(false)
    expect(next.messages[0].stockName).toBe('贵州茅台')
  })

  it('report_ready 无流式分块直接创建完整报告', () => {
    const state = baseState()
    const next = reduce(state, ev({
      type: 'report_ready', analysis_id: 'a1', session_id: 's1',
      report_markdown: '完整报告', chart_data: {}, file_paths: {},
      stock_name: '贵州茅台', duration_ms: 3000, timestamp: '',
    }))
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].type).toBe('report')
    expect(next.messages[0].reportMarkdown).toBe('完整报告')
  })
})

describe('reduce - chat_token / chat_done', () => {
  it('chat_token 无 chat 消息时创建新消息', () => {
    const state = baseState()
    const next = reduce(state, ev({ type: 'chat_token', token: '你好', timestamp: '' }))
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].type).toBe('chat')
    expect(next.messages[0].chatResponse).toBe('你好')
    expect(next.messages[0].streaming).toBe(true)
  })

  it('chat_token 累加到现有 chat 消息', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '你好', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'chat_token', token: '世界', timestamp: '' }))
    expect(next.messages[0].chatResponse).toBe('你好世界')
  })

  it('chat_done 结束流式并收口 thinking', () => {
    const chatMsg: UIMessage = {
      id: 'c1', type: 'chat', content: '', chatResponse: '回答', streaming: true,
      agentTimeline: [{ type: 'thinking', content: '思考' }],
    }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'chat_done', timestamp: '' }))
    expect(next.messages[0].streaming).toBe(false)
    const item = next.messages[0].agentTimeline![0]
    if (item.type === 'thinking') expect(item.done).toBe(true)
  })
})

describe('reduce - awaiting_input / done / interrupted / error', () => {
  it('awaiting_input 设置 phase 并停止流式', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'awaiting_input', session_id: 's1', pending_intent: '分析', timestamp: '' }))
    expect(next.phase).toBe('awaiting_input')
    expect(next.messages[0].streaming).toBe(false)
  })

  it('done 设置 phase 并停止所有流式', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const reportMsg: UIMessage = { id: 'r1', type: 'report', content: '', streaming: true }
    const state = stateWithMessages([chatMsg, reportMsg])
    const next = reduce(state, ev({ type: 'done', analysis_id: 'a1', duration_ms: 1000, timestamp: '' }))
    expect(next.phase).toBe('done')
    expect(next.messages.every((m) => !m.streaming)).toBe(true)
  })

  it('interrupted 设置 phase 并停止所有流式', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'interrupted', timestamp: '' }))
    expect(next.phase).toBe('interrupted')
    expect(next.messages[0].streaming).toBe(false)
  })

  it('error 管线模式下更新管线消息', () => {
    const pipelineMsg: UIMessage = { id: 'p1', type: 'pipeline', content: '' }
    const state = stateWithMessages([pipelineMsg])
    const next = reduce(state, ev({ type: 'error', node_id: 'n1', message: '执行失败', timestamp: '' }))
    expect(next.phase).toBe('error')
    expect(next.messages[0].type).toBe('error')
    expect(next.messages[0].content).toBe('错误: 执行失败')
  })

  it('error 非管线模式下添加 error 消息', () => {
    const chatMsg: UIMessage = { id: 'c1', type: 'chat', content: '', chatResponse: '', streaming: true }
    const state = stateWithMessages([chatMsg])
    const next = reduce(state, ev({ type: 'error', node_id: 'n1', message: '执行失败', timestamp: '' }))
    expect(next.phase).toBe('error')
    expect(next.messages).toHaveLength(2)
    expect(next.messages[1].type).toBe('error')
    expect(next.messages[1].content).toBe('错误: 执行失败')
  })
})

describe('reduce - 事件序列 fixture', () => {
  it('完整深度分析序列：session_created → analysis_start → node_start → thinking → node_complete → report_chunk → report_ready → done', () => {
    let state = baseState()
    state = reduce(state, ev({ type: 'session_created', session_id: 's1', display_name: '茅台分析', timestamp: '' }))
    state = reduce(state, ev({ type: 'analysis_start', analysis_id: 'a1', stock_code: '600519', stock_name: '贵州茅台', timestamp: '' }))
    state = reduce(state, ev({ type: 'node_start', node_id: 'technical_analyst', layer: 'Layer I', desc: '技术面分析', icon: '📊', timestamp: '' }))
    state = reduce(state, ev({ type: 'thinking_token', token: '分析中', node: 'technical_analyst', timestamp: '' }))
    state = reduce(state, ev({ type: 'node_complete', node_id: 'technical_analyst', layer: 'Layer I', desc: '技术面分析', completed: ['technical_analyst'], progress: 0.5, output: {}, timestamp: '' }))
    state = reduce(state, ev({ type: 'report_chunk', chunk_index: 0, total_chunks: 1, text: '# 报告', timestamp: '' }))
    state = reduce(state, ev({ type: 'report_ready', analysis_id: 'a1', session_id: 's1', report_markdown: '# 报告', chart_data: {}, file_paths: {}, stock_name: '贵州茅台', duration_ms: 1000, timestamp: '' }))
    state = reduce(state, ev({ type: 'done', analysis_id: 'a1', duration_ms: 1000, timestamp: '' }))

    expect(state.phase).toBe('done')
    expect(state.messages).toHaveLength(2) // pipeline + report
    expect(state.messages[0].type).toBe('pipeline')
    expect(state.messages[1].type).toBe('report')
    expect(state.messages[1].streaming).toBe(false)
  })

  it('快速对话序列：chat_token → chat_done', () => {
    let state = baseState()
    state = reduce(state, ev({ type: 'chat_token', token: '你好', timestamp: '' }))
    state = reduce(state, ev({ type: 'chat_token', token: '世界', timestamp: '' }))
    state = reduce(state, ev({ type: 'chat_done', timestamp: '' }))

    expect(state.messages).toHaveLength(1)
    expect(state.messages[0].chatResponse).toBe('你好世界')
    expect(state.messages[0].streaming).toBe(false)
  })

  it('澄清序列：thinking → search → tool_call → tool_result → chat_token → awaiting_input', () => {
    let state = baseState()
    // 先创建 chat 消息
    state = reduce(state, ev({ type: 'chat_token', token: '', timestamp: '' }))
    state = reduce(state, ev({ type: 'thinking_token', token: '让我搜索', timestamp: '' }))
    state = reduce(state, ev({ type: 'search_start', query: '茅台', timestamp: '' }))
    state = reduce(state, ev({ type: 'search_result', query: '茅台', results: [], count: 0, timestamp: '' }))
    state = reduce(state, ev({ type: 'tool_call', name: 'search_stock', args: { query: '茅台' }, iteration: 1, timestamp: '' }))
    state = reduce(state, ev({ type: 'tool_result', name: 'search_stock', result: '600519', timestamp: '' }))
    state = reduce(state, ev({ type: 'chat_token', token: '为您找到', timestamp: '' }))
    state = reduce(state, ev({ type: 'awaiting_input', session_id: 's1', pending_intent: '分析', timestamp: '' }))

    expect(state.phase).toBe('awaiting_input')
    expect(state.messages[0].streaming).toBe(false)
    const timeline = state.messages[0].agentTimeline!
    expect(timeline.some((i) => i.type === 'thinking')).toBe(true)
    expect(timeline.some((i) => i.type === 'search')).toBe(true)
    expect(timeline.some((i) => i.type === 'tool_call' && i.name === 'search_stock')).toBe(true)
  })
})

describe('reduce - report_ready 携带股票代码', () => {
  it('report_ready 消息记录 stockCode 与既有字段', () => {
    const state = baseState()
    const next = reduce(state, ev({
      type: 'report_ready',
      session_id: 's1',
      report_markdown: '# 报告',
      chart_data: {},
      file_paths: { md: '/tmp/贵州茅台_600519_x_report.md' },
      stock_name: '贵州茅台',
      stock_code: '600519',
      duration_ms: 1234,
      timestamp: 't',
    }))
    const report = next.messages.find((m) => m.type === 'report')
    expect(report?.stockCode).toBe('600519')
    expect(report?.stockName).toBe('贵州茅台')
    expect(report?.filePaths).toEqual({ md: '/tmp/贵州茅台_600519_x_report.md' })
  })
})
