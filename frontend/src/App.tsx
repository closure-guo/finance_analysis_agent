import { useState, useRef, useEffect, useCallback } from 'react'
import type { SSEEvent, PipelineStep, UIMessage } from './types'

// ── Pipeline steps (mirrors backend LAYER_STEPS) ──
const PIPELINE_STEPS: PipelineStep[] = [
  { node: 'check_cache', layer: 'PREP', desc: 'PREP', icon: 'database' },
  { node: 'technical_analyst', layer: 'Layer I', desc: 'Layer I', icon: 'users' },
  { node: 'bull_r1', layer: 'Layer II', desc: 'Layer II', icon: 'comments' },
  { node: 'trader', layer: 'Layer III', desc: 'Trader', icon: 'hand-holding-usd' },
  { node: 'aggressive_r1', layer: 'Layer IV', desc: 'Risk', icon: 'shield-alt' },
  { node: 'fund_manager', layer: 'Layer V', desc: 'Fund', icon: 'user-tie' },
]

// 6-stage pipeline display nodes (one per layer)
const STAGE_NODES = ['check_cache', 'technical_analyst', 'bull_r1', 'trader', 'aggressive_r1', 'fund_manager']

let msgIdCounter = 0
const genId = () => `msg-${++msgIdCounter}`

export default function App() {
  const [appState, setAppState] = useState<'empty' | 'analyzing' | 'report'>('empty')
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [apiKey, setApiKey] = useState('')
  const [showApiKeyInput, setShowApiKeyInput] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pipelineMsgRef = useRef<UIMessage | null>(null)

  // Auto-scroll to bottom
  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
    }, 100)
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // ── SSE analysis ──
  const startAnalysis = async (stockCode: string, mode: string) => {
    if (!apiKey.trim()) {
      setShowApiKeyInput(true)
      return
    }

    // Transition to chat mode
    if (appState === 'empty') {
      setAppState('analyzing')
    }

    // Add user message
    const userMsg: UIMessage = {
      id: genId(),
      type: 'user',
      content: mode === 'quick'
        ? `快速分析 ${stockCode}`
        : `深度分析 ${stockCode}`,
    }
    setMessages(prev => [...prev, userMsg])

    if (mode === 'quick') {
      // Quick mode — single LLM call
      await quickChat(stockCode, null)
      return
    }

    // Deep research — SSE stream
    const pipelineMsg: UIMessage = {
      id: genId(),
      type: 'pipeline',
      content: '',
      completedNodes: [],
      currentNode: '',
      nodeOutputs: {},
      progress: 0,
    }
    pipelineMsgRef.current = pipelineMsg
    setMessages(prev => [...prev, pipelineMsg])

    try {
      const resp = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: stockCode,
          api_key: apiKey,
          analysis_type: 'comprehensive',
        }),
      })

      const reader = resp.body?.getReader()
      if (!reader) return

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event: SSEEvent = JSON.parse(line.slice(6))
            handleSSEEvent(event, pipelineMsg)
          } catch (e) {
            // Skip malformed lines
          }
        }
      }
    } catch (e) {
      console.error('SSE error:', e)
      updateMessage(pipelineMsg.id, {
        type: 'error',
        content: `连接错误: ${e instanceof Error ? e.message : 'Unknown'}`,
      })
    }
  }

  const handleSSEEvent = (event: SSEEvent, pipelineMsg: UIMessage) => {
    switch (event.type) {
      case 'analysis_start':
        updateMessage(pipelineMsg.id, {
          content: `开始分析 ${event.stock_name} (${event.stock_code})`,
        })
        break

      case 'node_start':
        updateMessage(pipelineMsg.id, {
          currentNode: event.node_id,
          content: `${event.layer}: ${event.desc}...`,
        })
        break

      case 'node_complete':
        updateMessage(pipelineMsg.id, {
          completedNodes: event.completed,
          currentNode: '',
          progress: event.progress,
          nodeOutputs: {
            ...(pipelineMsg.nodeOutputs || {}),
            [event.node_id]: event.output,
          },
          content: `${event.layer}: ${event.desc} ✓`,
        })
        break

      case 'report_ready':
        setAppState('report')
        // Add completion system message
        const completionMsg: UIMessage = {
          id: genId(),
          type: 'system',
          content: `分析完成 · 耗时 ${Math.round(event.duration_ms / 1000)} 秒`,
        }
        setMessages(prev => [...prev, completionMsg])

        // Add report message
        const reportMsg: UIMessage = {
          id: genId(),
          type: 'report',
          content: '',
          reportMarkdown: event.report_markdown,
          filePaths: event.file_paths,
          stockName: event.stock_name,
          durationMs: event.duration_ms,
        }
        setMessages(prev => [...prev, reportMsg])
        break

      case 'error':
        updateMessage(pipelineMsg.id, {
          type: 'error',
          content: `错误: ${event.message}`,
        })
        break

      case 'done':
        break
    }
  }

  const updateMessage = (id: string, updates: Partial<UIMessage>) => {
    setMessages(prev => prev.map(m => {
      if (m.id !== id) return m
      const updated = { ...m, ...updates }
      if (pipelineMsgRef.current?.id === id) {
        pipelineMsgRef.current = updated
      }
      return updated
    }))
  }

  // ── Quick chat ──
  const quickChat = async (message: string, context: Record<string, any> | null) => {
    // Add typing indicator
    const typingId = genId()
    const typingMsg: UIMessage = {
      id: typingId,
      type: 'system',
      content: 'typing',
    }
    setMessages(prev => [...prev, typingMsg])

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, context, api_key: apiKey }),
      })
      const data = await resp.json()

      setMessages(prev => prev.map(m =>
        m.id === typingId
          ? { ...m, type: 'chat', content: '', chatResponse: data.response || '无响应' }
          : m
      ))
    } catch (e) {
      setMessages(prev => prev.map(m =>
        m.id === typingId
          ? { ...m, type: 'error', content: `错误: ${e instanceof Error ? e.message : 'Unknown'}` }
          : m
      ))
    }
  }

  const handleSendFromEmpty = (text: string) => {
    const code = text.trim()
    if (!code) return
    startAnalysis(code, 'deep')
  }

  const handleSendFromChat = (text: string) => {
    const t = text.trim()
    if (!t) return

    // Add user message
    const userMsg: UIMessage = { id: genId(), type: 'user', content: t }
    setMessages(prev => [...prev, userMsg])

    // If report is ready, use quick chat for follow-up questions
    if (appState === 'report') {
      const reportMsg = messages.find(m => m.type === 'report')
      quickChat(t, reportMsg ? { stock_name: reportMsg.stockName, report: reportMsg.reportMarkdown } : null)
    } else {
      quickChat(t, null)
    }
  }

  // ── Render ──
  return (
    <main className="flex flex-col items-center min-h-screen">
      {appState === 'empty' ? (
        <EmptyState onSend={handleSendFromEmpty} apiKey={apiKey} setApiKey={setApiKey} showApiKeyInput={showApiKeyInput} setShowApiKeyInput={setShowApiKeyInput} />
      ) : (
        <>
          {/* Header */}
          <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-3 glass-card">
            <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                  <i className="fas fa-chart-line text-white text-sm"></i>
                </div>
                <span className="font-semibold text-sm tracking-wide">FinAgent</span>
            </div>
            <div className="flex items-center gap-4">
              <button className="text-zinc-400 hover:text-white transition-colors text-sm">
                <i className="fas fa-history mr-1"></i>历史
              </button>
              <button className="text-zinc-400 hover:text-white transition-colors text-sm" onClick={() => setShowApiKeyInput(true)}>
                <i className="fas fa-cog mr-1"></i>设置
              </button>
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-zinc-600 to-zinc-700"></div>
            </div>
          </header>

          {/* Chat messages */}
          <div className="w-full max-w-3xl px-4 pt-20 pb-40 space-y-6">
            {messages.map(msg => (
              <MessageRenderer key={msg.id} msg={msg} />
            ))}
          </div>

          {/* Fixed input at bottom */}
          <ChatInputBar onSend={handleSendFromChat} />
        </>
      )}

      {/* API Key modal */}
      {showApiKeyInput && (
        <ApiKeyModal
          apiKey={apiKey}
          setApiKey={setApiKey}
          onClose={() => setShowApiKeyInput(false)}
        />
      )}
    </main>
  )
}

