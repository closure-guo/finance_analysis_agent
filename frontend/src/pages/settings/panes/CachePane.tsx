// CachePane 缓存管理分区（add-agent-settings-center Task 8）
// 聚合后端三个缓存端点：统计 / 清理 / 能力探测缓存清除；
// 高危全清需输入「清空」二次确认（与后端 confirm=true 红线对齐）。
import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '../../../components/ui/button'

interface CacheTypeStats {
  category: string
  entries: number
  bytes: number | null
  earliest_expire: number | null
}

interface CacheStats {
  data: {
    entries: number
    bytes: number
    expired: number
    permanent: number
    per_type: CacheTypeStats[]
  }
  probe: { entries: number; expired: number }
  monitor: { hits: number; misses: number; fails: Record<string, number>; last_hit: number | null }
}

// 字节数 → 人类可读（B/KB/MB）
function formatBytes(n: number | null): string {
  if (n === null || n === undefined) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

// 秒级时间戳 → 本地时间字符串；无值显示占位符
function formatTime(ts: number | null | undefined): string {
  if (ts === null || ts === undefined) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 汇总统计卡（总条目 / 占用 / 已过期待清 / 最近命中）
function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
      <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="text-lg font-medium">{value}</p>
    </div>
  )
}

export function CachePane() {
  const [stats, setStats] = useState<CacheStats | null>(null)
  // 加载状态机：loading 首次加载中 / ready 已就绪（含刷新失败保留旧数据）/ error 首次加载失败
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [code, setCode] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  // 拉取缓存统计：
  // - mode='full'（初次挂载 / 失败后点重试）：进入 loading，失败置 error 渲染错误态
  // - mode='refresh'（清理操作后刷新）：失败保留旧 stats 不清空、不回落加载态，仅 toast
  const loadStats = useCallback(async (mode: 'full' | 'refresh' = 'full') => {
    if (mode === 'full') setStatus('loading')
    try {
      const res = await fetch('/api/cache/stats')
      if (!res.ok) throw new Error(String(res.status))
      setStats((await res.json()) as CacheStats)
      setStatus('ready')
    } catch {
      if (mode === 'full') setStatus('error')
      toast.error('缓存统计加载失败')
    }
  }, [])

  useEffect(() => { void loadStats() }, [loadStats])

  // 清理请求 + 成功后刷新统计（刷新走 refresh 模式，失败不清空已展示数据）
  const postAndRefresh = useCallback(async (path: string, body: unknown) => {
    try {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(String(res.status))
    } catch {
      toast.error('缓存清理失败')
    } finally {
      void loadStats('refresh')
    }
  }, [loadStats])

  // 按类别清空
  const clearType = (category: string) => {
    void postAndRefresh('/api/cache/clear', { scope: 'type', data_type: category })
  }

  // 按股票代码清空该代码全部类别
  const clearCode = () => {
    const trimmed = code.trim()
    if (!trimmed) return
    void postAndRefresh('/api/cache/clear', { scope: 'code', code: trimmed })
  }

  // 全部清空（高危确认：仅当输入「清空」时携带 confirm:true）
  const clearAll = () => {
    if (confirmText.trim() !== '清空') return
    void postAndRefresh('/api/cache/clear', { scope: 'all', confirm: true })
    setConfirmOpen(false)
    setConfirmText('')
  }

  // 能力探测缓存一键清除
  const clearProbe = () => {
    void postAndRefresh('/api/cache/probe-cache/clear', {})
  }

  // 首次加载失败：错误文案 + 重试（点击重新 full 加载）
  if (status === 'error') {
    return (
      <div data-testid="cache-pane-error" className="py-6 text-sm space-y-3" style={{ color: 'var(--text-tertiary)' }}>
        <p>缓存统计加载失败</p>
        <Button data-testid="cache-stats-retry" size="sm" variant="outline" onClick={() => void loadStats('full')}>
          重试
        </Button>
      </div>
    )
  }

  if (!stats) {
    return <div className="py-6 text-sm" style={{ color: 'var(--text-tertiary)' }}>缓存统计加载中…</div>
  }

  return (
    <div data-testid="cache-pane" className="space-y-6">
      {/* 汇总统计条 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryCard label="总条目" value={String(stats.data.entries)} />
        <SummaryCard label="占用" value={formatBytes(stats.data.bytes)} />
        <SummaryCard label="已过期待清" value={String(stats.data.expired)} />
        <SummaryCard label="最近命中" value={formatTime(stats.monitor.last_hit)} />
      </div>

      {/* 按类别表格：每类条目数 / 占用 / 最早过期 + 「清空该类」 */}
      <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">数据缓存按类别</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-left" style={{ color: 'var(--text-secondary)' }}>
              <th className="py-1 pr-2 font-normal">类别</th>
              <th className="py-1 pr-2 font-normal">条目数</th>
              <th className="py-1 pr-2 font-normal">占用</th>
              <th className="py-1 pr-2 font-normal">最早过期</th>
              <th className="py-1 font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {stats.data.per_type.map((row) => (
              <tr key={row.category} className="border-t" style={{ borderColor: 'var(--border-neutral-l1)' }}>
                <td className="py-2 pr-2">{row.category}</td>
                <td className="py-2 pr-2">{row.entries}</td>
                <td className="py-2 pr-2">{formatBytes(row.bytes)}</td>
                <td className="py-2 pr-2">{formatTime(row.earliest_expire)}</td>
                <td className="py-2">
                  <Button size="sm" variant="outline" onClick={() => clearType(row.category)}>清空该类</Button>
                </td>
              </tr>
            ))}
            {stats.data.per_type.length === 0 && (
              <tr>
                <td colSpan={5} className="py-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>暂无数据缓存条目</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 按股票代码清理 */}
      <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">按股票代码清理</h3>
        <div className="flex flex-wrap gap-2">
          <input
            data-testid="cache-code-input"
            className="glass-input rounded-md px-2 py-1.5 text-sm w-56"
            placeholder="输入股票代码，如 600519"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Button data-testid="cache-code-clear" size="sm" variant="outline" onClick={clearCode}>清空该代码全部缓存</Button>
        </div>
      </div>

      {/* 全部清空（高危） */}
      <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">全部清空数据缓存</h3>
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>高危操作：将删除全部数据缓存条目，点击后需输入「清空」二次确认。</p>
        <Button data-testid="cache-clear-all" size="sm" variant="destructive" onClick={() => setConfirmOpen(true)}>全部清空</Button>
      </div>

      {/* 能力探测缓存 */}
      <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">能力探测缓存</h3>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            内存条目 {stats.probe.entries} 条（已过期 {stats.probe.expired} 条）；清除后下次分析将重新执行能力探测。
          </p>
          <Button data-testid="cache-probe-clear" size="sm" variant="outline" onClick={clearProbe}>清除能力探测缓存</Button>
        </div>
      </div>

      {/* 全清确认框：输入「清空」二字后启用提交 */}
      {confirmOpen && (
        <div
          data-testid="cache-clear-all-confirm"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.45)' }}
        >
          <div
            className="rounded-xl p-5 w-full max-w-sm space-y-3"
            style={{ background: 'var(--bg-overlay-l1)', border: '1px solid var(--border-neutral-l1)' }}
          >
            <p className="text-sm font-medium">确认全部清空？</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>请输入「清空」二字确认后执行，此操作不可恢复。</p>
            <input
              data-testid="cache-clear-all-input"
              className="glass-input rounded-md px-2 py-1.5 text-sm w-full"
              placeholder="输入「清空」"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                data-testid="cache-clear-all-cancel"
                onClick={() => { setConfirmOpen(false); setConfirmText('') }}
              >
                取消
              </Button>
              <Button
                size="sm"
                variant="destructive"
                data-testid="cache-clear-all-submit"
                disabled={confirmText.trim() !== '清空'}
                onClick={clearAll}
              >
                确认清空
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
