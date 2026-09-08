import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import ReactECharts from 'echarts-for-react'
import type { CalibrationResponse } from '../../types'
import { Button } from '../../components/ui/button'

function fmtPct(v: number | null, digits = 1) {
  return v === null ? '—' : `${(v * 100).toFixed(digits)}%`
}

export function CalibrationPage({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<CalibrationResponse | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setError(false)
    try {
      const resp = await fetch('/api/v1/track-record/calibration')
      if (!resp.ok) throw new Error(String(resp.status))
      setData((await resp.json()) as CalibrationResponse)
    } catch {
      setError(true)
      toast.error('校准数据加载失败')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const buckets = data?.buckets ?? []
  const hasSamples = (data?.sample_size ?? 0) > 0

  const chartOption = {
    color: ['#1677ff', '#b0b0b0'],
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['实际命中率', '完美校准'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 48, right: 16, top: 24, bottom: 40 },
    xAxis: { type: 'category' as const, data: buckets.map(b => b.bucket), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, min: 0, max: 1, axisLabel: { fontSize: 10, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    series: [
      { name: '实际命中率', type: 'line' as const, data: buckets.map(b => b.hit_rate), showSymbol: true, symbolSize: 8, connectNulls: false },
      { name: '完美校准', type: 'line' as const, data: buckets.map(b => b.mid), showSymbol: false, lineStyle: { type: 'dashed' as const } },
    ],
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8" data-testid="calibration-page">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--text-default)' }}>置信度校准</h1>
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="calibration-back">返回战绩</Button>
      </div>

      {error ? (
        <div className="text-sm py-16 text-center" style={{ color: 'var(--text-tertiary)' }}>数据加载失败，请刷新重试</div>
      ) : data === null ? (
        <div className="py-16 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>
      ) : (
        <>
          {/* Brier Score + 样本量 */}
          <div className="grid grid-cols-2 gap-3 mb-6" data-testid="calibration-summary">
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Brier Score（越低校准越好）</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }}>{data.brier === null ? '—' : data.brier.toFixed(4)}</div>
            </div>
            <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>参与校准样本</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--text-default)' }}>{data.sample_size}</div>
            </div>
          </div>

          {!hasSamples ? (
            <div className="py-16 text-center" data-testid="calibration-empty">
              <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>暂无已结算样本——完成深度分析并等待判定后，置信度校准曲线会出现在这里。</p>
            </div>
          ) : (
            <>
              {/* 校准曲线 */}
              <div className="rounded-xl p-4 mb-6" style={{ background: 'var(--bg-overlay-l1)' }} data-testid="calibration-curve">
                <div className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>实际命中率 vs 置信度分桶中值（虚线 = 完美校准）</div>
                <ReactECharts option={chartOption} style={{ height: 240 }} notMerge />
              </div>

              {/* 分桶明细 */}
              <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-neutral-l1)' }} data-testid="calibration-table">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      <th className="px-4 py-2 font-normal">置信度桶</th>
                      <th className="px-4 py-2 font-normal text-right">桶中值</th>
                      <th className="px-4 py-2 font-normal text-right">样本数</th>
                      <th className="px-4 py-2 font-normal text-right">实际命中率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buckets.map(b => (
                      <tr key={b.bucket} className="border-t" style={{ borderColor: 'var(--border-neutral-l1)' }}>
                        <td className="px-4 py-3" style={{ color: 'var(--text-default)' }}>{b.bucket}</td>
                        <td className="px-4 py-3 text-right" style={{ color: 'var(--text-secondary)' }}>{fmtPct(b.mid)}</td>
                        <td className="px-4 py-3 text-right" style={{ color: 'var(--text-secondary)' }}>{b.n}</td>
                        <td className="px-4 py-3 text-right" style={{ color: 'var(--text-secondary)' }}>{fmtPct(b.hit_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div data-testid="calibration-disclaimer" className="mt-6 rounded-lg px-4 py-3 text-xs" style={{ background: 'rgba(250, 204, 21, 0.12)', color: 'var(--text-secondary)' }}>
            {data.disclaimer}，投资需谨慎
          </div>
        </>
      )}
    </div>
  )
}