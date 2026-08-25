import type { SSEEvent, SessionDetail, UIMessage } from '../../types'
import type { LLMConfigPayload } from '../../llmConfig'
import type { SessionStreamState, StreamPhase } from './types'
import { IDLE_STATE, genMsgId } from './types'
import { reduce } from './reduce'
import { buildTimelineFromHistory, deserializeTimeline, deserializeNodeTimelines } from '../../timeline'
import { deserializeLayerTree } from '../../pipelineTree'
import { recordDuration } from '../../eta'

// ── 请求/响应类型 ──

export interface AnalyzeRequest {
  query: string
  api_key: string
  user_id: string
  analysis_type: string
  session_id?: string
  stock_code?: string
  stock_name?: string
  focus?: string
  // 请求级 LLM 配置（覆盖后端环境变量默认值）；null/undefined 时不携带
  llm_config?: LLMConfigPayload | null
}

export interface ChatRequest {
  message: string
  user_id: string
  api_key: string
  session_id?: string
  // 请求级 LLM 配置（覆盖后端环境变量默认值）；null/undefined 时不携带
  llm_config?: LLMConfigPayload | null
}

// ── 回调通知 ──

export interface StreamStoreCallbacks {
  onSessionCreated?: (sessionId: string, displayName: string) => void
  onSessionsChanged?: () => void
  onPhaseChange?: (sessionId: string, phase: StreamPhase) => void
  onError?: (sessionId: string, error: string) => void
}

// ── StreamStore ──

export class StreamStore {
  private streams = new Map<string, SessionStreamState>()
  private listeners = new Set<() => void>()
  private activeReader: { sessionId: string; abort: AbortController } | null = null
  private callbacks: StreamStoreCallbacks = {}
  // 提交路径的会话绑定意图：session_created 到达前记录调用方选择的视图，
  // 供「绑定后是否保留预提交用户消息」判断（无全局 currentSessionId ref 的替代）
  private pendingView: string | null | undefined = undefined

  // 微批 emit：同一次事件循环的多个事件合并为一次通知
  private emitScheduled = false

  setCallbacks(callbacks: StreamStoreCallbacks): void {
    this.callbacks = callbacks
  }

  // ── React 订阅接口（useSyncExternalStore 契约）──

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  getSnapshot = (sessionId: string): SessionStreamState => {
    return this.streams.get(sessionId) ?? IDLE_STATE
  }

  // 获取所有活跃会话 ID（用于侧边栏运行指示）
  getActiveSessionIds(): string[] {
    const ids: string[] = []
    for (const [id, state] of this.streams) {
      if (state.phase === 'streaming' || state.phase === 'connecting' || state.phase === 'resuming') {
        ids.push(id)
      }
    }
    return ids
  }

  // 判断指定会话是否正在运行（拦截用户输入语义=前端有活跃 SSE 订阅在消费）。
  // 恢复态（rebuild 后 phase=streaming 但无 reader）不算：后端任务虽在跑，
  // 前端未订阅，允许用户发起新分析（对齐旧 abortRef 语义，避免误拦截）。
  isSessionRunning(sessionId: string): boolean {
    if (this.activeReader?.sessionId !== sessionId) return false
    return !this.activeReader.abort.signal.aborted
  }

  // 是否有活跃 SSE reader（轮询让位信号）
  hasActiveReader(): boolean {
    return this.activeReader !== null
  }

  // 删除会话时清理本地状态（终端模式等待 kill 后端任务由调用方负责）
  dropStream(sessionId: string): void {
    if (this.activeReader?.sessionId === sessionId) {
      this.activeReader.abort.abort()
      this.activeReader = null
    }
    this.streams.delete(sessionId)
    this.emit()
  }

  // 页面卸载前断开所有本地 SSE 订阅（仅退订，不调后端 cancel）
  abortAll(): void {
    if (this.activeReader) {
      this.activeReader.abort.abort()
      this.activeReader = null
    }
  }

  // 更新会话的管线消息内容（轮询快照/超时提示等组件侧低频修正）
  updatePipelineContent(sessionId: string, content: string): void {
    const state = this.streams.get(sessionId)
    if (!state) return
    const hasPipeline = state.messages.some((m) => m.type === 'pipeline' && m.progress !== 1)
    const nextMessages = hasPipeline
      ? state.messages.map((m) =>
          m.type === 'pipeline' && m.progress !== 1 ? { ...m, content } : m,
        )
      : [...state.messages, { id: genMsgId(), type: 'pipeline' as const, content, completedNodes: [], currentNode: '', nodeOutputs: {}, progress: 0, startedAt: Date.now() }]
    this.streams.set(sessionId, { ...state, messages: nextMessages })
    this.emit()
  }

