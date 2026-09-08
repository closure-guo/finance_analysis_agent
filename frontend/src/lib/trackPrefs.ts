// trackPrefs 战绩展示偏好存取（add-agent-settings-center Task 12）
// 纯前端展示偏好：持久化到 localStorage（key fa_track_prefs），结构沿用既有
// fa_theme / fa_llm_profiles 模式；读取时与默认值合并，存储损坏时回退默认。
//
// 字段说明：
// - timeSpan 默认时间跨度：'all' 全部 | '3m' 近 3 月 | '6m' 近 6 月 | '1y' 近 1 年
//   （后端 /api/v1/track-record/equity-curve 暂不支持区间参数，先存储，接入待后端支持）
// - benchmark 对比基准指数：'none' 不对比 | 'hs300' 沪深300 | 'zz500' 中证500 | 'zz1000' 中证1000
//   （净值曲线当前仅有沪深300基准序列，zz500/zz1000 的序列待接入）
// - drawdownThreshold 回撤警示阈值（比例，0.2 = 20%）
// - navChartForm 净值图默认形态：'cumulative' 累计净值折线 | 'interval' 区间收益面积

export type TrackTimeSpan = 'all' | '3m' | '6m' | '1y'
export type TrackBenchmark = 'none' | 'hs300' | 'zz500' | 'zz1000'
export type TrackNavChartForm = 'cumulative' | 'interval'

export interface TrackPrefs {
  timeSpan: TrackTimeSpan
  benchmark: TrackBenchmark
  drawdownThreshold: number
  navChartForm: TrackNavChartForm
}

export const DEFAULT_TRACK_PREFS: TrackPrefs = {
  timeSpan: 'all',
  benchmark: 'none',
  drawdownThreshold: 0.2,
  navChartForm: 'cumulative',
}

const KEY = 'fa_track_prefs'

// 读取偏好：无存储 / JSON 损坏 → 默认值；部分存储 → 与默认值合并补全
export function loadTrackPrefs(): TrackPrefs {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...DEFAULT_TRACK_PREFS, ...JSON.parse(raw) } : { ...DEFAULT_TRACK_PREFS }
  } catch {
    return { ...DEFAULT_TRACK_PREFS }
  }
}

// 保存偏好：全量覆盖写入 localStorage
export function saveTrackPrefs(p: TrackPrefs): void {
  localStorage.setItem(KEY, JSON.stringify(p))
}