import type { SSEEvent, UIMessage } from '../../types'
import type { SessionStreamState } from './types'
import { genMsgId } from './types'
import {
  applyChatStreamEvent,
  applyPipelineThinkingToken,
  applyPipelineNodeComplete,
} from '../../timeline'
import { buildLayerTree, applyNodeEvent } from '../../pipelineTree'

// 搜索类工具集合（与 App.tsx isSearchTool 保持一致）
const SEARCH_TOOL_NAMES = new Set<string>(['web_search', 'batch_web_search'])

function isSearchToolName(name: string): boolean {
  return SEARCH_TOOL_NAMES.has(name)
}

// ── 消息查找辅助 ──

function findLastChatMessage(messages: UIMessage[]): UIMessage | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].type === 'chat') return messages[i]
  }
  return undefined
}

function findLastPipelineMessage(messages: UIMessage[]): UIMessage | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].type === 'pipeline') return messages[i]
  }
  return undefined
}

function findLastReportMessage(messages: UIMessage[]): UIMessage | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].type === 'report') return messages[i]
  }
  return undefined
}

function updateMessage(messages: UIMessage[], id: string, updates: Partial<UIMessage>): UIMessage[] {
  return messages.map((m) => (m.id === id ? { ...m, ...updates } : m))
}

// ── 对话流事件处理（复用 timeline.ts 纯函数）──

// 获取或创建当前回复的助手消息（承载思考过程、工具调用、澄清回复）。
// 仅当最后一条消息是仍在 streaming 的 chat 时才复用（同一条回复的后续事件）；
// 否则创建新 chat 消息——对齐旧 ensureAssistantMsg 语义：新一轮回复开新消息，
// 避免追问时把 token 追加到上一轮的完整回复上（重复/串字根因）。
function applyChatEventToLastChat(messages: UIMessage[], event: SSEEvent): UIMessage[] {
  const last = messages[messages.length - 1]
  if (last && last.type === 'chat' && last.streaming) {
    return messages.map((m) => (m.id === last.id ? applyChatStreamEvent(m, event) : m))
  }
  const newMsg: UIMessage = {
    id: genMsgId(),
    type: 'chat',
    content: '',
    chatResponse: '',
    streaming: true,
    agentTimeline: [],
  }
  return [...messages, applyChatStreamEvent(newMsg, event)]
}

// ── 管线事件处理 ──

// 获取或创建当前轮管线消息：仅复用未完成（progress!==1）的管线；
// 上一轮的完整管线（progress===1 静态时间轴）不复用，追问时新建，
// 避免新一轮进度事件覆盖旧时间轴（对齐 chat 消息的新轮语义）。
function ensurePipelineMessage(messages: UIMessage[], content: string): UIMessage[] {
  const existing = findLastPipelineMessage(messages)
  if (existing && existing.progress !== 1) return messages
  return [
    ...messages,
    {
      id: genMsgId(),
      type: 'pipeline',
      content,
      completedNodes: [],
      currentNode: '',
      nodeOutputs: {},
      progress: 0,
      startedAt: Date.now(),
    },
  ]
}

