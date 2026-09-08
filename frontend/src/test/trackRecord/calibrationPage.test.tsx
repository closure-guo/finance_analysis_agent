import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CalibrationPage } from '../../pages/trackRecord/CalibrationPage'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="mock-chart" />,
}))

const CALIBRATION = {
  buckets: [
    { bucket: '[0.5,0.6)', mid: 0.55, n: 2, hit_rate: 0.5 },
    { bucket: '[0.7,0.8)', mid: 0.75, n: 2, hit_rate: 0.75 },
    { bucket: '[0.9,1.0)', mid: 0.95, n: 1, hit_rate: 0 },
  ],
  brier: 0.12,
  sample_size: 5,
  as_of: '2026-09-04',
  disclaimer: '历史业绩不代表未来表现',
}

function mockFetch(payload: unknown = CALIBRATION) {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(payload), { status: 200 }))))
}

function renderPage() {
  return render(<CalibrationPage onBack={vi.fn()} />)
}

describe('校准页（add-track-record-stage-c）', () => {
  beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('渲染 Brier Score 与样本量', async () => {
    mockFetch()
    renderPage()
    expect(await screen.findByTestId('calibration-page')).toBeInTheDocument()
    expect(screen.getByText('0.1200')).toBeInTheDocument()
    expect(screen.getByTestId('calibration-summary').textContent).toContain('5')
  })

  it('有样本时渲染曲线与分桶表', async () => {
    mockFetch()
    renderPage()
    await screen.findByTestId('calibration-page')
    expect(screen.getByTestId('calibration-curve')).toBeInTheDocument()
    const table = screen.getByTestId('calibration-table')
    expect(table.textContent).toContain('[0.7,0.8)')
    expect(table.textContent).toContain('75.0%')
  })

  it('无样本时显示空态且无曲线', async () => {
    mockFetch({ ...CALIBRATION, sample_size: 0, brier: null })
    renderPage()
    await screen.findByTestId('calibration-page')
    expect(screen.getByTestId('calibration-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('calibration-curve')).not.toBeInTheDocument()
  })

  it('免责声明常驻', async () => {
    mockFetch()
    renderPage()
    await screen.findByTestId('calibration-page')
    expect(screen.getByTestId('calibration-disclaimer')).toBeInTheDocument()
  })
})