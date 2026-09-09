// SessionsPane 会话管理分区（add-agent-settings-center Task 9）
// 挂载时拉取 GET /api/sessions 展示会话总数；
// 「清空全部会话」为高危操作，弹二次确认框，确认后 POST /api/sessions/clear-all 并回调 onCleared。
import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '../../../components/ui/button'

interface SessionsPaneProps {
  // 清空成功后回调（父组件可用于刷新会话列表 / 提示）
  onCleared?: () => void
}

export function SessionsPane({ onCleared }: SessionsPaneProps) {
  const [count, setCount] = useState<number | null>(null)
  // 加载状态机：loading 首次加载中 / ready 已就绪（含刷新失败保留旧数据）/ error 首次加载失败
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // 拉取会话总数：
  // - mode='full'（初次挂载 / 失败后点重试）：进入 loading，失败置 error 渲染错误态
  // - mode='refresh'（清空操作后刷新）：失败保留旧 count 不清空、不回落加载态，仅 toast
  const loadSessions = useCallback(async (mode: 'full' | 'refresh' = 'full') => {
    if (mode === 'full') setStatus('loading')
    try {
      const res = await fetch('/api/sessions')
      if (!res.ok) throw new Error(String(res.status))
      const data = (await res.json()) as { sessions?: unknown }
      // 契约：GET /api/sessions 返回 { sessions: [...] }；缺字段或非数组视为失败
      if (!Array.isArray(data.sessions)) throw new Error('invalid sessions payload')
      setCount(data.sessions.length)
      setStatus('ready')
    } catch {
      if (mode === 'full') setStatus('error')
      toast.error('会话列表加载失败')
    }
  }, [])

  useEffect(() => { void loadSessions() }, [loadSessions])

  // 确认清空：POST clear-all 成功回调 onCleared，失败仅 toast。
  // 提交期间 submitting 禁用确认按钮防重复点击；结束后走 refresh 刷新（失败保留旧数据）。
  const clearAll = async () => {
    setSubmitting(true)
    try {
      const res = await fetch('/api/sessions/clear-all', { method: 'POST' })
      if (!res.ok) throw new Error(String(res.status))
      onCleared?.()
    } catch {
      toast.error('清空会话失败')
    } finally {
      setSubmitting(false)
      setConfirmOpen(false)
      void loadSessions('refresh')
    }
  }

  // 首次加载失败：错误文案 + 重试
  if (status === 'error') {
    return (
      <div data-testid="sessions-pane-error" className="py-6 text-sm space-y-3" style={{ color: 'var(--text-tertiary)' }}>
        <p>会话列表加载失败</p>
        <Button data-testid="sessions-retry" size="sm" variant="outline" onClick={() => void loadSessions()}>
          重试
        </Button>
      </div>
    )
  }

  if (status === 'loading') {
    return <div className="py-6 text-sm" style={{ color: 'var(--text-tertiary)' }}>会话列表加载中…</div>
  }

  return (
    <div data-testid="sessions-pane" className="space-y-6">
      {/* 会话总数统计卡 */}
      <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
        <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>会话总数</p>
        <p className="text-lg font-medium">{count}</p>
      </div>

      {/* 清空全部会话（高危） */}
      <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">全部会话管理</h3>
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>高危操作：将删除全部会话记录。</p>
        <Button data-testid="sessions-clear-all" size="sm" variant="destructive" onClick={() => setConfirmOpen(true)}>
          清空全部会话
        </Button>
      </div>

      {/* 二次确认框 */}
      {confirmOpen && (
        <div
          data-testid="sessions-clear-all-confirm"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.45)' }}
        >
          <div
            className="rounded-xl p-5 w-full max-w-sm space-y-3"
            style={{ background: 'var(--bg-overlay-l1)', border: '1px solid var(--border-neutral-l1)' }}
          >
            <p className="text-sm font-medium">清空全部会话？</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>此操作不可恢复，删除后无法找回。</p>
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                data-testid="sessions-clear-all-cancel"
                onClick={() => setConfirmOpen(false)}
              >
                取消
              </Button>
              <Button
                size="sm"
                variant="destructive"
                data-testid="sessions-clear-all-submit"
                disabled={submitting}
                onClick={() => void clearAll()}
              >
                {submitting ? '清空中…' : '确认清空'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
