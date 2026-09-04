// adopt-assistant-ui-chat Task 2.2：SSE 适配层（唯一手写翻译层）。
//
// 职责：把 streamStore 归约产物 UIMessage 翻译为 assistant-ui 消息部件
// （ThreadMessageLike），不含任何副作用——SSE 连接、seq 去重、续传、重建
// 全部保留在 streamStore（非目标：session-store 语义不变）。
//
// 事件 → 部件映射表见 docs/superpowers/plans/2026-08-30-adopt-assistant-ui-chat.md：
// - agentTimeline thinking → reasoning 部件（思考折叠卡数据源）
// - agentTimeline tool_call → tool-call 部件（loading 语义经 artifact.done 传递，
//   result 缺省不触发 runtime requires-action 状态机）
// - agentTimeline search → data-search 部件
// - pipeline / report / system / error 消息 → data-* 部件（自定义部件承载项目独有 UI）
// - chatResponse → text 部件（流式中 status running，供渲染层显示光标）
//
// 未知事件类型在 streamStore.reduce 的 default 分支已安全忽略（forward-compatible），
// 本层不做二次过滤。
import type { ThreadMessageLike } from '@assistant-ui/react'
import type { ReadonlyJSONObject } from 'assistant-stream/utils'
import type { UIMessage } from '../types'

export type AnalysisThreadMessage = ThreadMessageLike

// 自定义部件类型名（data-* 前缀经 assistant-ui 转为 data 部件，按 by_name 分发）
export const DATA_PART = {
  pipeline: 'data-pipeline',
  report: 'data-report',
  search: 'data-search',
  system: 'data-system',
  error: 'data-error',
} as const

// metadata.custom.kind：消息形态标记，渲染层据此选择消息容器（chat 消息承载
// stream-output 测试契约：思考/工具横幅与正文同容器）
export type MessageKind = UIMessage['type']

// 工具参数展示文本是浓缩后的字符串（timeline.summarizeToolArgs 产物），
// 尝试还原为 JSON 对象供 tool-call 部件 args 字段使用（非对象/非法 JSON 返回 undefined）
function parseArgsText(argsText: string): ReadonlyJSONObject | undefined {
  if (!argsText) return undefined
  try {
    const parsed: unknown = JSON.parse(argsText)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as ReadonlyJSONObject) : undefined
  } catch {
    return undefined
  }
}

// 消息部件联合类型（ThreadMessageLike.content 的数组形态元素）
type AnalysisPart = Exclude<ThreadMessageLike['content'], string>[number]

function timelineParts(msg: UIMessage): AnalysisPart[] {
  const parts: AnalysisPart[] = []
  const timeline = msg.agentTimeline ?? []
  timeline.forEach((item, i) => {
    if (item.type === 'thinking') {
      if (!item.content) return
      // 流式中的思考段 status running（渲染层显示"思考中"），已完成不带 status
      parts.push({
        type: 'reasoning',
        text: item.content,
        ...(msg.streaming && i === timeline.length - 1 && item.done !== true
          ? { status: { type: 'running' as const } }
          : {}),
      })
      return
    }
    if (item.type === 'answer') {
      // 正文作为时间轴 item(时序修复):与思考/工具同轴按到达序渲染
      parts.push({
        type: 'text',
        text: item.content,
        ...(msg.streaming && i === timeline.length - 1
          ? { status: { type: 'running' as const } }
          : {}),
      })
      return
    }
    if (item.type === 'search') {
      parts.push({
        type: DATA_PART.search,
        data: { status: item.status, query: item.query, results: item.results ?? [] },
      })
      return
    }
    // tool_call
    parts.push({
      type: 'tool-call',
      toolCallId: `tc-${msg.id}-${i}`,
      toolName: item.name,
      argsText: item.args,
      args: parseArgsText(item.args),
      result: item.result,
      artifact: { done: item.done === true },
    })
  })
  return parts
}

// 单条 UIMessage → ThreadMessageLike（纯函数，逐事件类型单测覆盖其输入形态）
export function translateMessage(msg: UIMessage): ThreadMessageLike {
  switch (msg.type) {
    case 'user':
      return {
        role: 'user',
        id: msg.id,
        content: [{ type: 'text', text: msg.content }],
        metadata: { custom: { kind: 'user' } },
      }
    case 'chat': {
      const parts: AnalysisPart[] = [...timelineParts(msg)]
      // 正文已作为 'answer' 时间轴 item 由 timelineParts 按序渲染;chatResponse
      // 仅作历史重建/旧数据兜底(无 answer item 时末尾追加,保持现状不回归)。
      if (msg.chatResponse && !parts.some((p) => p.type === 'text')) {
        parts.push({
          type: 'text',
          text: msg.chatResponse,
          ...(msg.streaming ? { status: { type: 'running' as const } } : {}),
        })
      }
      return {
        role: 'assistant',
        id: msg.id,
        // 显式 status：流式 running / 否则 complete——避免 runtime 依据无 result 的
        // tool-call 部件推导 requires-action（外部 store 的消息状态由 store 拥有）
        status: msg.streaming ? { type: 'running' } : { type: 'complete', reason: 'unknown' },
        metadata: { custom: { kind: 'chat' } },
        content: parts,
      }
    }
    case 'pipeline':
      return {
        role: 'assistant',
        id: msg.id,
        status: { type: 'complete', reason: 'unknown' },
        metadata: { custom: { kind: 'pipeline' } },
        content: [{ type: DATA_PART.pipeline, data: msg }],
      }
    case 'report':
      return {
        role: 'assistant',
        id: msg.id,
        status: { type: 'complete', reason: 'unknown' },
        metadata: { custom: { kind: 'report' } },
        content: [{ type: DATA_PART.report, data: msg }],
      }
    case 'system':
      return {
        role: 'assistant',
        id: msg.id,
        status: { type: 'complete', reason: 'unknown' },
        metadata: { custom: { kind: 'system' } },
        content: [{ type: DATA_PART.system, data: { content: msg.content } }],
      }
    case 'error':
      return {
        role: 'assistant',
        id: msg.id,
        status: { type: 'complete', reason: 'unknown' },
        metadata: { custom: { kind: 'error' } },
        content: [{ type: DATA_PART.error, data: { content: msg.content } }],
      }
  }
}

// 批量翻译（保序）；经 useExternalStoreRuntime.convertMessage 逐条调用
export function translateMessages(messages: UIMessage[]): AnalysisThreadMessage[] {
  return messages.map(translateMessage)
}
