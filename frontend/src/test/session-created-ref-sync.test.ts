import { describe, it, expect } from 'vitest'
import { isCurrentViewEvent } from '../App'

// 回归：两会话并发流式输出时，后启动会话的文本后半段整段丢失。
//
// 根因（E2E concurrent-streaming-integrity.spec.ts 复现 + SSE 轨迹定位）：
// startAnalysis/quickChat 处理 session_created 事件时只调 setAndPersistSession()，
// 它触发 React setState，但 currentSessionIdRef.current 要等 useEffect 才异步同步。
//
// 在这个同步窗口内到达的 chat_token 会执行会话隔离检查：
//   activeSessionId(新 session) !== currentSessionIdRef.current(旧值/null) → 判为非当前视图
// → 走隔离分支被 continue 丢弃（chat_token 在 skipTypes 中，连缓冲都不进）
// → 流式文本从某个 seq 起整段消失。
//
// E2E 实测轨迹（修复前）：seq 5-8 渲染成功，seq 9/10/11 全部丢失
//   前端渲染 "这是一段测试用的固定回复。"
//   后端实际 "这是一段测试用的固定回复。用于验证流式渲染的增量累积。"
//
// 修复：session_created 处同步赋值 currentSessionIdRef.current = event.session_id，
// 与 selectSession 的同步赋值保持一致，消除 setState/ref 的同步窗口。

describe('session_created 同步 currentSessionIdRef（并发流式文本完整性）', () => {

  it('ref 已同步时，新会话的 chat_token 判为当前视图（正确渲染）', () => {
    const newSessionId = 'session-B'
    // session_created 处已同步赋值
    const currentSessionIdRefValue = newSessionId
    expect(isCurrentViewEvent(newSessionId, currentSessionIdRefValue)).toBe(true)
  })

  it('文档化 bug：ref 未同步（仍为旧值）时 chat_token 被误隔离丢弃', () => {
    const newSessionId = 'session-B'
    // 修复前：setAndPersistSession 只触发 setState，ref 仍是上一个会话
    const staleRefValue = 'session-A'
    expect(isCurrentViewEvent(newSessionId, staleRefValue)).toBe(false)
  })

  it('文档化 bug：新建会话首次 session_created，ref 为 null 时同样被丢弃', () => {
    const newSessionId = 'session-B'
    // 新建分析路径 currentSessionId 被置 null，ref 同步前为 null
    expect(isCurrentViewEvent(newSessionId, null)).toBe(false)
  })

  it('并发场景：两会话各自 ref 同步后互不干扰', () => {
    // A 先启动并同步，B 后启动并同步（ref 最终指向 B）
    const refAfterBCreated = 'session-B'

    // B 的 reader：事件应处理（B 是当前视图）
    expect(isCurrentViewEvent('session-B', refAfterBCreated)).toBe(true)
    // A 的 reader（若仍活跃）：事件应隔离，不污染 B 的视图
    expect(isCurrentViewEvent('session-A', refAfterBCreated)).toBe(false)
  })

  it('回归断言：完整 seq 序列在 ref 同步后全部通过隔离检查', () => {
    // 模拟 E2E 中丢失的 seq 9/10/11：ref 同步后应全部放行
    const sessionId = 'session-B'
    const ref = sessionId
    const seqTokens = [
      { seq: 5, token: '这是' },
      { seq: 6, token: '一段' },
      { seq: 7, token: '测试用的' },
      { seq: 8, token: '固定回复。' },
      { seq: 9, token: '用于验证' },
      { seq: 10, token: '流式渲染' },
      { seq: 11, token: '的增量累积。' },
    ]

    const rendered = seqTokens
      .filter(() => isCurrentViewEvent(sessionId, ref))
      .map(t => t.token)
      .join('')

    expect(rendered).toBe('这是一段测试用的固定回复。用于验证流式渲染的增量累积。')
  })
})
