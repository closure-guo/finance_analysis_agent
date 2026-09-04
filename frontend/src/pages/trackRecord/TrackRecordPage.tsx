import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import ReactECharts from 'echarts-for-react'
import type { EquityCurvePoint, PredictionRecord, PredictionStatus, TrackRecordOverview } from '../../types'
import { Button } from '../../components/ui/button'
import { navigate } from '../../route'

const STATUS_LABEL: Record<PredictionStatus, string> = {
  open: '进行中',
  resolved_win: '命中',
  resolved_loss: '未中',
  resolved_neutral: '中性',
  unresolvable: '不可判定',
}

// 状态标签色：命中=绿、未中=红、中性=灰、进行中=蓝、不可判定=灰斜杠
const STATUS_CLS: Record<PredictionStatus, string> = {
  open: 'text-blue-600',
  resolved_win: 'text-green-600',
  resolved_loss: 'text-red-500',
  resolved_neutral: 'text-gray-500',
  unresolvable: 'text-gray-400 line-through',
}

const DIRECTION_LABEL: Record<string, string> = {
  long: '看多',
  short: '看空',
  neutral: '中性',
}

function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="text-txt-tertiary">—</span>
  const pct = value * 100
  const up = value >= 0
  return <span className={`${up ? 'text-red-500' : 'text-green-600'} font-medium`}>{up ? '+' : ''}{pct.toFixed(2)}%</span>
}

function fmt(value: number | null, digits = 2) {
  return value === null ? '—' : value.toFixed(digits)
}

function pct(value: number | null, digits = 1) {
  return value === null ? '—' : `${(value * 100).toFixed(digits)}%`
}

// 风险分 → 展示色（stage-b：分数越高风险越高）
function riskColor(score: number | null) {
  if (score === null) return ''
  if (score >= 8) return 'text-red-500'
  if (score >= 5) return 'text-orange-500'
  return 'text-green-600'
}

