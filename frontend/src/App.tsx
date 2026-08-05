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

// 快照恢复路径：决定 resumeStream 的 after_seq。
// 快照只含前端实时流渲染到的内容，lastSeq 是实际渲染进度。
// 优先用前端 lastSeq 续传未渲染事件；为 0（从未收到事件）时用后端 last_seq 兜底。
// 不可用 Math.max(front, back)——后端 last_seq 是 journal 全量 max，
// 用它会跳过快照与后端之间前端未渲染的事件（流式文字内容缺失根因）。
export function resumeAfterSeqFromSnapshot(frontLastSeq: number, backLastSeq: number): number {
  return frontLastSeq > 0 ? frontLastSeq : backLastSeq
}

// selectSession stale guard：fetch 返回后判断用户是否仍在请求的会话。
//
// 根因：selectSession 是 async 函数，await fetch 期间用户可能已切换到其他会话。
// 若不检查，fetch 返回后会为已切走的会话启动 resumeStream，导致两个 resumeStream
// reader 并发——它们竞争覆盖全局 streamingSessionIdRef，使隔离检查失效，
// chat_token 等增量事件被误判为「非当前视图」丢弃（continue 跳过）→ 内容缺失。
export function shouldProcessFetchedSession(
  requestedSessionId: string,
  currentSessionId: string | null,
): boolean {
  return requestedSessionId === currentSessionId
}

// resumeStream 会话隔离检查：判断 SSE 事件是否属于当前视图。
//
// 必须用 reader 的局部 sessionId（绑定到本次 SSE 订阅），不可用全局
// streamingSessionIdRef.current——多个并发 resumeStream reader 会竞争覆盖该全局 ref，
// 导致隔离检查使用错误的值（内容缺失根因）。
export function isCurrentViewEvent(
  readerSessionId: string,
  currentSessionId: string | null,
): boolean {
  return readerSessionId === currentSessionId
}

// Single-reader 不变量：启动新 SSE reader 前先 abort 现存的全局 controller。
// 根因：resumeStream/quickChat 直接覆盖 abortRef.current 而不先 abort 旧值，
// 旧 reader 继续运行并写全局 assistantMsgIdRef → 串字/丢内容。
export function ensureSingleReader(
  currentAbort: AbortController | null,
  newAbort: AbortController,
): AbortController {
  if (currentAbort && !currentAbort.signal.aborted) {
    currentAbort.abort()
  }
  return newAbort
}

// reader 退出时该清理哪条消息的 streaming 游标。
//
// 根因（E2E 复现确认）：reader 退出的兜底清理读全局 assistantMsgIdRef.current，
// 但并发场景下该 ref 已被后启动的会话覆盖 → 旧 reader 退出时把
// 新会话正在流式的消息误置 streaming:false → 前端停止渲染后续 token
// → 新会话文本后半段整段丢失（症状：「这是一段测试用的固定回复。」后面全没了）。
//
// 修复：只清理本 reader 自己创建的消息（局部 ownMsgId），
// 且仅当全局 ref 仍指向它时才动（双重保险）。
export function msgIdToClearOnReaderExit(
  ownMsgId: string | null,
  globalMsgId: string | null,
): string | null {
  if (!ownMsgId) return null
  return ownMsgId === globalMsgId ? ownMsgId : null
}

