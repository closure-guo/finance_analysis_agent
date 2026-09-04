import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TrackRecordPage } from '../../pages/trackRecord/TrackRecordPage'
import App from '../../App'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

// ECharts 需要 canvas，jsdom 不支持：stub 组件（chartsMarkLine.test 同款方案）
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="mock-chart" />,
}))

const OVERVIEW = {
  total: 2, open: 1, settled: 1, win_rate: 1, avg_excess: 0.1,
  status_counts: { open: 1, resolved_win: 1 }, source_type: 'live',
  insufficient_sample: true, as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
  portfolio: {
    available: true, annual_return: 0.12, volatility: 0.2, sharpe: 0.5,
    max_drawdown: 0.05, risk_score: 4, risk_label: '中', as_of: '2026-09-04',
  },
}

const PREDICTIONS: Record<string, unknown>[] = [
  {
    prediction_id: 'p1', source_type: 'live', symbol: '600519.SH', symbol_name: '贵州茅台',
    direction: 'long', entry_price: 100, target_price: 120, horizon_days: 252,
    confidence: 0.8, benchmark: '000300.SH', langfuse_trace_id: null,
    status: 'resolved_win', created_at: '2026-09-01T10:00:00', resolved_at: '2026-09-02',
    exit_price: 115, raw_return: 0.15, excess_return: 0.1, resolution_rule: 'expiry',
  },
  {
    prediction_id: 'p2', source_type: 'live', symbol: '300308.SZ', symbol_name: '中际旭创',
    direction: 'neutral', entry_price: 100, target_price: null, horizon_days: 252,
    confidence: 0.5, benchmark: '000300.SH', langfuse_trace_id: null,
    status: 'open', created_at: '2026-09-02T10:00:00', resolved_at: null,
    exit_price: null, raw_return: null, excess_return: null, resolution_rule: null,
  },
]

function mockFetch(opts: { overview?: unknown; predictions?: unknown; equity?: unknown } = {}) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/api/v1/track-record/overview')) {
      return Promise.resolve(new Response(JSON.stringify(opts.overview ?? {
        total: 0, open: 0, settled: 0, win_rate: null, avg_excess: null,
        status_counts: {}, source_type: null, insufficient_sample: true,
        as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
        portfolio: { available: false, annual_return: null, volatility: null,
          sharpe: null, max_drawdown: null, risk_score: null, risk_label: null, as_of: null },
      }), { status: 200 }))
    }
    if (url.includes('/api/v1/track-record/equity-curve')) {
      return Promise.resolve(new Response(JSON.stringify({
        points: opts.equity ?? [], as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
      }), { status: 200 }))
    }
    if (url.includes('/api/v1/track-record/predictions')) {
      return Promise.resolve(new Response(JSON.stringify({
        predictions: opts.predictions ?? [], page: 1, page_size: 50, total: 0,
        as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
      }), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 404 }))
  }))
}

function renderPage() {
  return render(<TrackRecordPage onBack={vi.fn()} />)
}

