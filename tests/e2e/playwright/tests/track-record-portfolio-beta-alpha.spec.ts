import { expect, test } from '@playwright/test'

/**
 * add-portfolio-beta-alpha:总览 β/α 指标位 E2E(专属套件,独立测试库)。
 * 造数经 /api/test/seed 直写指标快照(计算正确性由后端集成测试覆盖)。
 * 串行模式。
 *
 * update-track-record-data-integrity 后 portfolio.available 收紧为
 * 「快照存在 且 equity_curve 有数据」(as_of 必须是净值数据日期的诚实性要求),
 * 故本 spec 种子必须同时写一行 equity_curve。
 * 文件名带 portfolio- 前缀保证排在 track-record-index-compare.spec.ts 之后
 * ('p' > 'i'):本 spec 写 equity_curve,而 index-compare 首用例依赖空库。
 */
test.describe.configure({ mode: 'serial' })

test.describe('战绩页:β/α 指标位', () => {
  test('快照有值时渲染两格', async ({ page, request }) => {
    const resp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          equity_curve: [{ curve_date: '2026-09-30', agent_nav: 1.0, benchmark_nav: 1.0 }],
          metrics_snapshot: { beta: 0.85, jensen_alpha: 0.031, annual_return: 0.1, volatility: 0.15, sharpe: 0.5, max_drawdown: 0.05, risk_score: 3, risk_label: '低' },
        },
      },
    })
    expect(resp.ok()).toBeTruthy()
    await page.goto('/track-record')
    await expect(page.getByTestId('portfolio-beta')).toHaveText('0.85')
    await expect(page.getByTestId('portfolio-alpha')).toHaveText('+3.10%')
  })

  test('样本不足时两格显示 —', async ({ page, request }) => {
    const resp = await request.post('/api/test/seed', {
      data: { track_record: { metrics_snapshot: { beta: null, jensen_alpha: null, annual_return: 0.1, volatility: 0.15, sharpe: 0.5, max_drawdown: 0.05, risk_score: 3, risk_label: '低' } } },
    })
    expect(resp.ok()).toBeTruthy()
    await page.goto('/track-record')
    await expect(page.getByTestId('portfolio-beta')).toHaveText('—')
    await expect(page.getByTestId('portfolio-alpha')).toHaveText('—')
  })
})
