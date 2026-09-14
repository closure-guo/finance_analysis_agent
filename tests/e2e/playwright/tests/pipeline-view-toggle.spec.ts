import { test, expect } from '@playwright/test'

/**
 * 管线卡视图切换 E2E（add-pipeline-graph-view）
 *
 * 覆盖变更后的产品默认：`fa_pipeline_view` 未设时管线卡渲染 **graph 视图**，
 * 列表时间轴不在 DOM；点击「列表」后时间轴渲染（切换即时生效）。
 * 持久化与窄屏降级由组件测试覆盖（PipelineCardViewToggle.test.tsx）。
 *
 * 环境：STUB_SCENARIO=pipeline（8002/前端 5175，playwright.timeline.config.ts 拉起）。
 */
test.setTimeout(180_000)

test.describe('管线卡视图切换（graph 默认 / 列表可切）', () => {
  test('默认 graph 渲染且时间轴不在 DOM；切列表后时间轴可见', async ({ page }) => {
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-view-toggle')
      // 不设 fa_pipeline_view → 走默认（graph）
      localStorage.removeItem('fa_pipeline_view')
    })
    await page.reload()

    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 默认 graph：图视图渲染，列表时间轴不在 DOM
    await expect(page.getByTestId('pipeline-graph')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('pipeline-timeline')).toHaveCount(0)

    // 切「列表」→ 时间轴渲染
    await page.getByTestId('pipeline-view-list').click()
    await expect(page.getByTestId('pipeline-timeline')).toBeVisible({ timeout: 15_000 })
  })
})
