import type { UIMessage, SSEEvent } from '../../types'

export type StreamPhase =
  | 'idle'         // 无活跃流
  | 'connecting'   // 已发起，等待首个事件
  | 'streaming'    // 流式接收中
  | 'awaiting_input' // 澄清等待（对应 awaiting_input 事件）
  | 'resuming'     // 切回/刷新后 replay 中
  | 'done'         // 正常完成（done / report_ready 后收口）
  | 'interrupted'  // 中断（interrupted 事件或后端 reconcile 状态）
  | 'error'        // 失败

// 会话状态来源标记：
// 'live'    — 由 SSE 事件流实时构建（submit/resume 驱动）
// 'pending' — 仅记录了 lastSeq 等元数据，messages 尚未从后端重建
// 'rebuilt' — 已从后端 chat_history 重建（rebuildSession）
export type StateOrigin = 'live' | 'pending' | 'rebuilt'

export interface SessionStreamState {
  phase: StreamPhase
  messages: UIMessage[]        // 唯一事实源，替代现 messages + messagesRef + 快照
  lastSeq: number              // 已应用的最大 seq，去重与续传游标
  origin?: StateOrigin          // pending 时组件需触发 rebuildSession（缺省视为 live）
  error?: string               // phase === 'error' 时的信息
  // 进行中会话 rebuild 的 messages 只是 chat_history user 种子（预览/204 兜底），
  // 首个回放事件到达时清除——种子里 user 气泡堆叠失序，真正的有序消息由
  // 全量回放（含后端注入的 user_message）重建。
  seededFromHistory?: boolean
}

// 共享的 IDLE 常量（引用稳定，useSyncExternalStore 不触发重渲染）
export const IDLE_STATE: SessionStreamState = {
  phase: 'idle',
  messages: [],
  lastSeq: 0,
  origin: 'pending',
}

// 生成消息 ID（模块级计数器，与 App.tsx 现有 genId 同策略）
let msgIdCounter = 0
export function genMsgId(): string {
  return `msg-${++msgIdCounter}`
}

// 重置计数器（测试用）
export function resetMsgIdCounter(): void {
  msgIdCounter = 0
}