// ── Empty State ──
function EmptyState({ onSend, apiKey, setApiKey, showApiKeyInput, setShowApiKeyInput }: {
  onSend: (text: string) => void
  apiKey: string
  setApiKey: (v: string) => void
  showApiKeyInput: boolean
  setShowApiKeyInput: (v: boolean) => void
}) {
  const [text, setText] = useState('')

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend(text)
      setText('')
    }
  }

  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 transition-all duration-700" style={{ minHeight: '100vh' }}>
      {/* Logo & Title */}
      <div className="text-center mb-10 animate-fade-in-up">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center mx-auto mb-5 shadow-2xl shadow-indigo-500/20">
          <i className="fas fa-chart-line text-white text-2xl"></i>
        </div>
        <h1 className="text-3xl font-bold mb-2 bg-gradient-to-r from-white via-zinc-200 to-zinc-400 bg-clip-text text-transparent">
          Finance Analysis Agent
        </h1>
        <p className="text-zinc-500 text-sm">AI 驱动的 A 股投研分析系统</p>
      </div>

      {/* Input Box */}
      <div className="w-full max-w-2xl animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <div className="glass-input rounded-2xl p-2">
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              placeholder="输入股票代码或名称，例如：000858 五粮液..."
              className="flex-1 bg-transparent text-zinc-200 placeholder-zinc-600 px-4 py-3 resize-none outline-none text-sm leading-relaxed"
              style={{ minHeight: '48px', maxHeight: '120px' }}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeydown}
            />
            <button
              onClick={() => { onSend(text); setText('') }}
              className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center hover:shadow-lg hover:shadow-indigo-500/30 transition-all mb-1 mr-1"
            >
              <i className="fas fa-arrow-up text-white text-sm"></i>
            </button>
          </div>
          {/* Quick actions */}
          <div className="flex gap-2 px-4 pb-2 pt-1">
            <button className="chip px-3 py-1 rounded-lg text-xs border border-zinc-700/50 text-zinc-400 bg-zinc-800/50" onClick={() => { if (!apiKey) { setShowApiKeyInput(true); return }; onSend('000858') }}>
              <i className="fas fa-bolt mr-1 text-yellow-500"></i>快速分析
            </button>
            <button className="chip px-3 py-1 rounded-lg text-xs border border-zinc-700/50 text-zinc-400 bg-zinc-800/50" onClick={() => { if (!apiKey) { setShowApiKeyInput(true); return }; onSend('600519') }}>
              <i className="fas fa-layer-group mr-1 text-indigo-400"></i>深度报告
            </button>
            <button className="chip px-3 py-1 rounded-lg text-xs border border-zinc-700/50 text-zinc-400 bg-zinc-800/50" onClick={() => { if (!apiKey) { setShowApiKeyInput(true); return }; onSend('000858,000568') }}>
              <i className="fas fa-balance-scale mr-1 text-green-400"></i>同业对比
            </button>
          </div>
        </div>
        {!apiKey && (
          <p className="text-center text-xs text-zinc-600 mt-2">
            <i className="fas fa-info-circle mr-1"></i>
            需要配置 API Key 才能开始分析
            <button className="text-indigo-400 hover:underline ml-1" onClick={() => setShowApiKeyInput(true)}>去配置</button>
          </p>
        )}
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-8 max-w-2xl w-full px-4 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
        {[
          { icon: 'users', color: 'text-indigo-400', label: '4 维并行分析' },
          { icon: 'comments', color: 'text-amber-400', label: 'Bull/Bear 辩论' },
          { icon: 'shield-alt', color: 'text-red-400', label: 'Risk 压力测试' },
          { icon: 'file-alt', color: 'text-cyan-400', label: '结构化报告' },
        ].map(f => (
          <div key={f.label} className="glass-card rounded-xl p-3 text-center">
            <div className={`${f.color} text-lg mb-1`}><i className={`fas fa-${f.icon}`}></i></div>
            <div className="text-xs text-zinc-400">{f.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Message Renderer ──
function MessageRenderer({ msg }: { msg: UIMessage }) {
  if (msg.type === 'user') {
    return (
      <div className="flex justify-end animate-slide-in">
        <div className="max-w-[85%] md:max-w-[75%]">
          <div className="msg-user rounded-2xl rounded-tr-sm px-5 py-3 text-sm text-white leading-relaxed shadow-lg shadow-indigo-500/10">
            {msg.content}
          </div>
        </div>
      </div>
    )
  }

  if (msg.type === 'error') {
    return (
      <div className="flex justify-start animate-slide-in">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center flex-shrink-0 mt-1">
              <i className="fas fa-exclamation text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-2xl rounded-tl-sm px-5 py-3 flex-1">
              <p className="text-sm text-red-400">{msg.content}</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (msg.type === 'system' && msg.content === 'typing') {
    return (
      <div className="flex justify-start">
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-lg shadow-indigo-500/20">
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-2xl rounded-tl-sm px-4 py-3">
            <div className="flex gap-1.5">
              <div className="w-2 h-2 rounded-full bg-zinc-500 typing-dot"></div>
              <div className="w-2 h-2 rounded-full bg-zinc-500 typing-dot"></div>
              <div className="w-2 h-2 rounded-full bg-zinc-500 typing-dot"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (msg.type === 'system') {
    return (
      <div className="flex justify-start animate-slide-in">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
              <i className="fas fa-robot text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-2xl rounded-tl-sm px-5 py-3 flex-1">
              <div className="flex items-center gap-2 text-green-400 text-xs">
                <i className="fas fa-check-circle"></i>
                <span>{msg.content}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (msg.type === 'pipeline') {
    return <PipelineCard msg={msg} />
  }

  if (msg.type === 'report') {
    return <ReportCard msg={msg} />
  }

  if (msg.type === 'chat') {
    return (
      <div className="flex justify-start animate-slide-in">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
              <i className="fas fa-robot text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-2xl rounded-tl-sm px-5 py-4 flex-1">
              <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{msg.chatResponse}</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return null
}

// ── Pipeline Card ──
function PipelineCard({ msg }: { msg: UIMessage }) {
  const [showLog, setShowLog] = useState(false)
  const completed = msg.completedNodes || []
  const current = msg.currentNode || ''
  const progress = msg.progress || 0
  const outputs = msg.nodeOutputs || {}

  // Determine stage status
  const getStageStatus = (node: string) => {
    // Check if this stage or any node in the same layer is completed
    const layerMap: Record<string, string[]> = {
      'check_cache': ['check_cache', 'fetch_data', 'validate_financials', 'compute_metrics'],
      'technical_analyst': ['technical_analyst', 'verify_citations'],
      'bull_r1': ['bull_r1', 'bear_r1', 'bull_r2', 'bear_r2', 'research_manager'],
      'trader': ['trader'],
      'aggressive_r1': ['aggressive_r1', 'conservative_r1', 'neutral_r1', 'aggressive_r2', 'conservative_r2', 'neutral_r2', 'risk_judge'],
      'fund_manager': ['fund_manager', 'generate_report', 'generate_file'],
    }
    const layerNodes = layerMap[node] || [node]
    const allDone = layerNodes.every(n => completed.includes(n))
    const anyRunning = layerNodes.some(n => n === current)
    if (allDone) return 'completed'
    if (anyRunning) return 'running'
    // Check if any earlier stage is still running
    const stageIdx = STAGE_NODES.indexOf(node)
    if (stageIdx > 0) {
      const prevStatus = getStageStatus(STAGE_NODES[stageIdx - 1])
      if (prevStatus === 'completed') return 'running'  // Next stage should be running
    }
    return 'pending'
  }

  // Get analyst cards from outputs
  const analystOutput = outputs['technical_analyst']
  const analystCards = [
    { name: 'Fundamental', nameZh: '基本面', summary: '分析中...', status: 'pending', color: 'green' as const },
    { name: 'Technical', nameZh: '技术面', summary: '分析中...', status: 'pending', color: 'yellow' as const },
    { name: 'Macro', nameZh: '宏观', summary: '分析中...', status: 'pending', color: 'green' as const },
    { name: 'Sentiment', nameZh: '舆情', summary: '等待中...', status: 'pending', color: 'neutral' as const },
  ]

  // Update analyst cards based on completed nodes
  if (completed.includes('technical_analyst')) {
    analystCards[0] = { name: 'Fundamental', nameZh: '基本面', summary: analystOutput?.summary || '基本面分析完成', status: 'completed', color: 'green' }
    analystCards[1] = { name: 'Technical', nameZh: '技术面', summary: analystOutput?.summary || '技术面分析完成', status: 'completed', color: 'yellow' }
    analystCards[2] = { name: 'Macro', nameZh: '宏观', summary: '宏观分析完成', status: 'completed', color: 'green' }
    analystCards[3] = { name: 'Sentiment', nameZh: '舆情', summary: '舆情分析完成', status: 'completed', color: 'green' }
  } else if (current === 'technical_analyst') {
    analystCards.forEach(c => { c.status = 'running'; c.summary = '分析中...' })
  }

  return (
    <div className="flex justify-start animate-slide-in">
      <div className="max-w-[95%] md:max-w-[90%] w-full">
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-2xl rounded-tl-sm overflow-hidden flex-1">
            {/* Progress Pipeline */}
            <div className="px-5 pt-4 pb-2">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-zinc-400">分析进度</span>
                  <span className="text-xs text-zinc-600">{msg.content || '准备中...'}</span>
                </div>
                <span className="text-xs text-zinc-600 font-mono">~90s</span>
              </div>
              <div className="flex items-center gap-1 mb-4">
                <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-1000"
                    style={{ width: `${Math.max(5, progress * 100)}%` }}
                  />
                </div>
              </div>
              {/* Pipeline Nodes */}
              <div className="flex justify-between px-1">
                {PIPELINE_STEPS.map((step, i) => {
                  const status = getStageStatus(step.node)
                  return (
                    <div key={step.node} className="flex items-center" style={{ flex: i < PIPELINE_STEPS.length - 1 ? '1' : 'none' }}>
                      <div className="flex flex-col items-center gap-1">
                        <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center node-${status} ${status === 'running' ? 'pulse-ring' : ''}`}
                          style={status === 'running' ? { borderColor: '#6366f1', background: 'rgba(99,102,241,0.2)' } : status === 'completed' ? { borderColor: '#22c55e', background: 'rgba(34,197,94,0.2)' } : { borderColor: '#3f3f46' }}>
                          <i className={`fas fa-${step.icon} text-xs`}></i>
                        </div>
                        <span className="text-[10px] text-zinc-500">{step.desc}</span>
                      </div>
                      {i < PIPELINE_STEPS.length - 1 && (
                        <div className="flex-1 flex items-center justify-center pt-2 px-1">
                          <div className={`w-full h-px ${status === 'completed' ? 'bg-green-500/50' : 'bg-zinc-800'}`}></div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Layer I: Analyst Cards */}
            {(completed.includes('check_cache') || current === 'technical_analyst' || completed.includes('technical_analyst')) && (
              <div className="px-5 py-3 border-t border-zinc-800/50">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Layer I - 并行分析师</span>
                  <span className="text-[10px] text-zinc-600">
                    {completed.includes('technical_analyst') ? '4/4 完成' : '0/4 完成'}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 pipeline-grid">
                  {analystCards.map(card => (
                    <AnalystCard key={card.name} {...card} />
                  ))}
                </div>
              </div>
            )}

            {/* Expandable log */}
            <div className="px-5 py-3 border-t border-zinc-800/50">
              <button
                onClick={() => setShowLog(!showLog)}
                className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors w-full"
              >
                <i className={`fas fa-chevron-down transition-transform ${showLog ? '' : 'rotate-[-90deg]'}`}></i>
                <span>查看实时输出日志</span>
              </button>
              {showLog && (
                <div className="mt-2 bg-zinc-950 rounded-lg p-3 font-mono text-[11px] text-zinc-500 leading-relaxed overflow-x-auto">
                  {completed.map(node => (
                    <div key={node}>
                      <span className="text-zinc-700">[{new Date().toLocaleTimeString()}]</span>{' '}
                      <span className="text-indigo-500">{node.toUpperCase()}</span>{' '}
                      {outputs[node]?.summary || 'completed'}
                    </div>
                  ))}
                  {current && (
                    <div>
                      <span className="text-zinc-700">[{new Date().toLocaleTimeString()}]</span>{' '}
                      <span className="text-yellow-500">{current.toUpperCase()}</span>{' '}
                      running...
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Analyst Card ──
function AnalystCard({ name, nameZh, summary, status, color }: {
  name: string
  nameZh: string
  summary: string
  status: string
  color: 'green' | 'yellow' | 'red' | 'neutral'
}) {
  const colors = {
    green: { border: 'border-green-500/30', bg: 'bg-green-500/10', text: 'text-green-400' },
    yellow: { border: 'border-yellow-500/30', bg: 'bg-yellow-500/10', text: 'text-yellow-400' },
    red: { border: 'border-red-500/30', bg: 'bg-red-500/10', text: 'text-red-400' },
    neutral: { border: 'border-indigo-500/30', bg: 'bg-indigo-500/10', text: 'text-indigo-400' },
  }
  const c = colors[color]

  const statusIcon = status === 'completed'
    ? <i className="fas fa-check-circle text-green-500"></i>
    : status === 'running'
    ? <div className="w-3 h-3 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin"></div>
    : <div className="w-2 h-2 rounded-full bg-zinc-600"></div>

  return (
    <div className={`${c.border} ${c.bg} border rounded-xl p-3 cursor-pointer hover:border-opacity-60 transition-all`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${c.text}`}>{name}</span>
          <span className="text-[10px] text-zinc-600">{nameZh}</span>
        </div>
        {statusIcon}
      </div>
      <div className="text-[11px] text-zinc-400 leading-snug">{summary}</div>
    </div>
  )
}

// ── Report Card ──
function ReportCard({ msg }: { msg: UIMessage }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    fundamental: true,
    technical: false,
    debate: false,
    risk: false,
  })

  const toggle = (key: string) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  return (
    <div className="flex justify-start animate-slide-in">
      <div className="max-w-[95%] md:max-w-[90%] w-full">
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-2xl rounded-tl-sm overflow-hidden flex-1">
            {/* Report Header */}
            <div className="px-5 pt-4 pb-3 border-b border-zinc-800/50">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-lg font-bold text-white">{msg.stockName}</h3>
                    <span className="px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-400 text-[10px] font-semibold">深度分析</span>
                  </div>
                  <p className="text-xs text-zinc-500">深度分析报告 · 5 层 Agent 架构 · 耗时 {Math.round((msg.durationMs || 0) / 1000)}s</p>
                </div>
                <div className="flex gap-2">
                  {msg.filePaths?.docx && (
                    <a href={`/api/files/${msg.filePaths.docx.split(/[\\/]/).pop()}`} download
                      className="w-8 h-8 rounded-lg bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-zinc-400 transition-colors" title="导出 Word">
                      <i className="fas fa-file-word text-xs"></i>
                    </a>
                  )}
                  {msg.filePaths?.pptx && (
                    <a href={`/api/files/${msg.filePaths.pptx.split(/[\\/]/).pop()}`} download
                      className="w-8 h-8 rounded-lg bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-zinc-400 transition-colors" title="导出 PPT">
                      <i className="fas fa-file-powerpoint text-xs"></i>
                    </a>
                  )}
                </div>
              </div>
            </div>

            {/* Report Markdown */}
            {msg.reportMarkdown && (
              <div className="px-5 py-3 border-b border-zinc-800/50">
                <div className="text-sm text-zinc-300 leading-relaxed max-h-[400px] overflow-y-auto whitespace-pre-wrap">
                  {msg.reportMarkdown.slice(0, 2000)}
                  {msg.reportMarkdown.length > 2000 && '...'}
                </div>
              </div>
            )}

            {/* Disclaimer */}
            <div className="px-5 py-3">
              <p className="text-[10px] text-zinc-600 leading-relaxed">
                <i className="fas fa-info-circle mr-1"></i>
                本报告由 AI 系统基于公开数据自动生成，仅供参考研究，不构成投资建议。投资有风险，入市需谨慎。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Chat Input Bar ──
function ChatInputBar({ onSend }: { onSend: (text: string) => void }) {
  const [text, setText] = useState('')

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend(text)
      setText('')
    }
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 px-4 pb-4 pt-2" style={{ background: 'linear-gradient(to top, #0a0a0f 80%, transparent)' }}>
      <div className="max-w-3xl mx-auto">
        <div className="glass-input rounded-2xl p-2">
          <div className="flex items-end gap-2">
            <button className="w-8 h-8 rounded-lg hover:bg-zinc-700/50 flex items-center justify-center text-zinc-500 transition-colors mb-1">
              <i className="fas fa-plus text-xs"></i>
            </button>
            <textarea
              rows={1}
              placeholder="追问报告中的任何内容..."
              className="flex-1 bg-transparent text-zinc-200 placeholder-zinc-600 px-2 py-3 resize-none outline-none text-sm leading-relaxed"
              style={{ minHeight: '40px', maxHeight: '100px' }}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeydown}
            />
            <button
              onClick={() => { onSend(text); setText('') }}
              className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center hover:shadow-lg hover:shadow-indigo-500/30 transition-all mb-0.5 mr-0.5"
            >
              <i className="fas fa-arrow-up text-white text-xs"></i>
            </button>
          </div>
        </div>
        <div className="text-center mt-1">
          <span className="text-zinc-600 text-[10px]">AI 生成仅供参考，不构成投资建议</span>
        </div>
      </div>
    </div>
  )
}

// ── API Key Modal ──
function ApiKeyModal({ apiKey, setApiKey, onClose }: {
  apiKey: string
  setApiKey: (v: string) => void
  onClose: () => void
}) {
  const [value, setValue] = useState(apiKey)

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="glass-card rounded-2xl p-6 max-w-md w-full mx-4" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-white mb-4">配置 API Key</h3>
        <p className="text-xs text-zinc-500 mb-4">输入 DeepSeek API Key 用于 LLM 调用。Key 仅保存在浏览器内存中，不会持久化。</p>
        <input
          type="password"
          placeholder="sk-..."
          value={value}
          onChange={e => setValue(e.target.value)}
          className="w-full glass-input rounded-xl px-4 py-3 text-sm text-zinc-200 outline-none mb-4"
        />
        <div className="flex gap-3">
          <button
            onClick={() => { setApiKey(value); onClose() }}
            className="flex-1 py-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white text-sm font-medium hover:shadow-lg hover:shadow-indigo-500/30 transition-all"
          >
            确认
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-zinc-800 text-zinc-400 text-sm hover:bg-zinc-700 transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
