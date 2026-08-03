import { describe, it, expect } from 'vitest'
import type { SSEEvent, UIMessage } from '../types'
import { applyChatStreamEvent } from '../timeline'

// 流式游标生命周期测试（fix-terminal-event-dedup-scope）
//
// 背景：后端终态事件 CAS 曾按"会话 journal 全历史"去重，导致第二轮起
// done/interrupted/error 被吞，前端游标永久卡死。修复分两层：
//   D2 深度模式 SSE 循环补 chat_done 路由（与 quickChat 对齐）
//   D3 流结束/连接异常时兜底清 streaming（游标不依赖单一终态事件）
//
// 本文件用 reducer + 清理函数模拟 App.tsx startAnalysis 的 SSE 循环语义，
// 验证「无论终态事件是否抵达，流结束后游标必须消失」。

const baseMsg = (overrides: Partial<UIMessage> = {}): UIMessage => ({
  id: 'assistant-1',
  type: 'chat',
  content: '',
  streaming: true,
  ...overrides,
})

const ev = (e: Record<string, unknown>): SSEEvent => e as unknown as SSEEvent

/**
 * 模拟 App.tsx startAnalysis 的 SSE 事件循环 + 流结束兜底清理。
 *
 * 与实现保持同构的三条路径：
 *  - chat_done / error 走 handleChatStreamEvent -> applyChatStreamEvent（D2）
 *  - done / interrupted 终态分支直接置 streaming=false
 *  - 循环退出后的防御性清理（D3）
 */
function runStreamLoop(
  events: Array<Record<string, unknown>>,
  options: { aborted?: boolean } = {},
): UIMessage {
  let msg = baseMsg()

  for (const raw of events) {
    const event = ev(raw)
    switch (event.type) {
      // 对话流事件：统一交给 applyChatStreamEvent（含 chat_done 收口）
      case 'thinking_token':
      case 'chat_token':
      case 'chat_done':
      case 'error':
        msg = applyChatStreamEvent(msg, event)
        break
      // 终态事件分支：清除流式状态
      case 'done':
      case 'interrupted':
        msg = { ...msg, streaming: false }
        break
      default:
        break
    }
  }

  // 流结束防御性清理（D3）：AbortError 路径提前 return，不清当前视图消息
  if (!options.aborted) {
    msg = { ...msg, streaming: false }
  }
  return msg
}

describe('流式游标生命周期 - chat_done 路由（D2）', () => {
  it('收到 chat_done 时游标消失且 thinking item 收口', () => {
    const msg = runStreamLoop([
      { type: 'thinking_token', token: '正在分析' },
      { type: 'chat_token', token: '茅台' },
      { type: 'chat_done' },
    ])

    expect(msg.streaming).toBe(false)
    const thinking = msg.agentTimeline?.find(i => i.type === 'thinking')
    expect(thinking).toBeDefined()
    if (thinking?.type === 'thinking') {
      expect(thinking.done).toBe(true)
    }
  })

  it('chat_done 与随后的 done 终态事件重复置 streaming 幂等', () => {
    const msg = runStreamLoop([
      { type: 'chat_token', token: '回答' },
      { type: 'chat_done' },
      { type: 'done' },
    ])

    expect(msg.streaming).toBe(false)
    expect(msg.chatResponse).toBe('回答')
  })
})

describe('流式游标生命周期 - 流结束兜底清理（D3）', () => {
  it('缺少 done 终态事件时流结束仍清除游标（后端终态被吞的场景）', () => {
    // 复现 bug：第二轮 done 被后端 CAS 吞掉，前端只读到内容事件后流关闭
    const msg = runStreamLoop([
      { type: 'thinking_token', token: '第二轮思考' },
      { type: 'chat_token', token: '第二轮回答' },
    ])

    expect(msg.streaming).toBe(false)
    expect(msg.chatResponse).toBe('第二轮回答')
  })

  it('完全无事件的空流结束后不残留游标', () => {
    const msg = runStreamLoop([])
    expect(msg.streaming).toBe(false)
  })

  it('AbortError（切换会话）路径不清当前视图消息的游标', () => {
    const msg = runStreamLoop(
      [{ type: 'chat_token', token: '进行中' }],
      { aborted: true },
    )
    // 切走的会话由会话恢复逻辑接管，此处保持 streaming 不被就地清除
    expect(msg.streaming).toBe(true)
  })
})

describe('流式游标生命周期 - 终态事件正常抵达', () => {
  it.each(['done', 'interrupted'] as const)('%s 终态事件清除游标', terminalType => {
    const msg = runStreamLoop([
      { type: 'chat_token', token: '内容' },
      { type: terminalType },
    ])
    expect(msg.streaming).toBe(false)
  })

  it('error 终态事件清除游标并写入错误文案', () => {
    const msg = runStreamLoop([
      { type: 'thinking_token', token: '思考' },
      { type: 'error', message: '后端异常' },
    ])
    expect(msg.streaming).toBe(false)
    expect(msg.chatResponse).toContain('后端异常')
  })
})
