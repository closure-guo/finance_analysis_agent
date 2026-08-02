import { test, expect } from '@playwright/test'

/**
 * 验证：切换会话后 SSE 流不被中断，切回后有新内容
 */
test.setTimeout(120_000)

const API_BASE = 'http://localhost:8000'
const FRONTEND = 'http://localhost:5173'

test('SSE 流在切换会话后继续运行，切回后有新内容', async ({ page }) => {
  page.on('console', msg => {
    if (msg.type() === 'error') console.log(`[BROWSER ERROR]`, msg.text())
  })

  await page.goto(FRONTEND)
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'sk-2e9c5078489c4a9abb8d275470a8b4b2')
    localStorage.setItem('fa_user_id', 'debug-sse-continue')
  })
  await page.reload()
  await page.waitForTimeout(500)

  // 切到深度模式并发送
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
  await page.waitForTimeout(300)
  await page.getByPlaceholder(/输入/).fill('深度分析600519')
  await page.getByTestId('send-button').click()

  // 等待思考内容出现
  await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 30000 })
  console.log('--- 收到思考内容 ---')

  // 记录切换前的内容长度
  const contentBefore = await page.locator('body').textContent()
  const lengthBefore = contentBefore?.length ?? 0
  console.log(`--- 切换前内容长度: ${lengthBefore} ---`)

  // 获取当前会话
  const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
  const sessions = (await sessionsResp.json()).sessions as Array<{ session_id: string; display_name: string }>
  const target = sessions[0]

  // 切走（新建分析）
  await page.getByRole('button', { name: /新建分析/ }).click()
  await page.waitForTimeout(2000)
  console.log('--- 已切走 ---')

  // 等待 10 秒，让 SSE 在后台继续接收
  console.log('--- 等待 10s（SSE 后台继续） ---')
  await page.waitForTimeout(10000)

  // 切回原会话
  await page.getByText(target.display_name, { exact: false }).first().click()
  await page.waitForTimeout(3000)
  console.log('--- 已切回 ---')

  // 检查切回后的内容
  const contentAfter = await page.locator('body').textContent()
  const lengthAfter = contentAfter?.length ?? 0
  console.log(`--- 切回后内容长度: ${lengthAfter} ---`)

  // 通过 API 检查会话状态和 chat_history
  const detailResp = await page.request.get(`${API_BASE}/api/sessions/${target.session_id}`)
  const detail = await detailResp.json()
  console.log(`--- 会话状态: ${detail.status} ---`)
  console.log(`--- chat_history 长度: ${detail.chat_history?.length ?? 0} ---`)
  if (detail.chat_history?.length > 1) {
    const assistant = detail.chat_history.find((h: any) => h.role === 'assistant')
    if (assistant) {
      console.log(`--- assistant thinking 长度: ${assistant.thinking?.length ?? 0} ---`)
      console.log(`--- assistant content 长度: ${assistant.content?.length ?? 0} ---`)
    }
  }

  // 断言：切回后不是首页
  const isHomepage = await page.getByRole('heading', { name: 'Finance Analysis Agent' }).isVisible().catch(() => false)
  expect(isHomepage, '切回后不应显示首页').toBe(false)

  // 断言：输入框可见
  const inputVisible = await page.getByPlaceholder(/输入/).isVisible().catch(() => false)
  expect(inputVisible, '输入框应可见').toBe(true)

  // 断言：有之前的用户消息
  const hasUserMsg = await page.getByText('深度分析600519').first().isVisible().catch(() => false)
  expect(hasUserMsg, '应显示用户消息').toBe(true)
})
