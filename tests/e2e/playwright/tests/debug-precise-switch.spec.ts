import { test, expect } from '@playwright/test'

/**
 * 精确测试：切换会话后切回，检查前端状态
 * 复用 Docker 服务（后端 8000 / 前端 5173）
 */
test.setTimeout(120_000)

const API_BASE = 'http://localhost:8000'
const FRONTEND = 'http://localhost:5173'

test('切换会话后切回：前端 SHALL 恢复聊天界面', async ({ page }) => {
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      console.log(`[BROWSER ${msg.type()}]`, msg.text())
    }
  })
  page.on('pageerror', err => console.log('[BROWSER ERROR]', err.message))

  // 1. 打开前端，设置 API key
  await page.goto(FRONTEND)
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'sk-2e9c5078489c4a9abb8d275470a8b4b2')
    localStorage.setItem('fa_user_id', 'debug-test-switch')
  })
  await page.reload()
  await page.waitForTimeout(500)

  // 2. 切到深度模式并发送
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
  await page.waitForTimeout(300)
  await page.getByPlaceholder(/输入/).fill('深度分析600519')
  await page.getByTestId('send-button').click()

  // 3. 等待思考内容出现（证明 SSE 在工作）
  console.log('--- 等待思考内容 ---')
  await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 30000 })
  console.log('--- 收到思考内容，SSE 正常 ---')

  // 4. 通过 API 获取当前会话 ID
  const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
  const sessions = (await sessionsResp.json()).sessions as Array<{
    session_id: string
    display_name: string
    status: string
  }>
  // 最新的会话是我们刚创建的
  const target = sessions[0]
  console.log(`--- 当前会话: ${target.session_id}, name="${target.display_name}", status=${target.status} ---`)

  // 5. 截图：切换前
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/precise-01-before-switch.png', fullPage: true })

  // 6. 点击"新建分析"切走
  await page.getByRole('button', { name: /新建分析/ }).click()
  await page.waitForTimeout(2000)

  // 7. 截图：切走后
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/precise-02-after-switch.png', fullPage: true })
  console.log('--- 已切走（新建分析） ---')

  // 8. 切回：在侧边栏中点击原会话
  // 用 display_name 精确匹配
  const sessionItem = page.getByText(target.display_name, { exact: false }).first()
  await expect(sessionItem).toBeVisible({ timeout: 5000 })
  await sessionItem.click()
  await page.waitForTimeout(3000)

  // 9. 截图：切回后
  await page.screenshot({ path: 'tests/e2e/debug-screenshots/precise-03-after-return.png', fullPage: true })
  console.log('--- 已切回 ---')

  // 10. 检查页面状态
  // ARIA snapshot 检查
  const snapshot = await page.locator('body').ariaSnapshot()
  console.log('--- 切回后 ARIA snapshot (前 500 字符) ---')
  console.log(snapshot.substring(0, 500))

  // 11. 断言：不应该是首页（empty 状态）
  const isHomepage = await page.getByRole('heading', { name: 'Finance Analysis Agent' }).isVisible().catch(() => false)
  console.log(`--- 是首页: ${isHomepage} ---`)

  // 12. 断言：输入框应该可见
  const inputVisible = await page.getByPlaceholder(/输入/).isVisible().catch(() => false)
  console.log(`--- 输入框可见: ${inputVisible} ---`)

  // 13. 断言：应该能看到之前的输出内容（思考内容或用户消息）
  const hasContent = await page.getByText('深度分析600519').first().isVisible().catch(() => false)
  console.log(`--- 有之前的内容: ${hasContent} ---`)

  // 14. 核心断言
  expect(isHomepage, '切回后不应显示首页').toBe(false)
  expect(inputVisible, '切回后输入框应可见').toBe(true)
})
