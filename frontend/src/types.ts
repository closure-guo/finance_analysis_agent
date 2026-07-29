// SSE event types from the backend

export interface AnalysisStartEvent {
  type: 'analysis_start'
  analysis_id: string
  stock_code: string
  stock_name: string
  timestamp: string
}

export interface NodeStartEvent {
  type: 'node_start'
  node_id: string
  layer: string
  desc: string
  icon: string
  timestamp: string
  // 后端真实入口时间戳（fix-node-timer-real-lifecycle）
  server_start_ts?: number
}

export interface NodeCompleteEvent {
  type: 'node_complete'
  node_id: string
  layer: string
  desc: string
  completed: string[]
  progress: number
  output: Record<string, any>
  timestamp: string
}

// 节点真实耗时（node_end 到达时下发，覆盖 updates 近似值）
export interface NodeTimingEvent {
  type: 'node_timing'
  node_id: string
  server_start_ts?: number
  server_end_ts?: number
  server_duration_ms?: number
  timestamp: string
}

export interface ReportReadyEvent {
  type: 'report_ready'
  analysis_id: string
  session_id: string
  report_markdown: string
  chart_data: ChartData
  file_paths: Record<string, string>
  stock_name: string
  duration_ms: number
  web_sources?: Array<{ query: string; title: string; url: string; content: string }>
  timestamp: string
}

// ── New streaming events ──

export interface ParsingEvent {
  type: 'parsing'
  query: string
  timestamp: string
}

export interface ResolvedEvent {
  type: 'resolved'
  stock_code: string
  stock_name: string
  timestamp: string
}

export interface ReportChunkEvent {
  type: 'report_chunk'
  chunk_index: number
  total_chunks: number
  text: string
  timestamp: string
}

export interface ChatTokenEvent {
  type: 'chat_token'
  token: string
  timestamp: string
}

export interface ThinkingTokenEvent {
  type: 'thinking_token'
  token: string
  node?: string
  timestamp: string
}

export interface ThinkingToAnswerEvent {
  type: 'thinking_to_answer'
  answer: string
  timestamp: string
}

export interface ThinkingReplaceEvent {
  type: 'thinking_replace'
  token: string
  timestamp: string
}

export interface ToolCallEvent {
  type: 'tool_call'
  name: string
  args: Record<string, any>
  iteration: number
  timestamp: string
}

export interface ToolResultEvent {
  type: 'tool_result'
  name: string
  result: any
  timestamp: string
}

export interface ChatDoneEvent {
  type: 'chat_done'
  timestamp: string
}

export interface SearchStartEvent {
  type: 'search_start'
  query: string
  timestamp: string
}

export interface SearchResultEvent {
  type: 'search_result'
  query: string
  results: Array<{ title: string; url: string; content: string }>
  count: number
  timestamp: string
}

export interface StockResolvedEvent {
  type: 'stock_resolved'
  stock_code: string
  stock_name: string
  timestamp: string
}

export interface SearchErrorEvent {
  type: 'search_error'
  message: string
  timestamp: string
}

// ── Chart data types ──

export interface AnnualEntry {
  year: string
  revenue: number | null
  net_profit: number | null
  gross_margin: number | null
  net_margin: number | null
  roe: number | null
  roa: number | null
  ocf: number | null
  total_assets: number | null
  equity: number | null
  contract_liab: number | null
  cip: number | null
  debt_ratio: number | null
}

export interface ChartData {
  stock_code: string
  stock_name: string
  annual: AnnualEntry[]
  growth: {
    years: string[]
    revenue_growth: (number | null)[]
    profit_growth: (number | null)[]
  }
  price: {
    daily: Array<{ date: string; close: number }>
    earnings_dates: string[]
  }
  kpi: {
    current_price?: number
    market_cap?: number
    pe?: number
    pb?: number
    '52w_high'?: number
    '52w_low'?: number
  }
  market_share: any
}

export interface ErrorEvent {
  type: 'error'
  node_id: string
  message: string
  timestamp: string
}

export interface DoneEvent {
  type: 'done'
  analysis_id: string
  duration_ms: number
  timestamp: string
}

