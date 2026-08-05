import { describe, it, expect } from 'vitest'
import { shouldProcessFetchedSession, isCurrentViewEvent } from '../App'

// 回归：selectSession 是 async 函数，await fetch 期间用户可能已切换到其他会话。
// fetch 返回后若无 stale guard，会为已切走的会话启动 resumeStream，
// 导致两个 resumeStream reader 并发——它们竞争覆盖全局 streamingSessionIdRef.current，
// 使隔离检查（line 1653: streamingSessionIdRef.current !== currentSessionIdRef.current）
// 使用错误的值，chat_token 等增量事件被误判为「非当前视图」丢弃（continue 跳过）→ 内容缺失。
// 症状：两会话同时 running + 同标签快速切换 → 两个会话都出现不同程度的文字缺失。
// 修复：(1) selectSession fetch 后加 stale guard (2) resumeStream 隔离检查改用局部 sessionId。

describe('selectSession 并发竞态防护', () => {

  describe('shouldProcessFetchedSession（stale guard）', () => {
    it('fetch 期间用户未切换：应继续处理', () => {
      expect(shouldProcessFetchedSession('A', 'A')).toBe(true)
    })

    it('fetch 期间用户已切换到其他会话：应跳过', () => {
      expect(shouldProcessFetchedSession('B', 'A')).toBe(false)
    })

    it('快速切换 A→B→A：selectSession(B) 的 fetch 返回时用户已回到 A → 应跳过 B', () => {
      // 模拟竞态时序：
      // 1. selectSession(B) await fetch(B) 挂起
      // 2. 用户切到 A，currentSessionIdRef.current = A
      // 3. fetch(B) 返回 → stale guard 阻止 resumeStream(B)
      expect(shouldProcessFetchedSession('B', 'A')).toBe(false)
    })

    it('currentSessionId 为 null 时不应处理', () => {
      expect(shouldProcessFetchedSession('A', null)).toBe(false)
    })

    it('两个 selectSession 交错（fetch 返回顺序不确定）只有当前会话被处理', () => {
      // 场景：selectSession(B) 和 selectSession(A) 交错
      // 最终用户停在 A
      const currentSessionId = 'A'

      // fetch(B) 先返回 → 应跳过
      expect(shouldProcessFetchedSession('B', currentSessionId)).toBe(false)
      // fetch(A) 后返回 → 应处理
      expect(shouldProcessFetchedSession('A', currentSessionId)).toBe(true)

      // 反过来：最终用户停在 B
      const currentSessionId2 = 'B'
      expect(shouldProcessFetchedSession('A', currentSessionId2)).toBe(false)
      expect(shouldProcessFetchedSession('B', currentSessionId2)).toBe(true)
    })
  })

  describe('isCurrentViewEvent（resumeStream 隔离检查）', () => {
    it('reader 的 session 是当前视图：事件应处理', () => {
      expect(isCurrentViewEvent('A', 'A')).toBe(true)
    })

    it('reader 的 session 不是当前视图：事件应隔离', () => {
      expect(isCurrentViewEvent('B', 'A')).toBe(false)
    })

    it('关键回归：两个 resumeStream 并发时，局部 sessionId 不受全局 ref 覆盖影响', () => {
      // 场景：resumeStreamA 和 resumeStreamB 因 selectSession 交错而同时运行
      // resumeStreamB 后启动，全局 streamingSessionIdRef.current 被覆盖为 'B'
      // 用户当前在 A（currentSessionIdRef.current = 'A'）
      const currentSessionId: string = 'A'
      const globalStreamingRefAfterB: string = 'B'   // 被 resumeStreamB 覆盖
      const readerA_localSessionId = 'A'             // resumeStreamA 的局部变量

      // 旧逻辑（bug）：隔离检查用全局 ref → 'B' !== 'A' → 误隔离
      // → A 的 chat_token 被丢弃 → 内容缺失
      const oldIsolationCheck = globalStreamingRefAfterB !== currentSessionId
      expect(oldIsolationCheck).toBe(true)   // 旧逻辑误隔离

      // 新逻辑（修复）：隔离检查用局部 sessionId → 'A' === 'A' → 正确处理
      const newCheck = isCurrentViewEvent(readerA_localSessionId, currentSessionId)
      expect(newCheck).toBe(true)            // 新逻辑正确处理
    })

    it('反向：resumeStreamB 的 reader 在用户视图为 A 时应隔离', () => {
      expect(isCurrentViewEvent('B', 'A')).toBe(false)
    })

    it('currentSessionId 为 null 时不应处理（无活跃视图）', () => {
      expect(isCurrentViewEvent('A', null)).toBe(false)
    })
  })
})
