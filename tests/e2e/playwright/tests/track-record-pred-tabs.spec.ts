import { expect, test } from '@playwright/test'

/**
 * update-prediction-log-tabs:观点日志标题与状态 tab E2E(专属套件,独立测试库)。
 * 红线:不 mock 业务接口。专属库无 predictions 造数通道(观点经分析产出),
 * 故数据态断言由前端单测覆盖(mock 层);本 spec 验证纯前端 tab 状态机:
 * 标题/副标题渲染、缺省 active=当前持有、点击切换 active 迁移。
 * 空库下表格走空态文案,不受 tab 影响——作为兜底断言。
 */
test.describe.configure({ mode: 'serial' })

test.describe('战绩页:观点日志标题与状态 tab', () => {
  test('标题与副标题渲染,缺省 active=当前持有', async ({ page }) => {
    await page.goto('/track-record')
    await expect(page.getByTestId('prediction-log-header')).toBeVisible()
    await expect(page.getByText('观点日志', { exact: true })).toBeVisible()
    await expect(page.getByText(/每条 = 一次分析结论/)).toBeVisible()
    await expect(page.getByTestId('prediction-tab-open')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('prediction-tab-resolved')).toHaveAttribute('aria-selected', 'false')
    await expect(page.getByTestId('prediction-tab-all')).toHaveAttribute('aria-selected', 'false')
  })

  test('点击切换 active 迁移,空态文案不受 tab 影响', async ({ page }) => {
    await page.goto('/track-record')
    await expect(page.getByTestId('prediction-log-header')).toBeVisible()
    await page.getByTestId('prediction-tab-resolved').click()
    await expect(page.getByTestId('prediction-tab-resolved')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('prediction-tab-open')).toHaveAttribute('aria-selected', 'false')
    await page.getByTestId('prediction-tab-all').click()
    await expect(page.getByTestId('prediction-tab-all')).toHaveAttribute('aria-selected', 'true')
    // 空库(无观点)→ 表格空态;切 tab 不改变空态语义
    await expect(page.getByTestId('track-record-empty')).toBeVisible()
  })
})