export interface SessionCreatedEvent {
  type: 'session_created'
  session_id: string
  display_name: string
  timestamp: string
}

export interface AwaitingInputEvent {
  type: 'awaiting_input'
  session_id: string
  pending_intent: string
  timestamp: string
}

// ── Session types ──
export type SSEEvent =
  | AnalysisStartEvent
  | NodeStartEvent
  | NodeCompleteEvent
  | NodeTimingEvent
  | ReportReadyEvent
  | ParsingEvent
  | ResolvedEvent
  | ReportChunkEvent
  | ChatTokenEvent
  | ThinkingTokenEvent
  | ThinkingToAnswerEvent
  | ThinkingReplaceEvent
  | ToolCallEvent
  | ToolResultEvent
  | ChatDoneEvent
  | SearchStartEvent
  | SearchResultEvent
  | StockResolvedEvent
  | SearchErrorEvent
  | ErrorEvent
  | DoneEvent
  | SessionCreatedEvent
  | AwaitingInputEvent

// ── Session types ──

export interface SessionMeta {
  session_id: string
  stock_code: string
  stock_name: string
  display_name: string
  status: string
  created_at: string
  duration_ms: number
  report_len?: number
  session_type?: string
}

export interface ChatHistoryEntry {
  role: string
  content: string
  ts: string
  thinking?: string
  tool_calls?: Array<{ name: string; args?: Record<string, any>; result_text?: string; done?: boolean }>
}

export interface SessionDetail extends SessionMeta {
  report_markdown: string
  chart_data: ChartData
  analyst_reports: Record<string, any>
  agent_process: Record<string, any>
  analyst_summaries: Record<string, any>
  chat_history: ChatHistoryEntry[]
}

// Pipeline step definition
export interface PipelineStep {
  node: string
  layer: string
  desc: string
  icon: string
}

// UI message types
export type MessageType = 'user' | 'pipeline' | 'report' | 'chat' | 'system' | 'error'

// 单次工具调用记录（ToolCallBanner 渲染用，从 TimelineItem tool_call 转换而来）
export interface ToolCallEntry {
  name: string
  label: string
  icon: string
  argText: string
  resultText?: string
  done?: boolean
}

// Agent 时序条目：按 SSE 事件到达顺序追加，渲染时按 type 分发为独立横幅。
// - thinking：思考片段（被搜索/工具调用断开的多段思考各自独立，title 由 extractThinkingTitle 提取）
// - search：搜索（web_search / batch_web_search 由 search_* 事件驱动，不生成 tool_call 条目）
// - tool_call：其他工具调用（每次调用一个独立条目）
export type TimelineItem =
  | { type: 'thinking'; content: string; title?: string; done?: boolean }
  | {
      type: 'search'
      query: string
      results?: Array<{ title: string; url: string; content: string }>
      status: 'searching' | 'done' | 'error'
    }
  | { type: 'tool_call'; name: string; args: string; result?: string; done: boolean }

export interface UIMessage {
  id: string
  type: MessageType
  content: string
  // Pipeline-specific
  completedNodes?: string[]
  currentNode?: string
  nodeOutputs?: Record<string, any>
  progress?: number
  // 管线启动时间戳（ms epoch），用于 ETA 已用时长计算
  startedAt?: number
  // 分层时间轴状态树（redesign delta）：node_start/node_complete 驱动的 6 层→子节点状态
  layerTree?: import('./pipelineTree').LayerNode[]
  // Report-specific
  reportMarkdown?: string
  chartData?: ChartData
  filePaths?: Record<string, string>
  stockName?: string
  durationMs?: number
  sessionId?: string
  streaming?: boolean
  webSources?: Array<{ query: string; title: string; url: string; content: string }>
  // Chat-specific
  chatResponse?: string
  // Agent 时序：思考/搜索/工具调用按 SSE 事件到达顺序纵向排列（chat 消息与管线消息共用）
  agentTimeline?: TimelineItem[]
  // 管线模式：按 node 分组的时序（key 为 thinking_token 事件的 node 字段，如 bull_debater）
  nodeTimelines?: Record<string, TimelineItem[]>
}
