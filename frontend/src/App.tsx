import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { SSEEvent, PipelineStep, UIMessage, SessionMeta, SessionDetail, ToolCallEntry } from './types'
import { ChartsSection } from './Charts'
import { SearchBanner } from './SearchBanner'

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

const getUserId = (): string => {
  const KEY = 'fa_user_id'
  let uid = localStorage.getItem(KEY)
  if (!uid) {
    uid = `user-${crypto.randomUUID()}`
    localStorage.setItem(KEY, uid)
  }
  return uid
}

// 格式化会话时间，对非法/缺失的 created_at 兜底，绝不返回 "Invalid Date"
function formatSessionTime(ts: string | undefined | null): string {
  if (!ts) return '未知时间'
  const d = new Date(ts)
  if (isNaN(d.getTime())) return '未知时间'
  // 后端用 epoch 占位的脏数据（无法还原真实时间）。浏览器解析 ISO 字符串时
  // 可能按本地时区得到 epoch 之前的负值时间戳，所以用 <= 0 或年份 <= 1970 兜底。
  if (d.getTime() <= 0 || d.getFullYear() <= 1970) return '未知时间'
  return d.toLocaleString()
}

// 根据工具名/参数构建展示用的 ToolCallEntry（图标、标签、参数摘要）
function buildToolCallEntry(
  name: string,
  args?: Record<string, any>,
  resultText?: string,
  done?: boolean,
): ToolCallEntry {
  const icon =
    name === 'search_stock' ? '🔍' :
    name === 'batch_web_search' ? '🌐' : '🛠️'
  const label =
    name === 'search_stock' ? '识别股票' :
    name === 'batch_web_search' ? '批量搜索' :
    name === 'web_search' ? '网络搜索' : name
  const argText = args?.query
    ? args.query
    : Array.isArray(args?.queries)
      ? args.queries.join('、')
      : Object.keys(args || {}).length
        ? JSON.stringify(args)
        : ''
  return { name, label, icon, argText, resultText, done }
}

// 将工具结果浓缩为简短文本（与后端 _summarize_tool_result 保持一致）
function summarizeToolResult(result: any): string {
  if (typeof result === 'string') return result.substring(0, 150)
  if (Array.isArray(result)) {
    return result.slice(0, 3)
      .map((r: any) => r?.title || r?.name || r?.code || JSON.stringify(r).substring(0, 50))
      .join('、')
  }
  if (result && typeof result === 'object') {
    return JSON.stringify(result).substring(0, 150)
  }
  return ''
}