  // 轮询快照刷新管线时间轴（无 pipeline 消息时按快照创建——SSE 不可用时的兜底）
  updatePipelineSnapshot(sessionId: string, snap: { layerTree: string; currentNodeId: string; progress: number }): void {
    const state = this.streams.get(sessionId)
    if (!state) return
    const hasPipeline = state.messages.some((m) => m.type === 'pipeline' && m.progress !== 1)
    const nextMessages = hasPipeline
      ? state.messages.map((m) =>
          m.type === 'pipeline' && m.progress !== 1
            ? { ...m, layerTree: deserializeLayerTree(snap.layerTree), currentNode: snap.currentNodeId, progress: snap.progress }
            : m,
        )
      : [...state.messages, { id: genMsgId(), type: 'pipeline' as const, content: '', completedNodes: [], currentNode: snap.currentNodeId, nodeOutputs: {}, progress: snap.progress, startedAt: Date.now(), layerTree: deserializeLayerTree(snap.layerTree) }]
    this.streams.set(sessionId, { ...state, messages: nextMessages })
    this.emit()
  }

  // ── 命令方法（组件唯一可调用的写入口）──

  async submit(req: AnalyzeRequest | ChatRequest, opts?: { currentView?: string | null }): Promise<void> {
    const isAnalyze = 'query' in req
    const sessionId = req.session_id || null

    // 记录提交时的视图意图，session_created 绑定时使用
    this.pendingView = opts ? opts.currentView : undefined

    // 如果已有活跃 reader，先 abort（单读取器不变量：
    // 同会话追问 abort 旧 reader；跨会话切换同样先断开旧订阅）
    if (this.activeReader) {
      this.activeReader.abort.abort()
      this.activeReader = null
    }

    // 已有状态的会话：live 状态（含在途消息）保留并追加用户消息；
    // rebuilt/pending 状态保留作为历史基础（追问场景消息已持久化在后端并重建过）
    const prev = sessionId ? (this.streams.get(sessionId) ?? IDLE_STATE) : IDLE_STATE
    const userMsg: UIMessage = {
      id: genMsgId(),
      type: 'user',
      content: isAnalyze ? (req as AnalyzeRequest).query : (req as ChatRequest).message,
    }
    const nextMessages = sessionId ? [...prev.messages, userMsg] : [userMsg]

    const targetKey = sessionId || ''
    this.streams.set(targetKey, {
      phase: 'connecting',
      messages: nextMessages,
      lastSeq: prev.lastSeq,
      origin: 'live',
    })
    this.emit()

    // 发起请求
    const url = isAnalyze ? '/api/analyze' : '/api/chat'
    const body = isAnalyze
      ? {
          query: (req as AnalyzeRequest).query,
          api_key: req.api_key,
          user_id: req.user_id,
          analysis_type: (req as AnalyzeRequest).analysis_type,
          ...(req.session_id ? { session_id: req.session_id } : {}),
          ...((req as AnalyzeRequest).stock_code ? { stock_code: (req as AnalyzeRequest).stock_code } : {}),
          ...((req as AnalyzeRequest).stock_name ? { stock_name: (req as AnalyzeRequest).stock_name } : {}),
          ...((req as AnalyzeRequest).focus ? { focus: (req as AnalyzeRequest).focus } : {}),
          ...(req.llm_config ? { llm_config: req.llm_config } : {}),
        }
      : {
          message: (req as ChatRequest).message,
          user_id: req.user_id,
          api_key: req.api_key,
          ...(req.session_id ? { session_id: req.session_id } : {}),
          ...(req.llm_config ? { llm_config: req.llm_config } : {}),
        }

    const abort = new AbortController()
    this.activeReader = { sessionId: targetKey, abort }

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: abort.signal,
      })

      if (!resp.ok) {
        if (resp.status === 409) {
          const errData = await resp.json().catch(() => ({}))
          throw new Error(errData.message || '该会话正在生成中，可停止后再发')
        }
        throw new Error(`HTTP ${resp.status}`)
      }

      await this.pump(targetKey, resp, abort.signal)
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        // 主动断开（切换会话/新建分析）：后端任务仍运行，保留相位并清 streaming 标志，
        // 切回时 selectSession 检测「live 且无 reader」会 resume 续传
        const st = this.streams.get(targetKey)
        if (st) {
          const nextMessages = st.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m))
          this.streams.set(targetKey, { ...st, messages: nextMessages })
          this.emit()
        }
        return
      }
      const prevState = this.streams.get(targetKey) ?? IDLE_STATE
      const errText = e instanceof Error ? e.message : 'Unknown error'
      // 连接级错误追加 error 消息（含 409 busy 提示）
      this.streams.set(targetKey, {
        ...prevState,
        phase: 'error',
        error: errText,
        messages: [
          ...prevState.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
          { id: genMsgId(), type: 'error', content: `错误: ${errText}` },
        ],
      })
      this.emit()
      this.callbacks.onError?.(targetKey, errText)
    } finally {
      this.pendingView = undefined
      // 同 abort 引用才清理：session_created 迁移保留原 abort 引用（仅换 sessionId），
      // 若期间已有新操作（switchSession/resume/再次 submit）替换 reader，不误清
      if (this.activeReader?.abort === abort) {
        this.activeReader = null
      }
    }
  }

  // 切换会话：abort 当前 reader；目标会话的 live 在途消息保留（继续后台写），
  // 非 live（rebuilt/pending/无）置为 pending——组件负责 loadSession + rebuildSession
  switchSession(sessionId: string | null): void {
    if (this.activeReader) {
      this.activeReader.abort.abort()
      this.activeReader = null
    }

    if (!sessionId) {
      return
    }

    const existing = this.streams.get(sessionId)
    if (existing && existing.origin === 'live') {
      // 在途会话：messages 保留（该会话的实时构建仍在内存中继续更新）
      return
    }
    // 保留 lastSeq（续传游标），置 pending 等待重建
    this.streams.set(sessionId, {
      ...IDLE_STATE,
      lastSeq: existing?.lastSeq ?? 0,
      origin: 'pending',
    })
    this.emit()
  }

  async loadSession(sessionId: string): Promise<SessionDetail | null> {
    try {
      const resp = await fetch(`/api/sessions/${sessionId}`)
      if (!resp.ok) return null
      return await resp.json()
    } catch {
      return null
    }
  }

  async resume(sessionId: string): Promise<void> {
    const state = this.streams.get(sessionId)
    if (!state) return

    // abort 当前活跃 reader（单读取器不变量）
    if (this.activeReader) {
      this.activeReader.abort.abort()
      this.activeReader = null
    }

    const abort = new AbortController()
    this.activeReader = { sessionId, abort }

    this.streams.set(sessionId, { ...state, phase: 'resuming', origin: 'live' })
    this.emit()

    try {
      const resp = await fetch(`/api/sessions/${sessionId}/stream?after_seq=${state.lastSeq}`, {
        signal: abort.signal,
      })

      if (resp.status === 204 || resp.status === 404) {
        // 204 无在途事件 / 404 会话无在途流（或端点不可用）：无增量可续传。
        // phase 从 resuming 归位 streaming（触发订阅方重渲染，让轮询 effect 在
        // 无活跃 reader 时启动接管进度刷新）；不打 idle——后端任务可能仍在运行，
        // 任务完成时轮询拉 detail 发现终态再走 selectSession 完整重建。
        const cur = this.streams.get(sessionId) ?? state
        const nextMessages = cur.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m))
        this.streams.set(sessionId, { ...cur, messages: nextMessages, phase: 'streaming' })
        this.emit()
        return
      }

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }

      await this.pump(sessionId, resp, abort.signal)
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        // 主动断开：后端任务仍运行，保留相位并清 streaming 标志（切回时可 resume）
        const st = this.streams.get(sessionId)
        if (st) {
          const nextMessages = st.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m))
          this.streams.set(sessionId, { ...st, messages: nextMessages })
          this.emit()
        }
        return
      }
      const prevState = this.streams.get(sessionId) ?? IDLE_STATE
      this.streams.set(sessionId, {
        ...prevState,
        phase: 'error',
        error: e instanceof Error ? e.message : 'Unknown error',
      })
      this.emit()
    } finally {
      if (this.activeReader?.sessionId === sessionId && this.activeReader.abort === abort) {
        this.activeReader = null
      }
    }
  }

  async cancel(sessionId: string): Promise<void> {
    // 本地 abort
    if (this.activeReader?.sessionId === sessionId) {
      this.activeReader.abort.abort()
      this.activeReader = null
    }

    // 调用后端 cancel
    try {
      await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' })
    } catch (e) {
      console.error('Failed to cancel:', e)
    }

    const state = this.streams.get(sessionId)
    if (state) {
      // 本地即时收口 streaming 状态（后端 interrupted 事件到达前 UI 不停转圈）
      const nextMessages = state.messages.map((m) =>
        m.streaming ? { ...m, streaming: false } : m,
      )
      this.streams.set(sessionId, { ...state, messages: nextMessages, phase: 'interrupted' })
      this.emit()
    }
  }

  // 从 SessionDetail 重建会话消息（供组件调用）
  rebuildMessagesFromDetail(data: SessionDetail): UIMessage[] {
    // 进行中会话（running/clarifying）走 journal replay：rebuild 只播种 user 消息
    // 作为预览/204 兜底（seededFromHistory，首个回放事件到达即清除），
    // assistant/pipeline/user 全部由 resume(after_seq=0) 全量重放 journal 重建。
    // 原因：chat_history 是事后汇总快照（只含最终 thinking/tool_calls），不含中间
    // 流式事件（thinking_token 逐步累积、节点实时进度），用它重建会残缺；
    // 而 last_seq 续传又跳过已 journal 事件 → 刷新后内容永久丢失（三次刷新 bug 根因）。
    // journal 不落用户消息，后端全量重放时按 chat_history 的 ts 注入合成
    // user_message 事件，恢复 user 气泡的原始交错顺序（气泡错位 bug 修复）。
    if (data.status === 'running' || data.status === 'clarifying') {
      const history = Array.isArray(data.chat_history) ? data.chat_history : []
      return history
        .filter((h) => h.role === 'user')
        .map((h) => ({ id: genMsgId(), type: 'user' as const, content: h.content }))
    }

    const messages: UIMessage[] = []
    const history = Array.isArray(data.chat_history) ? data.chat_history : []
    const anchor = data.pipeline_anchor ?? null
    let reportInserted = false

    // 解析管线快照
    let snapshot: { layerTree: string; currentNodeId: string; progress: number; updatedAt: number; pipeline_start_ts?: number } | null = null
    if (data.pipeline_snapshot) {
      try {
        snapshot = JSON.parse(data.pipeline_snapshot)
      } catch {
        snapshot = null
      }
    }

    const restoredNodeTimelines = data.pipeline_timelines
      ? deserializeNodeTimelines(data.pipeline_timelines)
      : undefined

    // 运行中管线消息
    const runningPipelineMsg: UIMessage | null =
      data.status === 'running' && snapshot
        ? {
            id: genMsgId(),
            type: 'pipeline',
            content: '',
            completedNodes: [],
            currentNode: snapshot.currentNodeId,
            nodeOutputs: {},
            progress: snapshot.progress,
            startedAt: snapshot.pipeline_start_ts ?? Date.now(),
            layerTree: deserializeLayerTree(snapshot.layerTree),
            ...(restoredNodeTimelines ? { nodeTimelines: restoredNodeTimelines } : {}),
          }
        : null

    // 已完成管线消息
    const pipelineDoneMsg: UIMessage | null =
      data.status === 'completed' && snapshot && data.session_type !== 'chat'
        ? {
            id: genMsgId(),
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

    // 报告消息
    const reportMsg: UIMessage | null =
      (data.status === 'completed' || data.status === 'failed') && data.session_type !== 'chat'
        ? {
            id: genMsgId(),
            type: 'report',
            content: '',
            reportMarkdown: data.report_markdown,
            chartData: data.chart_data,
            stockName: data.stock_name,
            stockCode: data.stock_code,
            filePaths: data.file_paths || undefined,
            durationMs: data.duration_ms,
            sessionId: data.session_id,
          }
        : null

    // 管线/报告插入点：anchor 指向「触发 user 之后」，但实时流中本轮 ReAct
    // agent 气泡（澄清思考/工具调用）先于 run_deep_analysis 触发的管线出现。
    // 若 anchor 处紧跟 assistant 条目，插入点顺延过连续的非 user 条目，
    // 与实时顺序 [user, agent气泡, 管线, 报告] 对齐（澄清气泡错位修复）。
    let insertAfter: number | null = anchor
    if (insertAfter !== null) {
      while (insertAfter < history.length && history[insertAfter].role !== 'user') {
        insertAfter++
      }
    }

    for (let i = 0; i < history.length; i++) {
      const h = history[i]
      if (h.role === 'user') {
        messages.push({ id: genMsgId(), type: 'user', content: h.content })
      } else {
        messages.push({
          id: genMsgId(),
          type: 'chat',
          content: '',
          chatResponse: h.content,
          agentTimeline: Array.isArray(h.agentTimeline)
            ? deserializeTimeline(h.agentTimeline)
            : buildTimelineFromHistory(h.thinking, h.tool_calls),
        })
      }

      if (anchor !== null && i + 1 === insertAfter && reportMsg && !reportInserted) {
        if (pipelineDoneMsg) messages.push(pipelineDoneMsg)
        messages.push(reportMsg)
        reportInserted = true
      }
      if (anchor === null && h.role === 'user' && reportMsg && !reportInserted) {
        if (pipelineDoneMsg) messages.push(pipelineDoneMsg)
        messages.push(reportMsg)
        reportInserted = true
      }
    }

    if (reportMsg && !reportInserted) {
      if (pipelineDoneMsg) messages.push(pipelineDoneMsg)
      messages.push(reportMsg)
    } else if (!reportMsg && pipelineDoneMsg) {
      messages.push(pipelineDoneMsg)
    }

    if (runningPipelineMsg) {
      messages.push(runningPipelineMsg)
    }

    // interrupted 会话：清除最后一条 chat 消息的 streaming
    if (data.status === 'interrupted') {
      const lastChat = [...messages].reverse().find((m) => m.type === 'chat')
      if (lastChat) {
        lastChat.streaming = false
      }
    }

    return messages
  }

  // 重建会话状态（switchSession 置 pending 后由组件调用）。
  // 进行中会话（running/clarifying）走 journal replay：rebuild 只保留 user 消息，
  // lastSeq=0 让 resume 从头全量重放 journal，逐条累积出完整的 assistant/pipeline。
  // 终态会话（completed/failed/interrupted）用 chat_history 完整快照重建（已是最终结果），
  // lastSeq 取后端 last_seq（不再续传）。
  rebuildSession(sessionId: string, data: SessionDetail): void {
    const messages = this.rebuildMessagesFromDetail(data)
    const isInFlight = data.status === 'running' || data.status === 'clarifying'
    // 进行中：lastSeq=0（全量 replay）；终态：用后端 last_seq
    const lastSeq = isInFlight ? 0 : (data.last_seq ?? 0)

    let phase: StreamPhase = 'idle'
    if (data.status === 'running') phase = 'streaming'
    else if (data.status === 'completed') phase = 'done'
    else if (data.status === 'interrupted') phase = 'interrupted'
    else if (data.status === 'failed') phase = 'error'
    else if (data.status === 'clarifying') phase = 'awaiting_input'

    this.streams.set(sessionId, {
      phase,
      messages,
      lastSeq,
      origin: 'rebuilt',
      // 进行中会话的 messages 只是 user 种子（预览/204 兜底）；首个回放事件
      // 到达时清除，由全量回放（含 user_message 注入）按原始顺序重建
      ...(isInFlight && messages.length > 0 ? { seededFromHistory: true } : {}),
    })
    this.emit()
  }

  // ── 内部 ──

  private async pump(sessionId: string, resp: Response, signal?: AbortSignal): Promise<void> {
    const reader = resp.body?.getReader()
    if (!reader) return

    const decoder = new TextDecoder()
    let buffer = ''

    try {
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
            // session_created 迁移后 activeReader.sessionId 已换为实际 key，
            // 后续事件必须写入新 key（旧 key 的流状态已删除）
            const key = this.activeReader?.sessionId ?? sessionId
            this.applyEvent(key, event)
          } catch {
            // Skip malformed lines
          }
        }
      }
    } finally {
      reader.releaseLock()
    }

    // 主动 abort（切换会话/新建分析）：后端任务仍运行，保留 streaming 相位，
    // 切回时可 resume 续传；仅清 streaming 标志避免 UI 无限转圈。
    if (signal?.aborted) {
      const abortedKey = sessionId
      const st = this.streams.get(abortedKey)
      if (st) {
        const nextMessages = st.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m))
        this.streams.set(abortedKey, { ...st, messages: nextMessages })
        this.emit()
      }
      return
    }

    // 流自然结束但未收到终态事件：防御性清理（连接被服务端关闭且无 done）
    const finalKey = this.activeReader?.sessionId ?? sessionId
    const state = this.streams.get(finalKey)
    if (state && (state.phase === 'streaming' || state.phase === 'resuming' || state.phase === 'connecting')) {
      const nextMessages = state.messages.map((m) =>
        m.streaming ? { ...m, streaming: false } : m,
      )
      this.streams.set(finalKey, { ...state, messages: nextMessages, phase: 'idle' })
      this.emit()
      this.callbacks.onSessionsChanged?.()
    }
  }

  private applyEvent(sessionId: string, event: SSEEvent): void {
    let prev = this.streams.get(sessionId) ?? IDLE_STATE

    // 首个回放/实时事件到达：丢弃 chat_history user 种子（堆叠失序的预览），
    // 从空开始按事件顺序重建——回放流含后端注入的 user_message，顺序正确
    if (prev.seededFromHistory) {
      prev = { ...prev, messages: [], seededFromHistory: false }
      this.streams.set(sessionId, prev)
    }

    // session_created 特殊处理：把临时 key（''）或旧 key 的提交态迁移到实际 sessionId。
    // 视图意图判断：提交后用户未切换视图（pendingView 为空/未变）时保留预提交
    // 的用户消息；已切到其他会话则丢弃（新会话的构建从事件流重新开始）。
    if (event.type === 'session_created') {
      const actualSessionId = event.session_id
      if (sessionId !== actualSessionId) {
        const state = this.streams.get(sessionId) ?? IDLE_STATE
        this.streams.delete(sessionId)
        const keepMessages = this.pendingView === null || this.pendingView === undefined
        this.streams.set(actualSessionId, {
          ...state,
          messages: keepMessages ? state.messages : [],
          lastSeq: event.seq ?? state.lastSeq,
          origin: 'live',
        })
        // 迁移 reader 绑定，后续事件写入实际 sessionId
        if (this.activeReader?.sessionId === sessionId) {
          this.activeReader = { sessionId: actualSessionId, abort: this.activeReader.abort }
        }
        this.callbacks.onSessionCreated?.(actualSessionId, event.display_name)
        this.callbacks.onSessionsChanged?.()
        this.emit()
        return
      }
    }

    // seq 守门：去重过期事件
    if (event.seq !== undefined) {
      if (event.seq <= prev.lastSeq) {
        return // 过期事件丢弃
      }
      // seq 空洞检测：event.seq > lastSeq + 1 时触发 resync
      if (event.seq > prev.lastSeq + 1 && prev.lastSeq > 0) {
        // 触发 resume 补齐缺失事件（异步，不阻塞当前事件处理）
        void this.resume(sessionId)
        return
      }
    }

    const next = reduce(prev, event)
    next.lastSeq = event.seq ?? prev.lastSeq
    this.streams.set(sessionId, next)

    // phase 变化通知
    if (next.phase !== prev.phase) {
      this.callbacks.onPhaseChange?.(sessionId, next.phase)
    }

    // report_ready：记录 ETA 历史耗时 + 刷新会话列表
    if (event.type === 'report_ready') {
      if (event.duration_ms > 0) recordDuration(event.duration_ms)
      this.callbacks.onSessionsChanged?.()
    }

    // 终态事件：刷新会话列表（移除侧边栏运行指示）
    if (event.type === 'done' || event.type === 'interrupted' || event.type === 'error') {
      this.callbacks.onSessionsChanged?.()
    }

    this.emit()
  }

  private emit(): void {
    if (this.emitScheduled) return
    this.emitScheduled = true
    queueMicrotask(() => {
      this.emitScheduled = false
      this.listeners.forEach((fn) => fn())
    })
  }
}

// ── 模块级单例 ──

let storeInstance: StreamStore | null = null

export function getStreamStore(): StreamStore {
  if (!storeInstance) {
    storeInstance = new StreamStore()
  }
  return storeInstance
}

// 测试用：重置单例
export function resetStreamStore(): void {
  storeInstance = null
}