describe('track-record 战绩页（add-track-record）', () => {
  beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('空态显示「样本积累中」且不显示 0 冒充数据', async () => {
    mockFetch()
    renderPage()
    expect(await screen.findByTestId('track-record')).toBeInTheDocument()
    expect(screen.getByText(/样本积累中/)).toBeInTheDocument()
    // 风险提示常驻可见
    expect(screen.getByTestId('track-record-disclaimer')).toBeInTheDocument()
  })

  it('总览与观点日志渲染，默认含 loss，风险提示可见', async () => {
    mockFetch({
      overview: OVERVIEW,
      predictions: PREDICTIONS,
    })
    renderPage()
    expect(await screen.findByText('贵州茅台')).toBeInTheDocument()
    expect(screen.getByText('中际旭创')).toBeInTheDocument()
    // 状态标签：命中(绿)、进行中(蓝/持有中)
    expect(screen.getByText('命中')).toBeInTheDocument()
    // 进行中观点展示浮动收益并标「未结算」
    expect(screen.getAllByText(/未结算/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('track-record-disclaimer')).toBeInTheDocument()
    // 样本不足标注
    expect(screen.getByText(/样本较少|样本积累中/)).toBeInTheDocument()
  })

  it('null 胜率与超额占位「—」', async () => {
    mockFetch({
      overview: { ...OVERVIEW, win_rate: null, avg_excess: null, insufficient_sample: true },
      predictions: PREDICTIONS,
    })
    renderPage()
    await screen.findByText('贵州茅台')
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})

describe('战绩页全页视图下的导航（bug 复现：新建会话应回聊天首页）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    window.history.pushState({}, '', '/')
  })

  function appMock() {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/api/v1/track-record/overview')) {
        return Promise.resolve(new Response(JSON.stringify({
          total: 0, open: 0, settled: 0, win_rate: null, avg_excess: null,
          status_counts: {}, source_type: null, insufficient_sample: true,
          as_of: '2026-09-03', disclaimer: '历史业绩不代表未来表现',
          portfolio: { available: false, annual_return: null, volatility: null,
            sharpe: null, max_drawdown: null, risk_score: null, risk_label: null, as_of: null },
        }), { status: 200 }))
      }
      if (url.includes('/api/v1/track-record/equity-curve')) {
        return Promise.resolve(new Response(JSON.stringify({ points: [], as_of: '2026-09-03', disclaimer: 'x' }), { status: 200 }))
      }
      if (url.includes('/api/v1/track-record/predictions')) {
        return Promise.resolve(new Response(JSON.stringify({ predictions: [], page: 1, page_size: 50, total: 0, as_of: '2026-09-03', disclaimer: 'x' }), { status: 200 }))
      }
      if (url === '/api/sessions') {
        return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), { status: 200 }))
      }
      return Promise.resolve(new Response('', { status: 404 }))
    }))
  }

  it('战绩页点击「新建分析」回到聊天首页', async () => {
    appMock()
    window.history.pushState({}, '', '/track-record')
    render(<App />)
    await screen.findByTestId('track-record')
    fireEvent.click(screen.getByTestId('sidebar-new'))
    await waitFor(() => expect(window.location.pathname).toBe('/'))
    expect(await screen.findByText('今天想研究什么？')).toBeTruthy()
  })
})

describe('组合风险指标与净值曲线（add-track-record-stage-b）', () => {
  beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('风险卡渲染真实指标与风险分', async () => {
    mockFetch({ overview: OVERVIEW, predictions: PREDICTIONS })
    renderPage()
    await screen.findByText('贵州茅台')
    const risk = screen.getByTestId('track-record-risk')
    expect(risk.textContent).toContain('12.00%') // 年化收益(Delta 两位小数)
    expect(risk.textContent).toContain('20.0%') // 波动率
    expect(risk.textContent).toContain('0.50') // 夏普
    expect(risk.textContent).toContain('5.0%') // 最大回撤
    expect(risk.textContent).toContain('4') // 风险分
    expect(risk.textContent).toContain('中')
  })

  it('无快照时显示「暂无净值快照」空态，不渲染曲线', async () => {
    mockFetch({ overview: undefined, predictions: [] })
    renderPage()
    await screen.findByTestId('track-record')
    expect(screen.getByTestId('track-record-risk-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('track-record-curve')).not.toBeInTheDocument()
  })

  it('净值点 ≥2 时渲染净值曲线（agent vs 基准）', async () => {
    mockFetch({
      overview: OVERVIEW,
      predictions: PREDICTIONS,
      equity: [
        { date: '2026-09-01', agent_nav: 1.0, benchmark_nav: 1.0 },
        { date: '2026-09-02', agent_nav: 1.01, benchmark_nav: 1.005 },
        { date: '2026-09-03', agent_nav: 1.02, benchmark_nav: 1.01 },
      ],
    })
    renderPage()
    await screen.findByText('贵州茅台')
    expect(screen.getByTestId('track-record-curve')).toBeInTheDocument()
  })

  it('风险分 ≥8 高亮红色', async () => {
    const highRiskOverview = {
      ...OVERVIEW,
      portfolio: { available: true, annual_return: -0.2, volatility: 0.8,
        sharpe: -0.3, max_drawdown: 0.41, risk_score: 10, risk_label: '极高', as_of: '2026-09-04' },
    }
    mockFetch({ overview: highRiskOverview, predictions: PREDICTIONS })
    renderPage()
    await screen.findByText('贵州茅台')
    const score = screen.getByText('10')
    expect(score.className).toContain('text-red-500')
  })
})
