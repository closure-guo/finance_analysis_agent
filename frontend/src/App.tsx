import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { SSEEvent, PipelineStep, UIMessage, SessionMeta, SessionDetail } from './types'
import { ChartsSection } from './Charts'

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
  const pipelineMsgRef = useRef<UIMessage | null>(null)

  // Session state
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const streamingReportRef = useRef<UIMessage | null>(null)
  const [mode, setMode] = useState<'quick' | 'deep'>('deep')

  // Auto-scroll to bottom
  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
    }, 100)
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // ── Session management ──
  const loadSessions = useCallback(async () => {
    try {
      const resp = await fetch('/api/sessions')
      const data = await resp.json()
      setSessions(data.sessions || [])
    } catch (e) {
      console.error('Failed to load sessions:', e)
    }
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  const selectSession = async (sessionId: string) => {
    try {
      const resp = await fetch(`/api/sessions/${sessionId}`)
      if (!resp.ok) throw new Error('Failed to load session')
      const data: SessionDetail = await resp.json()
      setCurrentSessionId(sessionId)
      setAppState('report')
      streamingReportRef.current = null

      const newMessages: UIMessage[] = []
      // Add report message
      newMessages.push({
        id: genId(),
        type: 'report',
        content: '',
        reportMarkdown: data.report_markdown,
        chartData: data.chart_data,
        stockName: data.stock_name,
        durationMs: data.duration_ms,
        sessionId: data.session_id,
      })
      // Add chat history
      if (data.chat_history) {
        for (const h of data.chat_history) {
          if (h.role === 'user') {
            newMessages.push({ id: genId(), type: 'user', content: h.content })
          } else {
            newMessages.push({ id: genId(), type: 'chat', content: '', chatResponse: h.content })
          }
        }
      }
      setMessages(newMessages)
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  const deleteSession = async (sessionId: string) => {
    try {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null)
        streamingReportRef.current = null
        setMessages([])
        setAppState('empty')
      }
    } catch (e) {
      console.error('Failed to delete session:', e)
    }
  }

  const renameSession = async (sessionId: string, displayName: string) => {
    try {
      await fetch(`/api/sessions/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName }),
      })
      setSessions(prev => prev.map(s => s.session_id === sessionId ? { ...s, display_name: displayName } : s))
    } catch (e) {
      console.error('Failed to rename session:', e)
    }
  }

  const newAnalysis = () => {
    setCurrentSessionId(null)
    streamingReportRef.current = null
    setMessages([])
    setAppState('empty')
  }

  // ── SSE analysis ──
  const startAnalysis = async (query: string, mode: string, stockCode?: string, stockName?: string) => {
    if (!apiKey.trim()) {
      setShowApiKeyInput(true)
      return
    }

    // Transition to chat mode
    if (appState === 'empty') {
      setAppState('analyzing')
    }

    setCurrentSessionId(null)
    streamingReportRef.current = null

    // Add user message
    const userMsg: UIMessage = {
      id: genId(),
      type: 'user',
      content: mode === 'quick'
        ? `快速分析 ${query}`
        : `深度分析 ${query}`,
    }
    setMessages(prev => [...prev, userMsg])

    if (mode === 'quick') {
      // Quick mode — single LLM call
      await quickChat(query)
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
      thinkingContent: '',
    }
    pipelineMsgRef.current = pipelineMsg
    setMessages(prev => [...prev, pipelineMsg])

    try {
      const resp = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          api_key: apiKey,
          analysis_type: 'comprehensive',
          ...(stockCode ? { stock_code: stockCode } : {}),
          ...(stockName ? { stock_name: stockName } : {}),
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
          } catch {
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
      case 'parsing':
        updateMessage(pipelineMsg.id, {
          content: `正在识别：${event.query}...`,
        })
        break

      case 'resolved':
        updateMessage(pipelineMsg.id, {
          content: `已识别：${event.stock_name} (${event.stock_code})`,
        })
        break

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

      case 'thinking_token':
        updateMessage(pipelineMsg.id, {
          thinkingContent: (pipelineMsg.thinkingContent || '') + event.token,
        })
        break

      case 'report_chunk': {
        // Accumulate report chunks and render progressively
        if (!streamingReportRef.current) {
          const reportMsg: UIMessage = {
            id: genId(),
            type: 'report',
            content: '',
            reportMarkdown: event.text,
            streaming: true,
          }
          streamingReportRef.current = reportMsg
          setMessages(prev => [...prev, reportMsg])
        } else {
          const id = streamingReportRef.current.id
          const newText = (streamingReportRef.current.reportMarkdown || '') + event.text
          streamingReportRef.current = { ...streamingReportRef.current, reportMarkdown: newText }
          setMessages(prev => prev.map(m => m.id === id ? { ...m, reportMarkdown: newText } : m))
        }
        break
      }

      case 'report_ready': {
        // Finalize streaming report or create new if no chunks were received
        if (streamingReportRef.current) {
          updateMessage(streamingReportRef.current.id, {
            reportMarkdown: event.report_markdown,
            chartData: event.chart_data,
            filePaths: event.file_paths,
            stockName: event.stock_name,
            durationMs: event.duration_ms,
            sessionId: event.session_id,
            streaming: false,
          })
          streamingReportRef.current = null
        } else {
          const reportMsg: UIMessage = {
            id: genId(),
            type: 'report',
            content: '',
            reportMarkdown: event.report_markdown,
            chartData: event.chart_data,
            filePaths: event.file_paths,
            stockName: event.stock_name,
            durationMs: event.duration_ms,
            sessionId: event.session_id,
          }
          setMessages(prev => [...prev, reportMsg])
        }
        setAppState('report')
        setCurrentSessionId(event.session_id)
        loadSessions()

        // Add completion system message
        const completionMsg: UIMessage = {
          id: genId(),
          type: 'system',
          content: `分析完成 · 耗时 ${Math.round(event.duration_ms / 1000)} 秒`,
        }
        setMessages(prev => [...prev, completionMsg])
        break
      }

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

  // ── Streaming chat ──
  const quickChat = async (message: string) => {
    const chatId = genId()
    const chatMsg: UIMessage = {
      id: chatId,
      type: 'chat',
      content: '',
      chatResponse: '',
      streaming: true,
    }
    setMessages(prev => [...prev, chatMsg])

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: currentSessionId,
          api_key: apiKey,
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
            if (event.type === 'search_start') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'searching', searchQuery: event.query }
                  : m
              ))
            } else if (event.type === 'search_result') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'done', searchResults: event.results }
                  : m
              ))
            } else if (event.type === 'search_error') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'error' }
                  : m
              ))
            } else if (event.type === 'thinking_token') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, thinkingContent: (m.thinkingContent || '') + event.token }
                  : m
              ))
            } else if (event.type === 'chat_token') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, chatResponse: (m.chatResponse || '') + event.token }
                  : m
              ))
            } else if (event.type === 'error') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, chatResponse: `❌ ${event.message || '未知错误'}`, streaming: false }
                  : m
              ))
            } else if (event.type === 'chat_done') {
              setMessages(prev => prev.map(m =>
                m.id === chatId ? { ...m, streaming: false } : m
              ))
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    } catch (e) {
      setMessages(prev => prev.map(m =>
        m.id === chatId
          ? { ...m, type: 'error', content: `错误: ${e instanceof Error ? e.message : 'Unknown'}`, streaming: false }
          : m
      ))
    }
  }

  // ── Deep research intent clarification (Kimi-style) ──
  const startDeepClarify = async (query: string) => {
    if (!apiKey.trim()) {
      setShowApiKeyInput(true)
      return
    }

    if (appState === 'empty') {
      setAppState('analyzing')
    }
    setCurrentSessionId(null)
    streamingReportRef.current = null

    // 用户消息
    const userMsg: UIMessage = { id: genId(), type: 'user', content: query }
    setMessages(prev => [...prev, userMsg])

    // 澄清卡片占位（loading 态）
    const clarifyMsg: UIMessage = {
      id: genId(),
      type: 'clarify',
      content: '',
      clarifyData: null,
      clarifyStarted: false,
      streaming: true,
      clarifyThinking: '',
      clarifyTools: [],
    }
    setMessages(prev => [...prev, clarifyMsg])

    try {
      const resp = await fetch('/api/clarify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, api_key: apiKey }),
      })
      if (!resp.ok) {
        throw new Error(`服务器错误 (${resp.status})`)
      }
      const reader = resp.body!.getReader()
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

            if (event.type === 'clarify_tool') {
              setMessages(prev => prev.map(m => {
                if (m.id !== clarifyMsg.id) return m
                const tools = [...(m.clarifyTools || [])]
                if (event.status === 'running') {
                  tools.push({ tool: event.tool, status: 'running' })
                } else {
                  const idx = tools.findIndex(t => t.tool === event.tool && t.status === 'running')
                  if (idx >= 0) {
                    tools[idx] = {
                      tool: event.tool,
                      status: event.status,
                      result_summary: event.result_summary,
                      source: event.source,
                      error: event.error,
                    }
                  } else {
                    tools.push({
                      tool: event.tool,
                      status: event.status,
                      result_summary: event.result_summary,
                      source: event.source,
                      error: event.error,
                    })
                  }
                }
                return { ...m, clarifyTools: tools }
              }))
            } else if (event.type === 'clarify_thinking') {
              setMessages(prev => prev.map(m =>
                m.id === clarifyMsg.id
                  ? { ...m, clarifyThinking: (m.clarifyThinking || '') + event.token }
                  : m
              ))
            } else if (event.type === 'clarify_answer') {
              setMessages(prev => prev.map(m =>
                m.id === clarifyMsg.id
                  ? { ...m, clarifyThinking: (m.clarifyThinking || '') + event.token }
                  : m
              ))
            } else if (event.type === 'clarify_done') {
              setMessages(prev => prev.map(m =>
                m.id === clarifyMsg.id
                  ? { ...m, clarifyData: event.data, streaming: false }
                  : m
              ))
            }
          } catch {
            // Skip malformed line
          }
        }
      }

      // 如果流结束但没有收到 clarify_done，标记为错误
      setMessages(prev => prev.map(m =>
        m.id === clarifyMsg.id && m.streaming
          ? {
              ...m,
              streaming: false,
              clarifyData: m.clarifyData || {
                status: 'error',
                query,
                stock_code: '',
                stock_name: '',
                understanding: '',
                questions: [],
                plan: [],
                needs_selection: false,
                candidates: [],
                message: '意图识别未返回结果',
              },
            }
          : m
      ))
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '连接错误'
      setMessages(prev => prev.map(m =>
        m.id === clarifyMsg.id
          ? {
              ...m,
              streaming: false,
              clarifyData: {
                status: 'error',
                query,
                stock_code: '',
                stock_name: '',
                understanding: '',
                questions: [],
                plan: [],
                needs_selection: false,
                candidates: [],
                message: `意图识别失败：${errMsg}`,
              },
            }
          : m
      ))
    }
  }

  // 用户在澄清卡片上确认后，带 stock_code 启动深度分析
  const handleClarifyStart = (stockCode: string, stockName: string, clarifyMsgId: string) => {
    setMessages(prev => prev.map(m => m.id === clarifyMsgId ? { ...m, clarifyStarted: true } : m))
    startAnalysis(stockName || stockCode, 'deep', stockCode, stockName)
  }

  const handleSendFromEmpty = (text: string, mode: string = 'deep') => {
    const query = text.trim()
    if (!query) return
    if (mode === 'deep') {
      startDeepClarify(query)
    } else {
      startAnalysis(query, mode)
    }
  }

  const handleSendFromChat = (text: string) => {
    const t = text.trim()
    if (!t) return

    // Add user message
    const userMsg: UIMessage = { id: genId(), type: 'user', content: t }
    setMessages(prev => [...prev, userMsg])

    // Deep mode: 先做意图澄清；Quick mode: 直接快速对话
    if (mode === 'deep') {
      startDeepClarify(t)
    } else {
      quickChat(t)
    }
  }

  // ── Render ──
  const leftInset = sidebarOpen ? 256 : 48

  return (
    <>
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelect={selectSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onNew={newAnalysis}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />
      <div className={`transition-all duration-200 ${sidebarOpen ? 'ml-64' : 'ml-12'}`}>
        {appState === 'empty' ? (
          <EmptyState onSend={handleSendFromEmpty} apiKey={apiKey} setApiKey={setApiKey} showApiKeyInput={showApiKeyInput} setShowApiKeyInput={setShowApiKeyInput} mode={mode} setMode={setMode} />
        ) : (
          <>
            {/* Header */}
            <header
              className="fixed top-0 right-0 z-50 flex items-center justify-between px-6 py-3 glass-card"
              style={{ left: leftInset }}
            >
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="text-zinc-400 hover:text-white transition-colors"
                >
                  <i className="fas fa-bars text-sm"></i>
                </button>
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                  <i className="fas fa-chart-line text-white text-sm"></i>
                </div>
                <span className="font-semibold text-sm tracking-wide">FinAgent</span>
              </div>
              <div className="flex items-center gap-4">
                <button className="text-zinc-400 hover:text-white transition-colors text-sm" onClick={() => setShowApiKeyInput(true)}>
                  <i className="fas fa-cog mr-1"></i>设置
                </button>
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-zinc-600 to-zinc-700"></div>
              </div>
            </header>

            {/* Chat messages */}
            <div className="w-full max-w-3xl mx-auto px-4 pt-20 pb-40 space-y-6">
              {messages.map(msg => (
                <MessageRenderer key={msg.id} msg={msg} onClarifyStart={handleClarifyStart} />
              ))}
            </div>

            {/* Fixed input at bottom */}
            <ChatInputBar onSend={handleSendFromChat} leftInset={leftInset} mode={mode} setMode={setMode} />
          </>
        )}
      </div>

      {/* API Key modal */}
      {showApiKeyInput && (
        <ApiKeyModal
          apiKey={apiKey}
          setApiKey={setApiKey}
          onClose={() => setShowApiKeyInput(false)}
        />
      )}
    </>
  )
}

// ── Sidebar ──
function Sidebar({ sessions, currentSessionId, onSelect, onDelete, onRename, onNew, isOpen, onToggle }: {
  sessions: SessionMeta[]
  currentSessionId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, name: string) => void
  onNew: () => void
  isOpen: boolean
  onToggle: () => void
}) {
  const [search, setSearch] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  const filtered = sessions.filter(s =>
    s.stock_name.toLowerCase().includes(search.toLowerCase()) ||
    s.stock_code.includes(search) ||
    s.display_name.toLowerCase().includes(search.toLowerCase())
  )

  if (!isOpen) {
    return (
      <div className="fixed left-0 top-0 bottom-0 w-12 bg-zinc-900 border-r border-zinc-800 flex flex-col items-center py-4 z-50">
        <button onClick={onToggle} className="text-zinc-400 hover:text-white transition-colors">
          <i className="fas fa-bars"></i>
        </button>
      </div>
    )
  }

  return (
    <div className="fixed left-0 top-0 bottom-0 w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col z-50">
      {/* Header */}
      <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-200">会话历史</span>
        <button onClick={onToggle} className="text-zinc-500 hover:text-white transition-colors">
          <i className="fas fa-times text-xs"></i>
        </button>
      </div>

      {/* New analysis button */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full py-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white text-sm font-medium hover:shadow-lg hover:shadow-indigo-500/30 transition-all flex items-center justify-center gap-2"
        >
          <i className="fas fa-plus text-xs"></i>
          新建分析
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-3">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="搜索股票..."
          className="w-full bg-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {filtered.length === 0 ? (
          <p className="text-center text-xs text-zinc-600 py-4">暂无历史会话</p>
        ) : (
          filtered.map(s => (
            <div
              key={s.session_id}
              onClick={() => onSelect(s.session_id)}
              className={`group relative px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1 ${
                currentSessionId === s.session_id ? 'bg-zinc-800' : 'hover:bg-zinc-800/50'
              }`}
            >
              {editingId === s.session_id ? (
                <input
                  type="text"
                  value={editText}
                  onChange={e => setEditText(e.target.value)}
                  onBlur={() => {
                    if (editText.trim()) onRename(s.session_id, editText.trim())
                    setEditingId(null)
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      if (editText.trim()) onRename(s.session_id, editText.trim())
                      setEditingId(null)
                    }
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  onClick={e => e.stopPropagation()}
                  autoFocus
                  className="w-full bg-zinc-700 rounded px-2 py-1 text-xs text-white outline-none"
                />
              ) : (
                <>
                  <div
                    className="text-sm text-zinc-200 truncate"
                    onDoubleClick={e => {
                      e.stopPropagation()
                      setEditingId(s.session_id)
                      setEditText(s.display_name)
                    }}
                  >
                    {s.display_name}
                  </div>
                  <div className="text-[10px] text-zinc-500 flex items-center gap-2">
                    <span>{s.stock_name}</span>
                    <span>{new Date(s.created_at).toLocaleString()}</span>
                  </div>
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      onDelete(s.session_id)
                    }}
                    className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-opacity"
                  >
                    <i className="fas fa-trash text-xs"></i>
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ── Empty State ──
function EmptyState({ onSend, apiKey, setApiKey, showApiKeyInput, setShowApiKeyInput, mode, setMode }: {
  onSend: (text: string, mode?: string) => void
  apiKey: string
  setApiKey: (v: string) => void
  showApiKeyInput: boolean
  setShowApiKeyInput: (v: boolean) => void
  mode: 'quick' | 'deep'
  setMode: (m: 'quick' | 'deep') => void
}) {
  const [text, setText] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const query = text.trim()
      if (!query) return
      if (!apiKey) { setShowApiKeyInput(true); return }
      onSend(query, mode)
      setText('')
    }
  }

  const handleSend = () => {
    const query = text.trim()
    if (!query) return
    if (!apiKey) { setShowApiKeyInput(true); return }
    onSend(query, mode)
    setText('')
  }

  const modes = [
    { id: 'quick' as const, label: '快速模式', icon: 'fa-bolt', color: 'text-yellow-400', desc: '单次 LLM + Web Search，秒级响应' },
    { id: 'deep' as const, label: '深度研究', icon: 'fa-layer-group', color: 'text-indigo-400', desc: '5 层 Agent 流水线，2-5 分钟完整报告' },
  ]
  const currentMode = modes.find(m => m.id === mode)!

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
          {/* Mode dropdown */}
          <div className="relative px-4 pt-1 pb-0">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 text-[10px] font-medium hover:bg-zinc-800/50 rounded px-2 py-0.5 transition-colors"
            >
              <span className="text-zinc-600">模式：</span>
              <i className={`fas ${currentMode.icon} ${currentMode.color}`}></i>
              <span className={currentMode.color}>{currentMode.label}</span>
              <i className={`fas fa-chevron-${dropdownOpen ? 'up' : 'down'} text-zinc-600 text-[8px] ml-0.5`}></i>
            </button>
            {dropdownOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setDropdownOpen(false)} />
                <div className="absolute left-4 top-7 z-20 w-72 glass-card rounded-lg border border-zinc-700/50 shadow-xl overflow-hidden">
                  {modes.map(m => (
                    <button
                      key={m.id}
                      onClick={() => { setMode(m.id); setDropdownOpen(false) }}
                      className={`w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors ${
                        mode === m.id ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/40'
                      }`}
                    >
                      <i className={`fas ${m.icon} ${m.color} text-xs mt-0.5`}></i>
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs font-medium ${mode === m.id ? m.color : 'text-zinc-300'}`}>
                          {m.label}
                          {mode === m.id && <i className="fas fa-check ml-1.5 text-[10px]"></i>}
                        </div>
                        <div className="text-[10px] text-zinc-500 mt-0.5">{m.desc}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              placeholder={mode === 'quick' ? '输入问题，如：茅台、宁德时代怎么样' : '输入股票名称或代码，如 茅台、300750'}
              className="flex-1 bg-transparent text-zinc-200 placeholder-zinc-600 px-4 py-3 resize-none outline-none text-sm leading-relaxed"
              style={{ minHeight: '48px', maxHeight: '120px' }}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeydown}
            />
            <button
              onClick={handleSend}
              className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center hover:shadow-lg hover:shadow-indigo-500/30 transition-all mb-1 mr-1"
            >
              <i className="fas fa-arrow-up text-white text-sm"></i>
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
function MessageRenderer({ msg, onClarifyStart }: { msg: UIMessage; onClarifyStart?: (stockCode: string, stockName: string, clarifyMsgId: string) => void }) {
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

  if (msg.type === 'clarify') {
    return <ClarifyCard msg={msg} onStart={onClarifyStart} />
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
              {/* Thinking banner */}
              {msg.thinkingContent && (
                <ThinkingBanner content={msg.thinkingContent} streaming={!!msg.streaming && !msg.chatResponse} />
              )}
              {/* Search status (Kimi-style) */}
              {msg.searchStatus === 'searching' && (
                <div className="mb-3">
                  <div className="flex items-center gap-2 px-3 py-2 bg-blue-500/10 rounded-lg">
                    <span className="relative flex h-2 w-2 flex-shrink-0">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                    </span>
                    <span className="text-xs text-blue-400">正在搜索</span>
                    <span className="text-xs text-zinc-500 truncate">{msg.searchQuery}</span>
                  </div>
                </div>
              )}
              {msg.searchStatus === 'done' && msg.searchResults && msg.searchResults.length > 0 && (
                <SearchBanner results={msg.searchResults} query={msg.searchQuery || ''} />
              )}
              {msg.searchStatus === 'error' && (
                <div className="mb-3">
                  <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/10 rounded-lg">
                    <i className="fas fa-exclamation-triangle text-xs text-amber-400 flex-shrink-0"></i>
                    <span className="text-xs text-amber-400">搜索失败</span>
                    <span className="text-xs text-zinc-500">基于已有知识回答</span>
                  </div>
                </div>
              )}
              {/* Response content or typing indicator */}
              {msg.streaming && !msg.chatResponse && !msg.thinkingContent && msg.searchStatus !== 'searching' ? (
                <div className="flex items-center gap-1.5 py-1">
                  <div className="w-2 h-2 rounded-full bg-zinc-500 typing-dot"></div>
                  <div className="w-2 h-2 rounded-full bg-zinc-500 typing-dot"></div>
                  <div className="w-2 h-2 rounded-full bg-zinc-500 typing-dot"></div>
                </div>
              ) : (
                <div className="text-sm text-zinc-300 leading-relaxed">
                  <ReactMarkdown
                    components={{
                      p: ({ children }) => <p className="mb-2 whitespace-pre-wrap">{children}</p>,
                      a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">{children}</a>,
                    }}
                  >
                    {msg.chatResponse || ''}
                  </ReactMarkdown>
                  {msg.streaming && msg.chatResponse && <span className="animate-pulse ml-0.5">▋</span>}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return null
}

// ── Thinking Banner (Kimi-style collapsible reasoning) ──
function ThinkingBanner({ content, streaming }: { content: string; streaming: boolean }) {
  const [expanded, setExpanded] = useState(streaming)
  const contentRef = useRef<HTMLDivElement>(null)
  const prevStreamingRef = useRef(streaming)

  useEffect(() => {
    if (streaming) setExpanded(true)
    prevStreamingRef.current = streaming
  }, [streaming])

  useEffect(() => {
    if (expanded && streaming && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight
    }
  }, [content, expanded, streaming])

  const charCount = content.length
  const isJustFinished = !streaming && prevStreamingRef.current

  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-zinc-800/40 hover:bg-zinc-800/60 rounded-lg transition-colors text-left"
      >
        {streaming ? (
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
          </span>
        ) : (
          <i className="fas fa-check-circle text-xs text-purple-400 flex-shrink-0"></i>
        )}
        <span className="text-xs text-zinc-400">
          {streaming ? '正在思考' : isJustFinished ? `已深度思考` : '思考过程'}
          {!streaming && charCount > 0 && (
            <span className="text-zinc-600 ml-1.5">· {charCount} 字</span>
          )}
        </span>
        <i className={`fas fa-chevron-${expanded ? 'down' : 'right'} text-[10px] text-zinc-600 ml-auto transition-transform`}></i>
      </button>
      <div
        className="overflow-hidden transition-all duration-300 ease-out"
        style={{ maxHeight: expanded ? '240px' : '0px', opacity: expanded ? 1 : 0 }}
      >
        <div
          ref={contentRef}
          className="px-3 py-2 max-h-[240px] overflow-y-auto mt-1 bg-zinc-900/40 rounded-lg border border-zinc-800/50"
        >
          <p className="text-xs text-zinc-500 leading-relaxed whitespace-pre-wrap break-words">{content}</p>
        </div>
      </div>
    </div>
  )
}

// ── Search Banner (Kimi-style collapsible search results) ──
function SearchBanner({ results, query }: { results: Array<{ title: string; url: string; content: string }>; query: string }) {
  const [expanded, setExpanded] = useState(false)

  const getDomain = (url: string) => {
    try {
      return new URL(url).hostname.replace('www.', '')
    } catch {
      return url
    }
  }

  const getFavicon = (url: string) => {
    try {
      const domain = new URL(url).hostname
      return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
    } catch {
      return ''
    }
  }

  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-zinc-800/40 hover:bg-zinc-800/60 rounded-lg transition-colors text-left"
      >
        <i className="fas fa-search text-xs text-green-400 flex-shrink-0"></i>
        <span className="text-xs text-zinc-400">
          已搜索
          <span className="text-zinc-300 font-medium mx-1">{results.length}</span>
          个网页
          {query && <span className="text-zinc-600 ml-1.5">· {query}</span>}
        </span>
        <i className={`fas fa-chevron-${expanded ? 'down' : 'right'} text-[10px] text-zinc-600 ml-auto transition-transform`}></i>
      </button>
      <div
        className="overflow-hidden transition-all duration-300 ease-out"
        style={{ maxHeight: expanded ? '400px' : '0px', opacity: expanded ? 1 : 0 }}
      >
        <div className="space-y-2 mt-1 max-h-[400px] overflow-y-auto pr-1">
          {results.map((r, i) => (
            <a
              key={i}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block px-3 py-2 bg-zinc-900/40 rounded-lg border border-zinc-800/50 hover:border-zinc-700 hover:bg-zinc-800/40 transition-all group"
            >
              <div className="flex items-start gap-2">
                <img
                  src={getFavicon(r.url)}
                  alt=""
                  className="w-4 h-4 rounded-sm flex-shrink-0 mt-0.5"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-zinc-600 font-mono flex-shrink-0">{i + 1}</span>
                    <span className="text-xs text-zinc-300 group-hover:text-blue-400 transition-colors truncate font-medium">
                      {r.title}
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-1 line-clamp-2 leading-relaxed">{r.content}</p>
                  <span className="text-[10px] text-zinc-600 truncate block mt-1">{getDomain(r.url)}</span>
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Clarify Card (Kimi-style intent confirmation) ──
function ClarifyCard({ msg, onStart }: { msg: UIMessage; onStart?: (stockCode: string, stockName: string, clarifyMsgId: string) => void }) {
  if (msg.clarifyStarted) return null

  const data = msg.clarifyData
  const thinking = msg.clarifyThinking || ''
  const tools = msg.clarifyTools || []

  // Loading 状态
  if (msg.streaming && !data) {
    return (
      <div className="flex justify-start animate-slide-in">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
              <i className="fas fa-robot text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-2xl rounded-tl-sm px-5 py-4 flex-1">
              {/* 工具调用展示 */}
              {tools.map((t, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-zinc-400 mb-2">
                  {t.status === 'running' ? (
                    <>
                      <div className="w-3 h-3 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin"></div>
                      <span>正在搜索股票...</span>
                    </>
                  ) : t.status === 'done' ? (
                    <>
                      <i className="fas fa-check-circle text-green-500 text-xs"></i>
                      <span>{t.result_summary}</span>
                    </>
                  ) : (
                    <>
                      <i className="fas fa-exclamation-circle text-red-500 text-xs"></i>
                      <span>{t.error || '失败'}</span>
                    </>
                  )}
                </div>
              ))}
              {/* 思考过程 */}
              {thinking && (
                <ThinkingBanner content={thinking} streaming={msg.streaming} />
              )}
              {/* 加载中 */}
              {!thinking && tools.length === 0 && (
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <div className="w-3 h-3 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin"></div>
                  <span>正在理解您的需求...</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // 错误状态
  if (data?.status === 'error') {
    return (
      <div className="flex justify-start animate-slide-in">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-red-500/20 flex items-center justify-center flex-shrink-0 mt-1">
              <i className="fas fa-exclamation text-red-400 text-xs"></i>
            </div>
            <div className="msg-system rounded-2xl rounded-tl-sm px-5 py-4 flex-1">
              <p className="text-sm text-zinc-300">{data.message}</p>
              <button
                onClick={() => onStart?.('', '', msg.id)}
                className="mt-3 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-xs text-white transition-colors"
              >
                重新输入
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // 正常结果
  return (
    <div className="flex justify-start animate-slide-in">
      <div className="max-w-[95%] md:max-w-[90%] w-full">
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-2xl rounded-tl-sm px-5 py-4 flex-1">
            {/* 思考过程（可折叠） */}
            {thinking && <ThinkingBanner content={thinking} streaming={false} />}

            {/* 意图摘要 - 重点展示 */}
            {data?.understanding && (
              <div className="mb-4 p-3 bg-indigo-500/10 rounded-lg border border-indigo-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <i className="fas fa-lightbulb text-xs text-indigo-400"></i>
                  <span className="text-xs font-medium text-indigo-400">意图理解</span>
                </div>
                <p className="text-sm text-zinc-300 leading-relaxed">{data.understanding}</p>
              </div>
            )}

            {/* 股票信息 */}
            {data?.stock_code && (
              <div className="mb-3 flex items-center gap-2">
                <i className="fas fa-chart-line text-xs text-green-400"></i>
                <span className="text-sm text-zinc-200 font-medium">{data.stock_name}</span>
                <span className="text-xs text-zinc-500 font-mono">{data.stock_code}</span>
              </div>
            )}

            {/* 候选选择 */}
            {data?.needs_selection && data.candidates.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-zinc-400 mb-2">找到多个候选股票，请选择：</p>
                <div className="space-y-1">
                  {data.candidates.map(c => (
                    <button
                      key={c.stock_code}
                      onClick={() => onStart?.(c.stock_code, c.stock_name, msg.id)}
                      className="w-full flex items-center justify-between px-3 py-2 bg-zinc-800/50 hover:bg-zinc-800 rounded-lg transition-colors text-left"
                    >
                      <span className="text-sm text-zinc-300">{c.stock_name}</span>
                      <span className="text-xs text-zinc-500 font-mono">{c.stock_code}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 研究计划 */}
            {data?.plan && data.plan.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-zinc-400 mb-2 flex items-center gap-1">
                  <i className="fas fa-list-ol text-[10px]"></i> 研究计划
                </p>
                <div className="space-y-1">
                  {data.plan.map((step, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="text-zinc-600 font-mono flex-shrink-0">{i + 1}.</span>
                      <div>
                        <span className="text-zinc-300">{step.title}</span>
                        <span className="text-zinc-500 ml-1">- {step.desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 开始分析按钮 */}
            {data?.stock_code && !data.needs_selection && (
              <button
                onClick={() => onStart?.(data.stock_code, data.stock_name, msg.id)}
                className="w-full py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 rounded-xl text-sm text-white font-medium transition-all flex items-center justify-center gap-2"
              >
                <i className="fas fa-play text-xs"></i>
                开始深度分析
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
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

            {/* 流式思考过程（真实 LLM reasoning） */}
            {msg.thinkingContent && (
              <div className="px-5 py-3 border-t border-zinc-800/50">
                <ThinkingBanner content={msg.thinkingContent} streaming={!!current} />
              </div>
            )}

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
                <i className={`fas fa-chevron-down transition-transform duration-300 ${showLog ? '' : 'rotate-[-90deg]'}`}></i>
                <span>查看实时输出日志</span>
                {completed.length > 0 && (
                  <span className="text-[10px] text-zinc-600 ml-1">· {completed.length} 条</span>
                )}
              </button>
              <div
                className="overflow-hidden transition-all duration-300 ease-out"
                style={{ maxHeight: showLog ? '300px' : '0px', opacity: showLog ? 1 : 0 }}
              >
                <div className="mt-2 bg-zinc-950 rounded-lg p-3 font-mono text-[11px] text-zinc-500 leading-relaxed overflow-y-auto max-h-[300px]">
                  {completed.map(node => (
                    <div key={node} className="flex items-start gap-2 py-0.5">
                      <i className="fas fa-check-circle text-[10px] text-green-500 flex-shrink-0 mt-0.5"></i>
                      <span className="text-zinc-700 text-[10px] flex-shrink-0">{new Date().toLocaleTimeString()}</span>
                      <span className="text-indigo-400 flex-shrink-0">{node.toUpperCase()}</span>
                      <span className="text-zinc-500 truncate">{outputs[node]?.summary || 'completed'}</span>
                    </div>
                  ))}
                  {current && (
                    <div className="flex items-start gap-2 py-0.5">
                      <span className="relative flex h-2 w-2 flex-shrink-0 mt-0.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-500"></span>
                      </span>
                      <span className="text-zinc-700 text-[10px] flex-shrink-0">{new Date().toLocaleTimeString()}</span>
                      <span className="text-yellow-400 flex-shrink-0">{current.toUpperCase()}</span>
                      <span className="text-zinc-500">running...</span>
                    </div>
                  )}
                </div>
              </div>
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
  return (
    <div className="flex justify-start animate-slide-in">
      <div className="max-w-[95%] md:max-w-[90%] w-full">
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-2xl rounded-tl-sm overflow-hidden flex-1">
            {/* Streaming indicator */}
            {msg.streaming && (
              <div className="px-5 py-2 border-b border-zinc-800/50 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                </span>
                <span className="text-xs text-indigo-400">正在生成报告</span>
                <span className="text-xs text-zinc-600">· 流式输出中</span>
              </div>
            )}

            {/* Report Header */}
            {!msg.streaming && (
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
            )}

            {/* Charts Section */}
            {msg.chartData && msg.chartData.annual && msg.chartData.annual.length > 0 && (
              <div className="px-5 py-3 border-b border-zinc-800/50">
                <div className="flex items-center gap-2 mb-3">
                  <i className="fas fa-chart-bar text-indigo-400 text-xs"></i>
                  <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">财务图表</span>
                </div>
                <ChartsSection data={msg.chartData} />
              </div>
            )}

            {/* Report Markdown */}
            {msg.reportMarkdown && (
              <div className="px-5 py-3 border-b border-zinc-800/50">
                <div className="text-sm text-zinc-300 leading-relaxed max-h-[600px] overflow-y-auto markdown-body">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      img: () => null,
                      h1: ({children}) => <h1 className="text-lg font-bold text-white mt-4 mb-2">{children}</h1>,
                      h2: ({children}) => <h2 className="text-base font-bold text-zinc-100 mt-4 mb-2 pb-1 border-b border-zinc-800">{children}</h2>,
                      h3: ({children}) => <h3 className="text-sm font-semibold text-zinc-200 mt-3 mb-1">{children}</h3>,
                      p: ({children}) => <p className="text-sm text-zinc-300 mb-2 leading-relaxed">{children}</p>,
                      ul: ({children}) => <ul className="text-sm text-zinc-300 mb-2 ml-4 list-disc">{children}</ul>,
                      ol: ({children}) => <ol className="text-sm text-zinc-300 mb-2 ml-4 list-decimal">{children}</ol>,
                      li: ({children}) => <li className="mb-0.5">{children}</li>,
                      strong: ({children}) => <strong className="text-zinc-100 font-semibold">{children}</strong>,
                      table: ({children}) => <table className="w-full text-xs border-collapse mb-2">{children}</table>,
                      th: ({children}) => <th className="border border-zinc-700 px-2 py-1 bg-zinc-800 text-zinc-200 text-left">{children}</th>,
                      td: ({children}) => <td className="border border-zinc-700 px-2 py-1 text-zinc-400">{children}</td>,
                      hr: () => <hr className="border-zinc-800 my-3" />,
                      blockquote: ({children}) => <blockquote className="border-l-2 border-indigo-500 pl-3 text-zinc-400 italic my-2">{children}</blockquote>,
                    }}
                  >
                    {msg.reportMarkdown}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Disclaimer */}
            {!msg.streaming && (
              <div className="px-5 py-3">
                <p className="text-[10px] text-zinc-600 leading-relaxed">
                  <i className="fas fa-info-circle mr-1"></i>
                  本报告由 AI 系统基于公开数据自动生成，仅供参考研究，不构成投资建议。投资有风险，入市需谨慎。
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Chat Input Bar ──
function ChatInputBar({ onSend, leftInset, mode, setMode }: { onSend: (text: string) => void; leftInset: number; mode: 'quick' | 'deep'; setMode: (m: 'quick' | 'deep') => void }) {
  const [text, setText] = useState('')

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend(text)
      setText('')
    }
  }

  return (
    <div
      className="fixed bottom-0 right-0 z-40 px-4 pb-4 pt-2"
      style={{ left: leftInset, background: 'linear-gradient(to top, #0a0a0f 80%, transparent)' }}
    >
      <div className="max-w-3xl mx-auto">
        <div className="glass-input rounded-2xl p-2">
          {/* Mode switcher */}
          <div className="flex items-center gap-1 px-1 pb-1">
            <button
              onClick={() => setMode('deep')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${mode === 'deep' ? 'bg-indigo-600/30 text-indigo-300' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              <i className="fas fa-layer-group text-[10px] mr-1"></i>深度研究
            </button>
            <button
              onClick={() => setMode('quick')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${mode === 'quick' ? 'bg-amber-600/30 text-amber-300' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              <i className="fas fa-bolt text-[10px] mr-1"></i>快速对话
            </button>
          </div>
          <div className="flex items-end gap-2">
            <button className="w-8 h-8 rounded-lg hover:bg-zinc-700/50 flex items-center justify-center text-zinc-500 transition-colors mb-1">
              <i className="fas fa-plus text-xs"></i>
            </button>
            <textarea
              rows={1}
              placeholder={mode === 'deep' ? '输入股票名称或代码，如 茅台、300750' : '输入问题，如：茅台、宁德时代怎么样'}
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
