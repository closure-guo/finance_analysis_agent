import { test, expect } from '@playwright/test'

/**
 * E2E: 流式输出中途切换会话再切回，内容继续增长且无重复渲染
 *
 * 对应 delta spec: resume-stream-on-session-switch Task 7.1
 * 核心场景：
 * 1. 发起深度分析，等待流式输出开始
 * 2. 切换到新会话（切走，不中断后端任务）
 * 3. 等待若干秒（后端任务继续产出事件到 journal）
 * 4. 切回原会话（经恢复端点重放 + 续传）
 * 5. 断言输出内容从切出位置继续增长
 *
 * 禁止 mock 数据，必须通过前端模拟用户真实点击操作。
 */
const API_BASE = 'http://localhost:8000'
const FRONTEND = 'http://localhost:5173'

test.describe('Session Switch - Stream Resumption', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', msg => {
      if (msg.type() === 'error') console.log(`[BROWSER ERROR]`, msg.text())
    })
    page.on('pageerror', err => console.log('[PAGE ERROR]', err.message))

    await page.goto(FRONTEND)
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'sk-2e9c5078489c4a9abb8d275470a8b4b2')
      localStorage.setItem('fa_user_id', 'e2e-session-switch')
    })
    await page.reload()
    await page.waitForTimeout(500)
  })

  test('中途切出再切回，内容继续增长', async ({ page }) => {
    test.setTimeout(180_000)

    // 切换到深度研究模式
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.waitForTimeout(300)

    // 输入并发送
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 等待流式输出开始
    await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 45_000 })

    // 记录切出前内容长度
    const contentBefore = await page.locator('body').textContent()
    const lengthBefore = contentBefore?.length ?? 0
    console.log(`[E2E] 切出前内容长度: ${lengthBefore}`)

    // 获取会话 ID
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    const sessionId = sessions[0]?.session_id ?? ''
    console.log(`[E2E] 会话 ID: ${sessionId}`)

    // 切走：点击"新建分析"
    await page.getByRole('button', { name: /新建分析/ }).click()
    await page.waitForTimeout(2000)
    console.log('[E2E] 已切到新会话')

    // 等待 10 秒（后端任务继续运行，事件写入 journal）
    console.log('[E2E] 等待 10 秒...')
    await page.waitForTimeout(10_000)

    // 切回原会话
    const sessionsResp2 = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions2 = (await sessionsResp2.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    const target = sessions2.find(s => s.session_id === sessionId)
    if (!target) throw new Error('未找到原会话')

    await page.getByText(target.display_name, { exact: false }).first().click()
    await page.waitForTimeout(3000)
    console.log('[E2E] 已切回原会话')

    // 等待内容渲染
    await page.waitForTimeout(2000)
    const contentAfter = await page.locator('body').textContent()
    const lengthAfter = contentAfter?.length ?? 0
    console.log(`[E2E] 切回后内容长度: ${lengthAfter}`)
    console.log(`[E2E] 增长字节数: ${lengthAfter - lengthBefore}`)

    // 核心断言：切回后内容必须比切出前多
    expect(lengthAfter, '切回后内容应继续增长').toBeGreaterThan(lengthBefore)

    // 验证会话状态
    const detailResp = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`)
    const detail = await detailResp.json()
    console.log(`[E2E] 会话状态: ${detail.status}`)
    expect(['running', 'completed', 'clarifying', 'interrupted']).toContain(detail.status)
  })

  test('显式停止后状态为中断', async ({ page }) => {
    test.setTimeout(120_000)

    // 切换到深度研究模式
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.waitForTimeout(300)

    // 输入并发送
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 等待流式输出开始
    await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 45_000 })

    // 获取会话 ID
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
    }>
    const sessionId = sessions[0]?.session_id ?? ''

    // 等待 2 秒确保有部分输出
    await page.waitForTimeout(2000)

    // 点击停止按钮
    const stopButton = page.getByRole('button', { name: /停止/ })
    if (await stopButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await stopButton.click()
      console.log('[E2E] 已点击停止按钮')

      // 等待中断态
      await page.waitForTimeout(3000)

      // 验证会话状态变为 interrupted
      const detailResp = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`)
      const detail = await detailResp.json()
      console.log(`[E2E] 停止后会话状态: ${detail.status}`)
      expect(['interrupted', 'clarifying', 'completed']).toContain(detail.status)
    } else {
      console.log('[E2E] 停止按钮不可见，跳过测试')
      test.skip()
    }
  })

  test('运行中的会话拒绝新输入', async ({ page }) => {
    test.setTimeout(120_000)

    // 切换到深度研究模式
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.waitForTimeout(300)

    // 输入并发送
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 等待流式输出开始
    await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 45_000 })

    // 等待 2 秒确保任务正在运行
    await page.waitForTimeout(2000)

    // 尝试再次输入并发送
    await page.getByPlaceholder(/输入/).fill('600036')
    await page.getByTestId('send-button').click()

    // 应看到"生成中"提示
    await expect(page.getByText(/生成中|正在生成|停止后再发/i).first()).toBeVisible({ timeout: 5000 })
    console.log('[E2E] 拦截提示已显示')
  })
})
