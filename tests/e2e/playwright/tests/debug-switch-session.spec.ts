import { test, expect, type Page } from '@playwright/test'

/**
 * 调试脚本：测试切换会话后前端状态
 * 用真实 Docker 服务（后端 8000 / 前端 5173）
 */
test.setTimeout(120_000)

const FRONTEND = 'http://localhost:5173'
const LLM_KEY = process.env.LLM_API_KEY || 'stub-key-for-testing'

test('调试：切换会话后前端状态', async ({ page }) => {
  // 收集控制台日志
  page.on('console', msg => console.log(`[BROWSER ${msg.type()}]`, msg.text()))
  page.on('pageerror', err => console.log('[BROWSER ERROR]', err.message))

  // 1. 打开前端，设置 API key
  await page.goto(FRONTEND)
  await page.evaluate((key) => {
    localStorage.setItem('fa_api_key', key)
    localStorage.setItem('fa_user_id', 'debug-test')
  }, LLM_KEY)
  await page.reload()
  await page.waitForTimeout(1000)

  // 2. 切到深度模式
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
  await page.waitForTimeout(500)

  // 3. 输入并发送
  await page.getByPlaceholder(/输入/).fill('深度分析600519')
  await page.getByTestId('send-button').click()

  // 4. 等待第一个事件（思考内容或管线时间轴）
  console.log('--- 等待 SSE 事件 ---')
  try {
    await page.waitForSelector('text=分析', { timeout: 30000 })
    console.log('--- 收到事件，页面有内容 ---')
  } catch {
    console.log('--- 30s 内无事件 ---')
    // 截图看状态
    await page.screenshot({ path: 'tests/e2e/debug-screenshots/01-no-event.png' })
  }

  await page.waitForTimeout(5000) // 等待更多事件

  // 5. 截图：切换前
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/02-before-switch.png', fullPage: true })
  console.log('--- 截图：切换前 ---')

  // 6. 检查当前页面状态
  const bodyText1 = await page.locator('body').textContent()
  console.log('--- 切换前 body 文本长度:', bodyText1?.length ?? 0, '---')

  // 7. 新建分析（触发 selectSession 切走）
  await page.getByRole('button', { name: /新建分析/ }).click()
  await page.waitForTimeout(2000)

  // 8. 截图：切换后
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/03-after-switch.png', fullPage: true })
  console.log('--- 截图：切换后 ---')

  const bodyText2 = await page.locator('body').textContent()
  console.log('--- 切换后 body 文本长度:', bodyText2?.length ?? 0, '---')

  // 9. 切回：点击侧边栏第一个会话
  const sessions = page.locator('[class*="session"], [class*="sidebar"] button, [class*="history"] button')
  const count = await sessions.count()
  console.log('--- 侧边栏按钮数量:', count, '---')

  // 尝试点击第一个非"新建分析"的会话
  if (count > 1) {
    await sessions.nth(1).click()
    await page.waitForTimeout(3000)

    // 10. 截图：切回后
    await page.screenshot({ path: 'tests/e2e/debug-screenshots/04-after-return.png', fullPage: true })
    console.log('--- 截图：切回后 ---')

    const bodyText3 = await page.locator('body').textContent()
    console.log('--- 切回后 body 文本长度:', bodyText3?.length ?? 0, '---')

    // 11. 检查是否有输入框（界面是否可用）
    const inputVisible = await page.getByPlaceholder(/输入/).isVisible().catch(() => false)
    console.log('--- 输入框可见:', inputVisible, '---')
  }

  // 12. 检查是否有错误消息
  const errorVisible = await page.locator('text=/错误|失败|出错/i').first().isVisible().catch(() => false)
  console.log('--- 有错误消息:', errorVisible, '---')
})
