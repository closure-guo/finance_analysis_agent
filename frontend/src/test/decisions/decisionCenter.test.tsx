import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DecisionCenter } from '../../pages/decisions/DecisionCenter'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

const open: Record<string, unknown> = {
  decision_id: 'd1', session_id: 's1', langfuse_trace_id: null,
  timestamp: '2026-09-01T10:00:00', ticker: '600519', name: '贵州茅台',
  action: 'buy', entry_price: 100, stop_loss: 90, target_price: 120,
  confidence: 0.8, position_size: 0.3, status: 'open',
  settled_at: null, settle_price: null, hold_days: null,
  decision_return: null, benchmark_return: null, decision_excess: null,
  updated_at: '2026-09-01T10:00:00',
}
const hit: Record<string, unknown> = {
  decision_id: 'd2', session_id: 's2', langfuse_trace_id: null,
  timestamp: '2026-09-02T10:00:00', ticker: '300308', name: '中际旭创',
  action: 'buy', entry_price: 100, stop_loss: null, target_price: 120,
  confidence: 0.7, position_size: 0.2, status: 'hit_target',
  settled_at: '2026-09-10T15:00:00', settle_price: 115, hold_days: 5,
  decision_return: 0.15, benchmark_return: 0.05, decision_excess: 0.10,
  updated_at: '2026-09-10T15:00:00',
}

const EMPTY_STATS = {
  total: 0, open: 0, settled: 0, by_status: {}, win_rate: null, avg_return: null, avg_excess: null,
}

function mockFetch(opts: { decisions?: unknown; stats?: unknown } = {}) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/decisions') {
      return Promise.resolve(new Response(JSON.stringify(opts.decisions ?? []), { status: 200 }))
    }
    if (url === '/api/decisions/stats') {
      return Promise.resolve(new Response(JSON.stringify(opts.stats ?? EMPTY_STATS), { status: 200 }))
    }
    if (url === '/api/sessions') {
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 404 }))
  }))
}

function renderPage() {
  return render(<DecisionCenter onBack={vi.fn()} onOpenSession={vi.fn()} />)
}

describe('决策战绩页面（expose-decision-outcomes）', () => {
  beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('空态显示提示', async () => {
    mockFetch()
    renderPage()
    expect(await screen.findByTestId('decisions-empty')).toBeInTheDocument()
  })

  it('汇总卡与列表渲染、null 字段占位「—」', async () => {
    mockFetch({
      decisions: [hit, open],
      stats: { total: 2, open: 1, settled: 1, by_status: { open: 1, hit_target: 1 }, win_rate: 1, avg_return: 0.15, avg_excess: 0.1 },
    })
    renderPage()
    expect(await screen.findByText('贵州茅台')).toBeInTheDocument()
    expect(screen.getByText('中际旭创')).toBeInTheDocument()
    // 已结算行显示收益与超额（+15.00%/+10.00% 同时出现在汇总卡与 hit 行）；open 行收益显示「—」
    expect(screen.getAllByText('+15.00%').length).toBe(2)
    expect(screen.getAllByText('+10.00%').length).toBe(2)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    // 状态中文标签（下拉选项与行状态单元格都含这些文案）
    expect(screen.getAllByText('达标').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('持有中').length).toBeGreaterThanOrEqual(1)
  })

  it('正收益红涨、负收益绿跌', async () => {
    mockFetch({
      decisions: [hit, { ...hit, decision_id: 'd3', decision_return: -0.05, decision_excess: -0.02 }],
      stats: { total: 2, open: 0, settled: 2, by_status: { hit_target: 1, hit_stop: 1 }, win_rate: 0.5, avg_return: 0.05, avg_excess: 0.04 },
    })
    renderPage()
    const up = await screen.findByText('+15.00%')
    const down = await screen.findByText('-5.00%')
    expect(up.className).toContain('red')
    expect(down.className).toContain('green')
  })

  it('按状态与股票过滤调用带参数接口', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.startsWith('/api/decisions')) {
        return Promise.resolve(new Response(JSON.stringify([hit]), { status: 200 }))
      }
      if (url === '/api/decisions/stats') {
        return Promise.resolve(new Response(JSON.stringify(EMPTY_STATS), { status: 200 }))
      }
      return Promise.resolve(new Response('', { status: 404 }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    // 有数据时过滤控件渲染；初始加载两次 fetch 后进入列表态
    await screen.findByTestId('decision-row-d2')
    fireEvent.change(screen.getByTestId('decisions-status-filter'), { target: { value: 'hit_target' } })
    fireEvent.change(screen.getByTestId('decisions-ticker-filter'), { target: { value: '600519' } })
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(c => String(c[0]))
      expect(calls.some(u => u.includes('status=hit_target') && u.includes('ticker=600519'))).toBe(true)
    })
  })

  it('点击决策行触发 onOpenSession', async () => {
    mockFetch({ decisions: [hit] })
    const onOpen = vi.fn()
    render(<DecisionCenter onBack={vi.fn()} onOpenSession={onOpen} />)
    const row = await screen.findByTestId('decision-row-d2')
    fireEvent.click(row)
    expect(onOpen).toHaveBeenCalledWith('s2')
  })

  // 注:App 级集成用例已移除——add-track-record 将 /decisions 战绩页替换为
  // TrackRecordPage(见 frontend/src/test/trackRecord/),DecisionCenter 不再接入 App。
})
