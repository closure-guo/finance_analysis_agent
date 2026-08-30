import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import {
  AssistantRuntimeProvider,
  MessagePrimitive,
  ThreadPrimitive,
} from '@assistant-ui/react'
import type { AssistantRuntime } from '@assistant-ui/core'
import type {
  ReasoningMessagePartComponent,
  TextMessagePartComponent,
  ToolCallMessagePartComponent,
} from '@assistant-ui/core/react'
import { useAgUiRuntime } from '@assistant-ui/react-ag-ui'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { createQuickAgent } from './aguiAgent'
import type { LLMConfigPayload } from '../llmConfig'

// add-assistant-ui-thread Task 3a：quick 模式 assistant-ui Thread。
//
// 渲染路径（调研 §3.3 路径 (a)）：历史消息由 App 现有 MessageItem 渲染
// （streamStore rebuildSession 快照），本组件只接管挂载后发起的新 run——
// agentTimeline 横幅语义不变，Thread 不参与历史初始化。
//
// 发送路径：App.quickChat 经 handle.send() → runtime.thread.append →
// useAgUiRuntime 驱动 HttpAgent.runAgent（POST /api/agui/quick，SSE）。
// 切换守卫：App 在 selectSession/newAnalysis 时调用 handle.abort()
// （HttpAgent.abortRun，官方 API）→ 服务端 CancelledError → 中断落库。
//
// 视觉：design-system 令牌（var(--bg-*)/var(--text-*)），无硬编码色值。

export interface QuickThreadHandle {
  /** 发送一条用户消息并启动 run（发送前由调用方负责 isRunning 守卫） */
  send: (message: string) => void
  /** 中止当前 run（HttpAgent.abortRun） */
  abort: () => void
  isRunning: () => boolean
}

export interface QuickThreadProps {
  apiKey: string
  /** 请求级 LLM 配置（forwardedProps 透传，语义对齐现有通道 llm_config） */
  llmConfig?: LLMConfigPayload | null
  /** RUN_STARTED.thread_id 回传（新会话创建时由 App 绑定会话） */
  onSessionCreated?: (sessionId: string) => void
  /** run 正常结束（RUN_FINISHED） */
  onRunFinished?: () => void
  /** run 生命周期（流式指示/停止按钮显隐由 App 据此驱动） */
  onRunningChange?: (running: boolean) => void
  /** run 错误（RUN_ERROR / HTTP 失败 / 断连）——409 busy 等在此等价呈现 */
  onError?: (message: string) => void
}

// Markdown 文本渲染（与 App 中 chat response 同款 remark-gfm 配置）
const MarkdownText: TextMessagePartComponent = ({ text }) => (
  <div className="prose prose-sm max-w-none">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
            style={{ color: 'var(--bg-brand)' }}
          >
            {children}
          </a>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  </div>
)

// 思考段（REASONING_MESSAGE_* → reasoning part）：弱化色块呈现
const ReasoningBlock: ReasoningMessagePartComponent = ({ text }) => (
  <div
    className="text-xs leading-relaxed whitespace-pre-wrap rounded-lg px-3 py-2 mb-2"
    style={{ color: 'var(--text-tertiary)', background: 'var(--bg-overlay-l1)' }}
  >
    {text}
  </div>
)

// 工具调用段（TOOL_CALL_* → tool-call part）：单行横幅
const ToolCallBlock: ToolCallMessagePartComponent = ({ toolName }) => (
  <div
    className="text-xs rounded-lg px-3 py-1.5 mb-2 inline-flex items-center gap-1.5"
    style={{ color: 'var(--text-secondary)', background: 'var(--bg-overlay-l1)' }}
  >
    <i className="fas fa-tools text-[10px]" style={{ color: 'var(--text-brand)' }}></i>
    <span>调用工具 · {toolName}</span>
  </div>
)

const QuickUserMessage = () => (
  <div className="flex justify-end animate-slide-in" data-testid="agui-user-message">
    <div className="max-w-[85%] md:max-w-[75%]">
      <div
        className="msg-user rounded-2xl rounded-tr-sm px-5 py-3 text-sm leading-relaxed"
        style={{ color: 'var(--text-onbrand)' }}
      >
        <MessagePrimitive.Parts components={{ Text: ({ text }) => <span>{text}</span> }} />
      </div>
    </div>
  </div>
)

