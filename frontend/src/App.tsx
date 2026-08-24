import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { PipelineStep, UIMessage, SessionMeta, SessionDetail, ToolCallEntry, PipelineSnapshot } from './types'
import { ChartsSection } from './Charts'
import { SearchBanner } from './SearchBanner'
import { nodeDisplayName } from './timeline'
import { estimateTotalMs, estimateRemainingMs, formatDurationMs, loadDurations } from './eta'
import { buildLayerTree } from './pipelineTree'
import { PipelineTimeline } from './PipelineTimeline'
import { TimelineRenderer, type TimelineBannerComponents } from './TimelineRenderer'
import { useClickOutside } from './useClickOutside'
import { getStreamStore } from './stores/streamStore'
import { useSessionStream } from './stores/streamStore/useSessionStream'
import {
  loadProfiles,
  saveProfiles,
  addProfile,
  deleteProfile,
  activateProfile,
  getActiveConfig,
  getActiveProfileName,
  buildLlmConfigPayload,
  isDeepSeekModel,
  matchPreset,
  buildModelWithPrefix,
  PROVIDER_PRESETS,
  API_FORM_OPTIONS,
  DEFAULT_API_FORM,
  CUSTOM_PRESET_NAME,
  type LLMConfig,
  type LLMProfile,
  type ProfileStore,
  canEnterMode,
  clearCapability,
  parseCapability,
  type CapabilityMatrix,
} from './llmConfig'

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

// 从 stream.phase 派生视图状态（替代原 appState 的流相关部分）
// 空会话（无消息且无进行中流）显示首页；其余按 phase 映射。
function deriveAppState(
  phase: string,
  currentSessionId: string | null,
  messages: UIMessage[],
  sessions: SessionMeta[],
): 'empty' | 'analyzing' | 'report' | 'clarifying' {
  const running = phase === 'connecting' || phase === 'streaming' || phase === 'resuming'
  if (running && currentSessionId) {
    const session = sessions.find((s) => s.session_id === currentSessionId)
    const isChat = session?.session_type === 'chat'
    // 按会话类型判定视图：chat → 聊天视图（clarifying），analysis → 分析视图（analyzing）。
    // 不依赖 messages 是否已有 pipeline 消息——新架构下刷新恢复的 running 会话在
    // journal replay/轮询创建 pipeline 前 messages 只有 user 消息，但仍是分析视图。
    return isChat ? 'clarifying' : 'analyzing'
  }
  if (!currentSessionId) {
    // 新会话提交后 session_created 未到达：有消息则进入聊天视图
    return messages.length > 0 ? 'clarifying' : 'empty'
  }
  switch (phase) {
    case 'done':
      return 'report'
    case 'awaiting_input':
    case 'interrupted':
    case 'error':
      return 'clarifying'
    default:
      return messages.length > 0 ? 'clarifying' : 'empty'
  }
}