export default function App() {
  const [appState, setAppState] = useState<'empty' | 'analyzing' | 'report' | 'clarifying'>('empty')
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [apiKey, setApiKeyState] = useState(() => localStorage.getItem('fa_api_key') || '')
  const saveApiKey = useCallback((v: string) => {
    setApiKeyState(v)
    if (v) localStorage.setItem('fa_api_key', v)
    else localStorage.removeItem('fa_api_key')
  }, [])
  const setApiKey = saveApiKey
  const [showApiKeyInput, setShowApiKeyInput] = useState(false)
  const pipelineMsgRef = useRef<UIMessage | null>(null)

  // Session state
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const streamingReportRef = useRef<UIMessage | null>(null)
  const [mode, setMode] = useState<'quick' | 'deep'>('deep')
  // 中断进行中的 SSE 流：切换会话/新建分析/删除当前会话时调用，
  // 防止残留的 node_start/report_chunk 等事件继续 setMessages 把 pipeline UI 推回来。
  const abortRef = useRef<AbortController | null>(null)
  const abortStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

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
    // 中断进行中的 SSE 流，避免残留事件把 pipeline UI 推回到新载入的会话视图
    abortStreaming()
    try {
      const resp = await fetch(`/api/sessions/${sessionId}`)
      if (!resp.ok) throw new Error('Failed to load session')
      const data: SessionDetail = await resp.json()
      
      // 先完全重置所有状态
      setMessages([])
      setCurrentSessionId(sessionId)
      setAppState('report')
      // 按会话类型锁定模式：chat -> quick，analysis -> deep
      setMode(data.session_type === 'chat' ? 'quick' : 'deep')
      streamingReportRef.current = null
      pipelineMsgRef.current = null

      const reportMsg: UIMessage | null = data.session_type !== 'chat'
        ? {
            id: genId(),
            type: 'report',
            content: '',
            reportMarkdown: data.report_markdown,
            chartData: data.chart_data,
            stockName: data.stock_name,
            durationMs: data.duration_ms,
            sessionId: data.session_id,
          }
        : null

      const newMessages: UIMessage[] = []
      let reportInserted = false
      const history = Array.isArray(data.chat_history) ? data.chat_history : []
      for (const h of history) {
        if (h.role === 'user') {
          newMessages.push({ id: genId(), type: 'user', content: h.content })
          if (reportMsg && !reportInserted) {
            newMessages.push(reportMsg)
            reportInserted = true
          }
        } else {
          newMessages.push({
            id: genId(),
            type: 'chat',
            content: '',
            chatResponse: h.content,
            thinkingContent: h.thinking || undefined,
            toolCalls: (h.tool_calls || []).map((tc: any) =>
              buildToolCallEntry(tc.name, tc.args, tc.result_text, tc.done),
            ),
          })
        }
      }
      if (reportMsg && !reportInserted) {
        newMessages.push(reportMsg)
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
        abortStreaming()
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
    abortStreaming()
    setCurrentSessionId(null)
    streamingReportRef.current = null
    pipelineMsgRef.current = null
    setMessages([])
    setAppState('empty')
  }

  // ── SSE analysis (deep mode) ──
  const startAnalysis = async (
    query: string,
    sessionId: string | null = null,
    stockCode?: string,
    stockName?: string,
    focus?: string,
  ) => {
    if (!apiKey.trim()) {
      setShowApiKeyInput(true)
      return
    }

    // 首次进入聊天模式
    if (appState === 'empty') {
      setAppState('clarifying')
    }

    // 只有新会话才重置 session；澄清轮次保留 currentSessionId
    if (!sessionId) {
      setCurrentSessionId(null)
      streamingReportRef.current = null
    }

    // 添加用户消息
    const userMsg: UIMessage = {
      id: genId(),
      type: 'user',
      content: query,
    }
    setMessages(prev => [...prev, userMsg])

    // 流式处理 SSE 事件
    let assistantMsgId: string | null = null
    let pipelineMsgId: string | null = null
    // 每轮重置 pipeline ref，避免上一轮分析 pipeline 消息污染本轮澄清对话
    pipelineMsgRef.current = null

    const ensurePipelineMsg = (content: string): UIMessage => {
      if (pipelineMsgRef.current) return pipelineMsgRef.current
      const pm: UIMessage = {
        id: genId(),
        type: 'pipeline',
        content,
        completedNodes: [],
        currentNode: '',
        nodeOutputs: {},
        progress: 0,
        thinkingContent: '',
      }
      pipelineMsgId = pm.id
      pipelineMsgRef.current = pm
      setMessages(prev => [...prev, pm])
      setAppState('analyzing')
      return pm
    }

    // 获取或创建对话流中的助手消息（承载思考过程、工具调用、澄清回复）。
    // 澄清/解析阶段（search_stock / web_search / thinking）走对话流，不触发管线 UI；
    // 仅 run_deep_analysis 才调用 ensurePipelineMsg 进入管线 UI（ADR-0017）。
    const ensureAssistantMsg = (): string => {
      if (assistantMsgId) return assistantMsgId
      const newId = genId()
      assistantMsgId = newId
      setMessages(prev => [...prev, {
        id: newId,
        type: 'chat',
        content: '',
        chatResponse: '',
        thinkingContent: '',
        streaming: true,
      }])
      return newId
    }

    // 将结构化结果（搜索结果 / 股票识别）附加到助手消息最近一次匹配的工具调用记录上，
    // 把工具调用从思考过程中分离出来单独展示。优先按工具名匹配未完成条目，回退到最近
    // 未完成条目，都没有则新建一条仅含结果的记录。
    const attachToolResult = (chatId: string, names: string[] | string, resultText: string) => {
      const nameList = Array.isArray(names) ? names : [names]
      setMessages(prev => prev.map(m => {
        if (m.id !== chatId) return m
        const calls = [...(m.toolCalls || [])]
        let idx = -1
        for (let i = calls.length - 1; i >= 0; i--) {
          if (nameList.includes(calls[i].name) && !calls[i].done) { idx = i; break }
        }
        if (idx === -1) {
          for (let i = calls.length - 1; i >= 0; i--) {
            if (!calls[i].done) { idx = i; break }
          }
        }
        if (idx >= 0) {
          calls[idx] = { ...calls[idx], resultText, done: true }
        } else {
          calls.push(buildToolCallEntry(nameList[0], undefined, resultText, true))
        }
        return { ...m, toolCalls: calls }
      }))
    }

    try {
      // 每轮新建 controller；前一轮的已在 abortStreaming 时中断
      abortRef.current = new AbortController()
      const resp = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          api_key: apiKey,
          user_id: getUserId(),
          analysis_type: 'comprehensive',
          ...(sessionId ? { session_id: sessionId } : {}),
          ...(stockCode ? { stock_code: stockCode } : {}),
          ...(stockName ? { stock_name: stockName } : {}),
          ...(focus ? { focus } : {}),
        }),
        signal: abortRef.current.signal,
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

            if (event.type === 'session_created') {
              setCurrentSessionId(event.session_id)
              loadSessions()
              continue
            }

            if (event.type === 'analysis_start') {
              setAppState('analyzing')
              const pipelineMsg: UIMessage = {
                id: genId(),
                type: 'pipeline',
                content: `开始分析 ${event.stock_name} (${event.stock_code})`,
                completedNodes: [],
                currentNode: '',
                nodeOutputs: {},
                progress: 0,
                thinkingContent: '',
              }
              pipelineMsgId = pipelineMsg.id
              pipelineMsgRef.current = pipelineMsg
              setMessages(prev => [...prev, pipelineMsg])
              continue
            }

            if (event.type === 'chat_token') {
              // Agent 的文本回复（澄清/追问）
              if (!assistantMsgId) {
                const newAssistantId = genId()
                assistantMsgId = newAssistantId
                setMessages(prev => [...prev, {
                  id: newAssistantId,
                  type: 'chat',
                  content: '',
                  chatResponse: event.token,
                  streaming: true,
                }])
              } else {
                setMessages(prev => prev.map(m =>
                  m.id === assistantMsgId
                    ? { ...m, chatResponse: (m.chatResponse || '') + event.token }
                    : m
                ))
              }
              continue
            }

            if (event.type === 'awaiting_input') {
              setAppState('clarifying')
              if (assistantMsgId) {
                setMessages(prev => prev.map(m =>
                  m.id === assistantMsgId ? { ...m, streaming: false } : m
                ))
              }
              continue
            }

            if (event.type === 'tool_call') {
              if (event.name === 'run_deep_analysis') {
                // 仅深度分析管线触发管线 UI（ADR-0017 D1）
                ensurePipelineMsg('开始深度分析...')
              } else {
                // search_stock / web_search / batch_web_search 走对话流，不触发管线 UI
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'search_start') {
              const chatId = ensureAssistantMsg()
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'searching' as const, searchQuery: event.query }
                  : m
              ))
              continue
            }

            if (event.type === 'search_result') {
              const results = event.results || []
              const chatId = ensureAssistantMsg()
              setMessages(prev => prev.map(m => {
                if (m.id !== chatId) return m
                // 标记 web_search/batch_web_search toolCall 为已完成，避免 tool_result 重复附加
                const calls = (m.toolCalls || []).map(c =>
                  (c.name === 'web_search' || c.name === 'batch_web_search') && !c.done
                    ? { ...c, done: true }
                    : c
                )
                return { ...m, searchStatus: 'done' as const, searchResults: results, toolCalls: calls }
              }))
              continue
            }

            if (event.type === 'search_error') {
              const chatId = ensureAssistantMsg()
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'error' as const }
                  : m
              ))
              continue
            }

            if (event.type === 'tool_result') {
              if (event.name !== 'run_deep_analysis') {
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'stock_resolved') {
              if (pipelineMsgRef.current) {
                updateMessage(pipelineMsgRef.current.id, { content: `已识别：${event.stock_name} (${event.stock_code})` })
              } else {
                // 澄清阶段识别出股票，作为 search_stock 的结构化结果附加到工具调用记录
                attachToolResult(ensureAssistantMsg(), 'search_stock', `已识别：${event.stock_name} (${event.stock_code})`)
              }
              continue
            }

            if (event.type === 'thinking_token') {
              if (pipelineMsgRef.current) {
                // 管线运行期间的思考 -> 管线 UI
                handleSSEEvent(event, pipelineMsgRef.current)
              } else {
                // 澄清/解析阶段的思考 -> 对话流（agent 思考过程）
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'thinking_replace') {
              // 替换已流式输出的思考内容（DSML 清理等后处理）
              if (!pipelineMsgRef.current) {
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'thinking_to_answer') {
              // 文本已作为 thinking_token 逐 token 流式输出，流末判定为最终回答。
              if (!pipelineMsgRef.current) {
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'parsing' ||
                event.type === 'resolved' ||
                event.type === 'node_start' ||
                event.type === 'node_complete') {
              const pm = ensurePipelineMsg('深度分析进行中...')
              handleSSEEvent(event, pm)
              continue
            }

            if (event.type === 'report_chunk' || event.type === 'report_ready') {
              handleSSEEvent(event, pipelineMsgRef.current || { id: genId(), type: 'pipeline', content: '' } as UIMessage)
              continue
            }

            if (event.type === 'done') {
              // 流正常结束
              if (assistantMsgId) {
                setMessages(prev => prev.map(m =>
                  m.id === assistantMsgId ? { ...m, streaming: false } : m
                ))
              }
              continue
            }

            if (event.type === 'error') {
              if (pipelineMsgRef.current) {
                handleSSEEvent(event, pipelineMsgRef.current)
              } else {
                setMessages(prev => [...prev, {
                  id: genId(),
                  type: 'error',
                  content: `错误: ${event.message}`,
                }])
              }
              continue
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    } catch (e) {
      // 切换会话/新建分析主动中断，不是错误，静默退出
      if (e instanceof Error && e.name === 'AbortError') return
      console.error('SSE error:', e)
      setMessages(prev => [...prev, {
        id: genId(),
        type: 'error',
        content: `连接错误: ${e instanceof Error ? e.message : 'Unknown'}`,
      }])
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
        const webSources = event.web_sources || []
        if (streamingReportRef.current) {
          updateMessage(streamingReportRef.current.id, {
            reportMarkdown: event.report_markdown,
            chartData: event.chart_data,
            filePaths: event.file_paths,
            stockName: event.stock_name,
            durationMs: event.duration_ms,
            sessionId: event.session_id,
            webSources,
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
            webSources,
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

  // ── 对话流 SSE 事件共享处理 ──
  // 快速模式（/api/chat）与深度模式（/api/analyze）的澄清/解析阶段共用同一批
  // "对话流"事件：thinking_token / thinking_replace / thinking_to_answer /
  // tool_call / tool_result / chat_token / chat_done / error。
  // 抽出此函数避免两处循环各写一份导致行为漂移（如 tool_call 曾在 quickChat 漏处理）。
  //
  // 返回 true 表示事件已处理（调用方应 continue），false 表示非对话流事件
  // （调用方继续判断管线/搜索等专属事件）。
  const handleChatStreamEvent = (event: SSEEvent, chatId: string): boolean => {
    switch (event.type) {
      case 'thinking_token':
        setMessages(prev => prev.map(m =>
          m.id === chatId
            ? { ...m, thinkingContent: (m.thinkingContent || '') + event.token }
            : m
        ))
        return true

      case 'thinking_replace':
        setMessages(prev => prev.map(m =>
          m.id === chatId ? { ...m, thinkingContent: event.token } : m
        ))
        return true

      case 'thinking_to_answer': {
        // 文本已作为 thinking_token 逐 token 流式输出，流末判定为最终回答。
        // 保留之前的思考+工具轨迹（ThinkingBanner 始终展示），仅将末尾当前轮
        // 回答文本移至回答区，避免重复。
        const ans = event.answer
        setMessages(prev => prev.map(m => {
          if (m.id !== chatId) return m
          const tc = m.thinkingContent || ''
          const remaining = ans && tc.endsWith(ans) ? tc.slice(0, -ans.length) : tc
          return {
            ...m,
            thinkingContent: remaining,
            chatResponse: (m.chatResponse || '') + ans,
          }
        }))
        return true
      }

      case 'tool_call': {
        // 工具调用单独记录到 toolCalls（与思考过程分离展示），非 run_deep_analysis
        const entry = buildToolCallEntry(event.name, event.args, undefined, false)
        setMessages(prev => prev.map(m =>
          m.id === chatId
            ? { ...m, toolCalls: [...(m.toolCalls || []), entry] }
            : m
        ))
        return true
      }

      case 'tool_result': {
        const resultSummary = summarizeToolResult(event.result)
        setMessages(prev => prev.map(m => {
          if (m.id !== chatId) return m
          const calls = [...(m.toolCalls || [])]
          // 优先附加到同名且未完成的最近一次调用；若已完成（结构化事件如
          // search_result/stock_resolved 已先行附加），则跳过避免重复。
          let idx = -1
          for (let i = calls.length - 1; i >= 0; i--) {
            if (calls[i].name === event.name && !calls[i].done) { idx = i; break }
          }
          if (idx === -1) {
            for (let i = calls.length - 1; i >= 0; i--) {
              if (calls[i].name === event.name) { idx = i; break }
            }
          }
          if (idx >= 0) {
            if (calls[idx].done) return m
            calls[idx] = { ...calls[idx], resultText: resultSummary, done: true }
          } else if (resultSummary) {
            calls.push(buildToolCallEntry(event.name, undefined, resultSummary, true))
          }
          return { ...m, toolCalls: calls }
        }))
        return true
      }

      case 'chat_token':
        setMessages(prev => prev.map(m =>
          m.id === chatId
            ? { ...m, chatResponse: (m.chatResponse || '') + event.token }
            : m
        ))
        return true

      case 'chat_done':
        setMessages(prev => prev.map(m =>
          m.id === chatId ? { ...m, streaming: false } : m
        ))
        return true

      case 'error':
        setMessages(prev => prev.map(m =>
          m.id === chatId
            ? { ...m, chatResponse: `❌ ${event.message || '未知错误'}`, streaming: false }
            : m
        ))
        return true

      default:
        return false
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
    // 首次从首页进入对话：切换到对话视图（与 startAnalysis 保持一致）
    if (appState === 'empty') {
      setAppState('clarifying')
    }

    // 添加用户消息
    const userMsg: UIMessage = {
      id: genId(),
      type: 'user',
      content: message,
    }
    setMessages(prev => [...prev, userMsg])

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
      abortRef.current = new AbortController()
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: currentSessionId,
          user_id: getUserId(),
          api_key: apiKey,
        }),
        signal: abortRef.current.signal,
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
            // 对话流公共事件（thinking/tool/chat/error）统一走共享处理
            if (handleChatStreamEvent(event, chatId)) {
              continue
            }
            // 快速模式搜索专属事件
            if (event.type === 'search_start') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'searching', searchQuery: event.query }
                  : m
              ))
            } else if (event.type === 'search_result') {
              setMessages(prev => prev.map(m => {
                if (m.id !== chatId) return m
                const calls = (m.toolCalls || []).map(c =>
                  (c.name === 'web_search' || c.name === 'batch_web_search') && !c.done
                    ? { ...c, done: true }
                    : c
                )
                return { ...m, searchStatus: 'done', searchResults: event.results, toolCalls: calls }
              }))
            } else if (event.type === 'search_error') {
              setMessages(prev => prev.map(m =>
                m.id === chatId
                  ? { ...m, searchStatus: 'error' }
                  : m
              ))
            } else if (event.type === 'session_created') {
              setCurrentSessionId(event.session_id)
              loadSessions()
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      setMessages(prev => prev.map(m =>
        m.id === chatId
          ? { ...m, type: 'error', content: `错误: ${e instanceof Error ? e.message : 'Unknown'}`, streaming: false }
          : m
      ))
    }
  }

  const handleSendFromEmpty = (text: string, mode: string = 'deep') => {
    const query = text.trim()
    if (!query) return
    if (mode === 'quick') {
      quickChat(query)
    } else {
      startAnalysis(query, null)
    }
  }

  const handleSendFromChat = (text: string) => {
    const t = text.trim()
    if (!t) return

    if (mode === 'quick') {
      quickChat(t)
      return
    }

    // Deep mode：直接走 /api/analyze，由 Agent 决定是否反问或执行分析
    startAnalysis(t, currentSessionId)
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
                  className="text-[var(--icon-secondary)] hover:text-[var(--text-default)] transition-colors"
                >
                  <i className="fas fa-bars text-sm"></i>
                </button>
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--bg-brand)' }}>
                  <i className="fas fa-chart-line text-white text-sm"></i>
                </div>
                <span className="font-semibold text-sm tracking-wide" style={{ color: 'var(--text-default)' }}>FinAgent</span>
              </div>
              <div className="flex items-center gap-4">
                <button className="text-[var(--icon-secondary)] hover:text-[var(--text-default)] transition-colors text-sm" onClick={() => setShowApiKeyInput(true)}>
                  <i className="fas fa-cog mr-1"></i>设置
                </button>
                <div className="w-7 h-7 rounded-full" style={{ background: 'var(--bg-overlay-l3)' }}></div>
              </div>
            </header>

            {/* Chat messages */}
            <div className="w-full max-w-3xl mx-auto px-4 pt-20 pb-40 space-y-6">
              {messages
                .filter(msg => {
                  // 只有在实际分析过程中才显示 pipeline 消息
                  if (msg.type === 'pipeline') {
                    return appState === 'analyzing';
                  }
                  return true;
                })
                .map(msg => (
                  <MessageRenderer key={msg.id} msg={msg} />
                ))}
            </div>

            {/* Fixed input at bottom */}
            <ChatInputBar onSend={handleSendFromChat} leftInset={leftInset} mode={mode} setMode={setMode} locked={currentSessionId !== null} />
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
    (s.stock_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (s.stock_code || '').includes(search) ||
    (s.display_name || '').toLowerCase().includes(search.toLowerCase())
  )

  if (!isOpen) {
    return (
      <div className="fixed left-0 top-0 bottom-0 w-12 flex flex-col items-center py-4 z-50" style={{ background: 'var(--bg-base-secondary)', borderRight: '1px solid var(--border-neutral-l1)' }}>
        <button onClick={onToggle} className="text-[var(--icon-secondary)] hover:text-[var(--text-default)] transition-colors">
          <i className="fas fa-bars"></i>
        </button>
      </div>
    )
  }

  return (
    <div className="fixed left-0 top-0 bottom-0 w-64 flex flex-col z-50" style={{ background: 'var(--bg-base-secondary)', borderRight: '1px solid var(--border-neutral-l1)' }}>
      {/* Header */}
      <div className="p-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-default)' }}>会话历史</span>
        <button onClick={onToggle} className="text-[var(--text-tertiary)] hover:text-[var(--text-default)] transition-colors">
          <i className="fas fa-times text-xs"></i>
        </button>
      </div>

      {/* New analysis button */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full py-2 rounded-xl text-white text-sm font-medium transition-all flex items-center justify-center gap-2"
          style={{ background: 'var(--bg-brand)' }}
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
          className="w-full rounded-lg px-3 py-2 text-xs outline-none transition-all"
          style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', border: '1px solid transparent' }}
          onFocus={e => { e.target.style.borderColor = 'var(--bg-brand)'; e.target.style.boxShadow = '0 0 0 3px var(--bg-brand-popup)' }}
          onBlur={e => { e.target.style.borderColor = 'transparent'; e.target.style.boxShadow = 'none' }}
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {filtered.length === 0 ? (
          <p className="text-center text-xs py-4" style={{ color: 'var(--text-tertiary)' }}>暂无历史会话</p>
        ) : (
          filtered.map(s => (
            <div
              key={s.session_id}
              onClick={() => onSelect(s.session_id)}
              className="group relative px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1"
              style={currentSessionId === s.session_id ? { background: 'var(--bg-overlay-l2)' } : { background: 'transparent' }}
              onMouseEnter={(e) => { if (currentSessionId !== s.session_id) e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
              onMouseLeave={(e) => { if (currentSessionId !== s.session_id) e.currentTarget.style.background = 'transparent' }}
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
                  className="w-full rounded px-2 py-1 text-xs outline-none"
                  style={{ background: 'var(--bg-overlay-l2)', color: 'var(--text-default)' }}
                />
              ) : (
                <>
                  <div
                    className="text-sm truncate"
                    style={{ color: 'var(--text-default)' }}
                    onDoubleClick={e => {
                      e.stopPropagation()
                      setEditingId(s.session_id)
                      setEditText(s.display_name)
                    }}
                  >
                    {s.display_name}
                  </div>
                  <div className="text-[10px] flex items-center gap-2" style={{ color: 'var(--text-tertiary)' }}>
                    <span>{s.stock_name}</span>
                    <span>{formatSessionTime(s.created_at)}</span>
                  </div>
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      onDelete(s.session_id)
                    }}
                    className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ color: 'var(--text-tertiary)' }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--status-error-default)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)' }}
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
    { id: 'quick' as const, label: '快速模式', icon: 'fa-bolt', color: 'text-[var(--status-warning-default)]', desc: '单次 LLM + Web Search，秒级响应' },
    { id: 'deep' as const, label: '深度研究', icon: 'fa-layer-group', color: 'text-[var(--text-brand)]', desc: '5 层 Agent 流水线，2-5 分钟完整报告' },
  ]
  const currentMode = modes.find(m => m.id === mode)!

  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 transition-all duration-700" style={{ minHeight: '100vh' }}>
      {/* Logo & Title */}
      <div className="text-center mb-10 animate-fade-in-up">
        <div className="w-16 h-16 rounded-xl flex items-center justify-center mx-auto mb-5" style={{ background: 'var(--bg-brand)' }}>
          <i className="fas fa-chart-line text-white text-2xl"></i>
        </div>
        <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--text-default)', fontFamily: 'var(--font-family-heading)' }}>
          Finance Analysis Agent
        </h1>
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>AI 驱动的 A 股投研分析系统</p>
      </div>

      {/* Input Box */}
      <div className="w-full max-w-2xl animate-fade-in-up relative z-10" style={{ animationDelay: '0.1s' }}>
        <div className="glass-input rounded-2xl p-2">
          {/* Mode dropdown */}
          <div className="relative px-4 pt-1 pb-0">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 text-[10px] font-medium rounded px-2 py-0.5 transition-colors hover:bg-[var(--bg-overlay-l1)]"
            >
              <span style={{ color: 'var(--text-tertiary)' }}>模式：</span>
              <i className={`fas ${currentMode.icon} ${currentMode.color}`}></i>
              <span className={currentMode.color}>{currentMode.label}</span>
              <i className={`fas fa-chevron-${dropdownOpen ? 'up' : 'down'} text-[8px] ml-0.5`} style={{ color: 'var(--text-tertiary)' }}></i>
            </button>
            {dropdownOpen && (
              <div className="absolute left-4 top-7 z-[70] w-72 glass-card rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
                {modes.map(m => (
                  <button
                    key={m.id}
                    onClick={() => { setMode(m.id); setDropdownOpen(false) }}
                    className="w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors"
                    style={mode === m.id ? { background: 'var(--bg-overlay-l2)' } : { background: 'transparent' }}
                    onMouseEnter={(e) => { if (mode !== m.id) e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
                    onMouseLeave={(e) => { if (mode !== m.id) e.currentTarget.style.background = 'transparent' }}
                  >
                    <i className={`fas ${m.icon} ${m.color} text-xs mt-0.5`}></i>
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-medium ${mode === m.id ? m.color : ''}`} style={mode !== m.id ? { color: 'var(--text-secondary)' } : {}}>
                        {m.label}
                        {mode === m.id && <i className="fas fa-check ml-1.5 text-[10px]"></i>}
                      </div>
                      <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{m.desc}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              placeholder={mode === 'quick' ? '输入问题，如：茅台、宁德时代怎么样' : '输入股票名称或代码，如 茅台、300750'}
              className="flex-1 bg-transparent px-4 py-3 resize-none outline-none text-sm leading-relaxed"
              style={{ minHeight: '48px', maxHeight: '120px', color: 'var(--text-default)' }}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeydown}
            />
            <button
              onClick={handleSend}
              className="w-10 h-10 rounded-xl flex items-center justify-center mb-1 mr-1"
              style={{ background: 'var(--bg-brand)' }}
            >
              <i className="fas fa-arrow-up text-white text-sm"></i>
            </button>
          </div>
        </div>
        {!apiKey ? (
          <p className="text-center text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
            <i className="fas fa-info-circle mr-1"></i>
            需要配置 API Key 才能开始分析
            <button className="hover:underline ml-1" style={{ color: 'var(--text-brand)' }} onClick={() => setShowApiKeyInput(true)}>去配置</button>
          </p>
        ) : (
          <p className="text-center text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
            <i className="fas fa-check-circle mr-1" style={{ color: 'var(--status-success-default)' }}></i>
            API Key 已配置
            <button className="hover:underline ml-1" style={{ color: 'var(--text-brand)' }} onClick={() => setShowApiKeyInput(true)}>修改</button>
          </p>
        )}
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-8 max-w-2xl w-full px-4 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
        {[
          { icon: 'users', color: 'text-[var(--text-brand)]', label: '4 维并行分析' },
          { icon: 'comments', color: 'text-[var(--status-warning-default)]', label: 'Bull/Bear 辩论' },
          { icon: 'shield-alt', color: 'text-[var(--status-error-default)]', label: 'Risk 压力测试' },
          { icon: 'file-alt', color: 'text-[var(--status-success-default)]', label: '结构化报告' },
        ].map(f => (
          <div key={f.label} className="glass-card rounded-xl p-3 text-center">
            <div className={`${f.color} text-lg mb-1`}><i className={`fas fa-${f.icon}`}></i></div>
            <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{f.label}</div>
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
          <div className="msg-user rounded-2xl rounded-tr-sm px-5 py-3 text-sm leading-relaxed" style={{ color: 'var(--text-onbrand)' }}>
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
            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'var(--status-error-default)' }}>
              <i className="fas fa-exclamation text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-xl rounded-tl-sm px-5 py-3 flex-1">
              <p className="text-sm" style={{ color: 'var(--status-error-default)' }}>{msg.content}</p>
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
          <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--bg-brand)' }}>
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-xl rounded-tl-sm px-4 py-3">
            <div className="flex gap-1.5">
              <div className="w-2 h-2 rounded-full typing-dot" style={{ background: 'var(--text-tertiary)' }}></div>
              <div className="w-2 h-2 rounded-full typing-dot" style={{ background: 'var(--text-tertiary)' }}></div>
              <div className="w-2 h-2 rounded-full typing-dot" style={{ background: 'var(--text-tertiary)' }}></div>
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
            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'var(--bg-brand)' }}>
              <i className="fas fa-robot text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-xl rounded-tl-sm px-5 py-3 flex-1">
              <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--status-success-default)' }}>
                <i className="fas fa-check-circle"></i>
                <span>{msg.content}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (msg.type === 'chat') {
    return (
      <div className="flex justify-start animate-slide-in">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'var(--bg-brand)' }}>
              <i className="fas fa-robot text-white text-xs"></i>
            </div>
            <div className="msg-system rounded-xl rounded-tl-sm px-5 py-4 flex-1">
              {msg.searchStatus && (
                <SearchBanner
                  status={msg.searchStatus}
                  query={msg.searchQuery}
                  results={msg.searchResults}
                />
              )}
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <ToolCallBanner toolCalls={msg.toolCalls} streaming={!!msg.streaming && !msg.chatResponse} />
              )}
              {msg.thinkingContent && (
                <ThinkingBanner content={msg.thinkingContent} streaming={!!msg.streaming && !msg.chatResponse} />
              )}
              {msg.chatResponse ? (
                <div className="prose prose-sm max-w-none" style={{ color: 'var(--text-secondary)' }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      a: ({href, children}) => (
                        <a href={href} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: 'var(--bg-brand)' }}>
                          {children}
                        </a>
                      ),
                    }}
                  >
                    {msg.chatResponse}
                  </ReactMarkdown>
                </div>
              ) : null}
              {msg.streaming && (
                <div className="mt-2 flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  <div className="w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'var(--bg-brand)' }}></div>
                  <span>思考中...</span>
                </div>
              )}
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

  return null
}

// ── Thinking Banner (Kimi-style collapsible reasoning) ──
function ThinkingBanner({ content, streaming }: { content: string; streaming: boolean }) {
  const [expanded, setExpanded] = useState(true)
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
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left"
        style={{ background: 'var(--bg-overlay-l1)' }}
        onMouseEnter={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l2)'}}
        onMouseLeave={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l1)'}}
      >
        {streaming ? (
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }}></span>
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }}></span>
          </span>
        ) : (
          <i className="fas fa-check-circle text-xs flex-shrink-0" style={{ color: 'var(--text-brand)' }}></i>
        )}
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {streaming ? '正在思考' : isJustFinished ? `已深度思考` : '思考过程'}
          {!streaming && charCount > 0 && (
            <span className="ml-1.5" style={{ color: 'var(--text-tertiary)' }}>· {charCount} 字</span>
          )}
        </span>
        <i className={`fas fa-chevron-${expanded ? 'down' : 'right'} text-[10px] ml-auto transition-transform`} style={{ color: 'var(--text-tertiary)' }}></i>
      </button>
      <div
        className="overflow-hidden transition-all duration-300 ease-out"
        style={{ maxHeight: expanded ? '240px' : '0px', opacity: expanded ? 1 : 0 }}
      >
        <div
          ref={contentRef}
          className="px-3 py-2 max-h-[240px] overflow-y-auto mt-1 rounded-lg"
          style={{ background: 'var(--bg-overlay-l1)', border: '1px solid var(--border-neutral-l1)' }}
        >
          <p className="text-xs leading-relaxed whitespace-pre-wrap break-words" style={{ color: 'var(--text-tertiary)' }}>{content}</p>
        </div>
      </div>
    </div>
  )
}

// ── Tool Call Banner (工具调用，与思考过程分离展示) ──
function ToolCallBanner({ toolCalls, streaming }: { toolCalls: ToolCallEntry[]; streaming: boolean }) {
  const [expanded, setExpanded] = useState(true)
  const pendingCount = toolCalls.filter(t => !t.done).length
  const prevStreamingRef = useRef(streaming)

  useEffect(() => {
    if (streaming) setExpanded(true)
    prevStreamingRef.current = streaming
  }, [streaming])

  const isJustFinished = !streaming && prevStreamingRef.current

  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left"
        style={{ background: 'var(--bg-overlay-l1)' }}
        onMouseEnter={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l2)'}}
        onMouseLeave={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l1)'}}
      >
        {streaming && pendingCount > 0 ? (
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }}></span>
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }}></span>
          </span>
        ) : (
          <i className="fas fa-tools text-xs flex-shrink-0" style={{ color: 'var(--text-brand)' }}></i>
        )}
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {streaming && pendingCount > 0 ? '调用工具中' : isJustFinished ? '已调用工具' : '工具调用'}
          <span className="ml-1.5" style={{ color: 'var(--text-tertiary)' }}>· {toolCalls.length} 次</span>
        </span>
        <i className={`fas fa-chevron-${expanded ? 'down' : 'right'} text-[10px] ml-auto transition-transform`} style={{ color: 'var(--text-tertiary)' }}></i>
      </button>
      <div
        className="overflow-hidden transition-all duration-300 ease-out"
        style={{ maxHeight: expanded ? '240px' : '0px', opacity: expanded ? 1 : 0 }}
      >
        <div
          className="px-3 py-2 max-h-[240px] overflow-y-auto mt-1 rounded-lg flex flex-col gap-2"
          style={{ background: 'var(--bg-overlay-l1)', border: '1px solid var(--border-neutral-l1)' }}
        >
          {toolCalls.map((tc, i) => (
            <div key={i} className="text-xs leading-relaxed break-words">
              <div className="flex items-start gap-1.5" style={{ color: 'var(--text-secondary)' }}>
                <span className="flex-shrink-0">{tc.icon}</span>
                <span className="font-medium">[{tc.label}]</span>
                {tc.argText && <span style={{ color: 'var(--text-tertiary)' }}>{tc.argText}</span>}
              </div>
              {tc.resultText && (
                <div className="ml-5 mt-0.5" style={{ color: 'var(--text-tertiary)' }}>↳ {tc.resultText}</div>
              )}
              {!tc.done && (
                <div className="ml-5 mt-0.5 flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
                  <div className="w-2.5 h-2.5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'var(--bg-brand)' }}></div>
                  <span>执行中...</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Utility functions ──
function getDomain(url: string) {
  try {
    return new URL(url).hostname.replace('www.', '')
  } catch {
    return url
  }
}

function getFavicon(url: string) {
  try {
    const domain = new URL(url).hostname
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
  } catch {
    return ''
  }
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
          <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'var(--bg-brand)' }}>
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-xl rounded-tl-sm overflow-hidden flex-1">
            {/* Progress Pipeline */}
            <div className="px-5 pt-4 pb-2">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>分析进度</span>
                  <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{msg.content || '准备中...'}</span>
                </div>
                <span className="text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>~90s</span>
              </div>
              <div className="flex items-center gap-1 mb-4">
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-overlay-l1)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{ width: `${Math.max(5, progress * 100)}%`, background: 'var(--bg-brand)' }}
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
                          style={status === 'running' ? { borderColor: 'var(--status-primary-default)', background: 'var(--bg-brand-popup)' } : status === 'completed' ? { borderColor: 'var(--status-success-default)', background: 'rgba(16, 185, 129, 0.15)' } : { borderColor: 'var(--border-neutral-l2)' }}>
                          <i className={`fas fa-${step.icon} text-xs`}></i>
                        </div>
                        <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{step.desc}</span>
                      </div>
                      {i < PIPELINE_STEPS.length - 1 && (
                        <div className="flex-1 flex items-center justify-center pt-2 px-1">
                          <div className={`w-full h-px ${status === 'completed' ? '' : ''}`} style={{ background: status === 'completed' ? 'rgba(16,185,129,0.5)' : 'var(--bg-overlay-l2)' }}></div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* 流式思考过程（真实 LLM reasoning） */}
            {msg.thinkingContent && (
              <div className="px-5 py-3" style={{ borderTop: '1px solid var(--border-neutral-l1)' }}>
                <ThinkingBanner content={msg.thinkingContent} streaming={!!current} />
              </div>
            )}

            {/* Layer I: Analyst Cards */}
            {(completed.includes('check_cache') || current === 'technical_analyst' || completed.includes('technical_analyst')) && (
              <div className="px-5 py-3" style={{ borderTop: '1px solid var(--border-neutral-l1)' }}>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>Layer I - 并行分析师</span>
                  <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
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
            <div className="px-5 py-3" style={{ borderTop: '1px solid var(--border-neutral-l1)' }}>
              <button
                onClick={() => setShowLog(!showLog)}
                className="flex items-center gap-2 text-xs transition-colors w-full"
                style={{ color: 'var(--text-tertiary)' }}
                onMouseEnter={(e) => {e.currentTarget.style.color = 'var(--text-secondary)'}}
                onMouseLeave={(e) => {e.currentTarget.style.color = 'var(--text-tertiary)'}}
              >
                <i className={`fas fa-chevron-down transition-transform duration-300 ${showLog ? '' : 'rotate-[-90deg]'}`}></i>
                <span>查看实时输出日志</span>
                {completed.length > 0 && (
                  <span className="text-[10px] ml-1" style={{ color: 'var(--text-tertiary)' }}>· {completed.length} 条</span>
                )}
              </button>
              <div
                className="overflow-hidden transition-all duration-300 ease-out"
                style={{ maxHeight: showLog ? '300px' : '0px', opacity: showLog ? 1 : 0 }}
              >
                <div className="mt-2 rounded-lg p-3 font-mono text-[11px] leading-relaxed overflow-y-auto max-h-[300px]" style={{ background: 'var(--bg-base-secondary)' }}>
                  {completed.map(node => (
                    <div key={node} className="flex items-start gap-2 py-0.5">
                      <i className="fas fa-check-circle text-[10px] flex-shrink-0 mt-0.5" style={{ color: 'var(--status-success-default)' }}></i>
                      <span className="text-[10px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>{new Date().toLocaleTimeString()}</span>
                      <span className="flex-shrink-0" style={{ color: 'var(--text-brand)' }}>{node.toUpperCase()}</span>
                      <span className="truncate" style={{ color: 'var(--text-tertiary)' }}>{outputs[node]?.summary || 'completed'}</span>
                    </div>
                  ))}
                  {current && (
                    <div className="flex items-start gap-2 py-0.5">
                      <span className="relative flex h-2 w-2 flex-shrink-0 mt-0.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--status-warning-default)' }}></span>
                        <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--status-warning-default)' }}></span>
                      </span>
                      <span className="text-[10px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>{new Date().toLocaleTimeString()}</span>
                      <span className="flex-shrink-0" style={{ color: 'var(--status-warning-default)' }}>{current.toUpperCase()}</span>
                      <span style={{ color: 'var(--text-tertiary)' }}>running...</span>
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
    green: { border: 'rgba(16,185,129,0.3)', bg: 'rgba(16,185,129,0.08)', text: 'var(--status-success-default)' },
    yellow: { border: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.08)', text: 'var(--status-warning-default)' },
    red: { border: 'rgba(239,68,68,0.3)', bg: 'rgba(239,68,68,0.08)', text: 'var(--status-error-default)' },
    neutral: { border: 'rgba(75,63,227,0.3)', bg: 'var(--bg-brand-popup)', text: 'var(--text-brand)' },
  }
  const c = colors[color]

  const statusIcon = status === 'completed'
    ? <i className="fas fa-check-circle" style={{ color: 'var(--status-success-default)' }}></i>
    : status === 'running'
    ? <div className="w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'var(--bg-brand)' }}></div>
    : <div className="w-2 h-2 rounded-full" style={{ background: 'var(--text-tertiary)' }}></div>

  return (
    <div className="border rounded-xl p-3 cursor-pointer hover:border-opacity-60 transition-all" style={{ borderColor: c.border, background: c.bg }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: c.text }}>{name}</span>
          <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{nameZh}</span>
        </div>
        {statusIcon}
      </div>
      <div className="text-[11px] leading-snug" style={{ color: 'var(--text-secondary)' }}>{summary}</div>
    </div>
  )
}

// ── Report Card ──
function ReportCard({ msg }: { msg: UIMessage }) {
  return (
    <div className="flex justify-start animate-slide-in">
      <div className="max-w-[95%] md:max-w-[90%] w-full">
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'var(--bg-brand)' }}>
            <i className="fas fa-robot text-white text-xs"></i>
          </div>
          <div className="msg-system rounded-xl rounded-tl-sm overflow-hidden flex-1">
            {/* Streaming indicator */}
            {msg.streaming && (
              <div className="px-5 py-2 flex items-center gap-2" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }}></span>
                  <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }}></span>
                </span>
                <span className="text-xs" style={{ color: 'var(--text-brand)' }}>正在生成报告</span>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>· 流式输出中</span>
              </div>
            )}

            {/* Report Header */}
            {!msg.streaming && (
              <div className="px-5 pt-4 pb-3" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-bold" style={{ color: 'var(--text-default)' }}>{msg.stockName}</h3>
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold" style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}>深度分析</span>
                    </div>
                    <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>深度分析报告 · 5 层 Agent 架构 · {(msg.durationMs || 0) > 0 ? `耗时 ${Math.round(msg.durationMs / 1000)}s` : '耗时未知'}</p>
                  </div>
                  <div className="flex gap-2">
                    {msg.filePaths?.docx && (
                      <a href={`/api/files/${msg.filePaths.docx.split(/[\\/]/).pop()}`} download
                        className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" title="导出 Word"
                        style={{ background: 'var(--bg-base-secondary)', color: 'var(--icon-secondary)' }}
                        onMouseEnter={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l1)'}}
                        onMouseLeave={(e) => {e.currentTarget.style.background = 'var(--bg-base-secondary)'}}
                      >
                        <i className="fas fa-file-word text-xs"></i>
                      </a>
                    )}
                    {msg.filePaths?.pptx && (
                      <a href={`/api/files/${msg.filePaths.pptx.split(/[\\/]/).pop()}`} download
                        className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" title="导出 PPT"
                        style={{ background: 'var(--bg-base-secondary)', color: 'var(--icon-secondary)' }}
                        onMouseEnter={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l1)'}}
                        onMouseLeave={(e) => {e.currentTarget.style.background = 'var(--bg-base-secondary)'}}
                      >
                        <i className="fas fa-file-powerpoint text-xs"></i>
                      </a>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Charts Section */}
            {msg.chartData && msg.chartData.annual && msg.chartData.annual.length > 0 && (
              <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
                <div className="flex items-center gap-2 mb-3">
                  <i className="fas fa-chart-bar text-xs" style={{ color: 'var(--text-brand)' }}></i>
                  <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>财务图表</span>
                </div>
                <ChartsSection data={msg.chartData} />
              </div>
            )}

            {/* Report Markdown */}
            {msg.reportMarkdown && (
              <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
                <div className="text-sm leading-relaxed max-h-[600px] overflow-y-auto markdown-body">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      img: () => null,
                      a: ({href, children}) => (
                        <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline inline-flex items-center gap-0.5" style={{ color: 'var(--bg-brand)' }}>
                          {children}
                          <i className="fas fa-external-link-alt text-[8px]"></i>
                        </a>
                      ),
                      h1: ({children}) => <h1 className="text-lg font-bold mt-4 mb-2" style={{ color: 'var(--text-default)' }}>{children}</h1>,
                      h2: ({children}) => <h2 className="text-base font-bold mt-4 mb-2 pb-1" style={{ color: 'var(--text-default)', borderBottom: '1px solid var(--border-neutral-l1)' }}>{children}</h2>,
                      h3: ({children}) => <h3 className="text-sm font-semibold mt-3 mb-1" style={{ color: 'var(--text-default)' }}>{children}</h3>,
                      p: ({children}) => <p className="text-sm mb-2 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{children}</p>,
                      ul: ({children}) => <ul className="text-sm mb-2 ml-4 list-disc" style={{ color: 'var(--text-secondary)' }}>{children}</ul>,
                      ol: ({children}) => <ol className="text-sm mb-2 ml-4 list-decimal" style={{ color: 'var(--text-secondary)' }}>{children}</ol>,
                      li: ({children}) => <li className="mb-0.5">{children}</li>,
                      strong: ({children}) => <strong className="font-semibold" style={{ color: 'var(--text-default)' }}>{children}</strong>,
                      table: ({children}) => <table className="w-full text-xs border-collapse mb-2">{children}</table>,
                      th: ({children}) => <th className="border px-2 py-1 text-left" style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', borderColor: 'var(--border-neutral-l1)' }}>{children}</th>,
                      td: ({children}) => <td className="border px-2 py-1" style={{ color: 'var(--text-secondary)', borderColor: 'var(--border-neutral-l1)' }}>{children}</td>,
                      hr: () => <hr className="my-3" style={{ borderColor: 'var(--border-neutral-l1)' }} />,
                      blockquote: ({children}) => <blockquote className="border-l-2 pl-3 italic my-2" style={{ borderColor: 'var(--bg-brand)', color: 'var(--text-secondary)' }}>{children}</blockquote>,
                    }}
                  >
                    {msg.reportMarkdown}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Source Cards (Kimi-style citation cards) */}
            {!msg.streaming && msg.webSources && msg.webSources.length > 0 && (
              <div className="px-5 py-4 border-t" style={{ borderColor: 'var(--border-neutral-l1)' }}>
                <div className="flex items-center gap-2 mb-3">
                  <i className="fas fa-link text-xs" style={{ color: 'var(--text-tertiary)' }}></i>
                  <span className="text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>
                    参考资料（{msg.webSources.length} 个信源）
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {msg.webSources.map((src, i) => (
                    <a
                      key={i}
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block px-3 py-2 rounded-lg border transition-all hover:shadow-sm group"
                      style={{
                        background: 'var(--bg-overlay-l1)',
                        borderColor: 'var(--border-neutral-l1)',
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <img
                          src={getFavicon(src.url)}
                          alt=""
                          className="w-4 h-4 rounded-sm flex-shrink-0 mt-0.5"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>[{i + 1}]</span>
                            <span className="text-xs truncate font-medium" style={{ color: 'var(--text-secondary)' }}>
                              {src.title}
                            </span>
                          </div>
                          <p className="text-[10px] mt-0.5 line-clamp-2" style={{ color: 'var(--text-tertiary)' }}>
                            {src.content}
                          </p>
                          <div className="flex items-center gap-1 mt-1">
                            <i className="fas fa-external-link-alt text-[8px]" style={{ color: 'var(--text-tertiary)' }}></i>
                            <span className="text-[10px] truncate" style={{ color: 'var(--text-tertiary)' }}>
                              {getDomain(src.url)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Disclaimer */}
            {!msg.streaming && (
              <div className="px-5 py-3">
                <p className="text-[10px] leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
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
function ChatInputBar({ onSend, leftInset, mode, setMode, locked }: { onSend: (text: string) => void; leftInset: number; mode: 'quick' | 'deep'; setMode: (m: 'quick' | 'deep') => void; locked: boolean }) {
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
      style={{ left: leftInset, background: 'linear-gradient(to top, var(--bg-base-default) 80%, transparent)' }}
    >
      <div className="max-w-3xl mx-auto">
        <div className="glass-input rounded-2xl p-2">
          {/* Mode switcher */}
          <div className="flex items-center gap-1 px-1 pb-1" title={locked ? '当前会话模式已锁定，新建分析可切换' : ''}>
            <button
              onClick={() => !locked && setMode('deep')}
              disabled={locked}
              className="px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors"
              style={{
                ...(mode === 'deep'
                  ? { background: 'var(--bg-brand-popup)', color: 'var(--bg-brand)' }
                  : { color: 'var(--text-tertiary)' }),
                ...(locked ? { opacity: 0.55, cursor: 'not-allowed' } : {}),
              }}
            >
              <i className="fas fa-layer-group text-[10px] mr-1"></i>深度研究
            </button>
            <button
              onClick={() => !locked && setMode('quick')}
              disabled={locked}
              className="px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors"
              style={{
                ...(mode === 'quick'
                  ? { background: 'var(--bg-brand-popup)', color: 'var(--bg-brand)' }
                  : { color: 'var(--text-tertiary)' }),
                ...(locked ? { opacity: 0.55, cursor: 'not-allowed' } : {}),
              }}
            >
              <i className="fas fa-bolt text-[10px] mr-1"></i>快速对话
            </button>
            {locked && (
              <i className="fas fa-lock text-[9px] ml-1" style={{ color: 'var(--text-tertiary)' }} title="会话模式已锁定"></i>
            )}
          </div>
          <div className="flex items-end gap-2">
            <button
              className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors mb-1"
              style={{ color: 'var(--icon-secondary)' }}
            >
              <i className="fas fa-plus text-xs"></i>
            </button>
            <textarea
              rows={1}
              placeholder={mode === 'deep' ? '输入股票名称或代码，如 茅台、300750' : '输入问题，如：茅台、宁德时代怎么样'}
              className="flex-1 bg-transparent px-2 py-3 resize-none outline-none text-sm leading-relaxed"
              style={{ minHeight: '40px', maxHeight: '100px', color: 'var(--text-default)' }}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeydown}
            />
            <button
              onClick={() => { onSend(text); setText('') }}
              className="w-9 h-9 rounded-xl flex items-center justify-center transition-all mb-0.5 mr-0.5"
              style={{ background: 'var(--bg-brand)' }}
            >
              <i className="fas fa-arrow-up text-xs" style={{ color: 'var(--text-onbrand)' }}></i>
            </button>
          </div>
        </div>
        <div className="text-center mt-1">
          <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>AI 生成仅供参考，不构成投资建议</span>
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
    <div className="fixed inset-0 z-[100] flex items-center justify-center backdrop-blur-sm" style={{ background: 'rgba(0,0,0,0.25)' }} onClick={onClose}>
      <div className="glass-card rounded-2xl p-6 max-w-md w-full mx-4" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-default)' }}>配置 API Key</h3>
        <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>输入 DeepSeek API Key 用于 LLM 调用。Key 保存在浏览器本地，刷新页面不会丢失。</p>
        <input
          type="password"
          placeholder="sk-..."
          value={value}
          onChange={e => setValue(e.target.value)}
          className="w-full glass-input rounded-xl px-4 py-3 text-sm outline-none mb-4"
          style={{ color: 'var(--text-default)' }}
        />
        <div className="flex gap-3">
          <button
            onClick={() => { setApiKey(value); onClose() }}
            className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all"
            style={{ background: 'var(--bg-brand)', color: 'var(--text-onbrand)' }}
          >
            确认
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl text-sm transition-colors"
            style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-secondary)' }}
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
