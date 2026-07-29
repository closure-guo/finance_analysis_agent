// Agent 时序（agentTimeline）构建逻辑 -- 纯函数，供 App.tsx 事件处理与单测复用。
// 设计见 openspec/changes/agent-turn-box-display/design.md：
// - 决策 2：思考片段遇 search_start / tool_call 断开（末尾非 thinking item 则新建）
// - 决策 8：web_search / batch_web_search 走 search item，不进 tool_call item

import type { SSEEvent, TimelineItem, ToolCallEntry, UIMessage } from './types'

// 搜索类工具集合（与 App.tsx isSearchTool 保持一致；放这里避免 timeline.ts -> App.tsx 循环依赖）
const SEARCH_TOOL_NAMES = new Set<string>(['web_search', 'batch_web_search'])

// 判断工具是否为搜索类（web_search / batch_web_search）
function isSearchToolName(name: string): boolean {
  return SEARCH_TOOL_NAMES.has(name)
}

// 从思考内容中提取首个 ## 二级标题作为横幅标题（与 App.tsx extractThinkingTitle 同策略，
// 复制于此避免循环依赖；两处需保持同步）
function extractThinkingTitleLocal(content: string): string | undefined {
  if (!content) return undefined
  const match = content.match(/^\s*##\s+(.+?)\s*$/m)
  return match ? match[1] : undefined
}

// 将工具结果浓缩为简短文本（与 App.tsx summarizeToolResult 同策略）
function summarizeToolResultLocal(result: unknown): string {
  if (typeof result === 'string') return result.substring(0, 150)
  if (Array.isArray(result)) {
    return result
      .slice(0, 3)
      .map((r) => (r as Record<string, unknown>)?.title || (r as Record<string, unknown>)?.name || (r as Record<string, unknown>)?.code || JSON.stringify(r).substring(0, 50))
      .join('、')
  }
  if (result && typeof result === 'object') {
    return JSON.stringify(result).substring(0, 150)
  }
  return ''
}

// 将工具调用参数浓缩为展示文本（query / queries 优先，其余 JSON）
function summarizeToolArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return ''
  if (typeof args.query === 'string') return args.query
  if (Array.isArray(args.queries)) return args.queries.join('、')
  return Object.keys(args).length ? JSON.stringify(args) : ''
}

// 向 timeline 追加/累加一个 thinking token：末尾是 thinking item 则累加，否则新建
function appendThinkingToken(timeline: TimelineItem[], token: string): TimelineItem[] {
  const last = timeline[timeline.length - 1]
  if (last && last.type === 'thinking') {
    const next = timeline.slice()
    next[next.length - 1] = { ...last, content: last.content + token }
    return next
  }
  return [...timeline, { type: 'thinking', content: token, done: false }]
}

// 将 timeline 末尾未完成（done 不为 true）的 thinking item 置为完成态
function closeLastThinking(timeline: TimelineItem[]): TimelineItem[] {
  const last = timeline[timeline.length - 1]
  if (last && last.type === 'thinking' && last.done !== true) {
    const next = timeline.slice()
    next[next.length - 1] = { ...last, done: true }
    return next
  }
  return timeline
}

// 将所有未完成 thinking item 置为完成态（chat_done / error 收口用）
function closeAllThinking(timeline: TimelineItem[]): TimelineItem[] {
  return timeline.map((item) =>
    item.type === 'thinking' && item.done !== true ? { ...item, done: true } : item,
  )
}

