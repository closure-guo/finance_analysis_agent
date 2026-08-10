import { useCallback, useSyncExternalStore } from 'react'
import { getStreamStore } from './index'
import { IDLE_STATE } from './types'
import type { SessionStreamState } from './types'

// 订阅指定会话的流状态（useSyncExternalStore 封装）
// sessionId 为 null 时订阅临时 key ''（新会话提交后、session_created 迁移前的
// 提交态/错误态），无该状态时返回共享 IDLE_STATE（引用稳定）。
export function useSessionStream(sessionId: string | null): SessionStreamState {
  const store = getStreamStore()

  const subscribe = useCallback(
    (fn: () => void) => store.subscribe(fn),
    [store],
  )

  const getSnapshot = useCallback(
    (): SessionStreamState => {
      // null（空态/新会话提交中）：订阅临时 key ''，session_created 到达后迁移到
      // 真实 sessionId 并触发 onSessionCreated → setCurrentSessionId 切走
      const key = sessionId ?? ''
      return store.getSnapshot(key)
    },
    [store, sessionId],
  )

  return useSyncExternalStore(subscribe, getSnapshot)
}
