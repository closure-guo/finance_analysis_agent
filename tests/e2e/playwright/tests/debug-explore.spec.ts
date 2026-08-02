import { test } from '@playwright/test'

/**
 * 探索脚本：获取切换会话前后的页面 ARIA snapshot
 */
test('探索：切换会话前后的页面状态', async ({ page }) => {
  page.on('console', msg => console.log(`[BROWSER ${msg.type()}]`, msg.text()))
  page.on('pageerror', err => console.log('[BROWSER ERROR]', err.message))

  await page.goto('http://localhost:5173')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'sk-2e9c5078489c4a9abb8d275470a8b4b2')
    localStorage.setItem('fa_user_id', 'debug-explore')
  })
  await page.reload()
  await page.waitForTimeout(500)

  // 切到深度模式
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
  await page.waitForTimeout(300)

  // 输入并发送
  await page.getByPlaceholder(/输入/).fill('深度分析600519')
  await page.getByTestId('send-button').click()

  // 等待事件
  console.log('\n=== 等待 SSE 事件 (15s) ===')
  await page.waitForTimeout(15000)

  // 截图 + ARIA snapshot：切换前
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/explore-01-before-switch.png', fullPage: true })
  console.log('\n=== ARIA SNAPSHOT: 切换前 ===')
  console.log(await page.locator('body').ariaSnapshot())

  // 新建分析（切走）
  await page.getByRole('button', { name: /新建分析/ }).click()
  await page.waitForTimeout(2000)

  // 截图 + ARIA snapshot：切换后
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/explore-02-after-switch.png', fullPage: true })
  console.log('\n=== ARIA SNAPSHOT: 切换后（新建分析） ===')
  console.log(await page.locator('body').ariaSnapshot())

  // 切回：点击侧边栏第一个会话
  // 先看侧边栏有什么可点击的
  console.log('\n=== 侧边栏按钮 ===')
  const buttons = page.locator('button')
  const count = await buttons.count()
  for (let i = 0; i < Math.min(count, 15); i++) {
    const text = await buttons.nth(i).textContent().catch(() => '')
    const visible = await buttons.nth(i).isVisible().catch(() => false)
    if (visible && text && text.trim()) {
      console.log(`  button[${i}]: "${text.trim().substring(0, 50)}"`)
    }
  }

  // 尝试点击第一个会话项（跳过"新建分析"按钮）
  const sessionItems = page.locator('button:has-text("深度分析"), button:has-text("分析"), [class*="session"]')
  const sessionCount = await sessionItems.count()
  console.log(`\n=== 会话项数量: ${sessionCount} ===`)

  if (sessionCount > 0) {
    await sessionItems.first().click()
    await page.waitForTimeout(3000)

    // 截图 + ARIA snapshot：切回后
    await page.screenshot({ path: 'tests/e2e/debug-screenshots/explore-03-after-return.png', fullPage: true })
    console.log('\n=== ARIA SNAPSHOT: 切回后 ===')
    console.log(await page.locator('body').ariaSnapshot())

    // 检查输入框
    const inputVisible = await page.getByPlaceholder(/输入/).isVisible().catch(() => false)
    console.log(`\n=== 输入框可见: ${inputVisible} ===`)
  }
})