// 对话流事件（快速模式 + 深度澄清阶段共用）应用到消息的 agentTimeline。
// 返回新消息对象（不可变更新）。仅处理对话流相关事件，其他事件原样返回。
export function applyChatStreamEvent(msg: UIMessage, event: SSEEvent): UIMessage {
  const timeline = msg.agentTimeline ?? []

  switch (event.type) {
    case 'thinking_token':
      return { ...msg, agentTimeline: appendThinkingToken(timeline, event.token) }

    case 'thinking_replace': {
      // DSML 清理等后处理：整体替换末尾 thinking item 内容
      const last = timeline[timeline.length - 1]
      if (last && last.type === 'thinking') {
        const next = timeline.slice()
        next[next.length - 1] = { ...last, content: event.token }
        return { ...msg, agentTimeline: next }
      }
      return msg
    }

    case 'thinking_to_answer': {
      // 流末判定为最终回答：将末尾 thinking item 与 answer 匹配的部分移至 chatResponse
      const last = timeline[timeline.length - 1]
      if (last && last.type === 'thinking' && event.answer) {
        const idx = last.content.lastIndexOf(event.answer)
        if (idx >= 0) {
          const next = timeline.slice()
          next[next.length - 1] = { ...last, content: last.content.slice(0, idx), done: true }
          return { ...msg, agentTimeline: next, chatResponse: event.answer }
        }
      }
      return msg
    }

    case 'search_start':
      return {
        ...msg,
        agentTimeline: [...timeline, { type: 'search', query: event.query, status: 'searching' }],
      }

    case 'search_result': {
      // 更新最近的 searching 状态 search item 为 done 并写入结果
      const next = timeline.slice()
      for (let i = next.length - 1; i >= 0; i--) {
        const item = next[i]
        if (item.type === 'search' && item.status === 'searching') {
          next[i] = { ...item, status: 'done', results: event.results || [] }
          return { ...msg, agentTimeline: next }
        }
      }
      // 无 searching item（容错）：新建 done item
      return {
        ...msg,
        agentTimeline: [...timeline, { type: 'search', query: event.query, status: 'done', results: event.results || [] }],
      }
    }

    case 'search_error': {
      const next = timeline.slice()
      for (let i = next.length - 1; i >= 0; i--) {
        const item = next[i]
        if (item.type === 'search' && item.status === 'searching') {
          next[i] = { ...item, status: 'error' }
          return { ...msg, agentTimeline: next }
        }
      }
      return msg
    }

    case 'tool_call': {
      // 搜索类工具由 search_* 事件驱动 SearchBanner，不生成 tool_call item
      if (isSearchToolName(event.name)) return msg
      // 思考后接工具调用：末尾未完成 thinking item 显式收口
      return {
        ...msg,
        agentTimeline: [
          ...closeLastThinking(timeline),
          { type: 'tool_call', name: event.name, args: summarizeToolArgs(event.args), done: false },
        ],
      }
    }

    case 'tool_result': {
      // 搜索类工具结果由 search_result 事件驱动，不进入 tool_call item
      if (isSearchToolName(event.name)) return msg
      const resultSummary = summarizeToolResultLocal(event.result)
      const next = timeline.slice()
      // 优先：同名且 done=false 的最近 item
      let idx = -1
      for (let i = next.length - 1; i >= 0; i--) {
        const item = next[i]
        if (item.type === 'tool_call' && item.name === event.name && !item.done) { idx = i; break }
      }
      // 回退：最近未完成的任意 tool_call item
      if (idx === -1) {
        for (let i = next.length - 1; i >= 0; i--) {
          const item = next[i]
          if (item.type === 'tool_call' && !item.done) { idx = i; break }
        }
      }
      if (idx >= 0) {
        const item = next[idx]
        if (item.type === 'tool_call') {
          next[idx] = { ...item, result: resultSummary, done: true }
        }
        return { ...msg, agentTimeline: next }
      }
      // 无匹配且结果非空：新建仅含结果的 item
      if (resultSummary) {
        return {
          ...msg,
          agentTimeline: [...timeline, { type: 'tool_call', name: event.name, args: '', result: resultSummary, done: true }],
        }
      }
      return msg
    }

    case 'chat_token':
      // 思考后接回答：末尾未完成 thinking item 显式收口
      return { ...msg, chatResponse: (msg.chatResponse || '') + event.token, agentTimeline: closeLastThinking(timeline) }

    case 'chat_done': {
      // 流式结束：所有 thinking item 收口并提取标题写入 title
      const next = closeAllThinking(timeline).map((item) =>
        item.type === 'thinking' && item.title === undefined
          ? { ...item, title: extractThinkingTitleLocal(item.content) }
          : item,
      )
      return { ...msg, streaming: false, agentTimeline: next }
    }

    case 'error':
      return { ...msg, chatResponse: `❌ ${event.message || '未知错误'}`, streaming: false, agentTimeline: closeAllThinking(timeline) }

    default:
      return msg
  }
}

// 管线模式：thinking_token 按 node 字段写入对应 agent 阶段的 timeline（nodeTimelines）。
// node 缺失时归入 '' 键（与历史未分组思考兼容）。
// 收到新节点的 thinking_token 时，将其他节点未完成的 thinking item 防御性收口。
export function applyPipelineThinkingToken(msg: UIMessage, event: SSEEvent): UIMessage {
  if (event.type !== 'thinking_token') return msg
  const node = event.node || ''
  const nodeTimelines = { ...(msg.nodeTimelines ?? {}) }
  // 防御性收口：其他节点末尾未完成的 thinking item 置为完成态
  for (const key of Object.keys(nodeTimelines)) {
    if (key !== node) {
      nodeTimelines[key] = closeLastThinking(nodeTimelines[key])
    }
  }
  const current = nodeTimelines[node] ?? []
  nodeTimelines[node] = appendThinkingToken(current, event.token)
  return { ...msg, nodeTimelines }
}