export function TrackRecordPage({ onBack }: { onBack: () => void }) {
  const [overview, setOverview] = useState<TrackRecordOverview | null>(null)
  const [records, setRecords] = useState<PredictionRecord[] | null>(null)
  const [curve, setCurve] = useState<EquityCurvePoint[] | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setError(false)
    try {
      const [ovResp, prResp, cvResp] = await Promise.all([
        fetch('/api/v1/track-record/overview'),
        fetch('/api/v1/track-record/predictions'),
        fetch('/api/v1/track-record/equity-curve'),
      ])
      if (!ovResp.ok || !prResp.ok || !cvResp.ok) throw new Error(String(ovResp.status))
      setOverview((await ovResp.json()) as TrackRecordOverview)
      const pr = (await prResp.json()) as { predictions: PredictionRecord[] }
      setRecords(pr.predictions)
      const cv = (await cvResp.json()) as { points: EquityCurvePoint[] }
      setCurve(cv.points)
    } catch {
      setError(true)
      toast.error('战绩数据加载失败')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const disclaimer = overview?.disclaimer ?? '历史业绩不代表未来表现'
  const rows = records ?? []
  const showWinRate = overview !== null && !overview.insufficient_sample && overview.win_rate !== null
  const portfolio = overview?.portfolio
  const showCurve = curve !== null && curve.length >= 2

  const chartOption = {
    color: ['#1677ff', '#fa8c16'],
    tooltip: { trigger: 'axis' as const, valueFormatter: (v: unknown) => (typeof v === 'number' ? v.toFixed(4) : String(v)) },
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category' as const, data: (curve ?? []).map(p => p.date), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, axisLabel: { fontSize: 10 } },
    series: [
      { name: '组合净值', type: 'line' as const, data: (curve ?? []).map(p => p.agent_nav), showSymbol: false, connectNulls: false },
      { name: '沪深300', type: 'line' as const, data: (curve ?? []).map(p => p.benchmark_nav), showSymbol: false, connectNulls: false },
    ],
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8" data-testid="track-record">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--text-default)' }}>历史战绩</h1>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate('/track-record/calibration')} data-testid="track-record-calibration-link">校准查看</Button>
          <Button variant="ghost" size="sm" onClick={onBack} data-testid="track-record-back">返回聊天</Button>
        </div>
      </div>

      {error ? (
        <div className="text-sm py-16 text-center" style={{ color: 'var(--text-tertiary)' }}>数据加载失败，请刷新重试</div>
      ) : overview === null || records === null ? (
        <div className="py-16 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>
      ) : (
        <>
          {/* 总览区 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="track-record-summary">
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>观点总数</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }}>{overview.total}</div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>胜率（已判定）</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }}>
                {showWinRate ? `${(overview.win_rate! * 100).toFixed(1)}%` : '—'}
              </div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>平均超额</div>
              <div className="text-2xl font-semibold"><Delta value={overview.avg_excess} /></div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>截至</div>
              <div className="text-2xl font-semibold text-base mt-1" style={{ color: 'var(--text-default)' }}>{overview.as_of}</div>
            </div>
          </div>

          {/* 样本积累提示 */}
          {overview.insufficient_sample && (
            <div className="mb-4 rounded-lg px-4 py-3 text-xs" style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-secondary)' }} data-testid="track-record-insufficient">
              样本积累中（已判定 {overview.settled} 条，满 10 条解锁胜率）
            </div>
          )}

          {/* 组合风险指标（add-track-record-stage-b：P4 收益与风险成对） */}
          <div data-testid="track-record-risk" className="rounded-xl p-4 mb-6" style={{ background: 'var(--bg-overlay-l1)' }}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>组合风险指标 <span className="ml-1 text-[10px]">年化/波动/夏普/最大回撤/风险分</span></div>
              {portfolio?.as_of && (
                <div className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>快照截至 {portfolio.as_of}</div>
              )}
            </div>
            {portfolio && portfolio.available ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>年化收益</div>
                  <div className="text-lg font-semibold" style={{ color: portfolio.annual_return !== null && portfolio.annual_return >= 0 ? 'var(--text-default)' : 'var(--text-default)' }}>
                    <Delta value={portfolio.annual_return} />
                  </div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>波动率</div>
                  <div className="text-lg font-semibold" style={{ color: 'var(--text-default)' }}>{pct(portfolio.volatility)}</div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>夏普比率</div>
                  <div className="text-lg font-semibold" style={{ color: 'var(--text-default)' }}>{fmt(portfolio.sharpe)}</div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>最大回撤</div>
                  <div className="text-lg font-semibold" style={{ color: portfolio.max_drawdown !== null && portfolio.max_drawdown >= 0.2 ? 'text-red-500' : 'var(--text-default)' }}>{pct(portfolio.max_drawdown)}</div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>风险分（{portfolio.risk_label ?? '—'}）</div>
                  <div className={`text-lg font-semibold ${riskColor(portfolio.risk_score)}`}>{portfolio.risk_score ?? '—'}</div>
                </div>
              </div>
            ) : (
              <div className="text-xs py-2" style={{ color: 'var(--text-tertiary)' }} data-testid="track-record-risk-empty">
                暂无净值快照——每个交易日收盘后自动生成组合净值与风险指标
              </div>
            )}
          </div>

          {/* 净值曲线（stage-b：agent vs 沪深300，起点归一 1.0；数据缺口断点不插值） */}
          {showCurve && (
            <div className="rounded-xl p-4 mb-6" style={{ background: 'var(--bg-overlay-l1)' }} data-testid="track-record-curve">
              <div className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>组合净值 vs 沪深300（起点归一 1.0）</div>
              <ReactECharts option={chartOption} style={{ height: 240 }} notMerge />
            </div>
          )}

          {/* 观点日志 */}
          {rows.length === 0 ? (
            <div className="py-16 text-center" data-testid="track-record-empty">
              <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>暂无观点记录。完成深度分析产生交易建议后，判定结果会出现在这里。</p>
            </div>
          ) : (
            <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-neutral-l1)' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    <th className="px-4 py-2 font-normal">标的</th>
                    <th className="px-4 py-2 font-normal">方向</th>
                    <th className="px-4 py-2 font-normal">状态</th>
                    <th className="px-4 py-2 font-normal text-right">入场价</th>
                    <th className="px-4 py-2 font-normal text-right">结算价</th>
                    <th className="px-4 py-2 font-normal text-right">区间收益</th>
                    <th className="px-4 py-2 font-normal text-right">基准超额</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.prediction_id} className="border-t" style={{ borderColor: 'var(--border-neutral-l1)' }}>
                      <td className="px-4 py-3">
                        <div className="font-medium" style={{ color: 'var(--text-default)' }}>{r.symbol_name ?? r.symbol}</div>
                        <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{r.symbol}</div>
                      </td>
                      <td className="px-4 py-3" style={{ color: 'var(--text-secondary)' }}>{DIRECTION_LABEL[r.direction]}</td>
                      <td className="px-4 py-3">
                        <span className={STATUS_CLS[r.status]}>{STATUS_LABEL[r.status]}</span>
                        {r.status === 'open' && (
                          <span className="ml-1 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>未结算</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">{fmt(r.entry_price)}</td>
                      <td className="px-4 py-3 text-right">{fmt(r.exit_price)}</td>
                      <td className="px-4 py-3 text-right"><Delta value={r.raw_return} /></td>
                      <td className="px-4 py-3 text-right"><Delta value={r.excess_return} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* 风险提示：常驻，不可关闭 */}
      <div data-testid="track-record-disclaimer" className="mt-6 rounded-lg px-4 py-3 text-xs" style={{ background: 'rgba(250, 204, 21, 0.12)', color: 'var(--text-secondary)' }}>
        {disclaimer}，投资需谨慎
      </div>
    </div>
  )
}
