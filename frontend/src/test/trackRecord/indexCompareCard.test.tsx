import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { IndexCompareCard } from '../../pages/trackRecord/IndexCompareCard'

const RESP = {
  span: 'all',
  window: { start: '2026-09-28', end: '2026-10-09' },
  agent_return: 0.05,
  indices: [
    { code: '000001', name: '上证指数', return: 0.03, effective_start_date: '2026-09-28', beat: true },
    { code: '000300', name: '沪深300', return: 0.01, effective_start_date: '2026-09-26', beat: true },
    { code: '000905', name: '中证500', return: 0.1, effective_start_date: '2026-09-28', beat: false },
    { code: '000852', name: '中证1000', return: null, effective_start_date: null, beat: null },
    { code: '399006', name: '创业板指', return: 0.02, effective_start_date: '2026-09-28', beat: true },
  ],
  as_of: '2026-10-02',
  disclaimer: '历史业绩不代表未来表现',
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('IndexCompareCard', () => {
  it('渲染 N/M 摘要并按收益降序排列,跑赢绿↑跑输红↓', async () => {
    // 既有 fetch mock 模式(trackRecordPage.test 同款):new Response + status 200
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(RESP), { status: 200 })))
    render(<IndexCompareCard span="all" />)
    await screen.findByTestId('index-compare-summary')
    // 分母 = beat 非 null 数(spec: 无数据指数不参与 N/M 分母)→ 5 只中 000852 beat=null,故 3/4
    expect(screen.getByTestId('index-compare-summary').textContent).toContain('跑赢 3/4 个指数')
    const rows = screen.getAllByTestId(/^index-compare-row-/)
    // 正确降序:0.10, 0.03, 0.02, 0.01, null(brief 原稿此数组故意写错,TDD 前已修正)
    expect(rows.map(r => r.dataset.testid)).toEqual([
      'index-compare-row-000905', // 0.10
      'index-compare-row-000001', // 0.03
      'index-compare-row-399006', // 0.02
      'index-compare-row-000300', // 0.01
      'index-compare-row-000852', // null → 末位
    ])
    // 跑输红 ↓(000905)、跑赢绿 ↑(000001);无数据灰显「无数据」
    const row905 = screen.getByTestId('index-compare-row-000905')
    expect(row905.textContent).toContain('↓ 跑输')
    // 颜色挂在行内 beat 标记 span 上(style 属性),行 div 本身无 style
    expect(within(row905).getByText('↓ 跑输').getAttribute('style')).toContain('var(--status-error-default)')
    const row001 = screen.getByTestId('index-compare-row-000001')
    expect(row001.textContent).toContain('↑ 跑赢')
    expect(within(row001).getByText('↑ 跑赢').getAttribute('style')).toContain('var(--status-success-default)')
    expect(screen.getByTestId('index-compare-row-000852').textContent).toContain('无数据')
    // 起算日标注:000300 effective_start_date(2026-09-26)≠ 窗口首日(2026-09-28)
    expect(screen.getByTestId('index-compare-row-000300').textContent).toContain('(自 2026-09-26 起算)')
    // 风险提示常驻
    expect(screen.getByTestId('index-compare-card').textContent).toContain('历史业绩不代表未来表现')
  })

  it('agent_return 为 null 时展示空态,不渲染摘要与对比条', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...RESP, agent_return: null,
    }), { status: 200 })))
    render(<IndexCompareCard span="3m" />)
    expect(await screen.findByTestId('index-compare-empty')).toBeInTheDocument()
    expect(screen.getByTestId('index-compare-empty').textContent).toContain('净值数据积累中')
    expect(screen.queryByTestId('index-compare-summary')).not.toBeInTheDocument()
    expect(screen.queryByTestId(/^index-compare-row-/)).not.toBeInTheDocument()
  })
})