// 管线模式：node_complete 将该节点末尾未完成的 thinking item 显式置为完成态（折叠横幅）。
export function applyPipelineNodeComplete(msg: UIMessage, nodeId: string): UIMessage {
  const nodeTimelines = msg.nodeTimelines
  if (!nodeTimelines || !nodeTimelines[nodeId]) return msg
  const next = { ...nodeTimelines }
  next[nodeId] = closeLastThinking(next[nodeId])
  return { ...msg, nodeTimelines: next }
}

// 历史会话恢复：从 chat_history 的 thinking（合并字符串）+ tool_calls 重建 agentTimeline。
// 历史数据无完整时序信息，按"思考在前、工具调用在后"近似还原（design.md 决策 7）。
export function buildTimelineFromHistory(
  thinking: string | undefined,
  toolCalls: Array<{ name: string; args?: Record<string, unknown>; result_text?: string; done?: boolean }> | undefined,
): TimelineItem[] {
  const timeline: TimelineItem[] = []
  if (thinking) {
    timeline.push({ type: 'thinking', content: thinking, title: extractThinkingTitleLocal(thinking) })
  }
  for (const tc of toolCalls ?? []) {
    // 搜索类工具由独立搜索横幅承载，历史恢复时不还原到工具调用横幅
    if (isSearchToolName(tc.name)) continue
    timeline.push({
      type: 'tool_call',
      name: tc.name,
      args: summarizeToolArgs(tc.args),
      result: tc.result_text,
      done: tc.done ?? true,
    })
  }
  return timeline
}

// 持久化时序恢复（persist-full-session-timeline）：防御式反序列化 chat_history.agentTimeline。
// 后端落盘数据可能缺失/非法/含脏项——逐项校验 type 枚举，合法项原样保留，非法输入回退空数组。
// 仅校验 type，不做深度字段校验（字段缺失由渲染层容错）。
const TIMELINE_ITEM_TYPES = new Set<string>(['thinking', 'search', 'tool_call'])

export function deserializeTimeline(raw: unknown): TimelineItem[] {
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (item): item is TimelineItem =>
      item !== null && typeof item === 'object' && TIMELINE_ITEM_TYPES.has((item as { type?: unknown }).type as string),
  )
}

// 防御式反序列化 sessions.pipeline_timelines（后端 GET 已 json.loads，传入的是 dict 而非 JSON 字符串）。
// 逐 key 调 deserializeTimeline；非法节点值回退空数组，非对象/数组输入整体回退空对象。
export function deserializeNodeTimelines(raw: unknown): Record<string, TimelineItem[]> {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const result: Record<string, TimelineItem[]> = {}
  for (const [node, value] of Object.entries(raw as Record<string, unknown>)) {
    result[node] = deserializeTimeline(value)
  }
  return result
}

// 将 tool_call 类型 TimelineItem 转为 ToolCallBanner 展示用的 ToolCallEntry（label/icon 映射）
export function timelineToolCallToEntry(item: Extract<TimelineItem, { type: 'tool_call' }>): ToolCallEntry {
  const icon =
    item.name === 'search_stock' ? '🔍' :
    item.name === 'batch_web_search' ? '🌐' : '🛠️'
  const label =
    item.name === 'search_stock' ? '识别股票' :
    item.name === 'batch_web_search' ? '批量搜索' :
    item.name === 'web_search' ? '网络搜索' : item.name
  return { name: item.name, label, icon, argText: item.args, resultText: item.result, done: item.done }
}

// 管线 node -> 中文角色名（阶段分组标题用；未知 node 原样返回）
const NODE_DISPLAY_NAMES: Record<string, string> = {
  check_cache: '数据准备',
  fetch_data: '数据获取',
  validate_financials: '勾稽校验',
  compute_metrics: '指标计算',
  technical_analyst: '技术面分析师',
  verify_citations: '引用校验',
  bull_r1: '多头分析师',
  bear_r1: '空头分析师',
  bull_r2: '多头分析师',
  bear_r2: '空头分析师',
  research_manager: '研究经理',
  trader: 'Trader',
  aggressive_r1: '激进风控',
  conservative_r1: '保守风控',
  neutral_r1: '中性风控',
  aggressive_r2: '激进风控',
  conservative_r2: '保守风控',
  neutral_r2: '中性风控',
  risk_judge: '风控裁决',
  fund_manager: '基金经理',
  generate_report: '报告生成',
  generate_file: '文件导出',
}

export function nodeDisplayName(node: string): string {
  return NODE_DISPLAY_NAMES[node] ?? node
}