function applyPipelineEvent(messages: UIMessage[], event: SSEEvent): UIMessage[] {
  const before = findLastPipelineMessage(messages)
  if (!before || before.progress === 1) {
    messages = ensurePipelineMessage(messages, '深度分析进行中...')
  }
  const pipelineMsg = findLastPipelineMessage(messages)!

  switch (event.type) {
    case 'parsing':
      return updateMessage(messages, pipelineMsg.id, {
        content: `正在识别：${event.query}...`,
      })

    case 'resolved':
      return updateMessage(messages, pipelineMsg.id, {
        content: `已识别：${event.stock_name} (${event.stock_code})`,
      })

    case 'analysis_start':
      return updateMessage(messages, pipelineMsg.id, {
        content: `开始分析 ${event.stock_name} (${event.stock_code})`,
      })

    case 'node_start':
      return updateMessage(messages, pipelineMsg.id, {
        currentNode: event.node_id,
        content: `${event.layer}: ${event.desc}...`,
        layerTree: applyNodeEvent(pipelineMsg.layerTree ?? buildLayerTree(), event, Date.now()),
      })

    case 'node_timing':
      return updateMessage(messages, pipelineMsg.id, {
        layerTree: applyNodeEvent(pipelineMsg.layerTree ?? buildLayerTree(), event, Date.now()),
      })

    case 'node_complete':
      return updateMessage(messages, pipelineMsg.id, {
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

    case 'thinking_token':
      // 管线运行期间的思考按 node 字段写入对应 agent 阶段的 timeline
      return updateMessage(messages, pipelineMsg.id, applyPipelineThinkingToken(pipelineMsg, event))

    case 'error':
      return updateMessage(messages, pipelineMsg.id, {
        type: 'error',
        content: `错误: ${event.message}`,
      })

    default:
      return messages
  }
}

// ── 报告流事件处理 ──

function applyReportEvent(messages: UIMessage[], event: SSEEvent): UIMessage[] {
  switch (event.type) {
    case 'report_chunk': {
      const reportMsg = findLastReportMessage(messages)
      if (!reportMsg) {
        // 创建新的流式报告消息
        return [
          ...messages,
          {
            id: genMsgId(),
            type: 'report',
            content: '',
            reportMarkdown: event.text,
            streaming: true,
          },
        ]
      }
      // 累加到现有报告消息
      const newText = (reportMsg.reportMarkdown || '') + event.text
      return updateMessage(messages, reportMsg.id, { reportMarkdown: newText })
    }

    case 'report_ready': {
      const reportMsg = findLastReportMessage(messages)
      const updates: Partial<UIMessage> = {
        reportMarkdown: event.report_markdown,
        chartData: event.chart_data,
        filePaths: event.file_paths,
        stockName: event.stock_name,
        durationMs: event.duration_ms,
        sessionId: event.session_id,
        webSources: event.web_sources || [],
        streaming: false,
      }
      if (reportMsg) {
        return updateMessage(messages, reportMsg.id, updates)
      }
      // 无流式分块直接就绪：创建完整报告消息
      return [
        ...messages,
        {
          id: genMsgId(),
          type: 'report',
          content: '',
          ...updates,
        },
      ]
    }

    default:
      return messages
  }
}

// ── 主 reduce 函数 ──

export function reduce(state: SessionStreamState, event: SSEEvent): SessionStreamState {
  const { messages } = state

  switch (event.type) {
    // ── 会话创建（store 层处理，reduce 中仅确认 sessionId 绑定）──
    case 'session_created':
      return state

    // ── 合成用户消息（刷新全量回放注入）：按回放位置追加 user 气泡，
    // 恢复原始交错顺序（修复多轮会话刷新后 user 气泡堆叠错位）──
    case 'user_message':
      return {
        ...state,
        messages: [...messages, { id: genMsgId(), type: 'user', content: event.content }],
      }

    // ── 解析与识别 ──
    case 'parsing':
    case 'resolved':
      return { ...state, messages: applyPipelineEvent(messages, event) }

    case 'stock_resolved': {
      const pipelineMsg = findLastPipelineMessage(messages)
      if (pipelineMsg) {
        return {
          ...state,
          messages: updateMessage(messages, pipelineMsg.id, {
            content: `已识别：${event.stock_name} (${event.stock_code})`,
          }),
        }
      }
      // 澄清阶段：作为 search_stock 的结构化结果写入 timeline（无 chat 消息时自动创建）
      const toolResultEvent: SSEEvent = {
        type: 'tool_result',
        name: 'search_stock',
        result: `已识别：${event.stock_name} (${event.stock_code})`,
        timestamp: '',
      } as SSEEvent
      return { ...state, messages: applyChatEventToLastChat(messages, toolResultEvent) }
    }

    // ── 管线生命周期 ──
    case 'analysis_start': {
      const pipelineMsg: UIMessage = {
        id: genMsgId(),
        type: 'pipeline',
        content: `开始分析 ${event.stock_name} (${event.stock_code})`,
        completedNodes: [],
        currentNode: '',
        nodeOutputs: {},
        progress: 0,
        startedAt: Date.now(),
      }
      return {
        ...state,
        phase: 'streaming',
        messages: [...messages, pipelineMsg],
      }
    }

    case 'node_start':
    case 'node_timing':
    case 'node_complete':
      return { ...state, messages: applyPipelineEvent(messages, event) }

    // ── 思考流 ──
    case 'thinking_token': {
      if (event.node) {
        // 管线节点思考
        return { ...state, messages: applyPipelineEvent(messages, event) }
      }
      // 对话流思考
      return { ...state, messages: applyChatEventToLastChat(messages, event) }
    }

    case 'thinking_replace':
    case 'thinking_to_answer':
      return { ...state, messages: applyChatEventToLastChat(messages, event) }

    // ── 工具调用 ──
    case 'tool_call': {
      if (event.name === 'run_deep_analysis') {
        // 触发管线 UI
        const pipelineMsg: UIMessage = {
          id: genMsgId(),
          type: 'pipeline',
          content: '开始深度分析...',
          completedNodes: [],
          currentNode: '',
          nodeOutputs: {},
          progress: 0,
          startedAt: Date.now(),
        }
        return {
          ...state,
          phase: 'streaming',
          messages: [...messages, pipelineMsg],
        }
      }
      if (isSearchToolName(event.name)) {
        // 搜索类工具走 search item，不生成 tool_call
        return state
      }
      return { ...state, messages: applyChatEventToLastChat(messages, event) }
    }

    case 'tool_result': {
      if (event.name === 'run_deep_analysis' || isSearchToolName(event.name)) {
        return state
      }
      return { ...state, messages: applyChatEventToLastChat(messages, event) }
    }

    // ── 搜索 ──
    case 'search_start':
    case 'search_result':
    case 'search_error':
      return { ...state, messages: applyChatEventToLastChat(messages, event) }

    // ── 报告流 ──
    case 'report_chunk':
    case 'report_ready':
      return { ...state, messages: applyReportEvent(messages, event) }

    // ── 对话流 ──
    case 'chat_token': {
      const chatMsg = findLastChatMessage(messages)
      if (!chatMsg) {
        // 创建新的助手消息
        return {
          ...state,
          messages: [
            ...messages,
            {
              id: genMsgId(),
              type: 'chat',
              content: '',
              chatResponse: event.token,
              streaming: true,
            },
          ],
        }
      }
      return { ...state, messages: applyChatEventToLastChat(messages, event) }
    }

    case 'chat_done': {
      const chatMsg = findLastChatMessage(messages)
      if (!chatMsg) return state
      const nextMessages = messages.map((m) => (m.id === chatMsg.id ? applyChatStreamEvent(m, event) : m))
      return { ...state, messages: nextMessages }
    }

    // ── 状态转换 ──
    case 'awaiting_input': {
      // 管线等待输入：停留在澄清视图，管线消息保留展示但不再视为运行中
      const nextMessages = messages.map((m) =>
        m.streaming ? { ...m, streaming: false } : m,
      )
      return { ...state, phase: 'awaiting_input', messages: nextMessages }
    }

    case 'done': {
      const nextMessages = messages.map((m) =>
        m.streaming ? { ...m, streaming: false } : m,
      )
      return { ...state, phase: 'done', messages: nextMessages }
    }

    case 'interrupted': {
      const nextMessages = messages.map((m) => {
        let next = m.streaming ? { ...m, streaming: false } : m
        // 运行中管线收口提示（progress===1 的已完成时间轴不覆盖）
        if (next.type === 'pipeline' && next.progress !== 1) {
          next = { ...next, content: '输出已中断，可追问继续' }
        }
        return next
      })
      return { ...state, phase: 'interrupted', messages: nextMessages }
    }

    case 'error': {
      // 管线模式下更新管线消息，否则添加 error 消息
      const pipelineMsg = findLastPipelineMessage(messages)
      if (pipelineMsg) {
        return {
          ...state,
          phase: 'error',
          messages: applyPipelineEvent(messages, event),
          error: event.message,
        }
      }
      const errorMsg: UIMessage = {
        id: genMsgId(),
        type: 'error',
        content: `错误: ${event.message}`,
      }
      return {
        ...state,
        phase: 'error',
        messages: [...messages, errorMsg],
        error: event.message,
      }
    }

    default:
      return state
  }
}
