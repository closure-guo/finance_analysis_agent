import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { SSEEvent, PipelineStep, UIMessage, SessionMeta, SessionDetail, ToolCallEntry, PipelineSnapshot } from './types'
import { ChartsSection } from './Charts'
import { SearchBanner } from './SearchBanner'
import { applyChatStreamEvent, applyPipelineThinkingToken, applyPipelineNodeComplete, buildTimelineFromHistory, deserializeTimeline, deserializeNodeTimelines, nodeDisplayName } from './timeline'
import { estimateTotalMs, estimateRemainingMs, formatDurationMs, loadDurations, recordDuration } from './eta'
import { buildLayerTree, applyNodeEvent, deserializeLayerTree } from './pipelineTree'
import { PipelineTimeline } from './PipelineTimeline'
import { TimelineRenderer, type TimelineBannerComponents } from './TimelineRenderer'

// 搜索类工具集合：这类工具的状态与结果由独立搜索横幅（SearchBanner）承载，
// 不进入工具调用横幅（ToolCallBanner），避免同一搜索行为同时出现两个横幅。
export const SEARCH_TOOL_NAMES = new Set<string>(['web_search', 'batch_web_search'])

// 判断工具是否为搜索类（web_search / batch_web_search）
export function isSearchTool(name: string): boolean {
  return SEARCH_TOOL_NAMES.has(name)
}

