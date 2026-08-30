// adopt-assistant-ui-chat Task 2.3/3.1/3.2/4.1：深度分析通道 assistant-ui Thread。
//
// 架构（design.md 决策 2/3/4）：
// - streamStore 仍是 SSE 归约/续传/重建的唯一事实源；本组件经
//   useExternalStoreRuntime 把 UIMessage[]（经 adapter 翻译）接入 assistant-ui，
//   onNew/onCancel 桥接回 App 的 startAnalysis/stopGeneration——后端协议零改动。
// - 消息渲染全部由 assistant-ui 消息部件承载：
//   reasoning → 思考折叠卡（ThinkingBanner）；tool-call → 工具调用卡（ToolCallBanner）；
//   data-search → 搜索横幅；data-pipeline/report/system/error → 项目独有部件
//   （PipelineCard/ReportCard 原样挂载，ECharts/导出能力不丢）。
// - Viewport autoScroll 提供流式跟随/上翻暂停/回底恢复；中断由 onCancel 桥接
//   store.cancel，已生成内容保留在 streamStore（中断保留语义）。
//
// 测试 DOM 契约（既有测试无修改通过）：chat 消息容器 data-testid="stream-output"
// （含思考/工具横幅与正文）；流式光标 data-testid="stream-status"。
import type { ReactNode } from 'react'
import {
  AssistantRuntimeProvider,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useExternalStoreRuntime,
  type AppendMessage,
  type DataMessagePartComponent,
  type ReasoningMessagePartComponent,
  type TextMessagePartComponent,
  type ToolCallMessagePartComponent,
} from '@assistant-ui/react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { DATA_PART, translateMessage } from './adapter'
import type { UIMessage } from '../types'
import { extractThinkingTitle, PipelineCard, ReportCard, ThinkingBanner, ToolCallBanner } from '../App'
import { SearchBanner } from '../SearchBanner'
import { timelineToolCallToEntry } from '../timeline'

// AppendMessage → 纯文本（Composer 提交内容；本项目无附件/多模态）
export function extractComposerText(message: AppendMessage): string {
  return message.content
    .filter((c): c is Extract<typeof c, { type: 'text' }> => c.type === 'text')
    .map((c) => c.text)
    .join('')
}

// ── 消息头像（chat/system/error 消息共用，与原 MessageRenderer 视觉一致）──
function AssistantAvatar({ bg }: { bg?: string }) {
  return (
    <div
      className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1"
      style={{ background: bg ?? 'var(--bg-brand)' }}
    >
      <i className={`fas ${bg ? 'fa-exclamation' : 'fa-robot'} text-white text-xs`}></i>
    </div>
  )
}

// ── 部件组件 ──

// 正文 Markdown（与原 chat response 同款 remark-gfm 配置）；流式 running 时跟随光标
const MarkdownText: TextMessagePartComponent = ({ text, status }) => (
  <div className={`prose prose-sm max-w-none px-1 py-1 response-streaming ${status?.type === 'running' ? 'is-streaming' : ''}`}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: 'var(--bg-brand)' }}>
            {children}
          </a>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
    {status?.type === 'running' && (
      <span data-testid="stream-status" className="streaming-cursor">
        <span className="block w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'var(--bg-brand)' }}></span>
      </span>
    )}
  </div>
)

// 思考折叠卡：流式中"思考中"自动展开，完成后收起、可展开（ThinkingBanner 内建语义）
const ReasoningCard: ReasoningMessagePartComponent = ({ text, status }) => (
  <ThinkingBanner
    content={text}
    streaming={status?.type === 'running'}
    title={extractThinkingTitle(text)}
  />
)

// 工具调用卡：loading（执行中）/ 完成（结果摘要）；loading 语义经 artifact.done 传递
const ToolCallCard: ToolCallMessagePartComponent = (props) => {
  const done = (props.artifact as { done?: boolean } | undefined)?.done === true
  const entry = timelineToolCallToEntry({
    type: 'tool_call',
    name: props.toolName,
    args: props.argsText ?? '',
    result: typeof props.result === 'string' ? props.result : props.result != null ? String(props.result) : undefined,
    done,
  })
  return <ToolCallBanner toolCalls={[entry]} streaming={!done} />
}

// 搜索横幅（search_* 事件 → data-search 部件）
const SearchPart: DataMessagePartComponent = ({ data }) => {
  const d = data as { status: 'searching' | 'done' | 'error'; query?: string; results?: Array<{ title: string; url: string; content: string }> }
  return <SearchBanner status={d.status} query={d.query} results={d.results} />
}

// 项目独有部件（Task 4.1）：管线时间线 / 报告（含 ECharts、导出 filePaths）
const PipelinePart: DataMessagePartComponent = ({ data }) => <PipelineCard msg={data as UIMessage} />
const ReportPart: DataMessagePartComponent = ({ data }) => <ReportCard msg={data as UIMessage} />