// SSE 诊断日志：复现流式文字缺失问题时，在 URL 加 ?sse_debug 开启。
// 控制台过滤 [SSE] 查看事件路由轨迹、seq 去重、abort 时序、reader 生命周期。
const SSE_DEBUG = typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).has('sse_debug')
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function sseDebug(action: string, details: Record<string, any>) {
  if (!SSE_DEBUG) return
  console.warn('[SSE]', action, JSON.stringify(details))
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
  // 包装 setCurrentSessionId：同步持久化到 localStorage（fa_current_session_id），
  // 供刷新后自动恢复当前会话（delta spec: restore-session-on-refresh）
  const setAndPersistSession = useCallback((id: string | null) => {
    if (id) {
      localStorage.setItem('fa_current_session_id', id)
    } else {
      localStorage.removeItem('fa_current_session_id')
    }
    setCurrentSessionId(id)
  }, [])
  // ref 镜像：SSE 事件处理闭包中读取最新 currentSessionId，判断事件是否属于当前视图
  const currentSessionIdRef = useRef<string | null>(null)
  // SSE 流绑定的会话 ID：用于事件处理闭包中判断事件是否属于当前视图
  const streamingSessionIdRef = useRef<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const streamingReportRef = useRef<UIMessage | null>(null)
  const [mode, setMode] = useState<'quick' | 'deep'>('deep')
  // SSE 消息 ID ref：用于在会话切换时重置，确保切回后新事件能正确更新重建的消息
  const assistantMsgIdRef = useRef<string | null>(null)
  const pipelineMsgIdRef = useRef<string | null>(null)
  // 当前活跃订阅的 AbortController：切换会话/新建分析时 abort 仅断开本地订阅连接，
  // 不终止后端 stream_registry 后台任务（delta spec Task 5.2）
  const abortRef = useRef<AbortController | null>(null)
  // messages ref 镜像：会话切换时读取最新 messages 存入快照
  const messagesRef = useRef<UIMessage[]>([])

  // 统一 messages 更新入口：在 setMessages 调度的同时同步更新 messagesRef.current，
  // 避免 useEffect 滞后导致 selectSession 保存快照时读取到旧值（根因：async 函数中
  // setMessages 调度后渲染/effect 未及时执行，切换会话时快照保存了过时的 messages）
  const commitMessages = (updater: UIMessage[] | ((prev: UIMessage[]) => UIMessage[])) => {
    const newMsgs = typeof updater === 'function' ? updater(messagesRef.current) : updater
    messagesRef.current = newMsgs
    setMessages(newMsgs)
  }

  // ── per-session 流状态（delta spec Task 5.1）──
  // 每个 session 独立跟踪 abort/pipelineMsg/streamingReport/lastSeq，
  // 切换会话时保留状态，切回时恢复并经恢复端点续传事件流。
  // 在 sessionCacheRef / bufferedSseEventsRef 之上作为补充层。
  type StreamState = {
    abort: AbortController | null
    pipelineMsg: UIMessage | null
    streamingReport: UIMessage | null
    assistantMsgId: string | null
    pipelineMsgId: string | null
    lastSeq: number
    // 消息快照：切换会话时保存当前 messages，切回 running/clarifying 会话时恢复，
    // 避免后端 chat_history 未持久化 agent 在途内容导致切换后内容消失
    messages: UIMessage[]
  }
  const streamRegistryRef = useRef<Map<string, StreamState>>(new Map())

  // 获取或创建会话的流状态
  const getStreamState = useCallback((sessionId: string): StreamState => {
    let state = streamRegistryRef.current.get(sessionId)
    if (!state) {
      state = {
        abort: null, pipelineMsg: null, streamingReport: null,
        assistantMsgId: null, pipelineMsgId: null, lastSeq: 0,
        messages: [],
      }
      streamRegistryRef.current.set(sessionId, state)
    }
    return state
  }, [])

  // 保存当前视图状态到 streamRegistry（切换会话前调用）
  const saveCurrentStreamState = useCallback(() => {
    const curId = currentSessionIdRef.current
    if (!curId) return
    const state = getStreamState(curId)
    state.pipelineMsg = pipelineMsgRef.current
    state.streamingReport = streamingReportRef.current
    state.assistantMsgId = assistantMsgIdRef.current
    state.pipelineMsgId = pipelineMsgIdRef.current
    state.abort = abortRef.current
    state.messages = messagesRef.current
  }, [getStreamState])

  // 从 streamRegistry 恢复目标会话状态到当前视图 ref
  const restoreStreamState = useCallback((sessionId: string) => {
    const state = streamRegistryRef.current.get(sessionId)
    pipelineMsgRef.current = state?.pipelineMsg ?? null
    streamingReportRef.current = state?.streamingReport ?? null
    assistantMsgIdRef.current = state?.assistantMsgId ?? null
    pipelineMsgIdRef.current = state?.pipelineMsgId ?? null
  }, [])

  // 断开当前会话的本地 SSE 订阅连接（不取消后端任务）
  const disconnectSubscription = useCallback(() => {
    if (abortRef.current) {
      sseDebug('disconnect', {
        streamingSession: streamingSessionIdRef.current,
        view: currentSessionIdRef.current,
        aborted: !abortRef.current.signal.aborted,
      })
      abortRef.current.abort()
      abortRef.current = null
    }
    streamingSessionIdRef.current = null
  }, [])

  // ── 消息快照缓存（保留机制）──
  // 切换会话时保存当前 messages 快照，切回 running/clarifying 会话时恢复，
  // 避免后端 chat_history 未持久化 agent 在途内容导致切换后内容消失
  const sessionCacheRef = useRef<Map<string, {
    messages: UIMessage[]
    assistantMsgId: string | null
    pipelineMsgId: string | null
    pipelineMsg: UIMessage | null
    streamingReport: UIMessage | null
  }>>(new Map())

  // ── SSE 事件缓冲区（保留机制）──
  // 会话切换期间被跳过的事件存入缓冲区，切回时 replayBufferedEvents() 回放
  const bufferedSseEventsRef = useRef<SSEEvent[]>([])

  // 断开当前 SSE 订阅（仅本地 abort，不调后端 cancel）
  // 保留给 startAnalysis/deleteSession 等历史调用点使用
  const abortStreaming = useCallback(() => {
    disconnectSubscription()
  }, [disconnectSubscription])

  // 同步 currentSessionId 到 ref（SSE 闭包中读取最新值）
  useEffect(() => {
    currentSessionIdRef.current = currentSessionId
  }, [currentSessionId])

  // 同步 messages 到 ref（会话切换时读取最新 messages 存入快照）
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  // Auto-scroll to bottom：仅在用户未手动上拉时自动滚动（避免抢占手动滚动）
  const userScrolledUpRef = useRef(false)
  useEffect(() => {
    const onScroll = () => {
      const nearBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 100
      userScrolledUpRef.current = !nearBottom
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const scrollToBottom = useCallback(() => {
    if (userScrolledUpRef.current) return
    setTimeout(() => {
      if (userScrolledUpRef.current) return
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
    }, 100)
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // ── Session management ──
  // 返回加载到的会话数组（失败返回 null）：调用方可据此决定是否重试
  // （useEffect 初始化时退避重试），成功时亦可直接拿到列表做存在性校验
  const loadSessions = useCallback(async (): Promise<SessionMeta[] | null> => {
    try {
      const resp = await fetch('/api/sessions')
      if (!resp.ok) return null
      const data = await resp.json()
      // 200 但 body 缺 sessions 字段（代理/中间件异常返回 {} 等）视为失败，
      // 不用空数组覆盖已有列表（否则分析运行期间一次异常响应就清空侧边栏）
      if (!Array.isArray(data?.sessions)) return null
      setSessions(data.sessions)
      return data.sessions as SessionMeta[]
    } catch (e) {
      console.error('Failed to load sessions:', e)
      return null
    }
  }, [])

  // selectSession 引用：mount 自动恢复在 selectSession 定义之前执行，经 ref 取最新引用
  const selectSessionRef = useRef<((id: string) => Promise<void>) | null>(null)
  // 刷新自动恢复仅执行一次（避免 loadSessions 后续触发时重复恢复覆盖用户已切换视图）
  const restoredRef = useRef(false)

  // 首次加载：后端启动需要数秒（uvicorn + init_db），且深度分析运行期间
  // 事件循环被阻塞会导致 /api/sessions 长时间挂起。失败时持续退避重试
  // （间隔封顶 10s），后端恢复后列表自动出现，不再因重试次数耗尽而永久空白。
  useEffect(() => {
    let cancelled = false
    let retryCount = 0

    const loadWithRetry = async () => {
      const loaded = await loadSessions()
      if (cancelled || loaded === null) {
        if (cancelled) return
        // 退避：500ms, 1s, 2s, ... 封顶 10s，无限重试直到成功
        const delay = Math.min(500 * Math.pow(2, retryCount), 10000)
        retryCount++
        setTimeout(loadWithRetry, delay)
        return
      }
      // 列表加载成功：刷新后自动恢复此前查看的会话（delta spec: restore-session-on-refresh）
      if (!restoredRef.current) {
        restoredRef.current = true
        const persistedId = localStorage.getItem('fa_current_session_id')
        if (persistedId) {
          if (loaded.some(s => s.session_id === persistedId)) {
            // 会话仍存在：复用 selectSession 恢复（含 running 时 SSE 重连）
            void selectSessionRef.current?.(persistedId)
          } else {
            // 持久化会话已被删除：清除并停留空态首页
            localStorage.removeItem('fa_current_session_id')
          }
        }
      }
    }

    loadWithRetry()
    return () => { cancelled = true }
  }, [loadSessions])

  // ── Task 6: 运行指示与显式停止 ──

  // 临时警告提示（如"该会话正在生成中"）
  const [warningMessage, setWarningMessage] = useState<string | null>(null)

  // 判断指定会话是否正在运行生成任务
  // 条件：session status 为 running，或 streamRegistryRef 中有未中断的 abort controller
  const isSessionRunning = (sessionId: string | null): boolean => {
    if (!sessionId) return false
    const session = sessions.find(s => s.session_id === sessionId)
    if (session?.status === 'running') return true
    const state = streamRegistryRef.current.get(sessionId)
    return !!state?.abort && !state.abort.signal.aborted
  }

  // 终态事件后清理：清除活跃流标记并刷新会话列表（移除侧边栏运行指示）
  const handleStreamTerminal = useCallback((sessionId: string | null) => {
    if (sessionId) {
      const state = streamRegistryRef.current.get(sessionId)
      if (state) state.abort = null
    }
    loadSessions()
  }, [loadSessions])

  // 停止当前会话的生成任务（调用后端 cancel 端点）
  const stopGeneration = async () => {
    if (!currentSessionId) return
    try {
      await fetch(`/api/sessions/${currentSessionId}/cancel`, { method: 'POST' })
    } catch (e) {
      console.error('Failed to stop:', e)
    }
  }

  // 页面卸载时断开所有本地 SSE 订阅（仅退订，不调后端 cancel）
  useEffect(() => {
    const handleBeforeUnload = () => {
      streamRegistryRef.current.forEach(state => {
        state.abort?.abort()
      })
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [])

  const selectSession = async (sessionId: string) => {
    // 断开当前会话的本地 SSE 订阅连接（不调用后端 cancel，不影响后台任务）
    // delta spec Task 5.2：切换会话仅断开本地订阅
    disconnectSubscription()

    // 保存当前会话的 messages 快照：切回时若 agent 仍在生成则从快照恢复，
    // 避免后端 chat_history 未持久化 agent 内容导致内容丢失
    const curId = currentSessionIdRef.current
    if (curId && curId !== sessionId && messagesRef.current.length > 0) {
      sessionCacheRef.current.set(curId, {
        messages: messagesRef.current,
        assistantMsgId: assistantMsgIdRef.current,
        pipelineMsgId: pipelineMsgIdRef.current,
        pipelineMsg: pipelineMsgRef.current,
        streamingReport: streamingReportRef.current,
      })
    }

    setAndPersistSession(sessionId)
    // 同步更新 ref：setAndPersistSession 调用 setCurrentSessionId 触发 React 状态更新，
    // 但 currentSessionIdRef.current 要等 useEffect 异步同步。在 await fetch 挂起期间，
    // ref 可能仍是旧值，导致 stale guard 不可靠。此处同步赋值确保 ref 立即生效。
    currentSessionIdRef.current = sessionId
    try {
      const resp = await fetch(`/api/sessions/${sessionId}`)
      if (!resp.ok) throw new Error('Failed to load session')
      const data: SessionDetail = await resp.json()

      // stale guard：fetch 期间用户可能已切换到其他会话（selectSession 是 async，
      // 两个 selectSession 可交错执行）。若用户已切走，不处理此响应、不启动 resumeStream，
      // 否则两个 resumeStream reader 并发会竞争覆盖全局 streamingSessionIdRef，
      // 使隔离检查失效导致 chat_token 被误丢弃（内容缺失根因）。
      if (!shouldProcessFetchedSession(sessionId, currentSessionIdRef.current)) return

      // 若 agent 仍在生成（clarifying/running）且前端有该会话的消息快照，
      // 优先从快照恢复：后端 chat_history 此时未持久化 agent 的思考/工具调用内容
      const cached = sessionCacheRef.current.get(sessionId)
      if (cached && (data.status === 'clarifying' || data.status === 'running')) {
        commitMessages(cached.messages)
        setMode(data.session_type === 'chat' ? 'quick' : 'deep')
        streamingReportRef.current = cached.streamingReport
        pipelineMsgRef.current = cached.pipelineMsg
        assistantMsgIdRef.current = cached.assistantMsgId
        pipelineMsgIdRef.current = cached.pipelineMsgId
        setAppState(data.status === 'running' ? 'analyzing' : 'clarifying')
        // 清空缓冲区：快照已包含切换前的全部内容，缓冲事件会与之重叠导致叠加
        bufferedSseEventsRef.current = []
        // running 和 clarifying 会话都恢复实时事件流（只订阅新事件，不重放历史）
        // ReAct 路径中 session status 为 clarifying（非 running），但后端任务可能仍在运行
        // 用后端 last_seq 兜底：state.lastSeq 可能因首次切换、ref 重置等原因停留在 0，
        // 此时 after_seq=0 会重放全部历史事件（可能数百上千个）导致 UI 卡顿。
        // 取 max 确保不回退：已处理的 lastSeq 优先，后端 last_seq 作为下界兜底。
        if (data.status === 'running' || data.status === 'clarifying') {
          const streamState = getStreamState(sessionId)
          // 快照恢复：前端 lastSeq 是实际渲染进度，优先用它续传；
          // 为 0 时用后端 last_seq 兜底。不可取 Math.max（见 resumeAfterSeqFromSnapshot 注释）。
          streamState.lastSeq = resumeAfterSeqFromSnapshot(streamState.lastSeq, data.last_seq ?? 0)
          resumeStream(sessionId, false)
        }
        return
      }
      // agent 已完成或无快照：从后端 chat_history 重建

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
      commitMessages([])
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
              // 已用时计时起点：优先用后端快照的管线启动时间戳（刷新不归零），缺省回退本地
              startedAt: snapshot.pipeline_start_ts ?? Date.now(),
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

      const reportMsg: UIMessage | null = (data.status === 'completed' || data.status === 'failed') && data.session_type !== 'chat'
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
      // 管线触发锚点：非空时按锚点定位报告插入位置（多轮澄清场景）；
      // null/缺失（旧会话）回退第一个 user 消息后插入
      const anchor = data.pipeline_anchor ?? null
      for (let i = 0; i < history.length; i++) {
        const h = history[i]
        if (h.role === 'user') {
          newMessages.push({ id: genId(), type: 'user', content: h.content })
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
        // 锚点非空：处理完第 anchor 条后插入报告（多轮澄清场景正确定位）
        if (anchor !== null && i + 1 === anchor && reportMsg && !reportInserted) {
          if (pipelineDoneMsg) newMessages.push(pipelineDoneMsg)
          newMessages.push(reportMsg)
          reportInserted = true
        }
        // 锚点为 null（旧会话）：回退第一个 user 消息后插入
        if (anchor === null && h.role === 'user' && reportMsg && !reportInserted) {
          if (pipelineDoneMsg) newMessages.push(pipelineDoneMsg)
          newMessages.push(reportMsg)
          reportInserted = true
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
      } else if (data.status === 'clarifying') {
        // 澄清阶段：显示聊天界面，允许用户继续对话
        setAppState('clarifying')
      } else if (data.status === 'interrupted') {
        // 中断态：展示已落库的半截回复，进入可追问状态（delta spec Task 5.5）
        setAppState('clarifying')
        // 清除最后一条助手消息的 streaming 状态（避免无限转圈）
        const lastChat = [...newMessages].reverse().find(m => m.type === 'chat')
        if (lastChat) {
          lastChat.streaming = false
        }
      }
      // 重置 SSE 消息 ID ref：让后台 SSE 闭包检测到 ID 失效，
    // 为新重建的消息分配新 ID，确保后续事件能正确渲染
    assistantMsgIdRef.current = null
    pipelineMsgIdRef.current = null
    // 如果有恢复的运行中管线，设置 pipelineMsgIdRef 以便 SSE 事件能正确更新
    if (runningPipelineMsg) {
      pipelineMsgIdRef.current = runningPipelineMsg.id
      pipelineMsgRef.current = runningPipelineMsg
    }
    // 从重建的消息列表中找到最后一条 chat 消息的 ID，
    // 让后台 SSE 的 thinking/tool_call 事件能更新到这条已有消息，而不是创建新消息
    const lastChatMsg = [...newMessages].reverse().find(m => m.type === 'chat')
    if (lastChatMsg) {
      assistantMsgIdRef.current = lastChatMsg.id
    }
    // 如果重建的消息列表中有 pipeline 类型的消息（已完成管线快照），同步 ref
    if (pipelineDoneMsg && !runningPipelineMsg) {
      pipelineMsgIdRef.current = pipelineDoneMsg.id
      pipelineMsgRef.current = pipelineDoneMsg
    }
    commitMessages(newMessages)
    // 清空缓冲区：消息已从 chat_history 重建，缓冲事件会与之重叠导致叠加
    bufferedSseEventsRef.current = []

    // 恢复事件流（delta spec Task 5.2/5.4）
    // 消息已从 chat_history 重建，恢复流时用后端 last_seq 跳过历史重放，
    // 只订阅实时事件。避免重放历史事件与重建消息重叠导致重复叠加。
    // running 和 clarifying 都恢复：ReAct 路径 status 为 clarifying 但任务可能仍在运行
    if (data.status === 'running' || data.status === 'clarifying') {
      const streamState = getStreamState(sessionId)
      // 与快照恢复路径一致：前端 lastSeq 是实际渲染进度，优先用它续传；
      // 为 0 时用后端 last_seq 兜底。不可取 Math.max——后端 last_seq 是 journal 全量 max，
      // 用它会跳过 chat_history 重建后、后端 journal 中前端尚未通过流式渲染的增量事件
      // （两 session 同时运行时后端事件增长更快、backLastSeq 更大 → 跳过更多 → 必然缺失）。
      streamState.lastSeq = resumeAfterSeqFromSnapshot(streamState.lastSeq, data.last_seq ?? 0)
      // lastSeq 仍为 0 时（后端 journal 为空或字段缺失），after_seq=0 会重放全部历史。
      // 此时 skipIncremental=true 跳过增量内容事件（thinking_token/chat_token 等），
      // 避免与重建消息重复叠加；只处理状态转换事件（analysis_start/done 等）。
      const skipIncremental = streamState.lastSeq === 0
      resumeStream(sessionId, skipIncremental)
    }
    // interrupted/completed/failed 不恢复流（无活跃任务或已终态）
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }
  // 同步到 ref：供 mount 自动恢复（定义顺序在 selectSession 之前的 effect）调用
  selectSessionRef.current = selectSession

  const deleteSession = async (sessionId: string) => {
    try {
      // 先取消后端活跃任务（delta spec Task 5.3：删除会话时取消生成任务）
      // 后端 DELETE 端点也会 cancel，但显式调用确保取消
      try {
        await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' })
      } catch {
        // 忽略取消失败（可能无活跃任务），继续删除
      }
      // 断开本地 SSE 订阅并清理 streamRegistry（delta spec Task 5.3）
      const state = streamRegistryRef.current.get(sessionId)
      if (state?.abort) {
        state.abort.abort()
      }
      streamRegistryRef.current.delete(sessionId)
      sessionCacheRef.current.delete(sessionId)
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      // 同步后端列表（确保顺序/其他字段一致，乐观更新可能遗漏后端副作用）
      loadSessions()
      if (currentSessionId === sessionId) {
        disconnectSubscription()
        setAndPersistSession(null)
        streamingReportRef.current = null
        pipelineMsgRef.current = null
        assistantMsgIdRef.current = null
        pipelineMsgIdRef.current = null
        bufferedSseEventsRef.current = []
        commitMessages([])
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
      // 同步后端列表（确保顺序/其他字段一致）
      loadSessions()
    } catch (e) {
      console.error('Failed to rename session:', e)
    }
  }

  const newAnalysis = () => {
    // 断开当前会话的本地 SSE 订阅（不调后端 cancel，保留 streamStates）
    // delta spec Task 5.3：新建分析仅断开本地订阅，后台任务继续运行
    disconnectSubscription()

    // 保存当前会话的 messages 快照：切回时若 agent 仍在生成则从快照恢复
    const curId = currentSessionIdRef.current
    if (curId && messagesRef.current.length > 0) {
      sessionCacheRef.current.set(curId, {
        messages: messagesRef.current,
        assistantMsgId: assistantMsgIdRef.current,
        pipelineMsgId: pipelineMsgIdRef.current,
        pipelineMsg: pipelineMsgRef.current,
        streamingReport: streamingReportRef.current,
      })
    }

    setAndPersistSession(null)
    streamingReportRef.current = null
    pipelineMsgRef.current = null
    assistantMsgIdRef.current = null
    pipelineMsgIdRef.current = null
    // 清空缓冲区，避免旧会话的缓冲事件污染新分析
    bufferedSseEventsRef.current = []
    commitMessages([])
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

    // 拦截：当前会话正在运行时不允许提交新消息（delta spec Task 6.2）
    if (sessionId && isSessionRunning(sessionId)) {
      setWarningMessage('该会话正在生成中，可停止后再发')
      setTimeout(() => setWarningMessage(null), 3000)
      return
    }

    // 开始新分析前中断旧 SSE 流，防止资源泄漏
    abortStreaming()

    // 首次进入聊天模式
    if (appState === 'empty') {
      setAppState('clarifying')
    }

    // 只有新会话才重置 session；澄清轮次保留 currentSessionId
    if (!sessionId) {
      setAndPersistSession(null)
      streamingReportRef.current = null
    }

    // 添加用户消息
    const userMsg: UIMessage = {
      id: genId(),
      type: 'user',
      content: query,
    }
    commitMessages(prev => [...prev, userMsg])

    // 流式处理 SSE 事件
    // 每轮重置消息 ID ref，确保会话切换后新事件能正确更新重建的消息
    assistantMsgIdRef.current = null
    pipelineMsgIdRef.current = null
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
      pipelineMsgIdRef.current = pm.id
      pipelineMsgRef.current = pm
      commitMessages(prev => [...prev, pm])
      setAppState('analyzing')
      return pm
    }

    // 获取或创建对话流中的助手消息（承载思考过程、工具调用、澄清回复）。
    // 澄清/解析阶段（search_stock / web_search / thinking）走对话流，不触发管线 UI；
    // 仅 run_deep_analysis 才调用 ensurePipelineMsg 进入管线 UI（ADR-0017）。
    const ensureAssistantMsg = (): string => {
      if (assistantMsgIdRef.current) {
        ownAssistantMsgId = assistantMsgIdRef.current
        return assistantMsgIdRef.current
      }
      const newId = genId()
      assistantMsgIdRef.current = newId
      ownAssistantMsgId = newId
      commitMessages(prev => [...prev, {
        id: newId,
        type: 'chat',
        content: '',
        chatResponse: '',
        streaming: true,
      }])
      return newId
    }

    // 在 try 外声明：catch 块也需要访问（终止清理）
    let activeSessionId = sessionId || ''
    // 本 reader 自己创建/接管的助手消息 ID（局部，不受并发会话覆盖全局 ref 影响）。
    // reader 退出时只清理这条消息的游标，避免误清并发会话正在流式的消息。
    let ownAssistantMsgId: string | null = null

    try {
      // 并发订阅隔离：先 abort 该会话已有的活跃订阅（与 resumeStream 一致）。
      // 否则两条 SSE reader 并发累加同一消息，React setState 各自基于同一份 prev，
      // 后到的覆盖先到的，导致随机丢失 token（症状：流式文本概率性错乱）。
      if (sessionId) {
        const existingState = getStreamState(sessionId)
        if (existingState.abort && !existingState.abort.signal.aborted) {
          existingState.abort.abort()
        }
      }
      // 全局 single-reader 不变量：abort 任何残留 reader（与 resumeStream/quickChat 一致）。
      // line 736 的 abortStreaming() 只 abort 全局 abortRef，若期间有其他路径
      // （如 selectSession → resumeStream）重新赋值，此处兜底确保只有一条 reader。
      if (abortRef.current && !abortRef.current.signal.aborted) {
        sseDebug('global_abort', { source: 'startAnalysis', session: sessionId, aborting: streamingSessionIdRef.current })
      }
      const localAbort = ensureSingleReader(abortRef.current, new AbortController())
      abortRef.current = localAbort
      // 提前激活 seq 去重（与 quickChat 一致）：追问场景后端可能不重发 session_created，
      // fetch 前设置 streamingSessionIdRef 使去重从第一个事件起生效
      if (sessionId) {
        streamingSessionIdRef.current = sessionId
        // 追问路径后端不重发 session_created，localAbort 不会经 session_created 写入
        // streamRegistry。此处同步登记，使 isSessionRunning 在「澄清/工具执行中」
        // 能读到未中断 abort，拦截重复发送（否则工具执行中仍可发送消息）。
        getStreamState(sessionId).abort = localAbort
      }
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
        signal: localAbort.signal,
      })

      // 409 session_busy：后端检测到该会话已有活跃任务（delta spec Task 6.2）
      if (!resp.ok) {
        if (resp.status === 409) {
          try {
            const errData = await resp.json()
            setWarningMessage(errData.message || '该会话正在生成中，可停止后再发')
          } catch {
            setWarningMessage('该会话正在生成中，可停止后再发')
          }
          setTimeout(() => setWarningMessage(null), 3000)
        }
        return
      }

      const reader = resp.body?.getReader()
      if (!reader) return

      sseDebug('reader_start', { source: 'startAnalysis', session: activeSessionId, view: currentSessionIdRef.current })
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

            // abort 后跳过事件处理：disconnectSubscription 后 buffer 中残留的事件
            // 可能仍被读取，此时 streamingSessionIdRef 可能已被其他会话覆盖，
            // 隔离检查会失效导致事件更新到错误消息（症状：上海天气输出覆盖沈阳天气）
            if (localAbort.signal.aborted) {
              sseDebug('reader_abort', { source: 'startAnalysis', session: activeSessionId, eventType: event.type, seq: event.seq })
              break
            }

            // seq 去重：跳过 seq <= lastSeq 的旧事件
            if (activeSessionId) {
              const seq = event.seq
              if (seq !== undefined) {
                const ss = getStreamState(activeSessionId)
                if (seq <= ss.lastSeq) {
                  sseDebug('seq_skip', { source: 'startAnalysis', session: activeSessionId, seq, lastSeq: ss.lastSeq, eventType: event.type })
                  continue
                }
                ss.lastSeq = seq
              }
            }

            if (event.type === 'session_created') {
              activeSessionId = event.session_id
              streamingSessionIdRef.current = event.session_id
              setAndPersistSession(event.session_id)
              // 同步更新 ref：setAndPersistSession 只触发 React setState，
              // currentSessionIdRef 要等 useEffect 异步同步。在此期间到达的
              // chat_token 会因 activeSessionId !== currentSessionIdRef.current
              // 被会话隔离分支误判为「非当前视图」而丢弃 → 流式文本后半段整段缺失
              // （E2E concurrent-streaming-integrity 复现：seq 9+ 全部被隔离）。
              currentSessionIdRef.current = event.session_id
              // 将 abort controller 存入 per-session 流状态（delta spec Task 5.4）
              const streamState = getStreamState(event.session_id)
              streamState.abort = abortRef.current
              // session_created 的 seq 也计入 lastSeq：去重块在 streamingSessionIdRef
              // 赋值前执行，session_created 自身的 seq 不会被去重块处理，此处补推，
              // 避免 lastSeq 比实际已处理 seq 少 1（resumeStream 时 after_seq 偏小重放）
              const scSeq = event.seq
              if (scSeq !== undefined && scSeq > streamState.lastSeq) {
                streamState.lastSeq = scSeq
              }
              loadSessions()
              continue
            }

            // 会话隔离：如果当前视图不是 SSE 流的会话，事件存入缓冲区
            // 切回原会话时 replayBufferedEvents() 回放，确保状态转换（搜索结果、管线创建等）不丢失。
            // 纯增量内容事件（chat_token, thinking_token, report_chunk）不缓冲——这些在切回时从后端重建。
            if (activeSessionId && activeSessionId !== currentSessionIdRef.current) {
              if (event.type === 'chat_token' || event.type === 'thinking_token') {
                sseDebug('isolate', { source: 'startAnalysis', session: activeSessionId, view: currentSessionIdRef.current, eventType: event.type, seq: event.seq, token: (event.token || '').slice(0, 20) })
              }
              const skipTypes = new Set(['chat_token', 'thinking_token', 'report_chunk', 'report_ready'])
              if (!skipTypes.has(event.type)) {
                bufferedSseEventsRef.current.push(event)
              }
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
              pipelineMsgIdRef.current = pipelineMsg.id
              pipelineMsgRef.current = pipelineMsg
              commitMessages(prev => [...prev, pipelineMsg])
              continue
            }

            if (event.type === 'chat_token') {
              // Agent 的文本回复（澄清/追问）
              sseDebug('chat_token', { source: 'startAnalysis', session: activeSessionId, msgId: assistantMsgIdRef.current, seq: event.seq, token: (event.token || '').slice(0, 30) })
              if (!assistantMsgIdRef.current) {
                const newAssistantId = genId()
                assistantMsgIdRef.current = newAssistantId
                ownAssistantMsgId = newAssistantId
                commitMessages(prev => [...prev, {
                  id: newAssistantId,
                  type: 'chat',
                  content: '',
                  chatResponse: event.token,
                  streaming: true,
                }])
              } else {
                ownAssistantMsgId = assistantMsgIdRef.current
                // 复用 applyChatStreamEvent：累加 chatResponse 同时收口末尾 thinking item，
                // 避免思考横幅在 agent 回复期间持续显示"思考中"（与 quickChat 路径行为一致）
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? applyChatStreamEvent(m, event) : m
                ))
              }
              continue
            }

            if (event.type === 'chat_done') {
              // 对话流结束：置 streaming=false 并收口所有 thinking item（与 quickChat 对齐）。
              // 缺此分支时深度模式的 chat_done 被静默丢弃，游标依赖 done 终态事件，
              // 后端终态被吞时游标永久卡死（fix-terminal-event-dedup-scope D2）
              if (assistantMsgIdRef.current) {
                handleChatStreamEvent(event, assistantMsgIdRef.current)
              }
              continue
            }

            if (event.type === 'awaiting_input') {
              setAppState('clarifying')
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
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
              // 按事件归属路由（delta spec: fix-stream-event-routing）：
              // 仅管线节点思考（携带 node 字段）进管线 UI；
              // 澄清/解析阶段思考（不带 node）进对话流，即使管线消息已存在。
              if (event.node) {
                handleSSEEvent(event, pipelineMsgRef.current || ensurePipelineMsg('深度分析进行中...'))
              } else {
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'thinking_replace') {
              // 替换已流式输出的思考内容（DSML 清理等后处理）。
              // 作用于对话流末尾 thinking item，始终路由到对话流，不因管线消息存在而丢弃。
              handleChatStreamEvent(event, ensureAssistantMsg())
              continue
            }

            if (event.type === 'thinking_to_answer') {
              // 文本已作为 thinking_token 逐 token 流式输出，流末判定为最终回答。
              // 作用于对话流，始终路由，不因管线消息存在而丢弃。
              handleChatStreamEvent(event, ensureAssistantMsg())
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

            if (event.type === 'interrupted') {
              // 中断终态事件：清除 streaming 状态，回到可追问态（delta spec Task 5.5）
              const finishedSessionId = streamingSessionIdRef.current
              streamingSessionIdRef.current = null
              abortRef.current = null
              if (finishedSessionId) {
                sessionCacheRef.current.delete(finishedSessionId)
              }
              handleStreamTerminal(finishedSessionId)
              setAppState('clarifying')
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              if (pipelineMsgRef.current) {
                updateMessage(pipelineMsgIdRef.current || pipelineMsgRef.current.id, { content: '输出已中断，可追问继续' })
              }
              continue
            }

            if (event.type === 'done') {
              // 流正常结束：清理 SSE 会话标记
              const finishedSessionId = streamingSessionIdRef.current
              streamingSessionIdRef.current = null
              abortRef.current = null
              // 收口 pipelineMsgRef（delta spec: fix-stream-event-routing）
              pipelineMsgRef.current = null
              // agent 已完成，数据已持久化到后端，清除前端快照缓存
              if (finishedSessionId) {
                sessionCacheRef.current.delete(finishedSessionId)
              }
              handleStreamTerminal(finishedSessionId)
              // 流正常结束
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              continue
            }

            if (event.type === 'error') {
              // error 终态事件：与 interrupted 对齐清理，避免 isSessionRunning 误判
              const finishedSessionId = streamingSessionIdRef.current
              streamingSessionIdRef.current = null
              abortRef.current = null
              if (finishedSessionId) {
                sessionCacheRef.current.delete(finishedSessionId)
              }
              handleStreamTerminal(finishedSessionId)
              setAppState('clarifying')
              if (pipelineMsgRef.current) {
                handleSSEEvent(event, pipelineMsgRef.current)
              } else {
                commitMessages(prev => [...prev, {
                  id: genId(),
                  type: 'error',
                  content: `错误: ${event.message}`,
                }])
              }
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              continue
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
      // 流结束但未收到终态事件：清理本地状态（防御性，避免 isSessionRunning 误判）
      sseDebug('reader_exit', { source: 'startAnalysis', session: activeSessionId, reason: 'stream_end', view: currentSessionIdRef.current })
      if (activeSessionId) {
        // 仅当全局 ref 仍指向本次会话时才清理，避免误清并发会话的状态
        if (streamingSessionIdRef.current === activeSessionId) {
          streamingSessionIdRef.current = null
          abortRef.current = null
        }
        handleStreamTerminal(activeSessionId)
      }
      // 兜底清除游标：流已结束，助手消息不应再显示流式转圈
      // （游标不依赖单一终态事件，fix-terminal-event-dedup-scope D3）
      // 只清理本 reader 自己的消息：并发会话下全局 ref 可能已指向别的会话，
      // 直接用它会把对方正在流式的消息误置 streaming:false → 对方文本后半段丢失。
      const clearId = msgIdToClearOnReaderExit(ownAssistantMsgId, assistantMsgIdRef.current)
      if (clearId) {
        commitMessages(prev => prev.map(m =>
          m.id === clearId ? { ...m, streaming: false } : m
        ))
      }
    } catch (e) {
      sseDebug('reader_exit', { source: 'startAnalysis', session: activeSessionId, reason: e instanceof Error && e.name === 'AbortError' ? 'abort' : 'error', view: currentSessionIdRef.current })
      // 清理 SSE 会话标记：仅当全局 ref 仍指向本次会话时才清理
      if (streamingSessionIdRef.current === activeSessionId) {
        streamingSessionIdRef.current = null
        abortRef.current = null
      }
      // 切换会话/新建分析主动中断，不是错误，静默退出
      // （不清 streaming：消息属被切走的会话视图，由会话恢复逻辑接管）
      if (e instanceof Error && e.name === 'AbortError') return
      handleStreamTerminal(activeSessionId)
      console.error('SSE error:', e)
      commitMessages(prev => [...prev, {
        id: genId(),
        type: 'error',
        content: `连接错误: ${e instanceof Error ? e.message : 'Unknown'}`,
      }])
      // 兜底清除游标：连接异常中断，助手消息不应再显示流式转圈
      // 只清理本 reader 自己的消息（见 stream_end 分支同款注释）
      const errClearId = msgIdToClearOnReaderExit(ownAssistantMsgId, assistantMsgIdRef.current)
      if (errClearId) {
        commitMessages(prev => prev.map(m =>
          m.id === errClearId ? { ...m, streaming: false } : m
        ))
      }
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
          commitMessages(prev => [...prev, reportMsg])
        } else {
          const id = streamingReportRef.current.id
          const newText = (streamingReportRef.current.reportMarkdown || '') + event.text
          streamingReportRef.current = { ...streamingReportRef.current, reportMarkdown: newText }
          commitMessages(prev => prev.map(m => m.id === id ? { ...m, reportMarkdown: newText } : m))
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
          commitMessages(prev => [...prev, reportMsg])
        }
        setAppState('report')
        setAndPersistSession(event.session_id)
        loadSessions()
        // 管线完成：收口 pipelineMsgRef（delta spec: fix-stream-event-routing），
        // 避免后续轮次澄清思考被路由到已完成的管线消息。保留 pipelineMsg 展示，仅清 ref。
        pipelineMsgRef.current = null

        // Add completion system message
        const completionMsg: UIMessage = {
          id: genId(),
          type: 'system',
          content: `分析完成 · 耗时 ${Math.round(event.duration_ms / 1000)} 秒`,
        }
        commitMessages(prev => [...prev, completionMsg])
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
        commitMessages(prev => prev.map(m => (m.id === chatId ? applyChatStreamEvent(m, event) : m)))
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
    commitMessages(prev => prev.map(m => {
      if (m.id !== id) return m
      const updated = { ...m, ...updates }
      if (pipelineMsgRef.current?.id === id) {
        pipelineMsgRef.current = updated
      }
      return updated
    }))
  }

  // 回放缓冲的 SSE 事件：会话切换期间被跳过的事件存入缓冲区，
  // 切回时逐条回放，确保状态转换（搜索结果、管线创建、节点完成等）不丢失。
  const replayBufferedEvents = useCallback(() => {
    const events = bufferedSseEventsRef.current
    if (!events.length) return

    for (const event of events) {
      // 跳过已处理的事件类型
      if (event.type === 'session_created') continue

      // 管线创建/状态事件
      if (event.type === 'analysis_start') {
        setAppState('analyzing')
        if (!pipelineMsgRef.current) {
          const pm: UIMessage = {
            id: genId(),
            type: 'pipeline',
            content: `开始分析 ${event.stock_name} (${event.stock_code})`,
            completedNodes: [],
            currentNode: '',
            nodeOutputs: {},
            progress: 0,
            startedAt: Date.now(),
          }
          pipelineMsgIdRef.current = pm.id
          pipelineMsgRef.current = pm
          commitMessages(prev => [...prev, pm])
        } else {
          handleSSEEvent(event, pipelineMsgRef.current)
        }
        continue
      }

      // 管线节点/进度事件
      if (event.type === 'parsing' || event.type === 'resolved' ||
          event.type === 'node_start' || event.type === 'node_timing' || event.type === 'node_complete') {
        if (!pipelineMsgRef.current) {
          const pm: UIMessage = {
            id: genId(),
            type: 'pipeline',
            content: '深度分析进行中...',
            completedNodes: [],
            currentNode: '',
            nodeOutputs: {},
            progress: 0,
            startedAt: Date.now(),
          }
          pipelineMsgIdRef.current = pm.id
          pipelineMsgRef.current = pm
          commitMessages(prev => [...prev, pm])
        }
        handleSSEEvent(event, pipelineMsgRef.current)
        continue
      }

      // 报告流事件
      if (event.type === 'report_chunk' || event.type === 'report_ready') {
        if (!pipelineMsgRef.current) {
          const pm: UIMessage = {
            id: genId(),
            type: 'pipeline',
            content: '',
            completedNodes: [],
            currentNode: '',
            nodeOutputs: {},
            progress: 0,
            startedAt: Date.now(),
          }
          pipelineMsgIdRef.current = pm.id
          pipelineMsgRef.current = pm
          commitMessages(prev => [...prev, pm])
        }
        handleSSEEvent(event, pipelineMsgRef.current)
        continue
      }

      // 对话流事件：tool_call/tool_result/search_start/search_result 等
      if (event.type === 'tool_call') {
        if (event.name === 'run_deep_analysis') {
          // 触发管线创建
          if (!pipelineMsgRef.current) {
            const pm: UIMessage = {
              id: genId(),
              type: 'pipeline',
              content: '开始深度分析...',
              completedNodes: [],
              currentNode: '',
              nodeOutputs: {},
              progress: 0,
              startedAt: Date.now(),
            }
            pipelineMsgIdRef.current = pm.id
            pipelineMsgRef.current = pm
            commitMessages(prev => [...prev, pm])
          }
        } else {
          // 搜索类工具调用 → 对话流
          if (!assistantMsgIdRef.current) {
            const newId = genId()
            assistantMsgIdRef.current = newId
            commitMessages(prev => [...prev, {
              id: newId,
              type: 'chat',
              content: '',
              chatResponse: '',
              streaming: true,
            }])
          }
          handleChatStreamEvent(event, assistantMsgIdRef.current)
        }
        continue
      }

      if (event.type === 'tool_result') {
        if (event.name === 'run_deep_analysis') {
          // 忽略：管线已创建
        } else {
          if (!assistantMsgIdRef.current) {
            const newId = genId()
            assistantMsgIdRef.current = newId
            commitMessages(prev => [...prev, {
              id: newId,
              type: 'chat',
              content: '',
              chatResponse: '',
              streaming: true,
            }])
          }
          handleChatStreamEvent(event, assistantMsgIdRef.current)
        }
        continue
      }

      if (event.type === 'search_start' || event.type === 'search_result' || event.type === 'search_error') {
        if (!assistantMsgIdRef.current) {
          const newId = genId()
          assistantMsgIdRef.current = newId
          commitMessages(prev => [...prev, {
            id: newId,
            type: 'chat',
            content: '',
            chatResponse: '',
            streaming: true,
          }])
        }
        handleChatStreamEvent(event, assistantMsgIdRef.current)
        continue
      }

      if (event.type === 'stock_resolved') {
        if (pipelineMsgRef.current) {
          updateMessage(pipelineMsgRef.current.id, { content: `已识别：${event.stock_name} (${event.stock_code})` })
        } else if (assistantMsgIdRef.current) {
          handleChatStreamEvent(
            { type: 'tool_result', name: 'search_stock', result: `已识别：${event.stock_name} (${event.stock_code})`, timestamp: '' } as SSEEvent,
            assistantMsgIdRef.current,
          )
        }
        continue
      }

      if (event.type === 'awaiting_input') {
        setAppState('clarifying')
        if (assistantMsgIdRef.current) {
          commitMessages(prev => prev.map(m =>
            m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
          ))
        }
        continue
      }

      if (event.type === 'interrupted') {
        // 中断终态事件：清除 streaming 状态（delta spec Task 5.5）
        const finishedSessionId = streamingSessionIdRef.current
        streamingSessionIdRef.current = null
        abortRef.current = null
        if (finishedSessionId) {
          sessionCacheRef.current.delete(finishedSessionId)
        }
        handleStreamTerminal(finishedSessionId)
        setAppState('clarifying')
        if (assistantMsgIdRef.current) {
          commitMessages(prev => prev.map(m =>
            m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
          ))
        }
        if (pipelineMsgRef.current) {
          updateMessage(pipelineMsgRef.current.id, { content: '输出已中断，可追问继续' })
        }
        continue
      }

      if (event.type === 'done') {
        const finishedSessionId = streamingSessionIdRef.current
        streamingSessionIdRef.current = null
        abortRef.current = null
        // agent 已完成，数据已持久化到后端，清除前端快照缓存
        if (finishedSessionId) {
          sessionCacheRef.current.delete(finishedSessionId)
        }
        handleStreamTerminal(finishedSessionId)
        if (assistantMsgIdRef.current) {
          commitMessages(prev => prev.map(m =>
            m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
          ))
        }
        continue
      }

      if (event.type === 'error') {
        // error 终态事件：与 done 对齐清理，避免 isSessionRunning 误判
        const finishedSessionId = streamingSessionIdRef.current
        streamingSessionIdRef.current = null
        abortRef.current = null
        if (finishedSessionId) {
          sessionCacheRef.current.delete(finishedSessionId)
        }
        handleStreamTerminal(finishedSessionId)
        setAppState('clarifying')
        if (pipelineMsgRef.current) {
          handleSSEEvent(event, pipelineMsgRef.current)
        } else {
          commitMessages(prev => [...prev, {
            id: genId(),
            type: 'error',
            content: `错误: ${event.message}`,
          }])
        }
        if (assistantMsgIdRef.current) {
          commitMessages(prev => prev.map(m =>
            m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
          ))
        }
        continue
      }

      // thinking_token / thinking_replace / thinking_to_answer / chat_token 等
      // 纯增量内容事件已在缓冲区过滤（skipTypes），此处无需处理
    }

    // 清空缓冲区
    bufferedSseEventsRef.current = []
  }, [handleStreamTerminal])

  // ── 恢复事件流（delta spec Task 5.2）──
  // 切回 running/clarifying 会话时经 GET /api/sessions/{id}/stream 恢复事件流。
  // 重放事件与实时事件经同一 handleSSEEvent/handleChatStreamEvent 路径消费，
  // session_created/analysis_start 等做幂等处理。
  // skipIncremental=true 时跳过增量内容事件（chat_token/thinking_token 等），
  // 用于已从缓存恢复内容的场景，避免重放导致重复。
  const resumeStream = async (sessionId: string, skipIncremental: boolean) => {
    const state = getStreamState(sessionId)
    // 并发订阅隔离：同一会话同一时刻只允许一条活跃订阅消费 state.lastSeq。
    // 否则两条订阅（实时流 + resume）各自字节流进度不同步，会把对方尚未处理的
    // 事件误判为「旧事件」丢弃（seq <= lastSeq），导致随机丢整个 token —— 症状为
    // thinking/chat 流式文本概率性错乱（如「中环海陆（301040）」变「中陆301040」）。
    if (state.abort && !state.abort.signal.aborted) {
      state.abort.abort()
    }
    // 全局 single-reader 不变量：abort 其他 session 残留的 reader。
    // selectSession 虽在调用 resumeStream 前执行 disconnectSubscription，
    // 但 abort 是异步的——旧 reader 的 await reader.read() 不会立即返回。
    // 若不先 abort 全局 abortRef，直接覆盖会使旧 reader 的 controller 丢失引用，
    // 旧 reader 继续运行并写全局 assistantMsgIdRef → 与新 reader 串字/丢内容。
    if (abortRef.current && !abortRef.current.signal.aborted) {
      sseDebug('global_abort', { source: 'resumeStream', session: sessionId, aborting: streamingSessionIdRef.current })
    }
    const abortCtrl = ensureSingleReader(abortRef.current, new AbortController())
    abortRef.current = abortCtrl
    state.abort = abortCtrl
    streamingSessionIdRef.current = sessionId

    // 幂等创建管线消息（已存在则复用）
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
      pipelineMsgIdRef.current = pm.id
      pipelineMsgRef.current = pm
      commitMessages(prev => [...prev, pm])
      setAppState('analyzing')
      return pm
    }

    // 幂等创建助手消息（已存在则复用）
    const ensureAssistantMsg = (): string => {
      if (assistantMsgIdRef.current) return assistantMsgIdRef.current
      const newId = genId()
      assistantMsgIdRef.current = newId
      commitMessages(prev => [...prev, {
        id: newId,
        type: 'chat',
        content: '',
        chatResponse: '',
        streaming: true,
      }])
      return newId
    }

    try {
      sseDebug('resume_start', { session: sessionId, afterSeq: state.lastSeq, skipIncremental, view: currentSessionIdRef.current })
      const resp = await fetch(`/api/sessions/${sessionId}/stream?after_seq=${state.lastSeq}`, {
        signal: abortCtrl.signal,
      })
      if (!resp.ok) return
      const reader = resp.body?.getReader()
      if (!reader) return

      sseDebug('reader_start', { source: 'resumeStream', session: sessionId, view: currentSessionIdRef.current })
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

            // abort 后跳过事件处理（与 startAnalysis 一致）
            if (abortCtrl.signal.aborted) {
              sseDebug('reader_abort', { source: 'resumeStream', session: sessionId, eventType: event.type, seq: event.seq })
              break
            }

            // seq 去重：跳过 seq <= lastSeq 的旧事件
            const seq = event.seq
            if (seq !== undefined) {
              if (seq <= state.lastSeq) {
                sseDebug('seq_skip', { source: 'resumeStream', session: sessionId, seq, lastSeq: state.lastSeq, eventType: event.type })
                continue
              }
              state.lastSeq = seq
            }

            // 幂等：session_created 对已激活会话为 no-op
            if (event.type === 'session_created') continue

            // 中断终态事件：清除 streaming 状态，回到可操作态
            if (event.type === 'interrupted') {
              streamingSessionIdRef.current = null
              abortRef.current = null
              handleStreamTerminal(sessionId)
              setAppState('clarifying')
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              if (pipelineMsgRef.current) {
                updateMessage(pipelineMsgRef.current.id, { content: '输出已中断，可追问继续' })
              }
              continue
            }

            // 会话隔离：非当前视图事件存入缓冲区
            // 用局部 sessionId 而非全局 streamingSessionIdRef.current——后者在并发
            // resumeStream 场景下会被其他 reader 覆盖，导致本 reader 的事件被误隔离丢弃。
            if (!isCurrentViewEvent(sessionId, currentSessionIdRef.current)) {
              if (event.type === 'chat_token' || event.type === 'thinking_token') {
                sseDebug('isolate', { source: 'resumeStream', session: sessionId, view: currentSessionIdRef.current, eventType: event.type, seq: event.seq, token: (event.token || '').slice(0, 20) })
              }
              const skipTypes = new Set(['chat_token', 'thinking_token', 'report_chunk', 'report_ready'])
              if (!skipTypes.has(event.type)) {
                bufferedSseEventsRef.current.push(event)
              }
              continue
            }

            // 跳过增量内容事件（已从缓存恢复，避免重放重复）
            if (skipIncremental) {
              const incrementalTypes = new Set(['chat_token', 'thinking_token', 'thinking_replace', 'thinking_to_answer', 'report_chunk'])
              if (incrementalTypes.has(event.type)) {
                sseDebug('skip_incremental', { source: 'resumeStream', session: sessionId, eventType: event.type, seq: event.seq })
                continue
              }
            }

            // 以下事件路由与 startAnalysis 保持一致

            if (event.type === 'analysis_start') {
              setAppState('analyzing')
              // 幂等：已存在管线消息则不重复创建
              if (!pipelineMsgRef.current) {
                const pm: UIMessage = {
                  id: genId(),
                  type: 'pipeline',
                  content: `开始分析 ${event.stock_name} (${event.stock_code})`,
                  completedNodes: [],
                  currentNode: '',
                  nodeOutputs: {},
                  progress: 0,
                }
                pipelineMsgIdRef.current = pm.id
                pipelineMsgRef.current = pm
                commitMessages(prev => [...prev, pm])
              }
              continue
            }

            if (event.type === 'chat_token') {
              if (!assistantMsgIdRef.current) {
                const newAssistantId = genId()
                assistantMsgIdRef.current = newAssistantId
                commitMessages(prev => [...prev, {
                  id: newAssistantId,
                  type: 'chat',
                  content: '',
                  chatResponse: event.token,
                  streaming: true,
                }])
              } else {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? applyChatStreamEvent(m, event) : m
                ))
              }
              continue
            }

            if (event.type === 'awaiting_input') {
              setAppState('clarifying')
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              continue
            }

            if (event.type === 'tool_call') {
              if (event.name === 'run_deep_analysis') {
                ensurePipelineMsg('开始深度分析...')
              } else {
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'search_start' || event.type === 'search_result' || event.type === 'search_error') {
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
                handleChatStreamEvent(
                  { type: 'tool_result', name: 'search_stock', result: `已识别：${event.stock_name} (${event.stock_code})`, timestamp: '' } as SSEEvent,
                  ensureAssistantMsg(),
                )
              }
              continue
            }

            if (event.type === 'thinking_token') {
              // 按事件归属路由（delta spec: fix-stream-event-routing）：
              // 带 node 进管线 UI，不带 node 进对话流（与 startAnalysis 一致）
              if (event.node) {
                handleSSEEvent(event, pipelineMsgRef.current || ensurePipelineMsg('深度分析进行中...'))
              } else {
                handleChatStreamEvent(event, ensureAssistantMsg())
              }
              continue
            }

            if (event.type === 'thinking_replace') {
              // 作用于对话流末尾 thinking item，始终路由到对话流
              handleChatStreamEvent(event, ensureAssistantMsg())
              continue
            }

            if (event.type === 'thinking_to_answer') {
              // 作用于对话流，始终路由
              handleChatStreamEvent(event, ensureAssistantMsg())
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
              const finishedSessionId = streamingSessionIdRef.current
              streamingSessionIdRef.current = null
              abortRef.current = null
              // 收口 pipelineMsgRef（delta spec: fix-stream-event-routing）
              pipelineMsgRef.current = null
              if (finishedSessionId) {
                sessionCacheRef.current.delete(finishedSessionId)
              }
              handleStreamTerminal(finishedSessionId)
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              continue
            }

            if (event.type === 'error') {
              // error 终态事件：与 done 对齐清理，避免 isSessionRunning 误判
              const finishedSessionId = streamingSessionIdRef.current
              streamingSessionIdRef.current = null
              abortRef.current = null
              if (finishedSessionId) {
                sessionCacheRef.current.delete(finishedSessionId)
              }
              handleStreamTerminal(finishedSessionId)
              setAppState('clarifying')
              if (pipelineMsgRef.current) {
                handleSSEEvent(event, pipelineMsgRef.current)
              } else {
                commitMessages(prev => [...prev, {
                  id: genId(),
                  type: 'error',
                  content: `错误: ${event.message}`,
                }])
              }
              if (assistantMsgIdRef.current) {
                commitMessages(prev => prev.map(m =>
                  m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
                ))
              }
              continue
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
      // 流结束但未收到终态事件：清理本地状态（防御性，避免 isSessionRunning 误判）
      if (streamingSessionIdRef.current) {
        const finishedSessionId = streamingSessionIdRef.current
        streamingSessionIdRef.current = null
        abortRef.current = null
        handleStreamTerminal(finishedSessionId)
      }
    } catch (e) {
      const failedSessionId = streamingSessionIdRef.current
      streamingSessionIdRef.current = null
      abortRef.current = null
      if (e instanceof Error && e.name === 'AbortError') return
      handleStreamTerminal(failedSessionId)
      console.error('Resume stream error:', e)
    }
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
          // 尝试最后一次获取会话状态，检查是否有 failure_reason
          try {
            const finalResp = await fetch(`/api/sessions/${currentSessionId}`)
            if (finalResp.ok) {
              const finalData: SessionDetail = await finalResp.json()
              if (finalData.failure_reason) {
                updateMessage(pm.id, { content: `分析失败：${finalData.failure_reason}` })
                setAppState('clarifying')
                return
              }
            }
          } catch {
            // 忽略，回退到默认提示
          }
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
          // 后台管线完成：走 selectSession 完整重建（复用锚点定位、agentTimeline
          // 恢复、pipeline_timelines 结构化时序等逻辑，避免报告插入位置错误或时序丢失）。
          // clearInterval 先停止轮询，selectSession 内部 setCurrentSessionId 触发
          // effect 重跑时 timer 已清理，不会递归。
          clearInterval(timer)
          await selectSession(currentSessionId)
        } else if (data.status === 'failed') {
          // 管线失败：展示中断原因，停止轮询
          clearInterval(timer)
          const pm = pipelineMsgRef.current
          if (pm) {
            const reason = data.failure_reason || '管线执行失败'
            updateMessage(pm.id, { content: `分析失败：${reason}` })
          }
          setAppState('clarifying') // 回到可操作状态
        }
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
    // 拦截：当前会话正在运行时不允许提交新消息（delta spec Task 6.2）
    if (currentSessionId && isSessionRunning(currentSessionId)) {
      setWarningMessage('该会话正在生成中，可停止后再发')
      setTimeout(() => setWarningMessage(null), 3000)
      return
    }

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
    commitMessages(prev => [...prev, userMsg])

    const chatId = genId()
    const chatMsg: UIMessage = {
      id: chatId,
      type: 'chat',
      content: '',
      chatResponse: '',
      streaming: true,
    }
    commitMessages(prev => [...prev, chatMsg])
    // 同步设置 assistantMsgIdRef：quickChat 的 SSE 循环用局部 chatId 更新消息，
    // 但快照保存/resumeStream 依赖 assistantMsgIdRef。若不设置，切换会话后
    // 快照保存 null，切回时 resumeStream 创建新消息 ID，导致思考内容丢失
    // （症状：切换会话后思考 UI 消失）
    assistantMsgIdRef.current = chatId

    // 在 try 外声明：catch 块也需要访问（终止清理）
    let activeSessionId = currentSessionId || ''

    try {
      // 并发订阅隔离：先 abort 该会话已有的活跃订阅（与 resumeStream/startAnalysis 一致）。
      if (currentSessionId) {
        const existingState = getStreamState(currentSessionId)
        if (existingState.abort && !existingState.abort.signal.aborted) {
          existingState.abort.abort()
        }
      }
      // 全局 single-reader 不变量：abort 任何残留 reader（与 resumeStream 一致）。
      if (abortRef.current && !abortRef.current.signal.aborted) {
        sseDebug('global_abort', { source: 'quickChat', session: currentSessionId, aborting: streamingSessionIdRef.current })
      }
      const localAbort = ensureSingleReader(abortRef.current, new AbortController())
      abortRef.current = localAbort
      // 提前激活 seq 去重：fetch 前设置 streamingSessionIdRef，使 SSE 循环的
      // 去重块（if (streamingSessionIdRef.current)）从第一个事件起生效，
      // 不依赖后端是否下发 session_created（追问场景后端可能不重发）。
      // 不重置 lastSeq：保留切换前已消费的 seq，避免重放
      if (currentSessionId) {
        streamingSessionIdRef.current = currentSessionId
        // 追问路径后端不重发 session_created，同步登记 abort 使 isSessionRunning 生效
        getStreamState(currentSessionId).abort = localAbort
      }
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: currentSessionId,
          user_id: getUserId(),
          api_key: apiKey,
        }),
        signal: localAbort.signal,
      })

      // 409 session_busy：后端检测到该会话已有活跃任务（delta spec Task 6.2）
      if (!resp.ok) {
        if (resp.status === 409) {
          try {
            const errData = await resp.json()
            setWarningMessage(errData.message || '该会话正在生成中，可停止后再发')
          } catch {
            setWarningMessage('该会话正在生成中，可停止后再发')
          }
          setTimeout(() => setWarningMessage(null), 3000)
        }
        return
      }

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

            // abort 后跳过事件处理（与 startAnalysis 一致）
            if (localAbort.signal.aborted) break

            // seq 去重：跳过 seq <= lastSeq 的旧事件
            if (activeSessionId) {
              const seq = event.seq
              if (seq !== undefined) {
                const ss = getStreamState(activeSessionId)
                if (seq <= ss.lastSeq) continue
                ss.lastSeq = seq
              }
            }

            // error 终态事件：先清理 streaming 状态（与 interrupted 对齐），
            // 再由 handleChatStreamEvent 写入 agentTimeline 渲染错误
            if (event.type === 'error') {
              if (streamingSessionIdRef.current === activeSessionId) {
                streamingSessionIdRef.current = null
                abortRef.current = null
              }
              if (activeSessionId) {
                sessionCacheRef.current.delete(activeSessionId)
              }
              handleStreamTerminal(activeSessionId)
              setAppState('clarifying')
              // 仍让 handleChatStreamEvent 处理渲染（写入 agentTimeline）
              handleChatStreamEvent(event, chatId)
              commitMessages(prev => prev.map(m =>
                m.id === chatId ? { ...m, streaming: false } : m
              ))
              continue
            }

            // 对话流公共事件（thinking/tool/chat/error）统一走共享处理
            if (handleChatStreamEvent(event, chatId)) {
              continue
            }
            // search_* 已由共享分支处理；此处处理 session_created/terminal 事件
            if (event.type === 'session_created') {
              activeSessionId = event.session_id
              streamingSessionIdRef.current = event.session_id
              setAndPersistSession(event.session_id)
              // 同步更新 ref（与 startAnalysis 一致）：避免 useEffect 同步前到达的
              // 增量事件被会话隔离分支误判丢弃，导致流式文本缺失。
              currentSessionIdRef.current = event.session_id
              // 将 abort controller 存入 per-session 流状态（delta spec Task 5.4）
              const streamState = getStreamState(event.session_id)
              streamState.abort = abortRef.current
              // session_created 的 seq 计入 lastSeq（与 startAnalysis 一致）
              const scSeq = event.seq
              if (scSeq !== undefined && scSeq > streamState.lastSeq) {
                streamState.lastSeq = scSeq
              }
              loadSessions()
              continue
            }

            // 中断终态事件：清除 streaming 状态（delta spec Task 5.5）
            if (event.type === 'interrupted') {
              if (streamingSessionIdRef.current === activeSessionId) {
                streamingSessionIdRef.current = null
                abortRef.current = null
              }
              if (activeSessionId) {
                sessionCacheRef.current.delete(activeSessionId)
              }
              handleStreamTerminal(activeSessionId)
              setAppState('clarifying')
              commitMessages(prev => prev.map(m =>
                m.id === chatId ? { ...m, streaming: false } : m
              ))
              continue
            }

            // 流正常结束：清理 SSE 会话标记
            if (event.type === 'done') {
              if (streamingSessionIdRef.current === activeSessionId) {
                streamingSessionIdRef.current = null
                abortRef.current = null
              }
              if (activeSessionId) {
                sessionCacheRef.current.delete(activeSessionId)
              }
              handleStreamTerminal(activeSessionId)
              commitMessages(prev => prev.map(m =>
                m.id === chatId ? { ...m, streaming: false } : m
              ))
              continue
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
      // 流结束但未收到终态事件：清理本地状态（防御性，避免 isSessionRunning 误判）
      if (activeSessionId) {
        if (streamingSessionIdRef.current === activeSessionId) {
          streamingSessionIdRef.current = null
          abortRef.current = null
        }
        handleStreamTerminal(activeSessionId)
      }
    } catch (e) {
      if (streamingSessionIdRef.current === activeSessionId) {
        streamingSessionIdRef.current = null
        abortRef.current = null
      }
      if (e instanceof Error && e.name === 'AbortError') return
      handleStreamTerminal(activeSessionId)
      commitMessages(prev => prev.map(m =>
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

  // 计算正在运行的会话 ID 集合（status=running 或本地有活跃 abort controller）
  const runningSessionIds = new Set<string>()
  for (const s of sessions) {
    if (s.status === 'running') runningSessionIds.add(s.session_id)
  }
  streamRegistryRef.current.forEach((state, sessionId) => {
    if (state.abort && !state.abort.signal.aborted) {
      runningSessionIds.add(sessionId)
    }
  })

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
        runningSessionIds={runningSessionIds}
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

            {/* 「会话生成中」警告：fixed 顶部 toast，浮于 header(z-50)/输入框(z-40) 之上 */}
            {warningMessage && (
              <div
                className="fixed top-16 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-lg text-xs flex items-center gap-2 shadow-lg"
                style={{ background: 'var(--status-warning-default)', color: 'white' }}
              >
                <i className="fas fa-exclamation-triangle"></i>
                {warningMessage}
              </div>
            )}

            {/* 停止按钮（流式输出时显示） */}
            {(appState === 'analyzing' || messages.some(m => m.streaming)) && (
              <div
                className="fixed right-0 z-40 flex flex-col items-center gap-2 px-4"
                style={{ left: leftInset, bottom: '90px' }}
              >
                {(appState === 'analyzing' || messages.some(m => m.streaming)) && currentSessionId && (
                  <button
                    onClick={stopGeneration}
                    className="px-4 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all hover:opacity-80"
                    style={{ background: 'var(--status-error-default)', color: 'white' }}
                  >
                    <i className="fas fa-stop text-[10px]"></i>
                    停止生成
                  </button>
                )}
              </div>
            )}

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
function Sidebar({ sessions, currentSessionId, onSelect, onDelete, onRename, onNew, isOpen, onToggle, runningSessionIds }: {
  sessions: SessionMeta[]
  currentSessionId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, name: string) => void
  onNew: () => void
  isOpen: boolean
  onToggle: () => void
  runningSessionIds: Set<string>
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
                    className="text-sm truncate flex items-center gap-1.5"
                    style={{ color: 'var(--text-default)' }}
                    onDoubleClick={e => {
                      e.stopPropagation()
                      setEditingId(s.session_id)
                      setEditText(s.display_name)
                    }}
                  >
                    {runningSessionIds.has(s.session_id) && (
                      <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
                    )}
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

  // 流式时自动滚底，但用户手动上拉后不抢占
  const contentScrolledUpRef = useRef(false)
  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    const onScroll = () => {
      const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20
      contentScrolledUpRef.current = !nearBottom
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (expanded && streaming && contentRef.current && !contentScrolledUpRef.current) {
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
