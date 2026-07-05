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

export interface ReportReadyEvent {
  type: 'report_ready'
  analysis_id: string
  report_markdown: string
  chart_data: ChartData
  file_paths: Record<string, string>
  stock_name: string
  duration_ms: number
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

export type SSEEvent =
  | AnalysisStartEvent
  | NodeStartEvent
  | NodeCompleteEvent
  | ReportReadyEvent
  | ErrorEvent
  | DoneEvent

// Pipeline step definition
export interface PipelineStep {
  node: string
  layer: string
  desc: string
  icon: string
}

// UI message types
export type MessageType = 'user' | 'pipeline' | 'report' | 'chat' | 'system' | 'error'

export interface UIMessage {
  id: string
  type: MessageType
  content: string
  // Pipeline-specific
  completedNodes?: string[]
  currentNode?: string
  nodeOutputs?: Record<string, any>
  progress?: number
  // Report-specific
  reportMarkdown?: string
  chartData?: ChartData
  filePaths?: Record<string, string>
  stockName?: string
  durationMs?: number
  // Chat-specific
  chatResponse?: string
}
