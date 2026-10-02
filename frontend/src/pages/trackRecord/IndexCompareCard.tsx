import { useEffect, useState } from 'react'

import type { IndexCompareResponse } from '../../types'
import type { TrackTimeSpan } from '../../lib/trackPrefs'

// 跑赢指数对比卡片(add-index-performance-compare):组合区间收益 vs 主要指数同期收益。
// span 随战绩页跨度偏好传入;指数缺数灰显,beat 直读比较(与判定链 ±2% 带无关)。
export function IndexCompareCard({ span }: { span: TrackTimeSpan }) {
  const [data, setData] = useState<IndexCompareResponse | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    setFailed(false)
    fetch(`/api/v1/track-record/index-compare?span=${span}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: IndexCompareResponse) => {
        if (alive) setData(d)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [span])

  return (
    <div
      data-testid="index-compare-card"
      className="rounded-lg border p-4"
      style={{ borderColor: 'var(--border-neutral-l1)' }}
    >
      <div className="mb-2 text-sm font-medium">跑赢指数对比</div>
      {failed && <div className="text-xs text-[var(--text-secondary)]">对比数据加载失败</div>}
      {data && data.agent_return !== null && (
        <>
          <div data-testid="index-compare-summary" className="mb-3 text-lg font-semibold">
            跑赢 {data.indices.filter(i => i.beat === true).length}/{data.indices.filter(i => i.beat !== null).length} 个指数
          </div>
          <div className="flex flex-col gap-1.5">
            {/* 组合条置顶(对比基准线):无 beat 标记,不参与降序 */}
            <div data-testid="index-compare-row-agent" className="flex items-center gap-2 text-sm font-semibold">
              <span className="w-20 shrink-0">本组合</span>
              <span className="flex-1">{(data.agent_return * 100).toFixed(2)}%</span>
              <span className="text-xs text-[var(--text-secondary)]">对比基准线</span>
            </div>
            {[...data.indices]
              .sort((a, b) => (b.return ?? -Infinity) - (a.return ?? -Infinity))
              .map(i => (
                <div key={i.code} data-testid={`index-compare-row-${i.code}`} className="flex items-center gap-2 text-sm">
                  <span className="w-20 shrink-0">{i.name}</span>
                  {i.return === null ? (
                    <span className="text-[var(--text-secondary)]">无数据</span>
                  ) : (
                    <>
                      <span className="flex-1">
                        {(i.return * 100).toFixed(2)}%
                        {i.effective_start_date !== data.window.start && (
                          <span className="ml-1 text-xs text-[var(--text-secondary)]">
                            (自 {i.effective_start_date} 起算)
                          </span>
                        )}
                      </span>
                      <span style={{ color: i.beat ? 'var(--status-success-default)' : 'var(--status-error-default)' }}>
                        {i.beat ? '↑ 跑赢' : '↓ 跑输'}
                      </span>
                    </>
                  )}
                </div>
              ))}
          </div>
        </>
      )}
      {data && data.agent_return === null && (
        <div data-testid="index-compare-empty" className="text-xs text-[var(--text-secondary)]">
          净值数据积累中,暂无法对比
        </div>
      )}
      <div className="mt-2 text-xs text-[var(--text-secondary)]">{data?.disclaimer}</div>
    </div>
  )
}