// 从思考内容中提取首个 ## 二级标题作为思考横幅展示标题。
// 策略对齐：LLM 按信息密度决定输出 ## 标题分层 / **加粗** 分段 / 无标题，
// 仅 ## 层级标题提取为横幅标题，**加粗** 与无格式返回 undefined。
export function extractThinkingTitle(content: string): string | undefined {
  if (!content) return undefined
  // 允许 ## 前有空白（Markdown 缩进），## 后必须有空格，标题末尾空白被裁剪
  const match = content.match(/^\s*##\s+(.+?)\s*$/m)
  return match ? match[1] : undefined
}

// ── Pipeline steps 定义已迁移至 pipelineTree.LAYER_TREE_CONFIG（分层时间轴）──

let msgIdCounter = 0
const genId = () => `msg-${++msgIdCounter}`

// 轮询超时上限（Final Review Fix 2）：ReAct 路径切走后 status 可能永久 running，
// 轮询无限进行会泄漏资源。超过该时长后停止轮询并提示用户刷新或重新发起。
const MAX_POLLING_MS = 5 * 60 * 1000 // 5 分钟（150 次 × 2s）

// TimelineRenderer 注入的横幅组件集合（ThinkingBanner/ToolCallBanner 为函数声明，提升后可用）
const timelineBannerComponents: TimelineBannerComponents = {
  ThinkingBanner: (props) => <ThinkingBanner {...props} />,
  SearchBanner,
  ToolCallBanner: (props) => <ToolCallBanner {...props} />,
}

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
  // 轮询起始时间（超时保护基准，cleanup 时重置）
  const pollStartRef = useRef<number | null>(null)

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
    // 中断进行中的 SSE 流，避免残留事件把 pipeline UI 推回到新载入的会话视图。
    // 语义说明（resume-pipeline-across-sessions）：旧语义=中断一切；新语义下深度管线
    // 已由后端 PipelineRunner 后台化保护，前端 abort 仅断开 SSE 订阅，不影响后台续跑。
    abortStreaming()
    // 提前切换 currentSessionId：让轮询 effect 立即 cleanup 旧 timer，
    // 避免 fetch 期间旧轮询命中 completed 调 selectSession 把视图切回原会话
    setCurrentSessionId(sessionId)
    try {
      const resp = await fetch(`/api/sessions/${sessionId}`)
      if (!resp.ok) throw new Error('Failed to load session')
      const data: SessionDetail = await resp.json()

      // 管线进度快照（snapshot.layerTree 为内嵌的序列化 JSON 字符串，需二次解析）
      let snapshot: PipelineSnapshot | null = null
      if (data.pipeline_snapshot) {
        try {
          snapshot = JSON.parse(data.pipeline_snapshot)
        } catch {
          snapshot = null // 非法快照按无快照处理，走现有恢复逻辑
        }
      }

      // 先完全重置所有状态
      setMessages([])
      setAppState('report')
      // 按会话类型锁定模式：chat -> quick，analysis -> deep
      setMode(data.session_type === 'chat' ? 'quick' : 'deep')
      streamingReportRef.current = null
      pipelineMsgRef.current = null

      // 运行中会话：恢复快照分层时间轴并进入 analyzing（轮询 hook 接手进度更新）
      // nodeTimelines：pipeline_timelines 存在时恢复各节点结构化时序（后端已反序列化为 dict）
      const restoredNodeTimelines = data.pipeline_timelines
        ? deserializeNodeTimelines(data.pipeline_timelines)
        : undefined
      const runningPipelineMsg: UIMessage | null =
        data.status === 'running' && snapshot
          ? {
              id: genId(),
              type: 'pipeline',
              content: '',
              completedNodes: [],
              currentNode: snapshot.currentNodeId,
              nodeOutputs: {},
              progress: snapshot.progress,
              startedAt: Date.now(),
              layerTree: deserializeLayerTree(snapshot.layerTree),
              ...(restoredNodeTimelines ? { nodeTimelines: restoredNodeTimelines } : {}),
            }
          : null
      if (runningPipelineMsg) {
        pipelineMsgRef.current = runningPipelineMsg
      }

      // 已完成会话（有快照）：报告消息 + 静态完成时间轴（时间轴插在报告消息之前）
      const pipelineDoneMsg: UIMessage | null =
        data.status === 'completed' && snapshot && data.session_type !== 'chat'
          ? {
              id: genId(),
              type: 'pipeline',
              content: '',
              completedNodes: [],
              currentNode: '',
              nodeOutputs: {},
              progress: 1,
              layerTree: deserializeLayerTree(snapshot.layerTree),
              ...(restoredNodeTimelines ? { nodeTimelines: restoredNodeTimelines } : {}),
            }
          : null

      const reportMsg: UIMessage | null = data.status !== 'running' && data.session_type !== 'chat'
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
            if (pipelineDoneMsg) newMessages.push(pipelineDoneMsg)
            newMessages.push(reportMsg)
            reportInserted = true
          }
        } else {
          newMessages.push({
            id: genId(),
            type: 'chat',
            content: '',
            chatResponse: h.content,
            // 历史恢复：优先结构化 agentTimeline（防御式反序列化）；
            // 旧数据无该字段时回退 thinking + tool_calls 拍平近似还原
            // （思考在前、工具调用在后；搜索类工具不还原为 tool_call item）
            agentTimeline: Array.isArray(h.agentTimeline)
              ? deserializeTimeline(h.agentTimeline)
              : buildTimelineFromHistory(h.thinking, h.tool_calls),
          })
        }
      }
      if (reportMsg && !reportInserted) {
        if (pipelineDoneMsg) newMessages.push(pipelineDoneMsg)
        newMessages.push(reportMsg)
      } else if (!reportMsg && pipelineDoneMsg) {
        newMessages.push(pipelineDoneMsg)
      }
      // 运行中管线消息追加在 chat_history 之后（管线正在跑，无报告）
      if (runningPipelineMsg) {
        newMessages.push(runningPipelineMsg)
        setAppState('analyzing')
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
        startedAt: Date.now(),
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
        streaming: true,
      }])
      return newId
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
                // 复用 applyChatStreamEvent：累加 chatResponse 同时收口末尾 thinking item，
                // 避免思考横幅在 agent 回复期间持续显示"思考中"（与 quickChat 路径行为一致）
                setMessages(prev => prev.map(m =>
                  m.id === assistantMsgId ? applyChatStreamEvent(m, event) : m
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

            if (event.type === 'search_start' || event.type === 'search_result' || event.type === 'search_error') {
              // 搜索事件统一走对话流共享处理，写入 agentTimeline 的 search item
              handleChatStreamEvent(event, ensureAssistantMsg())
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
                // 澄清阶段识别出股票：作为 search_stock 的结构化结果写入 timeline 中对应 tool_call item
                handleChatStreamEvent(
                  { type: 'tool_result', name: 'search_stock', result: `已识别：${event.stock_name} (${event.stock_code})`, timestamp: '' } as SSEEvent,
                  ensureAssistantMsg(),
                )
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
                event.type === 'node_timing' ||
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
          layerTree: applyNodeEvent(pipelineMsg.layerTree ?? buildLayerTree(), event, Date.now()),
        })
        break

      case 'node_timing':
        // 节点真实耗时（node_end 到达时下发），覆盖 updates 到达时刻的近似值
        updateMessage(pipelineMsg.id, {
          layerTree: applyNodeEvent(pipelineMsg.layerTree ?? buildLayerTree(), event, Date.now()),
        })
        break

      case 'node_complete':
        updateMessage(pipelineMsg.id, {
          ...applyPipelineNodeComplete(pipelineMsg, event.node_id),
          completedNodes: event.completed,
          currentNode: '',
          progress: event.progress,
          nodeOutputs: {
            ...(pipelineMsg.nodeOutputs || {}),
            [event.node_id]: event.output,
          },
          layerTree: applyNodeEvent(pipelineMsg.layerTree ?? buildLayerTree(), event, Date.now()),
          content: `${event.layer}: ${event.desc} ✓`,
        })
        break

      case 'thinking_token':
        // 管线运行期间的思考按 node 字段写入对应 agent 阶段的 timeline（nodeTimelines）
        updateMessage(pipelineMsg.id, applyPipelineThinkingToken(pipelineMsg, event))
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
        // 管线完成：记录本次总耗时用于 ETA 历史中位数预估
        if (event.duration_ms > 0) recordDuration(event.duration_ms)
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
      case 'thinking_replace':
      case 'search_start':
      case 'search_result':
      case 'search_error':
      case 'tool_call':
      case 'tool_result':
      case 'chat_token':
      case 'chat_done':
      case 'error':
        // 统一写入 agentTimeline（含思考片段断开、搜索/工具调用 item 生命周期），
        // 具体规则见 timeline.ts 与 agent-turn-box-display design.md
        setMessages(prev => prev.map(m => (m.id === chatId ? applyChatStreamEvent(m, event) : m)))
        return true

      case 'thinking_to_answer':
        // DeepSeek 原生思考模式：reasoning 与 content 天然分离，不再下发此事件。
        // 保留 case 仅作向后兼容（旧后端可能仍下发），忽略不影响新逻辑。
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

  // 运行中会话快照轮询（resume-pipeline-across-sessions Task 5）：
  // 切回 running 会话进入 analyzing 且无活跃 SSE（abortRef 为空=仅恢复态、非实时订阅）时，
  // 每 2s 拉取会话详情刷新分层时间轴；completed 则走 selectSession 完整恢复报告并自然停止；
  // failed 仅停止轮询（MVP 不展示失败态）。
  // 超时保护（Final Review Fix 2）：超过 MAX_POLLING_MS（5 分钟）后停止轮询并提示
  // 「管线可能已中断」，避免 ReAct 路径 status 永久 running 时轮询无限泄漏。
  // 前提不变量：abortRef 作为「SSE 在线」信号，依赖「analyzing 态必然发生在 SSE 存活期间」；
  // 用户在恢复态发起新分析时 startAnalysis 会设置 abortRef，但可能无 setState 触发 effect 重跑，
  // 因此 interval 回调内必须复查 abortRef，避免 SSE 与轮询双写消息、以及轮询误调 selectSession 掐断新 SSE。
  useEffect(() => {
    if (appState !== 'analyzing' || !currentSessionId) return
    if (abortRef.current) return // 有活跃 SSE 订阅，进度由事件流驱动，无需轮询
    pollStartRef.current = Date.now() // 记录轮询起始时间（超时保护基准）
    const timer = setInterval(async () => {
      // 复查 SSE 在线信号：用户在恢复态发起新分析（startAnalysis 已设置 abortRef）时轮询立即让位，
      // 等 effect 因状态变化重跑后 interval 自然清理
      if (abortRef.current) return
      // 超时保护：超过 MAX_POLLING_MS 则停止轮询并提示（ReAct 路径 status 可能永久 running）
      if (pollStartRef.current && Date.now() - pollStartRef.current >= MAX_POLLING_MS) {
        clearInterval(timer)
        const pm = pipelineMsgRef.current
        if (pm) {
          updateMessage(pm.id, { content: '管线可能已中断，请刷新或重新发起' })
        }
        return
      }
      try {
        const resp = await fetch(`/api/sessions/${currentSessionId}`)
        if (!resp.ok) return
        const data: SessionDetail = await resp.json()
        if (data.status === 'running' && data.pipeline_snapshot) {
          let snap: PipelineSnapshot | null = null
          try {
            snap = JSON.parse(data.pipeline_snapshot)
          } catch {
            snap = null
          }
          const pm = pipelineMsgRef.current
          if (snap && pm) {
            const updated: UIMessage = {
              ...pm,
              layerTree: deserializeLayerTree(snap.layerTree),
              currentNode: snap.currentNodeId,
              progress: snap.progress,
            }
            pipelineMsgRef.current = updated
            updateMessage(pm.id, updated)
          }
          // running 但无快照（或快照解析失败）：本周期静默忽略，等下个周期重试
        } else if (data.status === 'completed') {
          // 后台管线完成：直接恢复报告 + 最终静态时间轴，不调 selectSession
          // （避免递归切换 + 切换 async 窗口期旧 timer 残留导致强制跳转）
          const pm = pipelineMsgRef.current
          const finalSnap: PipelineSnapshot | null = data.pipeline_snapshot
            ? (() => {
                try { return JSON.parse(data.pipeline_snapshot) } catch { return null }
              })()
            : null
          if (pm) {
            const updated: UIMessage = {
              ...pm,
              layerTree: finalSnap ? deserializeLayerTree(finalSnap.layerTree) : pm.layerTree,
              currentNode: '',
              progress: 1,
            }
            pipelineMsgRef.current = updated
            updateMessage(pm.id, updated)
          }
          // 报告消息追加（若后端有 report_markdown）
          if (data.report_markdown) {
            const reportMsg: UIMessage = {
              id: genId(),
              type: 'report',
              content: '',
              reportMarkdown: data.report_markdown,
              chartData: data.chart_data || {},
              stockName: data.stock_name,
              durationMs: data.duration_ms,
              sessionId: currentSessionId,
            }
            setMessages(prev => [...prev, reportMsg])
          }
          setAppState('report') // 切 report 后轮询 effect cleanup 自然停止
          loadSessions()
        }
        // failed：不处理，随下一次状态变化或停留 analyzing 由用户操作离开（MVP）
      } catch {
        // 轮询失败静默，下个周期重试
      }
    }, 2000)
    return () => {
      clearInterval(timer)
      pollStartRef.current = null // cleanup 重置，下次轮询重新计时
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appState, currentSessionId])

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
            // search_* 已由共享分支处理；此处仅处理 session_created
            if (event.type === 'session_created') {
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
                  // pipeline 消息渲染时机：运行中（analyzing）始终显示；
                  // completed 会话恢复的静态完成时间轴（progress===1）随报告一并展示；
                  // 其他情况（如历史会话无快照回退的空树）不显示
                  if (msg.type === 'pipeline') {
                    return appState === 'analyzing' || msg.progress === 1;
                  }
                  return true;
                })
                .map(msg => (
                  <MessageRenderer key={msg.id} msg={msg} />
                ))}
            </div>

            {/* Fixed input at bottom */}
            <ChatInputBar onSend={handleSendFromChat} leftInset={leftInset} mode={mode} setMode={setMode} onNewAnalysis={newAnalysis} />
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
              data-testid="send-button"
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
      <div className="flex justify-start animate-slide-in" data-testid="stream-error">
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
      <div className="flex justify-start animate-slide-in" data-testid="stream-output">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'var(--bg-brand)' }}>
              <i className="fas fa-robot text-white text-xs"></i>
            </div>
            {/* Kimi 风格：思考区为统一白色时间轴容器，response 纯白底无框直接排版 */}
            <div className="flex-1 min-w-0">
              {/* 按 agentTimeline 数组顺序渲染：每个思考片段/搜索/工具调用一个独立横幅，
                  包在统一白色容器内用左侧竖线串联（时间轴效果），
                  反映 agent 实际执行时序（思考 -> 搜索 -> 再思考 -> 工具调用 -> ...） */}
              {msg.agentTimeline && msg.agentTimeline.length > 0 && (
                <TimelineRenderer
                  timeline={msg.agentTimeline}
                  streaming={!!msg.streaming}
                  components={timelineBannerComponents}
                />
              )}
              {/* response：纯白底、无框体、无背景色，像普通文档直接排版 */}
              {msg.chatResponse ? (
                <div className={`prose prose-sm max-w-none px-1 py-1 response-streaming ${msg.streaming ? 'is-streaming' : ''}`} style={{ color: 'var(--text-secondary)' }}>
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
                  {/* 流式输出中：动态图标跟在 response 文字末尾（与最后段落同行） */}
                  {msg.streaming && (
                    <span data-testid="stream-status" className="streaming-cursor">
                      <span className="block w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'var(--bg-brand)' }}></span>
                    </span>
                  )}
                </div>
              ) : null}
              {/* 思考阶段（尚无 response）：动态图标单独显示，无文字 */}
              {msg.streaming && !msg.chatResponse && (
                <div data-testid="stream-status" className="mt-2 flex items-center">
                  <div className="w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'var(--bg-brand)' }}></div>
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
// 思考横幅：统一快速模式与深度模式澄清阶段的思考流式展示。
// 思考中显示"思考中"并自动展开；完成后按横幅展开/折叠状态与是否有标题分别展示。
// embedded=true 时嵌入 TimelineRenderer 统一白色容器：去掉自身灰底框与外边距，融入时间轴。
export function ThinkingBanner({ content, streaming, title, embedded = false }: { content: string; streaming: boolean; title?: string; embedded?: boolean }) {
  const [expanded, setExpanded] = useState(true)
  const contentRef = useRef<HTMLDivElement>(null)

  // 流式时展开（实时看思考过程），完成后自动折叠（与 Kimi 一致）
  useEffect(() => {
    setExpanded(streaming)
  }, [streaming])

  useEffect(() => {
    if (expanded && streaming && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight
    }
  }, [content, expanded, streaming])

  // 横幅标题文案：思考中显示"思考中"；完成折叠按标题有无显示标题/"思考已完成"；完成展开固定"思考已完成"
  const bannerText = streaming
    ? '思考中'
    : expanded
      ? '思考已完成'
      : (title || '思考已完成')

  return (
    <div className={embedded ? '' : 'mb-3'}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left"
        style={{ background: embedded ? 'transparent' : 'var(--bg-overlay-l1)' }}
        onMouseEnter={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l2)'}}
        onMouseLeave={(e) => {e.currentTarget.style.background = embedded ? 'transparent' : 'var(--bg-overlay-l1)'}}
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
          {bannerText}
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
          style={embedded
            ? { background: 'transparent', borderLeft: '2px solid var(--border-neutral-l1)', borderRadius: 0, marginLeft: '12px' }
            : { background: 'var(--bg-overlay-l1)', border: '1px solid var(--border-neutral-l1)' }
          }
        >
          {/* 有标题时标题加粗置顶 */}
          {!streaming && title && (
            <p className="font-bold text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{title}</p>
          )}
          {/* 思考正文按 Markdown 渲染（支持 ## 标题分层与 **加粗** 分段） */}
          <div className="text-xs leading-relaxed prose prose-sm max-w-none" style={{ color: 'var(--text-tertiary)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Tool Call Banner (工具调用，与思考过程分离展示) ──
// embedded=true 时嵌入 TimelineRenderer 统一白色容器：去掉自身灰底框与外边距，融入时间轴。
export function ToolCallBanner({ toolCalls, streaming, embedded = false }: { toolCalls: ToolCallEntry[]; streaming: boolean; embedded?: boolean }) {
  const [expanded, setExpanded] = useState(true)
  const pendingCount = toolCalls.filter(t => !t.done).length
  const prevStreamingRef = useRef(streaming)

  useEffect(() => {
    // 与 ThinkingBanner 对称：流式（有 pending 工具）时展开实时看调用过程，
    // 完成后自动折叠（深度模式 run_deep_analysis 使工具停留末尾 streaming 滞留 true，
    // 但 done=true 无 pending 时 streaming 已转 false，此处随 streaming 变 false 折叠）
    setExpanded(streaming)
    prevStreamingRef.current = streaming
  }, [streaming])

  const isJustFinished = !streaming && prevStreamingRef.current

  return (
    <div className={embedded ? '' : 'mb-3'}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left"
        style={{ background: embedded ? 'transparent' : 'var(--bg-overlay-l1)' }}
        onMouseEnter={(e) => {e.currentTarget.style.background = 'var(--bg-overlay-l2)'}}
        onMouseLeave={(e) => {e.currentTarget.style.background = embedded ? 'transparent' : 'var(--bg-overlay-l1)'}}
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
          style={embedded
            ? { background: 'transparent', borderLeft: '2px solid var(--border-neutral-l1)', borderRadius: 0, marginLeft: '12px' }
            : { background: 'var(--bg-overlay-l1)', border: '1px solid var(--border-neutral-l1)' }
          }
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

  // ETA 每秒刷新（仅管线运行中；完成后停止计时）
  const pipelineDone = completed.includes('generate_file') || completed.includes('fund_manager')
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (pipelineDone) return
    const timer = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [pipelineDone])

  const elapsedMs = msg.startedAt ? Math.max(0, nowMs - msg.startedAt) : 0
  const estimatedTotalMs = estimateTotalMs(loadDurations())
  const remainingMs = estimateRemainingMs(elapsedMs, progress, estimatedTotalMs)
  const etaText = pipelineDone
    ? `总耗时 ${formatDurationMs(elapsedMs)}`
    : `已用时 ${formatDurationMs(elapsedMs)} · 预计剩余 ~${formatDurationMs(remainingMs)}`

  // 分层时间轴状态树（无事件数据的历史会话回退为空树，PipelineTimeline 空渲染）
  const layerTree = msg.layerTree ?? buildLayerTree()

  // 当前运行节点的实时思考单行预览（从 nodeTimelines 提取末尾 thinking 内容尾 80 字符）
  const thinkingPreviewFor = (nodeId: string): string | undefined => {
    const items = msg.nodeTimelines?.[nodeId]
    if (!items || items.length === 0) return undefined
    const last = items[items.length - 1]
    if (last.type !== 'thinking' || !last.content) return undefined
    return last.content.slice(-80)
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
                <span className="text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>{etaText}</span>
              </div>
              <div className="flex items-center gap-1 mb-2">
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-overlay-l1)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{ width: `${Math.max(5, progress * 100)}%`, background: 'var(--bg-brand)' }}
                  />
                </div>
              </div>
              {/* 分层时间轴：6 层 layer + 可展开子节点（替换原 6 阶段圆点） */}
              <PipelineTimeline tree={layerTree} nowMs={nowMs} thinkingPreviewFor={thinkingPreviewFor} />
            </div>

            {/* 各 agent 阶段的思考/工具调用时序：按 node 分组，阶段间用角色名标题分隔（非折叠框）。
                阶段内按时间序列渲染该 agent 的 timeline items；当前活动 node 的横幅展开流式。 */}
            {msg.nodeTimelines && Object.keys(msg.nodeTimelines).length > 0 && (
              <div className="px-5 py-3" style={{ borderTop: '1px solid var(--border-neutral-l1)' }}>
                {Object.entries(msg.nodeTimelines).map(([node, items]) => (
                  <div key={node} className="mb-2">
                    {node && (
                      <div className="text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                        {nodeDisplayName(node)}
                      </div>
                    )}
                    <TimelineRenderer
                      timeline={items}
                      streaming={current === node}
                      components={timelineBannerComponents}
                    />
                  </div>
                ))}
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
                    <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>深度分析报告 · 5 层 Agent 架构 · {(msg.durationMs ?? 0) > 0 ? `耗时 ${Math.round((msg.durationMs ?? 0) / 1000)}s` : '耗时未知'}</p>
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
function ChatInputBar({ onSend, leftInset, mode, setMode, onNewAnalysis }: { onSend: (text: string) => void; leftInset: number; mode: 'quick' | 'deep'; setMode: (m: 'quick' | 'deep') => void; onNewAnalysis: () => void }) {
  const [text, setText] = useState('')
  const [modeDropdownOpen, setModeDropdownOpen] = useState(false)

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend(text)
      setText('')
    }
  }

  const modes = [
    { id: 'quick' as const, label: '快速模式', icon: 'fa-bolt', color: 'text-[var(--status-warning-default)]', desc: '单次 LLM + Web Search，秒级响应' },
    { id: 'deep' as const, label: '深度研究', icon: 'fa-layer-group', color: 'text-[var(--text-brand)]', desc: '5 层 Agent 流水线，2-5 分钟完整报告' },
  ]
  const currentMode = modes.find(m => m.id === mode)!

  // 会话中切换模式：更新模式并直接开启新会话
  const handleModeSelect = (m: 'quick' | 'deep') => {
    setModeDropdownOpen(false)
    if (m === mode) return
    setMode(m)
    onNewAnalysis()
  }

  return (
    <div
      className="fixed bottom-0 right-0 z-40 px-4 pb-4 pt-2"
      style={{ left: leftInset, background: 'linear-gradient(to top, var(--bg-base-default) 80%, transparent)' }}
    >
      <div className="max-w-3xl mx-auto">
        <div className="glass-input rounded-2xl p-2">
          {/* Mode switcher：下拉框，会话中切换模式直接开启新会话 */}
          <div className="relative flex items-center gap-1 px-1 pb-1">
            <button
              onClick={() => setModeDropdownOpen(!modeDropdownOpen)}
              className="flex items-center gap-1.5 text-[11px] font-medium rounded-lg px-2.5 py-1 transition-colors hover:bg-[var(--bg-overlay-l1)]"
            >
              <i className={`fas ${currentMode.icon} ${currentMode.color} text-[10px]`}></i>
              <span className={currentMode.color}>{currentMode.label}</span>
              <i className={`fas fa-chevron-${modeDropdownOpen ? 'down' : 'up'} text-[8px] ml-0.5`} style={{ color: 'var(--text-tertiary)' }}></i>
            </button>
            {modeDropdownOpen && (
              <div className="absolute left-1 bottom-8 z-[70] w-72 glass-card rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
                {modes.map(m => (
                  <button
                    key={m.id}
                    onClick={() => handleModeSelect(m.id)}
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
                    {mode !== m.id && (
                      <span className="text-[10px] mt-0.5 flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>新会话</span>
                    )}
                  </button>
                ))}
              </div>
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
              data-testid="send-button"
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
