import { test, expect } from '@playwright/test'

/**
 * 股价 K 线图 E2E（update-price-chart-kline delta）
 *
 * 覆盖：深度分析管线完成后，报告图表区渲染「股价 K 线」卡片
 *（data-testid=chart-stock-price，ECharts candlestick 落地为 canvas）。
 * 卡片标题 /股价 K 线/ 断言证明前端走的是 K 线分支而非折线降级
 * （折线分支标题为「股价趋势（红色虚线为年报发布日）」）。
 *
 * 环境：与 report-export.spec.ts 同一管线端口对（5175 → 8002
 * STUB_SCENARIO=pipeline，playwright.timeline.config.ts 拉起）；
 * selector 复用该 spec 已真实探索的 DOM 结论 + 本 delta 新增 testid。
 *
 * 历史会话（仅 close）降级分支由组件测试 stockPriceKline.test.tsx 覆盖
 *（管线 stub 恒产 OHLC，E2E 无法构造历史形态会话，不作虚假覆盖）。
 */

test.setTimeout(240_000)

test('深度分析完成后报告渲染股价 K 线图', async ({ page }) => {
  // 1. 进入应用并注入测试 API Key（管线端口对 5175 → 8002）
  await page.goto('http://localhost:5175')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-kline-chart')
  })
  await page.reload()

  // 2. 显式选中深度研究模式（EmptyState 两步下拉）
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()

  // 3. 发送深度分析请求（stub 确定性触发 5 层管线）
  await page.getByPlaceholder(/输入/).fill('深度分析600519')
  await page.getByTestId('send-button').click()

  // 4. 报告完成终态：报告卡标题出现
  await expect(
    page.getByRole('heading', { name: '贵州茅台（600519）' }),
  ).toBeVisible({ timeout: 150_000 })

  // 5. 股价 K 线卡片可见，标题证明 K 线分支（非折线降级）
  const klineCard = page.getByTestId('chart-stock-price')
  await expect(klineCard).toBeVisible({ timeout: 30_000 })
  await expect(klineCard.getByRole('heading', { name: /股价 K 线/ })).toBeVisible()
  // ECharts 成功挂载时 canvas 渲染（toBeVisible 自带非零包围盒断言；
  // option 构造崩溃时 ECharts 不产 canvas，本断言变红）
  await expect(klineCard.locator('canvas').first()).toBeVisible()
})
