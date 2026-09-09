// TrackPrefsPane 战绩展示偏好分区 + trackPrefs 持久化单测（add-agent-settings-center Task 12）
// 纯前端 localStorage（key fa_track_prefs）：无 fetch，无需 stub。
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TrackPrefsPane } from '../../pages/settings/panes/TrackPrefsPane'
import { loadTrackPrefs, saveTrackPrefs, DEFAULT_TRACK_PREFS } from '../../lib/trackPrefs'

describe('trackPrefs 存取（lib/trackPrefs）', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('无存储时返回默认值；保存后可读回', () => {
    expect(loadTrackPrefs()).toEqual(DEFAULT_TRACK_PREFS)
    saveTrackPrefs({ ...DEFAULT_TRACK_PREFS, timeSpan: '6m' })
    expect(loadTrackPrefs().timeSpan).toBe('6m')
    expect(loadTrackPrefs().navChartForm).toBe('cumulative')
  })

  it('localStorage 缺失 / JSON 损坏时回退默认值', () => {
    localStorage.setItem('fa_track_prefs', '{bad json')
    expect(loadTrackPrefs()).toEqual(DEFAULT_TRACK_PREFS)
    localStorage.removeItem('fa_track_prefs')
    expect(loadTrackPrefs()).toEqual(DEFAULT_TRACK_PREFS)
  })

  it('部分存储字段与默认值合并补全', () => {
    localStorage.setItem('fa_track_prefs', JSON.stringify({ drawdownThreshold: 0.1 }))
    const prefs = loadTrackPrefs()
    expect(prefs.drawdownThreshold).toBe(0.1)
    expect(prefs.timeSpan).toBe(DEFAULT_TRACK_PREFS.timeSpan)
    expect(prefs.benchmark).toBe(DEFAULT_TRACK_PREFS.benchmark)
    expect(prefs.navChartForm).toBe(DEFAULT_TRACK_PREFS.navChartForm)
  })
})

describe('TrackPrefsPane 战绩展示偏好分区', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('渲染四项偏好控件，无存储时回显默认值', () => {
    render(<TrackPrefsPane />)
    expect(screen.getByTestId('track-prefs-pane')).toBeInTheDocument()
    expect(screen.getByText('默认时间跨度')).toBeInTheDocument()
    expect(screen.getByText('对比基准指数')).toBeInTheDocument()
    expect(screen.getByText('回撤警示阈值')).toBeInTheDocument()
    expect(screen.getByText('净值图默认形态')).toBeInTheDocument()
    expect((screen.getByTestId('track-prefs-timespan') as HTMLSelectElement).value).toBe('all')
    expect((screen.getByTestId('track-prefs-benchmark') as HTMLSelectElement).value).toBe('none')
    expect((screen.getByTestId('track-prefs-drawdown') as HTMLSelectElement).value).toBe('0.2')
    expect((screen.getByTestId('track-prefs-form') as HTMLSelectElement).value).toBe('cumulative')
  })

  it('挂载时回显已存储偏好', () => {
    saveTrackPrefs({ timeSpan: '6m', benchmark: 'hs300', drawdownThreshold: 0.1, navChartForm: 'interval' })
    render(<TrackPrefsPane />)
    expect((screen.getByTestId('track-prefs-timespan') as HTMLSelectElement).value).toBe('6m')
    expect((screen.getByTestId('track-prefs-benchmark') as HTMLSelectElement).value).toBe('hs300')
    expect((screen.getByTestId('track-prefs-drawdown') as HTMLSelectElement).value).toBe('0.1')
    expect((screen.getByTestId('track-prefs-form') as HTMLSelectElement).value).toBe('interval')
  })

  it('改动即保存：四项偏好变更立即写入 localStorage', () => {
    render(<TrackPrefsPane />)
    fireEvent.change(screen.getByTestId('track-prefs-timespan'), { target: { value: '6m' } })
    fireEvent.change(screen.getByTestId('track-prefs-benchmark'), { target: { value: 'zz500' } })
    fireEvent.change(screen.getByTestId('track-prefs-drawdown'), { target: { value: '0.1' } })
    fireEvent.change(screen.getByTestId('track-prefs-form'), { target: { value: 'interval' } })
    expect(loadTrackPrefs()).toEqual({
      timeSpan: '6m', benchmark: 'zz500', drawdownThreshold: 0.1, navChartForm: 'interval',
    })
  })

  it('localStorage 损坏时仍可渲染默认值并正常改动保存', () => {
    localStorage.setItem('fa_track_prefs', '{bad')
    render(<TrackPrefsPane />)
    expect((screen.getByTestId('track-prefs-timespan') as HTMLSelectElement).value).toBe('all')
    fireEvent.change(screen.getByTestId('track-prefs-drawdown'), { target: { value: '0.15' } })
    expect(loadTrackPrefs().drawdownThreshold).toBe(0.15)
  })
})
