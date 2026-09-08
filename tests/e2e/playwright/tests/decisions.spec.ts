import { test, expect } from '@playwright/test'

/**
 * add-track-record Task 6：track-record 战绩页 E2E 门禁
 *
 * stub 后端使用独立测试库，predictions 初始为空 → 天然空态/样本积累中。
 * 侧边栏折叠态入口「决策战绩」（fa_sidebar_collapsed）固定折叠后可见。
 * /decisions 旧战绩页已重定向到 track-record 视图（同渲染）。
 *
 * 覆盖：
 * 1. 折叠态侧边栏「决策战绩」入口 → URL 变为 /track-record 且渲染战绩页 + 风险提示
 * 2. 直达 /track-record → 渲染 + 样本积累中/空态 + 返回聊天
 * 3. 旧 /decisions 路径仍渲染战绩页（重定向语义）
 *
 * 红线约束：不 mock /api/v1/track-record/* 业务接口；数据行渲染/状态分色等细节
 * 由组件测试（frontend/src/test/trackRecord/）覆盖。
 */
test.describe('add-track-record: 战绩页', () => {
  test.describe.configure({ retries: 2 })

  test('折叠态侧边栏「决策战绩」入口跳转 /track-record 并渲染战绩页', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('fa_sidebar_collapsed', '1'))
    await page.goto('/')
    const entry = page.getByTestId('sidebar-decisions-collapsed')
    await expect(entry).toBeVisible()
    await entry.click()
    await expect(page).toHaveURL(/\/track-record$/)
    await expect(page.getByTestId('track-record')).toBeVisible()
    // 风险提示常驻
    await expect(page.getByTestId('track-record-disclaimer')).toBeVisible()
  })

  test('直达 /track-record 渲染页面并显示样本积累中，可返回聊天', async ({ page }) => {
    test.setTimeout(240_000)
    await page.goto('/track-record')
    await expect(page.getByTestId('track-record')).toBeVisible()
    const insufficient = page.getByTestId('track-record-insufficient')
    const maxAttempts = 6
    let visible = false
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        await expect(insufficient).toBeVisible({ timeout: 20_000 })
        visible = true
        break
      } catch {
        if (attempt < maxAttempts - 1) {
          await page.reload({ timeout: 20_000 }).catch(() => {})
        }
      }
    }
    expect(visible, '轮询 6 次后样本积累提示仍未出现：track-record API 在全量套件负载下持续无响应窗口').toBe(true)
    // add-track-record-stage-b：无净值快照时展示风险指标空态（不渲染曲线）
    await expect(page.getByTestId('track-record-risk-empty')).toBeVisible()
    await expect(page.getByTestId('track-record-curve')).toHaveCount(0)
    await page.getByTestId('track-record-back').click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: '今天想研究什么？' })).toBeVisible()
  })

  test('旧 /decisions 路径重定向渲染战绩页', async ({ page }) => {
    await page.goto('/decisions')
    await expect(page).toHaveURL(/\/decisions$/)
    await expect(page.getByTestId('track-record')).toBeVisible()
  })
})
