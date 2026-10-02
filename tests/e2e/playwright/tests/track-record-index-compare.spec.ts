import { expect, test } from '@playwright/test'

/**
 * add-index-performance-compare:跑赢指数对比卡片 E2E 门禁。
 * 红线:不 mock /api/v1/track-record/*;数据经 TESTING=1 的 /api/test/seed 写入
 * 独立测试库(e2e webServer 的 SESSIONS_DB_PATH)。测试间有数据依赖,串行执行。
 *
 * 前提(与 decisions.spec.ts「天然空态」同一约定):测试库初始无 equity_curve 数据。
 * 本 spec 是套件中唯一写 track_record 造数的 spec(全仓 grep 核实),但 test 2 的
 * 种子会残留在共享测试库——重复跑/全量套件前需删除 `data/test-e2e-sessions.db*`
 * (brief 注意①;`/api/test/reset` 为占位骨架,不清数据)。残留也会污染
 * decisions.spec.ts 的「无净值快照空态」断言,全量套件必须从干净库起跑。
 *
 * 对 brief 的两处实现修正(详见 task-10-report.md):
 * 1. 种子 agent_nav 1.05 → 1.005:brief 原值(+5%)会跑赢全部四个指数(4/4),
 *    与其自身断言(跑赢 2/4、row-000300 ↓ 跑输)矛盾;+0.5% 使 000001/000300(+2%/+1%)
 *    跑输、000905/000852(-1%/-2%)跑赢,brief 断言逐字成立(beat = agent_return > ret)。
 * 2. test 3 的 `expect(spanReq).toPass()`:toPass() 要求可重试函数而非 Promise,
 *    改为注册 waitForRequest → goto → await 的标准免竞态写法,并补卡片可见终态锚点。
 */
test.describe.configure({ mode: 'serial', timeout: 120_000 })

test.describe('战绩页:跑赢指数对比', () => {
  test('无数据时空态渲染,卡片可见', async ({ page }) => {
    await page.goto('/track-record')
    await expect(page.getByTestId('track-record')).toBeVisible()
    await expect(page.getByTestId('index-compare-card')).toBeVisible()
    await expect(page.getByTestId('index-compare-empty')).toBeVisible()
  })

  test('造数后渲染摘要与对比条,跑赢/跑输分色', async ({ page, request }) => {
    const seedResp = await request.post('http://localhost:8000/api/test/seed', {
      data: {
        track_record: {
          equity_curve: [
            { curve_date: '2026-09-01', agent_nav: 1.0, benchmark_nav: 1.0 },
            { curve_date: '2026-09-30', agent_nav: 1.005, benchmark_nav: 0.99 }, // 组合 +0.5%
          ],
          index_closes: [
            { index_code: '000001', trade_date: '2026-09-01', close: 3000.0 },
            { index_code: '000001', trade_date: '2026-09-30', close: 3060.0 }, // +2% 跑输
            { index_code: '000300', trade_date: '2026-09-01', close: 4000.0 },
            { index_code: '000300', trade_date: '2026-09-30', close: 4040.0 }, // +1% 跑输
            { index_code: '000905', trade_date: '2026-09-01', close: 6000.0 },
            { index_code: '000905', trade_date: '2026-09-30', close: 5940.0 }, // -1% 跑赢
            { index_code: '000852', trade_date: '2026-09-01', close: 2500.0 },
            { index_code: '000852', trade_date: '2026-09-30', close: 2450.0 }, // -2% 跑赢
            // 399006 不造 → 无数据灰显,摘要分母为 4
          ],
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto('/track-record')
    await expect(page.getByTestId('index-compare-summary')).toHaveText(/跑赢 2\/4 个指数/)
    const row300 = page.getByTestId('index-compare-row-000300')
    await expect(row300).toContainText('↓ 跑输')
    const row905 = page.getByTestId('index-compare-row-000905')
    await expect(row905).toContainText('↑ 跑赢')
    const row006 = page.getByTestId('index-compare-row-399006')
    await expect(row006).toContainText('无数据')
  })

  test('跨度偏好决定请求参数', async ({ page }) => {
    // fa_track_prefs 四字段全量结构见 frontend/src/lib/trackPrefs.ts(TrackPrefs)
    await page.addInitScript(() => {
      localStorage.setItem(
        'fa_track_prefs',
        JSON.stringify({ timeSpan: '3m', benchmark: 'none', drawdownThreshold: 0.2, navChartForm: 'cumulative' }),
      )
    })
    // 注册先于 goto,免竞态;页面挂载即按偏好发 span=3m 请求(唯一带该参数的接口)
    const spanReq = page.waitForRequest(
      r => r.url().includes('/api/v1/track-record/index-compare') && r.url().includes('span=3m'),
    )
    await page.goto('/track-record')
    await spanReq
    await expect(page.getByTestId('index-compare-card')).toBeVisible()
  })
})
