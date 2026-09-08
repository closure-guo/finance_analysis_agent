import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import type { DecisionRecord, DecisionStats, DecisionStatus } from '../../types'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'

const STATUS_LABEL: Record<DecisionStatus, string> = {
  open: '持有中',
  hit_stop: '止损',
  hit_target: '达标',
  expired: '超期',
}

const ACTION_LABEL: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  hold: '持有',
  watch: '观望',
}

const STATUS_OPTIONS: { key: DecisionStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'open', label: '持有中' },
  { key: 'hit_target', label: '达标' },
  { key: 'hit_stop', label: '止损' },
  { key: 'expired', label: '超期' },
]

// 涨跌着色（A 股约定红涨绿跌）：收益与超额字段共用
function DeltaValue({ value }: { value: number | null }) {
  if (value === null) return <span className="text-txt-tertiary">—</span>
  const pct = value * 100
  const up = value >= 0
  const cls = up ? 'text-red-500' : 'text-green-600'
  return <span className={`${cls} font-medium`}>{up ? '+' : ''}{pct.toFixed(2)}%</span>
}

function fmt(value: number | null, digits = 2) {
  return value === null ? '—' : value.toFixed(digits)
}

export function DecisionCenter({ onBack, onOpenSession }: {
  onBack: () => void
  onOpenSession: (sessionId: string) => void
}) {
  // null = 加载中；error 与空态严格区分（与 DownloadCenter 同规）
  const [records, setRecords] = useState<DecisionRecord[] | null>(null)
  const [stats, setStats] = useState<DecisionStats | null>(null)
  const [error, setError] = useState(false)
  const [status, setStatus] = useState<DecisionStatus | 'all'>('all')
  const [ticker, setTicker] = useState('')

  const load = useCallback(async () => {
    setError(false)
    try {
      const params = new URLSearchParams()
      if (status !== 'all') params.set('status', status)
      if (ticker.trim()) params.set('ticker', ticker.trim())
      const qs = params.toString()
      const [listResp, statsResp] = await Promise.all([
        fetch(`/api/decisions${qs ? `?${qs}` : ''}`),
        fetch('/api/decisions/stats'),
      ])
      if (!listResp.ok || !statsResp.ok) throw new Error(String(listResp.status))
      setRecords((await listResp.json()) as DecisionRecord[])
      setStats((await statsResp.json()) as DecisionStats)
    } catch {
      setError(true)
      toast.error('决策数据加载失败')
    }
  }, [status, ticker])

  useEffect(() => { void load() }, [load])

  const rows = records ?? []

  return (
    <div className="mx-auto max-w-5xl px-6 py-8" data-testid="decision-center">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--text-default)' }}>决策战绩</h1>
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="decisions-back">返回聊天</Button>
      </div>

      {error ? (
        <div className="text-sm py-16 text-center" style={{ color: 'var(--text-tertiary)' }}>数据加载失败，请刷新重试</div>
      ) : records === null ? (
        <div className="py-16 text-center text-sm" style={{ color: 'var(--text-tertiary)' }} data-testid="decisions-loading">加载中…</div>
      ) : rows.length === 0 ? (
        <div className="py-16 text-center" data-testid="decisions-empty">
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>暂无决策记录。完成一次深度分析并产生交易决策后，结算结果会出现在这里。</p>
          <Button variant="ghost" size="sm" className="mt-4" onClick={onBack}>返回聊天</Button>
        </div>
      ) : (
        <>
          {/* 汇总卡 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="decisions-summary">
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>总决策数</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }} data-testid="summary-total">{stats?.total ?? 0}</div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>胜率（已结算）</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }}>{stats?.win_rate === null || stats?.win_rate === undefined ? '—' : `${(stats.win_rate * 100).toFixed(1)}%`}</div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>平均收益</div>
              <div className="text-2xl font-semibold"><DeltaValue value={stats?.avg_return ?? null} /></div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>平均超额（沪深300）</div>
              <div className="text-2xl font-semibold"><DeltaValue value={stats?.avg_excess ?? null} /></div>
            </div>
          </div>

          {/* 过滤 */}
          <div className="flex gap-3 mb-4">
            <select
              data-testid="decisions-status-filter"
              value={status}
              onChange={e => setStatus(e.target.value as DecisionStatus | 'all')}
              className="h-9 rounded-lg px-3 text-sm border"
              style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)', borderColor: 'var(--border-neutral-l1)' }}
            >
              {STATUS_OPTIONS.map(o => (
                <option key={o.key} value={o.key}>{o.label}</option>
              ))}
            </select>
            <Input
              type="text"
              data-testid="decisions-ticker-filter"
              value={ticker}
              onChange={e => setTicker(e.target.value)}
              placeholder="按股票代码过滤…"
              className="h-9 text-sm max-w-48"
            />
          </div>

          {/* 列表 */}
          <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-neutral-l1)' }}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  <th className="px-4 py-2 font-normal">标的</th>
                  <th className="px-4 py-2 font-normal">操作</th>
                  <th className="px-4 py-2 font-normal">状态</th>
                  <th className="px-4 py-2 font-normal text-right">入场价</th>
                  <th className="px-4 py-2 font-normal text-right">结算价</th>
                  <th className="px-4 py-2 font-normal text-right">持有天数</th>
                  <th className="px-4 py-2 font-normal text-right">收益</th>
                  <th className="px-4 py-2 font-normal text-right">基准超额</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr
                    key={r.decision_id}
                    data-testid={`decision-row-${r.decision_id}`}
                    onClick={() => onOpenSession(r.session_id)}
                    className="cursor-pointer transition-colors border-t"
                    style={{ borderColor: 'var(--border-neutral-l1)' }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium" style={{ color: 'var(--text-default)' }}>{r.name ?? r.ticker}</div>
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{r.ticker}</div>
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{ACTION_LABEL[r.action] ?? r.action}</td>
                    <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{STATUS_LABEL[r.status]}</td>
                    <td className="px-4 py-3 text-right">{fmt(r.entry_price)}</td>
                    <td className="px-4 py-3 text-right">{fmt(r.settle_price)}</td>
                    <td className="px-4 py-3 text-right">{fmt(r.hold_days, 0)}</td>
                    <td className="px-4 py-3 text-right"><DeltaValue value={r.decision_return} /></td>
                    <td className="px-4 py-3 text-right"><DeltaValue value={r.decision_excess} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