// system / error 消息（原 MessageRenderer 对应分支的视觉迁移）
const SystemPart: DataMessagePartComponent = ({ data }) => (
  <div className="msg-system rounded-xl rounded-tl-sm px-5 py-3 flex-1">
    <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--status-success-default)' }}>
      <i className="fas fa-check-circle"></i>
      <span>{(data as { content: string }).content}</span>
    </div>
  </div>
)

const ErrorPart: DataMessagePartComponent = ({ data }) => (
  <div className="msg-system rounded-xl rounded-tl-sm px-5 py-3 flex-1">
    <p className="text-sm" style={{ color: 'var(--status-error-default)' }}>
      {(data as { content: string }).content}
    </p>
  </div>
)

// 部件渲染映射（chat 消息：横幅 + 正文；其余：data 部件承载整卡）
const chatPartsComponents = {
  Text: MarkdownText,
  Reasoning: ReasoningCard,
  tools: { Fallback: ToolCallCard },
  data: { by_name: { [DATA_PART.search.slice(5)]: SearchPart } },
}

const dataPartsComponents = {
  data: {
    by_name: {
      [DATA_PART.pipeline.slice(5)]: PipelinePart,
      [DATA_PART.report.slice(5)]: ReportPart,
      [DATA_PART.system.slice(5)]: SystemPart,
      [DATA_PART.error.slice(5)]: ErrorPart,
    },
  },
}

// ── 消息容器 ──

const UserMessage = () => (
  <div className="flex justify-end animate-slide-in">
    <div className="max-w-[85%] md:max-w-[75%]">
      <div className="msg-user rounded-2xl rounded-tr-sm px-5 py-3 text-sm leading-relaxed" style={{ color: 'var(--text-onbrand)' }}>
        <MessagePrimitive.Parts components={{ Text: ({ text }) => <span>{text}</span> }} />
      </div>
    </div>
  </div>
)

const AssistantMessage = () => {
  // 消息形态标记（adapter metadata.custom.kind）
  const kind = useAuiState((s) => s.message.metadata?.custom?.kind as string | undefined)
  if (kind === 'chat') {
    // chat 消息容器：思考/工具横幅与正文同容器（stream-output 测试契约）
    return (
      <div className="flex justify-start animate-slide-in" data-testid="stream-output">
        <div className="max-w-[95%] md:max-w-[90%] w-full">
          <div className="flex items-start gap-3">
            <AssistantAvatar />
            <div className="flex-1 min-w-0 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <MessagePrimitive.Parts components={chatPartsComponents} />
            </div>
          </div>
        </div>
      </div>
    )
  }
  // pipeline/report/system/error：整卡由 data 部件组件承载
  const errorKind = kind === 'error'
  return (
    <div className="flex justify-start animate-slide-in" data-testid={errorKind ? 'stream-error' : undefined}>
      <div className="max-w-[95%] md:max-w-[90%] w-full">
        <div className="flex items-start gap-3">
          <AssistantAvatar bg={errorKind ? 'var(--status-error-default)' : undefined} />
          <MessagePrimitive.Parts components={dataPartsComponents} />
        </div>
      </div>
    </div>
  )
}

// ── 对外组件 ──

export interface AnalysisRuntimeProviderProps {
  /** streamStore 当前会话消息（唯一事实源） */
  messages: UIMessage[]
  /** 运行中（流式/连接/恢复/quick run）——驱动 Composer 发送↔停止切换 */
  isRunning: boolean
  /** Composer 提交（App 内按 mode 分发 quick/deep，各自守卫+toast 语义不变） */
  onSubmit: (text: string) => void
  /** 停止按钮（Composer Cancel + 独立停止按钮共用） */
  onCancel: () => void
  children: ReactNode
}

// Runtime Provider：把 streamStore 状态接入 assistant-ui（ExternalStore 模式）。
// 输入区（Composer）与消息区（ThreadMessages）都渲染在其内部以获得 runtime 上下文。
export function AnalysisRuntimeProvider({ messages, isRunning, onSubmit, onCancel, children }: AnalysisRuntimeProviderProps) {
  const runtime = useExternalStoreRuntime({
    messages,
    convertMessage: translateMessage,
    isRunning,
    onNew: async (message) => {
      onSubmit(extractComposerText(message))
    },
    onCancel: async () => {
      onCancel()
    },
  })
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
}

export interface ThreadMessagesProps {
  /** 视口尾部附加内容（会话级导出横幅、quick 通道 Thread） */
  footer?: ReactNode
}

// 消息区：Viewport autoScroll 提供流式跟随/上翻暂停/回底恢复（delta spec）
export function ThreadMessages({ footer }: ThreadMessagesProps) {
  return (
    <ThreadPrimitive.Root className="h-full">
      <ThreadPrimitive.Viewport autoScroll className="h-full overflow-y-auto">
        <div className="w-full max-w-3xl mx-auto px-4 pt-20 pb-40 flex flex-col gap-6">
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
          {footer}
        </div>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  )
}
