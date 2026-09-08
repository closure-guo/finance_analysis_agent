// TrackPrefsPane 战绩展示偏好分区（add-agent-settings-center Task 12）
// 四项偏好：默认时间跨度 / 对比基准指数 / 回撤警示阈值 / 净值图默认形态。
// 纯前端、无 props：读写 localStorage（lib/trackPrefs，key fa_track_prefs），改动即保存。
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type { TrackBenchmark, TrackNavChartForm, TrackPrefs, TrackTimeSpan } from '../../../lib/trackPrefs'
import { loadTrackPrefs, saveTrackPrefs } from '../../../lib/trackPrefs'

// 各偏好下拉可选项（value 即 fa_track_prefs 存储值；label 面向用户）
const TIME_SPAN_OPTIONS: Array<{ value: TrackTimeSpan; label: string }> = [
  { value: 'all', label: '全部时间' },
  { value: '3m', label: '近 3 月' },
  { value: '6m', label: '近 6 月' },
  { value: '1y', label: '近 1 年' },
]
const BENCHMARK_OPTIONS: Array<{ value: TrackBenchmark; label: string }> = [
  { value: 'none', label: '不对比基准' },
  { value: 'hs300', label: '沪深300' },
  { value: 'zz500', label: '中证500' },
  { value: 'zz1000', label: '中证1000' },
]
// 回撤警示阈值：比例 → 展示为百分比
const DRAWDOWN_OPTIONS = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
const NAV_FORM_OPTIONS: Array<{ value: TrackNavChartForm; label: string }> = [
  { value: 'cumulative', label: '累计净值' },
  { value: 'interval', label: '区间收益' },
]

// 原生 select 样式（与版本选择器等既有控件一致，用语义令牌）
const SELECT_STYLE: CSSProperties = {
  background: 'var(--bg-overlay-l1)',
  color: 'var(--text-default)',
  borderColor: 'var(--border-neutral-l1)',
}

// 一条偏好：左列标题 + 说明，右侧控件
function PrefRow({ label, hint, children }: { label: string; hint: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-2">
      <div>
        <div className="text-sm">{label}</div>
        <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{hint}</div>
      </div>
      {children}
    </div>
  )
}

export function TrackPrefsPane() {
  // 初始值取当前存储（无 / 损坏 → 默认）；改动即时保存并同步控件显示
  const [prefs, setPrefs] = useState<TrackPrefs>(loadTrackPrefs)

  // 更新某字段：先更新本地态，再全量写入 localStorage（改动即保存）
  const update = <K extends keyof TrackPrefs>(key: K, value: TrackPrefs[K]) => {
    setPrefs(prev => {
      const next = { ...prev, [key]: value }
      saveTrackPrefs(next)
      return next
    })
  }

  return (
    <div data-testid="track-prefs-pane" className="space-y-6">
      <div className="rounded-xl p-4" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium">战绩展示偏好</h3>
        <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          应用于历史战绩页的默认展示口径；仅保存在浏览器本地（fa_track_prefs），改动即时保存。
        </p>
      </div>

      <div className="rounded-xl p-4 space-y-2" style={{ background: 'var(--bg-overlay-l1)' }}>
        <PrefRow label="默认时间跨度" hint="净值曲线展示的时间范围（后端区间参数支持后生效）">
          <select
            data-testid="track-prefs-timespan"
            value={prefs.timeSpan}
            onChange={e => update('timeSpan', e.target.value as TrackTimeSpan)}
            className="text-xs rounded-lg px-2 py-1 border"
            style={SELECT_STYLE}
          >
            {TIME_SPAN_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </PrefRow>

        <PrefRow label="对比基准指数" hint="净值曲线是否叠加基准指数线（现仅沪深300有序列）">
          <select
            data-testid="track-prefs-benchmark"
            value={prefs.benchmark}
            onChange={e => update('benchmark', e.target.value as TrackBenchmark)}
            className="text-xs rounded-lg px-2 py-1 border"
            style={SELECT_STYLE}
          >
            {BENCHMARK_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </PrefRow>

        <PrefRow label="回撤警示阈值" hint="最大回撤超过该阈值时，风险卡以警示色高亮">
          <select
            data-testid="track-prefs-drawdown"
            value={String(prefs.drawdownThreshold)}
            onChange={e => update('drawdownThreshold', Number(e.target.value))}
            className="text-xs rounded-lg px-2 py-1 border"
            style={SELECT_STYLE}
          >
            {DRAWDOWN_OPTIONS.map(v => (
              <option key={v} value={String(v)}>{Math.round(v * 100)}%</option>
            ))}
          </select>
        </PrefRow>

        <PrefRow label="净值图默认形态" hint="累计净值折线，或区间收益面积视图">
          <select
            data-testid="track-prefs-form"
            value={prefs.navChartForm}
            onChange={e => update('navChartForm', e.target.value as TrackNavChartForm)}
            className="text-xs rounded-lg px-2 py-1 border"
            style={SELECT_STYLE}
          >
            {NAV_FORM_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </PrefRow>
      </div>
    </div>
  )
}