export default function App() {
  // 多配置管理（profiles，delta Decision 10）
  const [profileStore, setProfileStore] = useState<ProfileStore>(() => loadProfiles())
  // 激活配置从 profileStore 派生（替代直接读 fa_llm_config）
  const llmConfig = useMemo(() => getActiveConfig(profileStore), [profileStore])
  // apiKey 由激活 profile 派生（EmptyState/请求拦截保持语义不变）
  const apiKey = llmConfig.apiKey
  // 当前激活 profile 的能力矩阵（probe 事实；null = 未探测 → 门禁放行）
  const capability = llmConfig.capability ?? null
  // 切换激活 profile（LLM 切换下拉框使用）
  const switchProfile = useCallback((id: string) => {
    setProfileStore(prev => {
      const next = activateProfile(prev, id)
      saveProfiles(next)
      return next
    })
  }, [])
  // 保存配置到激活 profile（SettingsModal 确认按钮使用）
  // 无激活 profile 时自动创建「我的配置」profile 并保存（向前兼容：确认即视为显式配置）
  const handleSaveConfig = useCallback((cfg: LLMConfig) => {
    setProfileStore(prev => {
      // 无 profile 时自动创建默认 profile（含配置）
      if (prev.profiles.length === 0) {
        const next = addProfile(prev, '我的配置', clearCapability(cfg))
        saveProfiles(next)
        return next
      }
      // 更新激活 profile 的 config
      const newProfiles = prev.profiles.map(p => {
        if (p.id !== prev.activeId) return p
        // 连接三要素（apiKey/model/baseUrl）任一变更 → 旧 probe 事实失效，清空 capability；
        // 未变更 → 保留 probe 事实（含本次会话内新探测结果）
        const connectionChanged =
          p.config.apiKey !== cfg.apiKey || p.config.model !== cfg.model || p.config.baseUrl !== cfg.baseUrl
        const config = connectionChanged
          ? clearCapability(cfg)
          : { ...cfg, capability: cfg.capability ?? p.config.capability ?? null }
        return { ...p, config }
      })
      const next = { ...prev, profiles: newProfiles }
      saveProfiles(next)
      return next
    })
  }, [])
  // probe 事实落库：连通性测试成功后把 capability 写入激活 profile（无 profile 时不落库，仅在弹窗内展示）
  const handleProbeCapability = useCallback((capability: CapabilityMatrix | null) => {
    setProfileStore(prev => {
      const active = prev.profiles.find(p => p.id === prev.activeId)
      if (!active) return prev
      const newProfiles = prev.profiles.map(p =>
        p.id === prev.activeId ? { ...p, config: { ...p.config, capability } } : p
      )
      const next = { ...prev, profiles: newProfiles }
      saveProfiles(next)
      return next
    })
  }, [])
  // 另存为新 profile（SettingsModal「另存为」按钮使用）
  const handleSaveAsConfig = useCallback((cfg: LLMConfig, name: string) => {
    setProfileStore(prev => {
      const next = addProfile(prev, name, cfg)
      saveProfiles(next)
      return next
    })
  }, [])
  // 删除 profile（SettingsModal 列表删除按钮使用）
  const handleDeleteProfile = useCallback((id: string) => {
    setProfileStore(prev => {
      const next = deleteProfile(prev, id)
      saveProfiles(next)
      return next
    })
  }, [])
  const [showSettings, setShowSettings] = useState(false)
  // 后端默认 LLM 配置（GET /api/llm-config），用作设置面板输入框 placeholder（delta 5.3）
  const [backendDefaults, setBackendDefaults] = useState<{ model: string; baseUrl: string; thinking: string }>({ model: '', baseUrl: '', thinking: 'enabled' })
  useEffect(() => {
    let cancelled = false
    fetch('/api/llm-config')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return
        setBackendDefaults({
          model: typeof data.model === 'string' ? data.model : '',
          baseUrl: typeof data.base_url === 'string' ? data.base_url : '',
          thinking: typeof data.thinking === 'string' ? data.thinking : 'enabled',
        })
      })
      .catch(() => {
        // 后端不可用时静默回退到内置默认 placeholder，不阻塞使用
      })
    return () => { cancelled = true }
  }, [])
  // 轮询起始时间（超时保护基准，cleanup 时重置）
  const pollStartRef = useRef<number | null>(null)

  // Session state
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  // 刷新加载骨架：/api/sessions 首次成功前为 true 取反（侧边栏显示骨架而非闪「暂无历史会话」）
  const [sessionsLoaded, setSessionsLoaded] = useState(false)
  // 刷新恢复指示：有持久化会话且恢复未落定前，主区显示「恢复会话中」而非闪首页空态。
  // 初值直接读 localStorage，避免首帧就闪空态落地。
  const [bootRestoring, setBootRestoring] = useState(() => !!localStorage.getItem('fa_current_session_id'))
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
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mode, setMode] = useState<'quick' | 'deep'>('deep')
  // 临时警告提示（如"该会话正在生成中"）
  const [warningMessage, setWarningMessage] = useState<string | null>(null)
  const showWarning = useCallback((text: string) => {
    setWarningMessage(text)
    setTimeout(() => setWarningMessage(null), 3000)
  }, [])

  // ── StreamStore 集成：流状态唯一事实源 ──
  const store = getStreamStore()
  const stream = useSessionStream(currentSessionId)
  const messages = stream.messages
  const appState = deriveAppState(stream.phase, currentSessionId, messages, sessions)

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

  // store 回调桥接：session_created 绑定视图、终态/报告刷新会话列表
  useEffect(() => {
    store.setCallbacks({
      onSessionCreated: (id) => setAndPersistSession(id),
      onSessionsChanged: () => { void loadSessions() },
    })
  }, [store, setAndPersistSession, loadSessions])

  // Auto-scroll to bottom：仅在用户未手动上拉时自动滚动（避免抢占手动滚动）
  const userScrolledUpRef = useRef(false)
  const scrollTimerRef = useRef<number | null>(null)
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
    // 流式高频更新（chat_token / thinking_token）合并为单一 scroll：clearTimeout
    // 防多个 smooth scroll 叠加导致页面抖动（多思考窗口展开时尤其明显）
    if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current)
    scrollTimerRef.current = window.setTimeout(() => {
      scrollTimerRef.current = null
      if (userScrolledUpRef.current) return
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
    }, 100)
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

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
      // 列表加载成功：侧边栏骨架退场
      setSessionsLoaded(true)
      // 列表加载成功：刷新后自动恢复此前查看的会话（delta spec: restore-session-on-refresh）
      if (!restoredRef.current) {
        restoredRef.current = true
        const persistedId = localStorage.getItem('fa_current_session_id')
        if (persistedId) {
          if (loaded.some(s => s.session_id === persistedId)) {
            // 会话仍存在：复用 selectSession 恢复（含 running 时 SSE 重连）。
            // 恢复落定后退出「恢复会话中」指示；失败也要退场避免卡死。
            const p = selectSessionRef.current?.(persistedId)
            if (p) {
              p.finally(() => { if (!cancelled) setBootRestoring(false) })
            } else {
              setBootRestoring(false)
            }
          } else {
            // 持久化会话已被删除：清除并停留空态首页
            localStorage.removeItem('fa_current_session_id')
            setBootRestoring(false)
          }
        } else {
          // 无持久化会话：本就不在恢复中（防御，初值已为 false）
          setBootRestoring(false)
        }
      }
    }

    loadWithRetry()
    return () => { cancelled = true }
  }, [loadSessions])

  // ── 会话选择与生命周期 ──

  // 切换会话：store 统一管理订阅断开与状态重建
  // live 在途状态直接展示；pending 状态从后端重建并按需 resume 续传。
  // forceRebuild：轮询发现后台任务 completed 时强制从后端重建（拿报告/终态），
  // 跳过 live 短路——resume 把 origin 标为 live，completed 后需重建才有报告。
  const selectSession = async (sessionId: string, forceRebuild = false) => {
    store.switchSession(sessionId)
    setAndPersistSession(sessionId)

    const state = store.getSnapshot(sessionId)
    if (!forceRebuild && state.origin === 'live') {
      // 在途会话：messages 由事件流实时维护，直接展示即可；
      // 若后端任务仍运行但本地无订阅（切换中断/页面刷新的孤立态），补一次 resume 续传
      const stillRunning = state.phase === 'streaming' || state.phase === 'connecting' || state.phase === 'resuming'
      if (stillRunning && !store.hasActiveReader()) {
        void store.resume(sessionId)
      }
      return
    }

    // pending：从后端重建消息（chat_history + 管线快照 + 报告锚点定位）
    const data = await store.loadSession(sessionId)
    if (!data) return
    setMode(data.session_type === 'chat' ? 'quick' : 'deep')
    store.rebuildSession(sessionId, data)
    // running/clarifying 会话恢复事件流（ReAct 路径 status 为 clarifying 但任务可能仍在运行）。
    // 刷新后必须 resume 续传增量事件（thinking_token/chat_token 等）——思考/文本不进入
    // pipeline_snapshot，轮询 effect 只刷新管线快照，不 resume 则新生思考内容停止输出。
    // after_seq 用 rebuild 的 lastSeq：已持久化事件经 chat_history/thinking 重建并被
    // seq 守门去重，仅续传 journal 之后的新事件；无新事件时后端回 204，resume 收敛 idle。
    if (data.status === 'running' || data.status === 'clarifying') {
      void store.resume(sessionId)
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
      // 清理本地流状态（abort 订阅 + 移除会话状态）
      store.dropStream(sessionId)
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      // 同步后端列表（确保顺序/其他字段一致，乐观更新可能遗漏后端副作用）
      loadSessions()
      if (currentSessionId === sessionId) {
        setAndPersistSession(null)
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
    // 断开当前会话的本地 SSE 订阅（不调后端 cancel，后台任务继续运行）
    // delta spec Task 5.3：新建分析仅断开本地订阅
    store.switchSession(null)
    setAndPersistSession(null)
  }

  // 停止当前会话的生成任务（本地 abort + 后端 cancel + 状态收口）
  const stopGeneration = async () => {
    if (!currentSessionId) return
    await store.cancel(currentSessionId)
  }

  // 页面卸载时断开所有本地 SSE 订阅（仅退订，不调后端 cancel）
  useEffect(() => {
    const handleBeforeUnload = () => store.abortAll()
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [store])

  // ── 输入提交（SSE 流由 store.submit 统一驱动）──

  const startAnalysis = async (query: string, sessionId: string | null = null) => {
    if (!apiKey.trim()) {
      setShowSettings(true)
      return
    }
    // 拦截：当前会话正在运行时不允许提交新消息（delta spec Task 6.2）
    if (sessionId && store.isSessionRunning(sessionId)) {
      showWarning('该会话正在生成中，可停止后再发')
      return
    }
    // 请求级 LLM 配置（delta 5.4）：仅在有非空配置时携带 llm_config 字段
    const llmConfigPayload = buildLlmConfigPayload(llmConfig)
    try {
      await store.submit(
        {
          query,
          api_key: apiKey,
          user_id: getUserId(),
          analysis_type: 'comprehensive',
          ...(sessionId ? { session_id: sessionId } : {}),
          ...(llmConfigPayload ? { llm_config: llmConfigPayload } : {}),
        },
        { currentView: currentSessionId },
      )
    } catch {
      // 连接错误已在 store 内写入 error 消息；409 busy 额外提示
      const errText = store.getSnapshot(sessionId || currentSessionId || '')?.error
      if (errText) showWarning(errText)
    }
  }

  const quickChat = async (message: string) => {
    // 拦截：当前会话正在运行时不允许提交新消息（delta spec Task 6.2）
    if (currentSessionId && store.isSessionRunning(currentSessionId)) {
      showWarning('该会话正在生成中，可停止后再发')
      return
    }
    // 请求级 LLM 配置（delta 5.4）：仅在有非空配置时携带 llm_config 字段
    const llmConfigPayload = buildLlmConfigPayload(llmConfig)
    try {
      await store.submit(
        {
          message,
          user_id: getUserId(),
          api_key: apiKey,
          ...(currentSessionId ? { session_id: currentSessionId } : {}),
          ...(llmConfigPayload ? { llm_config: llmConfigPayload } : {}),
        },
        { currentView: currentSessionId },
      )
    } catch {
      const errText = store.getSnapshot(currentSessionId || '')?.error
      if (errText) showWarning(errText)
    }
  }

  const handleSendFromEmpty = (text: string, sendMode: string = 'deep') => {
    const query = text.trim()
    if (!query) return
    if (sendMode === 'quick') {
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

  // 运行中会话快照轮询（resume-pipeline-across-sessions Task 5）：
  // 切回 running 会话进入 analyzing 且无活跃 SSE（仅恢复态、非实时订阅）时，
  // 每 2s 拉取会话详情刷新分层时间轴；completed 则走 selectSession 完整恢复报告并自然停止；
  // failed 仅停止轮询（MVP 不展示失败态）。
  // 超时保护（Final Review Fix 2）：超过 MAX_POLLING_MS（5 分钟）后停止轮询并提示
  // 「管线可能已中断」，避免 ReAct 路径 status 永久 running 时轮询无限泄漏。
  // 前提不变量：store.hasActiveReader() 作为「SSE 在线」信号；
  // 用户在恢复态发起新分析时 store.submit 会建立新 reader，interval 回调内必须复查，
  // 避免 SSE 与轮询双写消息、以及轮询误调 selectSession 掐断新 SSE。
  useEffect(() => {
    if (appState !== 'analyzing' || !currentSessionId) return
    if (store.hasActiveReader()) return // 有活跃 SSE 订阅，进度由事件流驱动，无需轮询
    pollStartRef.current = Date.now() // 记录轮询起始时间（超时保护基准）
    const sessionId = currentSessionId
    const timer = setInterval(async () => {
      // 复查 SSE 在线信号：用户在恢复态发起新分析时轮询立即让位，
      // 等 effect 因状态变化重跑后 interval 自然清理
      if (store.hasActiveReader()) return
      // 超时保护：超过 MAX_POLLING_MS 则停止轮询并提示（ReAct 路径 status 可能永久 running）
      if (pollStartRef.current && Date.now() - pollStartRef.current >= MAX_POLLING_MS) {
        clearInterval(timer)
        // 尝试最后一次获取会话状态，检查是否有 failure_reason
        try {
          const finalResp = await fetch(`/api/sessions/${sessionId}`)
          if (finalResp.ok) {
            const finalData: SessionDetail = await finalResp.json()
            if (finalData.failure_reason) {
              store.updatePipelineContent(sessionId, `分析失败：${finalData.failure_reason}`)
              return
            }
          }
        } catch {
          // 忽略，回退到默认提示
        }
        store.updatePipelineContent(sessionId, '管线可能已中断，请刷新或重新发起')
        return
      }
      try {
        const resp = await fetch(`/api/sessions/${sessionId}`)
        if (!resp.ok) return
        const data: SessionDetail = await resp.json()
        if (data.status === 'running' && data.pipeline_snapshot) {
          let snap: PipelineSnapshot | null = null
          try {
            snap = JSON.parse(data.pipeline_snapshot)
          } catch {
            snap = null
          }
          if (snap) {
            store.updatePipelineSnapshot(sessionId, snap)
          }
          // running 但无快照（或快照解析失败）：本周期静默忽略，等下个周期重试
        } else if (data.status === 'completed') {
          // 后台管线完成：走 selectSession 完整重建（复用锚点定位、agentTimeline
          // 恢复、pipeline_timelines 结构化时序等逻辑，避免报告插入位置错误或时序丢失）。
          // clearInterval 先停止轮询，selectSession 内部状态变更触发
          // effect 重跑时 timer 已清理，不会递归。
          clearInterval(timer)
          await selectSession(sessionId, true)
        } else if (data.status === 'failed') {
          // 管线失败：展示中断原因，停止轮询
          clearInterval(timer)
          const reason = data.failure_reason || '管线执行失败'
          store.updatePipelineContent(sessionId, `分析失败：${reason}`)
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
  }, [appState, currentSessionId, store, stream.phase])

  // ── Render ──
  const leftInset = sidebarOpen ? 256 : 48

  // 计算正在运行的会话 ID 集合（后端 status=running 或 store 中有进行中流）
  const runningSessionIds = new Set<string>()
  for (const s of sessions) {
    if (s.status === 'running') runningSessionIds.add(s.session_id)
  }
  for (const id of store.getActiveSessionIds()) {
    runningSessionIds.add(id)
  }

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
        loading={!sessionsLoaded}
      />
      <div className={`transition-all duration-200 ${sidebarOpen ? 'ml-64' : 'ml-12'}`}>
        {bootRestoring && appState === 'empty' ? (
          // 刷新恢复中：有持久化会话但尚未重建消息，显示恢复指示而非闪首页空态
          <div data-testid="restoring-state" className="flex flex-col items-center justify-center h-screen gap-3">
            <i className="fas fa-circle-notch fa-spin text-2xl" style={{ color: 'var(--bg-brand)' }}></i>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>恢复会话中…</p>
          </div>
        ) : appState === 'empty' ? (
          <EmptyState
            onSend={handleSendFromEmpty}
            apiKey={apiKey}
            capability={capability}
            setShowSettings={setShowSettings}
            mode={mode}
            setMode={setMode}
            profileName={getActiveProfileName(profileStore)}
            profiles={profileStore.profiles}
            activeProfileId={profileStore.activeId}
            onSwitchProfile={switchProfile}
          />
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
                <button className="text-[var(--icon-secondary)] hover:text-[var(--text-default)] transition-colors text-sm" onClick={() => setShowSettings(true)}>
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
            <ChatInputBar
              onSend={handleSendFromChat}
              leftInset={leftInset}
              mode={mode}
              setMode={setMode}
              capability={capability}
              onNewAnalysis={newAnalysis}
              apiKey={apiKey}
              setShowSettings={setShowSettings}
              profileName={getActiveProfileName(profileStore)}
              profiles={profileStore.profiles}
              activeProfileId={profileStore.activeId}
              onSwitchProfile={switchProfile}
            />
          </>
        )}
      </div>

      {/* LLM 设置面板（取代旧版仅 API Key 的弹窗） */}
      {showSettings && (
        <SettingsModal
          config={llmConfig}
          backendDefaults={backendDefaults}
          profileStore={profileStore}
          capability={capability}
          onProbeCapability={handleProbeCapability}
          onSave={handleSaveConfig}
          onSaveAs={handleSaveAsConfig}
          onSwitchProfile={switchProfile}
          onDeleteProfile={handleDeleteProfile}
          onClose={() => setShowSettings(false)}
        />
      )}
    </>
  )
}

// ── Sidebar ──
function Sidebar({ sessions, currentSessionId, onSelect, onDelete, onRename, onNew, isOpen, onToggle, runningSessionIds, loading = false }: {
  sessions: SessionMeta[]
  currentSessionId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, name: string) => void
  onNew: () => void
  isOpen: boolean
  onToggle: () => void
  runningSessionIds: Set<string>
  loading?: boolean
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
        {loading && sessions.length === 0 ? (
          // 加载骨架：/api/sessions 首次返回前显示占位行，避免闪「暂无历史会话」
          <div data-testid="sidebar-skeleton" className="space-y-2 px-1 pt-1">
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="rounded-lg px-3 py-2 animate-pulse" style={{ background: 'var(--bg-overlay-l1)' }}>
                <div className="h-3 rounded w-2/3 mb-1.5" style={{ background: 'var(--bg-overlay-l2)' }} />
                <div className="h-2 rounded w-1/3" style={{ background: 'var(--bg-overlay-l2)' }} />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
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
export function EmptyState({ onSend, apiKey, capability, setShowSettings, mode, setMode, profileName, profiles, activeProfileId, onSwitchProfile }: {
  onSend: (text: string, mode?: string) => void
  apiKey: string
  capability: CapabilityMatrix | null
  setShowSettings: (v: boolean) => void
  mode: 'quick' | 'deep'
  setMode: (m: 'quick' | 'deep') => void
  profileName: string
  profiles: LLMProfile[]
  activeProfileId: string
  onSwitchProfile: (id: string) => void
}) {
  const [text, setText] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  // LLM 切换下拉框展开状态（delta Decision 11）
  const [llmDropdownOpen, setLlmDropdownOpen] = useState(false)
  // 点击下拉框外部区域关闭（delta fix-dropdown-outside-close）：
  // rowRef 包裹触发按钮与弹层两者，避免「点触发按钮先关后开」竞态
  const rowRef = useRef<HTMLDivElement>(null)
  useClickOutside(rowRef, dropdownOpen || llmDropdownOpen, () => {
    setDropdownOpen(false)
    setLlmDropdownOpen(false)
  })

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const query = text.trim()
      if (!query) return
      if (!apiKey) { setShowSettings(true); return }
      onSend(query, mode)
      setText('')
    }
  }

  const handleSend = () => {
    const query = text.trim()
    if (!query) return
    if (!apiKey) { setShowSettings(true); return }
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
          <div className="relative flex items-center gap-2 px-4 pt-1 pb-0" ref={rowRef}>
            <button
              onClick={() => { setLlmDropdownOpen(false); setDropdownOpen(!dropdownOpen) }}
              className="flex items-center gap-1.5 text-[10px] font-medium rounded px-2 py-0.5 transition-colors hover:bg-[var(--bg-overlay-l1)]"
            >
              <span style={{ color: 'var(--text-tertiary)' }}>模式：</span>
              <i className={`fas ${currentMode.icon} ${currentMode.color}`}></i>
              <span className={currentMode.color}>{currentMode.label}</span>
              <i className={`fas fa-chevron-${dropdownOpen ? 'up' : 'down'} text-[8px] ml-0.5`} style={{ color: 'var(--text-tertiary)' }}></i>
            </button>
            {dropdownOpen && (
              <div className="absolute left-4 top-7 z-[70] w-72 glass-card rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
                {modes.map(m => {
                  const gate = canEnterMode(m.id, capability)
                  return (
                  <button
                    key={m.id}
                    onClick={() => { if (gate.allowed) { setMode(m.id); setDropdownOpen(false) } }}
                    disabled={!gate.allowed}
                    title={gate.allowed ? undefined : gate.reason}
                    className="w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    style={mode === m.id ? { background: 'var(--bg-overlay-l2)' } : { background: 'transparent' }}
                    onMouseEnter={(e) => { if (mode !== m.id && gate.allowed) e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
                    onMouseLeave={(e) => { if (mode !== m.id) e.currentTarget.style.background = 'transparent' }}
                  >
                    <i className={`fas ${m.icon} ${m.color} text-xs mt-0.5`}></i>
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-medium ${mode === m.id ? m.color : ''}`} style={mode !== m.id ? { color: 'var(--text-secondary)' } : {}}>
                        {m.label}
                        {mode === m.id && <i className="fas fa-check ml-1.5 text-[10px]"></i>}
                      </div>
                      <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{m.desc}</div>
                      {!gate.allowed && (
                        <div className="text-[10px] mt-0.5" style={{ color: 'var(--status-error-default)' }}>{gate.reason}</div>
                      )}
                    </div>
                  </button>
                  )
                })}
              </div>
            )}

            {/* LLM 切换下拉框（delta Decision 11）；无 profile 时点击引导配置 */}
            <div className="relative inline-block">
              <button
                onClick={() => {
                  if (profiles.length === 0) { setShowSettings(true); return }
                  setDropdownOpen(false)
                  setLlmDropdownOpen(!llmDropdownOpen)
                }}
                className="flex items-center gap-1 text-[10px] font-medium rounded px-2 py-0.5 transition-colors hover:bg-[var(--bg-overlay-l1)]"
              >
                <i className="fas fa-microchip text-[var(--text-tertiary)]"></i>
                <span style={{ color: 'var(--text-secondary)' }}>{profileName}</span>
                <i className={`fas fa-chevron-${llmDropdownOpen ? 'up' : 'down'} text-[8px] ml-0.5`} style={{ color: 'var(--text-tertiary)' }}></i>
              </button>
              {llmDropdownOpen && profiles.length > 0 && (
                <div className="absolute left-0 top-7 z-[70] w-56 glass-card rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
                  {profiles.map(p => (
                    <button
                      key={p.id}
                      onClick={() => { onSwitchProfile(p.id); setLlmDropdownOpen(false) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors"
                      style={{ background: p.id === activeProfileId ? 'var(--bg-overlay-l2)' : 'transparent' }}
                    >
                      {p.id === activeProfileId && <i className="fas fa-check text-[10px]" style={{ color: 'var(--text-brand)' }}></i>}
                      <span style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
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
            请先配置 LLM API 才能开始分析
            <button className="hover:underline ml-1" style={{ color: 'var(--text-brand)' }} onClick={() => setShowSettings(true)}>去配置</button>
          </p>
        ) : (
          <p className="text-center text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
            <i className="fas fa-check-circle mr-1" style={{ color: 'var(--status-success-default)' }}></i>
            LLM API 已配置
            <button className="hover:underline ml-1" style={{ color: 'var(--text-brand)' }} onClick={() => setShowSettings(true)}>修改</button>
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
export function ChatInputBar({ onSend, leftInset, mode, setMode, capability, onNewAnalysis, apiKey, setShowSettings, profileName, profiles, activeProfileId, onSwitchProfile }: {
  onSend: (text: string) => void
  leftInset: number
  mode: 'quick' | 'deep'
  setMode: (m: 'quick' | 'deep') => void
  capability: CapabilityMatrix | null
  onNewAnalysis: () => void
  apiKey: string
  setShowSettings: (v: boolean) => void
  profileName: string
  profiles: LLMProfile[]
  activeProfileId: string
  onSwitchProfile: (id: string) => void
}) {
  const [text, setText] = useState('')
  const [modeDropdownOpen, setModeDropdownOpen] = useState(false)
  // LLM 切换下拉框展开状态（delta Decision 11）
  const [llmDropdownOpen, setLlmDropdownOpen] = useState(false)
  // 点击下拉框外部区域关闭（delta fix-dropdown-outside-close）：
  // rowRef 包裹触发按钮与弹层两者，避免「点触发按钮先关后开」竞态
  const rowRef = useRef<HTMLDivElement>(null)
  useClickOutside(rowRef, modeDropdownOpen || llmDropdownOpen, () => {
    setModeDropdownOpen(false)
    setLlmDropdownOpen(false)
  })

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!apiKey) { setShowSettings(true); return }
      onSend(text)
      setText('')
    }
  }

  const handleSendClick = () => {
    if (!apiKey) { setShowSettings(true); return }
    onSend(text)
    setText('')
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
          <div className="relative flex items-center gap-1 px-1 pb-1" ref={rowRef}>
            <button
              onClick={() => { setLlmDropdownOpen(false); setModeDropdownOpen(!modeDropdownOpen) }}
              className="flex items-center gap-1.5 text-[11px] font-medium rounded-lg px-2.5 py-1 transition-colors hover:bg-[var(--bg-overlay-l1)]"
            >
              <i className={`fas ${currentMode.icon} ${currentMode.color} text-[10px]`}></i>
              <span className={currentMode.color}>{currentMode.label}</span>
              <i className={`fas fa-chevron-${modeDropdownOpen ? 'down' : 'up'} text-[8px] ml-0.5`} style={{ color: 'var(--text-tertiary)' }}></i>
            </button>
            {modeDropdownOpen && (
              <div className="absolute left-1 bottom-8 z-[70] w-72 glass-card rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
                {modes.map(m => {
                  const gate = canEnterMode(m.id, capability)
                  return (
                  <button
                    key={m.id}
                    onClick={() => handleModeSelect(m.id)}
                    disabled={!gate.allowed}
                    title={gate.allowed ? undefined : gate.reason}
                    className="w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    style={mode === m.id ? { background: 'var(--bg-overlay-l2)' } : { background: 'transparent' }}
                    onMouseEnter={(e) => { if (mode !== m.id && gate.allowed) e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
                    onMouseLeave={(e) => { if (mode !== m.id) e.currentTarget.style.background = 'transparent' }}
                  >
                    <i className={`fas ${m.icon} ${m.color} text-xs mt-0.5`}></i>
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-medium ${mode === m.id ? m.color : ''}`} style={mode !== m.id ? { color: 'var(--text-secondary)' } : {}}>
                        {m.label}
                        {mode === m.id && <i className="fas fa-check ml-1.5 text-[10px]"></i>}
                      </div>
                      <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{m.desc}</div>
                      {!gate.allowed && (
                        <div className="text-[10px] mt-0.5" style={{ color: 'var(--status-error-default)' }}>{gate.reason}</div>
                      )}
                    </div>
                    {mode !== m.id && gate.allowed && (
                      <span className="text-[10px] mt-0.5 flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>新会话</span>
                    )}
                  </button>
                  )
                })}
              </div>
            )}

            {/* LLM 切换（delta Decision 11）；无 profile 时点击引导配置 */}
            <div className="relative inline-block">
              <button
                onClick={() => {
                  if (profiles.length === 0) { setShowSettings(true); return }
                  setModeDropdownOpen(false)
                  setLlmDropdownOpen(!llmDropdownOpen)
                }}
                className="flex items-center gap-1 text-[11px] font-medium rounded-lg px-2.5 py-1 transition-colors hover:bg-[var(--bg-overlay-l1)]"
              >
                <i className="fas fa-microchip text-[10px]" style={{ color: 'var(--text-tertiary)' }}></i>
                <span style={{ color: 'var(--text-secondary)' }}>{profileName}</span>
                <i className={`fas fa-chevron-${llmDropdownOpen ? 'down' : 'up'} text-[8px] ml-0.5`} style={{ color: 'var(--text-tertiary)' }}></i>
              </button>
              {llmDropdownOpen && profiles.length > 0 && (
                <div className="absolute left-32 bottom-8 z-[70] w-56 glass-card rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
                  {profiles.map(p => (
                    <button
                      key={p.id}
                      onClick={() => { onSwitchProfile(p.id); setLlmDropdownOpen(false) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors"
                      style={{ background: p.id === activeProfileId ? 'var(--bg-overlay-l2)' : 'transparent' }}
                    >
                      {p.id === activeProfileId && <i className="fas fa-check text-[10px]" style={{ color: 'var(--text-brand)' }}></i>}
                      <span style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
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
              onClick={handleSendClick}
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

// ── Settings Modal（LLM 设置面板，取代旧版仅 API Key 的弹窗）──
// 实现 delta 5.1/5.5（模型/BaseURL/思考开关）、6.1-6.5（Provider 预设 + 模型发现）、7.1-7.4（连通性测试）。
export function SettingsModal({ config, backendDefaults, profileStore, capability: capabilityProp, onProbeCapability, onSave, onSaveAs, onSwitchProfile, onDeleteProfile, onClose }: {
  config: LLMConfig
  backendDefaults: { model: string; baseUrl: string; thinking: string }
  profileStore: ProfileStore
  capability: CapabilityMatrix | null
  onProbeCapability: (cap: CapabilityMatrix | null) => void
  onSave: (cfg: LLMConfig) => void
  onSaveAs: (cfg: LLMConfig, name: string) => void
  onSwitchProfile: (id: string) => void
  onDeleteProfile: (id: string) => void
  onClose: () => void
}) {
  // 本地编辑态：确认时才回写父级并持久化（避免每次按键都写 localStorage）
  const [apiKey, setApiKey] = useState(config.apiKey)
  const [model, setModel] = useState(config.model)
  const [baseUrl, setBaseUrl] = useState(config.baseUrl)
  // 思考模式：已保存值优先，其次后端默认，最后内置 enabled
  const [thinking, setThinking] = useState<string>(config.thinking || backendDefaults.thinking || 'enabled')
  const [apiForm, setApiForm] = useState<string>(config.apiForm || DEFAULT_API_FORM)
  // 配置管理：另存为输入（delta Decision 10）
  const [profileName, setProfileName] = useState('')

  // 模型自动发现状态
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([])
  const [discoveryLoading, setDiscoveryLoading] = useState(false)
  const [discoveryMsg, setDiscoveryMsg] = useState<{ text: string; ok: boolean } | null>(null)

  // 连通性测试状态
  const [testStatus, setTestStatus] = useState<'idle' | 'loading' | 'success' | 'fail'>('idle')
  const [testLatencyMs, setTestLatencyMs] = useState<number | undefined>(undefined)
  const [testMessage, setTestMessage] = useState('')
  // probe 得到的能力矩阵（弹窗内展示；连接三要素变更后置空待重探测）
  const [capability, setCapability] = useState<CapabilityMatrix | null>(capabilityProp)
  const [testWarnings, setTestWarnings] = useState<string[]>([])

  // 切换 profile 时表单整体切换（设计档案 §15 原子切换，ZCode 式编辑逻辑）：
  // 本地 useState 只在挂载取初值，activeId 变化后必须显式同步为目标 profile 的
  // 配置，否则弹窗停留在旧 profile 的字段（且不清 apiKey——整体换，不留旧值）。
  useEffect(() => {
    const active = profileStore.profiles.find(p => p.id === profileStore.activeId)
    if (!active) return
    setApiKey(active.config.apiKey)
    setModel(active.config.model)
    setBaseUrl(active.config.baseUrl)
    setThinking(active.config.thinking || backendDefaults.thinking || 'enabled')
    setApiForm(active.config.apiForm || DEFAULT_API_FORM)
    setCapability(active.config.capability ?? null)
    setTestWarnings([])
    setTestStatus('idle')
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅在激活 profile 切换时同步；config 对象因保存/probe 更新会变 identity，不应重置用户编辑中字段
  }, [profileStore.activeId])

  // 连接三要素（apiKey/model/baseUrl）变更 → 旧 probe 事实失效
  const invalidateCapability = () => {
    setCapability(null)
    setTestWarnings([])
  }

  // 思考模式开关仅在 DeepSeek 模型下展示（delta 5.5）
  const showThinkingToggle = isDeepSeekModel(model)
  // 当前值匹配的预设名（手动修改后自动回退为"自定义"）
  const currentPreset = matchPreset({ model, baseUrl, thinking: showThinkingToggle ? thinking : '' })

  // 选择预设：自动填充 model/baseUrl/thinking（不触发保存）
  const applyPreset = (name: string) => {
    const preset = PROVIDER_PRESETS.find((p) => p.name === name)
    if (!preset) return
    setModel(preset.model)
    setBaseUrl(preset.baseUrl)
    setThinking(preset.thinking || 'enabled')
    setApiForm(preset.apiForm)
    invalidateCapability()
  }

  // 刷新模型列表：调用后端代理拉取 {base_url}/models（delta 6.3）
  const refreshModels = async () => {
    if (discoveryLoading) return
    setDiscoveryLoading(true)
    setDiscoveryMsg(null)
    try {
      const resp = await fetch('/api/llm-config/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // 字段名 camelCase 与后端 ModelsRequest(baseUrl/apiKey) 一致，否则被 Pydantic 忽略回退环境变量
        body: JSON.stringify({ baseUrl: baseUrl.trim(), apiKey: apiKey.trim() }),
      })
      const data: { models?: unknown[]; error?: string } = await resp.json().catch(() => ({}))
      const rawModels = Array.isArray(data?.models) ? data.models : []
      const models = rawModels.filter((m): m is string => typeof m === 'string')
      setDiscoveredModels(models)
      if (models.length === 0) {
        setDiscoveryMsg({ text: data?.error || '该端点不支持模型自动发现，请手动输入', ok: false })
      } else {
        setDiscoveryMsg({ text: `发现 ${models.length} 个可用模型`, ok: true })
      }
    } catch {
      setDiscoveredModels([])
      setDiscoveryMsg({ text: '连接超时，请检查 Base URL', ok: false })
    } finally {
      setDiscoveryLoading(false)
    }
  }

  // 从下拉选择模型：拼接 litellm 前缀填入 model 输入框（delta 6.4）
  const pickDiscoveredModel = (raw: string) => {
    setModel(buildModelWithPrefix(raw, baseUrl))
  }

  // 测试连接：后端发送极简 LLM 请求验证配置（delta 7.1）
  const testConnection = async () => {
    if (testStatus === 'loading') return
    setTestStatus('loading')
    setTestMessage('')
    setTestLatencyMs(undefined)
    try {
      const resp = await fetch('/api/llm-config/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // 字段名 camelCase 与后端 LLMConfigRequest(baseUrl/apiKey) 一致，否则被 Pydantic 忽略回退环境变量
        body: JSON.stringify({
          model: model.trim(),
          baseUrl: baseUrl.trim(),
          apiKey: apiKey.trim(),
          thinking: showThinkingToggle ? thinking : '',
        }),
      })
      // 后端响应为 camelCase（latencyMs/errorType/capability/warnings）；旧代码误读 snake_case 导致延迟不显示
      const data: { success?: boolean; latencyMs?: number; model?: string; error?: string; errorType?: string; capability?: unknown; warnings?: unknown } = await resp.json().catch(() => ({}))
      if (data?.success) {
        setTestStatus('success')
        setTestLatencyMs(typeof data.latencyMs === 'number' ? data.latencyMs : undefined)
        setTestMessage(typeof data.model === 'string' ? data.model : '')
        // probe 事实：capability 矩阵 + warnings（成功但无 capability 视为未探测）
        const cap = parseCapability(data.capability)
        setCapability(cap)
        setTestWarnings(Array.isArray(data.warnings) ? data.warnings.filter((w): w is string => typeof w === 'string') : [])
        onProbeCapability(cap)
      } else {
        setTestStatus('fail')
        setTestMessage(formatTestError(data?.errorType, data?.error))
      }
    } catch {
      setTestStatus('fail')
      setTestMessage('请求失败，请检查网络或后端服务')
    }
  }

  const handleSave = () => {
    onSave({
      apiKey: apiKey.trim(),
      model: model.trim(),
      baseUrl: baseUrl.trim(),
      // 非 DeepSeek 模型不持久化 thinking（开关已隐藏）
      thinking: showThinkingToggle ? thinking : '',
      apiForm: apiForm,
      // 携带当前 probe 事实（连接三要素未变时保留；变更则由父级 clearCapability 清空）
      capability,
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center backdrop-blur-sm" style={{ background: 'rgba(0,0,0,0.25)' }} onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="glass-card rounded-2xl p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-semibold mb-1" style={{ color: 'var(--text-default)' }}>LLM 配置</h3>
        <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>配置模型、API 端点与密钥。配置保存在浏览器本地，刷新页面不会丢失。</p>

        {/* Provider 预设选择器（delta 6.1） */}
        <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Provider 预设</label>
        <select
          value={currentPreset}
          onChange={e => applyPreset(e.target.value)}
          className="w-full glass-input rounded-xl px-3 py-2.5 text-sm outline-none mb-4"
          style={{ color: 'var(--text-default)' }}
        >
          {PROVIDER_PRESETS.map(p => (
            <option key={p.name} value={p.name}>{p.name}</option>
          ))}
        </select>

        {/* API 形式（add-llm-api-form）：显式指定协议，模型名前缀据此推导 */}
        <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>API 形式</label>
        <select
          value={apiForm}
          onChange={e => setApiForm(e.target.value)}
          className="w-full glass-input rounded-xl px-3 py-2.5 text-sm outline-none mb-4"
          style={{ color: 'var(--text-default)' }}
        >
          {API_FORM_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        {/* API Key（保留原有密码输入） */}
        <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>API Key</label>
        <input
          type="password"
          placeholder="sk-..."
          value={apiKey}
          onChange={e => { setApiKey(e.target.value); invalidateCapability() }}
          className="w-full glass-input rounded-xl px-4 py-3 text-sm outline-none mb-4"
          style={{ color: 'var(--text-default)' }}
        />

        {/* 模型名称 + 刷新按钮（delta 6.3） */}
        <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>模型名称</label>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
          placeholder={backendDefaults.model || 'deepseek/deepseek-chat'}
          value={model}
          onChange={e => { setModel(e.target.value); invalidateCapability() }}
            className="flex-1 glass-input rounded-xl px-4 py-3 text-sm outline-none"
            style={{ color: 'var(--text-default)' }}
          />
          <button
            onClick={refreshModels}
            disabled={discoveryLoading}
            className="px-3 rounded-xl text-xs font-medium transition-colors whitespace-nowrap disabled:opacity-50"
            style={{ background: 'var(--bg-overlay-l2)', color: 'var(--text-secondary)' }}
            title="从 Base URL 拉取可用模型列表"
          >
            <i className={`fas fa-sync-alt mr-1 ${discoveryLoading ? 'fa-spin' : ''}`}></i>
            {discoveryLoading ? '加载中' : '刷新模型'}
          </button>
        </div>

        {/* 自动发现的模型下拉（delta 6.4） */}
        {discoveredModels.length > 0 && (
          <select
            value=""
            onChange={e => { if (e.target.value) pickDiscoveredModel(e.target.value) }}
            className="w-full glass-input rounded-xl px-3 py-2.5 text-sm outline-none mb-4"
            style={{ color: 'var(--text-default)' }}
          >
            <option value="">从发现列表选择模型…</option>
            {discoveredModels.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        )}
        {/* 模型发现提示（delta 6.5：失败/空列表提示但不阻塞手动输入） */}
        {discoveryMsg && (
          <p className="text-xs mb-4" style={{ color: discoveryMsg.ok ? 'var(--status-success-default)' : 'var(--status-error-default)' }}>
            <i className={`fas ${discoveryMsg.ok ? 'fa-check-circle' : 'fa-exclamation-circle'} mr-1`}></i>
            {discoveryMsg.text}
          </p>
        )}
        {discoveredModels.length === 0 && !discoveryMsg && (
          <p className="text-[11px] mb-4" style={{ color: 'var(--text-tertiary)' }}>
            <i className="fas fa-info-circle mr-1"></i>
            litellm 格式：provider/model，如 deepseek/deepseek-chat
          </p>
        )}

        {/* API Base URL（delta 5.1） */}
        <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>API Base URL</label>
        <input
          type="text"
          placeholder={backendDefaults.baseUrl || 'https://api.deepseek.com/v1（留空使用默认）'}
          value={baseUrl}
          onChange={e => { setBaseUrl(e.target.value); invalidateCapability() }}
          className="w-full glass-input rounded-xl px-4 py-3 text-sm outline-none mb-4"
          style={{ color: 'var(--text-default)' }}
        />

        {/* 思考模式开关（delta 5.5：仅 DeepSeek 模型展示） */}
        {showThinkingToggle && (
          <div className="flex items-center justify-between glass-input rounded-xl px-4 py-3 mb-4">
            <div>
              <div className="text-sm font-medium" style={{ color: 'var(--text-default)' }}>思考模式</div>
              <div className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>DeepSeek 深度推理（enabled / disabled）</div>
            </div>
            <button
              onClick={() => setThinking(thinking === 'enabled' ? 'disabled' : 'enabled')}
              className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
              style={{ background: thinking === 'enabled' ? 'var(--bg-brand)' : 'var(--bg-overlay-l3)' }}
              role="switch"
              aria-checked={thinking === 'enabled'}
            >
              <span
                className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                style={{ transform: thinking === 'enabled' ? 'translateX(24px)' : 'translateX(4px)' }}
              />
            </button>
          </div>
        )}

        {/* 连通性测试（delta 7.1-7.4） */}
        <div className="mb-4">
          <button
            onClick={testConnection}
            disabled={testStatus === 'loading'}
            className="w-full py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
            style={{ background: 'var(--bg-overlay-l2)', color: 'var(--text-secondary)' }}
          >
            <i className={`fas ${testStatus === 'loading' ? 'fa-spinner fa-spin' : 'fa-plug'} mr-1.5`}></i>
            {testStatus === 'loading' ? '测试中…' : '测试连接'}
          </button>
          {testStatus === 'success' && (
            <p className="text-xs mt-2" style={{ color: 'var(--status-success-default)' }}>
              <i className="fas fa-check-circle mr-1"></i>
              连接成功{typeof testLatencyMs === 'number' ? ` · ${testLatencyMs}ms` : ''}{testMessage ? ` · ${testMessage}` : ''}
            </p>
          )}
          {testStatus === 'fail' && (
            <p className="text-xs mt-2" style={{ color: 'var(--status-error-default)' }}>
              <i className="fas fa-times-circle mr-1"></i>
              {testMessage}
            </p>
          )}

          {/* 能力矩阵（harden-llm-gateway Task 6：probe 事实驱动展示） */}
          <div className="mt-3 glass-input rounded-xl px-4 py-3">
            <div className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
              <i className="fas fa-clipboard-check mr-1"></i>能力矩阵
            </div>
            {capability ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5" data-testid="capability-matrix">
                {(
                  [
                    { key: 'non_stream', label: '非流式' },
                    { key: 'stream', label: '流式' },
                    { key: 'tool_call', label: '工具调用' },
                    { key: 'tool_followup', label: '工具跟随' },
                    { key: 'json_output', label: 'JSON 输出' },
                  ] as { key: keyof CapabilityMatrix; label: string }[]
                ).map(item => (
                  <div key={item.key} className="flex items-center gap-1.5 text-xs" data-testid={`capability-${item.key}`}>
                    <i
                      className={`fas ${capability[item.key] ? 'fa-check-circle' : 'fa-times-circle'}`}
                      style={{ color: capability[item.key] ? 'var(--status-success-default)' : 'var(--status-error-default)' }}
                    ></i>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      {item.label}
                      {!capability[item.key] && <span style={{ color: 'var(--text-tertiary)' }}>（不支持）</span>}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              // probe_required：未探测时提示（不展示错误，仅静态能力语义）
              <p className="text-[11px]" data-testid="capability-probe-required" style={{ color: 'var(--text-tertiary)' }}>
                <i className="fas fa-info-circle mr-1"></i>未探测，展示静态能力。点击「测试连接」获取该 provider 的实测能力矩阵。
              </p>
            )}
            {testWarnings.length > 0 && (
              <ul className="mt-2 space-y-1" data-testid="capability-warnings">
                {testWarnings.map((w, i) => (
                  <li key={i} className="text-[11px]" style={{ color: 'var(--status-warning-default)' }}>
                    <i className="fas fa-exclamation-triangle mr-1"></i>{w}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* 配置管理区（delta Decision 10） */}
        <div className="mb-4 pt-4" style={{ borderTop: '1px solid var(--border-neutral-l1)' }}>
          <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
            <i className="fas fa-bookmark mr-1"></i>配置管理
          </label>

          {/* 另存为新 profile */}
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              placeholder="输入配置名称，如「DeepSeek 办公」"
              value={profileName}
              onChange={e => setProfileName(e.target.value)}
              className="flex-1 glass-input rounded-xl px-3 py-2 text-xs outline-none"
              style={{ color: 'var(--text-default)' }}
            />
            <button
              onClick={() => {
                const name = profileName.trim()
                if (!name) return
                // 将当前表单值另存为新 profile
                onSaveAs({ apiKey: apiKey.trim(), model: model.trim(), baseUrl: baseUrl.trim(), thinking: showThinkingToggle ? thinking : '', apiForm: apiForm, capability }, name)
                setProfileName('')
              }}
              className="px-3 rounded-xl text-xs font-medium transition-colors whitespace-nowrap"
              style={{ background: 'var(--bg-overlay-l2)', color: 'var(--text-secondary)' }}
            >
              <i className="fas fa-save mr-1"></i>另存为
            </button>
          </div>

          {/* 已有 profile 列表 */}
          {profileStore.profiles.length > 0 && (
            <div className="space-y-1">
              {profileStore.profiles.map(p => (
                <div
                  key={p.id}
                  className="flex items-center justify-between px-3 py-1.5 rounded-lg text-xs"
                  style={{
                    background: p.id === profileStore.activeId ? 'var(--bg-overlay-l2)' : 'transparent',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <button
                    onClick={() => onSwitchProfile(p.id)}
                    className="flex items-center gap-1.5 flex-1 text-left"
                  >
                    {p.id === profileStore.activeId && <i className="fas fa-check text-[10px]" style={{ color: 'var(--text-brand)' }}></i>}
                    <span>{p.name}</span>
                  </button>
                  <button
                    onClick={() => onDeleteProfile(p.id)}
                    className="text-[10px] opacity-60 hover:opacity-100 transition-opacity"
                    style={{ color: 'var(--status-error-default)' }}
                  >
                    <i className="fas fa-trash-alt"></i>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleSave}
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

// 连通性测试失败提示：按 error_type 展示针对性文案（delta 7.3）
function formatTestError(errorType: string | undefined, error: string | undefined): string {
  switch (errorType) {
    case 'auth':
      return 'API Key 无效，请检查密钥配置'
    case 'network':
      return '无法连接到 API 端点，请检查 Base URL'
    case 'model_not_found':
      return '模型不存在，请检查模型名称'
    default:
      return error || '测试失败，请检查配置'
  }
}
