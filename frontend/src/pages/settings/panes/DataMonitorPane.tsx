// DataMonitorPane 数据监控分区（add-agent-settings-center Task 11）
// 挂载拉取 GET /api/data-source/status，展示命中/未命中/失败计数卡 + 数据新鲜度列表（含已过期标记）；
// 沿用 CachePane 的 loading/ready/error 状态机（full 加载 + 错误态重试）。
import { useCallback, useEffect, useState } from 'react'
import { Button } from '../../../components/ui/button'

interface MonitorSnapshot {
  hits: number
  misses: number
  fails: Record<string, number>
  last_hit: number | null
}

interface FreshnessRow {
  category: string
  entries: number
  bytes: number | null
  earliest_expire: number | null
}

// freshness 为后端 data_cache.stats 形状（含 entries 与 per_type）
interface DataSourceStatus {
  monitor: MonitorSnapshot
  freshness: {
    entries: number
    bytes: number
    expired: number
    permanent: number
    per_type: FreshnessRow[]
  }
}

// 秒级时间戳 → 本地时间字符串；无值显示占位符
function formatTime(ts: number | null | undefined): string {
  if (ts === null || ts === undefined) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 该类别数据是否已过期：存在最早过期时间且早于当前时间
function isExpired(earliestExpire: number | null): boolean {
  return earliestExpire !== null && earliestExpire < Date.now() / 1000
}

// 汇总统计卡（命中/未命中/失败）
function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
      <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="text-lg font-medium">{value}</p>
    </div>
  )
}

export function DataMonitorPane() {
  const [status, setStatus] = useState<DataSourceStatus | null>(null)
  // 加载状态机：loading 首次加载中 / ready 已就绪 / error 首次加载失败
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')

  // 拉取数据源状态：mode='full'（初次挂载 / 失败后重试）进入 loading，失败置 error。
  // 本分区只读、无写操作触发刷新，故仅使用 full 模式。
  const loadStatus = useCallback(async (mode: 'full' | 'refresh' = 'full') => {
    if (mode === 'full') setPhase('loading')
    try {
      const res = await fetch('/api/data-source/status')
      if (!res.ok) throw new Error(String(res.status))
      setStatus((await res.json()) as DataSourceStatus)
      setPhase('ready')
    } catch {
      if (mode === 'full') setPhase('error')
    }
  }, [])

  useEffect(() => { void loadStatus() }, [loadStatus])

  // 失败总次数：fails 各业务类别失败数求和
  const failCount = status
    ? Object.values(status.monitor.fails).reduce((a, b) => a + b, 0)
    : 0

  // 首次加载失败：错误文案 + 重试（点击重新 full 加载）
  if (phase === 'error') {
    return (
      <div data-testid="data-monitor-pane-error" className="py-6 text-sm space-y-3" style={{ color: 'var(--text-tertiary)' }}>
        <p>数据监控加载失败</p>
        <Button data-testid="data-monitor-retry" size="sm" variant="outline" onClick={() => void loadStatus('full')}>
          重试
        </Button>
      </div>
    )
  }

  if (!status) {
    return <div className="py-6 text-sm" style={{ color: 'var(--text-tertiary)' }}>数据监控加载中…</div>
  }

  return (
    <div data-testid="data-monitor-pane" className="space-y-6">
      {/* 命中 / 未命中 / 失败计数卡 */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <SummaryCard label="命中" value={String(status.monitor.hits)} />
        <SummaryCard label="未命中" value={String(status.monitor.misses)} />
        <SummaryCard label="失败" value={String(failCount)} />
      </div>

      {/* 数据新鲜度列表：按类别展示条目数 / 最早过期，过期类别带标记 */}
      <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">数据新鲜度</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-left" style={{ color: 'var(--text-secondary)' }}>
              <th className="py-1 pr-2 font-normal">类别</th>
              <th className="py-1 pr-2 font-normal">条目数</th>
              <th className="py-1 pr-2 font-normal">最早过期</th>
              <th className="py-1 font-normal">状态</th>
            </tr>
          </thead>
          <tbody>
            {status.freshness.per_type.map((row) => (
              <tr key={row.category} className="border-t" style={{ borderColor: 'var(--border-neutral-l1)' }}>
                <td className="py-2 pr-2">{row.category}</td>
                <td className="py-2 pr-2">{row.entries} 条</td>
                <td className="py-2 pr-2">{formatTime(row.earliest_expire)}</td>
                <td className="py-2">
                  {isExpired(row.earliest_expire) && (
                    <span
                      data-testid={`freshness-expired-${row.category}`}
                      className="text-xs rounded px-1.5 py-0.5"
                      style={{ color: 'var(--status-error-default)', background: 'var(--bg-overlay-l1)' }}
                    >
                      已过期
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {status.freshness.per_type.length === 0 && (
              <tr>
                <td colSpan={4} className="py-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>暂无数据缓存条目</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