const QuickAssistantMessage = () => (
  <div className="flex justify-start animate-slide-in" data-testid="agui-assistant-message">
    <div className="max-w-[95%] md:max-w-[90%] w-full">
      <div className="flex items-start gap-3">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1"
          style={{ background: 'var(--bg-brand)' }}
        >
          <i className="fas fa-robot text-white text-xs"></i>
        </div>
        <div className="flex-1 min-w-0 text-sm" style={{ color: 'var(--text-secondary)' }}>
          <MessagePrimitive.Parts
            components={{ Text: MarkdownText, Reasoning: ReasoningBlock, tools: { Fallback: ToolCallBlock } }}
          />
        </div>
      </div>
    </div>
  </div>
)

const QuickThread = forwardRef<QuickThreadHandle, QuickThreadProps>(function QuickThread(
  { apiKey, llmConfig = null, onSessionCreated, onRunFinished, onRunningChange, onError },
  ref,
) {
  // agent 每个 mount 创建一次（会话切换守卫由 App 通过 key 重挂载实现）
  const [agent] = useState(() => createQuickAgent({ apiKey, llmConfig }))
  const runtimeRef = useRef<AssistantRuntime | null>(null)
  // 回调经 ref 透传最新引用（避免回调 identity 变化重建 runtime/订阅）
  const callbacksRef = useRef({ onSessionCreated, onRunFinished, onRunningChange, onError })
  callbacksRef.current = { onSessionCreated, onRunFinished, onRunningChange, onError }

  const runtime = useAgUiRuntime({
    agent,
    showThinking: true,
    onError: (e) => callbacksRef.current.onError?.(e.message || '生成失败，请稍后重试'),
  })
  runtimeRef.current = runtime

  // agent 事件订阅：会话创建回传 + run 生命周期（与 runtime 订阅并行，官方 Subscriber API）
  useEffect(() => {
    let running = false
    const setRunning = (v: boolean) => {
      if (v === running) return
      running = v
      callbacksRef.current.onRunningChange?.(v)
    }
    const sub = agent.subscribe({
      onRunStartedEvent: ({ event }) => {
        setRunning(true)
        const threadId = (event as { threadId?: string }).threadId
        if (threadId) callbacksRef.current.onSessionCreated?.(threadId)
      },
      onRunFinishedEvent: () => {
        setRunning(false)
        callbacksRef.current.onRunFinished?.()
      },
      onRunErrorEvent: ({ event }) => {
        setRunning(false)
        callbacksRef.current.onError?.(event.message || '生成失败，请稍后重试')
      },
      onRunFailed: ({ error }) => {
        setRunning(false)
        callbacksRef.current.onError?.(error.message || '生成失败，请稍后重试')
      },
    })
    return () => sub.unsubscribe()
  }, [agent])

  useImperativeHandle(
    ref,
    () => ({
      send: (message: string) => {
        try {
          runtimeRef.current?.thread.append(message)
        } catch {
          // 发送失败（断连等）：错误已经 runtime onError 上报，这里兜底不再抛出
        }
      },
      abort: () => agent.abortRun(),
      isRunning: () => agent.isRunning,
    }),
    [agent],
  )

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="w-full" data-testid="agui-thread">
        <ThreadPrimitive.Root>
          <ThreadPrimitive.Viewport
            autoScroll
            className="flex flex-col gap-4 overflow-y-visible"
          >
            <ThreadPrimitive.Messages
              components={{ UserMessage: QuickUserMessage, AssistantMessage: QuickAssistantMessage }}
            />
            <ThreadPrimitive.If running>
              <div
                data-testid="agui-stream-status"
                className="flex items-center gap-2 px-1"
                style={{ color: 'var(--text-tertiary)' }}
              >
                <span
                  className="block w-3 h-3 rounded-full border-2 border-t-transparent animate-spin"
                  style={{ borderColor: 'var(--bg-brand)' }}
                ></span>
              </div>
            </ThreadPrimitive.If>
          </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
      </div>
    </AssistantRuntimeProvider>
  )
})

export default QuickThread
