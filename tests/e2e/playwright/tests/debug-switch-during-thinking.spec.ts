import { test, expect } from '@playwright/test'

/**
 * 验证：Agent 思考中途切换会话，切回后思考内容保持持续流式输出
 *
 * 核心场景：
 * 1. 发送深度分析请求，等待思考内容首次出现
 * 2. 切换到新会话（切走）
 * 3. 等待 10 秒（SSE 在后台持续接收）
 * 4. 切回原会话
 * 5. 断言：切回后 agent 生成的内容仍然存在（不全部消失）
 *
 * 对应 delta spec: harden-react-path-resilience
 * 验证任务：SSE 心跳保护 + 会话隔离机制 + 消息快照缓存
 */
const API_BASE = 'http://localhost:8000'
const FRONTEND = 'http://localhost:5173'

test.describe('Agent 思考中途切换会话 - 流式输出持续性', () => {
  let sessionId: string

  test.beforeEach(async ({ page }) => {
    test.setTimeout(180_000)

    // 捕获浏览器日志
    page.on('console', msg => {
      if (msg.type() === 'error') console.log(`[BROWSER ERROR]`, msg.text())
    })
    page.on('pageerror', err => console.log('[PAGE ERROR]', err.message))

    // 配置 API Key 和用户 ID
    await page.goto(FRONTEND)
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'sk-2e9c5078489c4a9abb8d275470a8b4b2')
      localStorage.setItem('fa_user_id', 'debug-thinking-switch')
    })
    await page.reload()
    await page.waitForTimeout(500)

    // Given: 切换到深度研究模式
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.waitForTimeout(300)

    // When: 输入并发送股票查询
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // Then: 等待思考内容首次出现（Agent 开始思考并输出 token）
    await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 45_000 })

    // 获取当前会话 ID
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    sessionId = sessions[0]?.session_id ?? ''
    console.log(`[THINKING] 当前会话 ID: ${sessionId}`)
  })

  test('思考中途切换会话，切回后思考内容持续增长', async ({ page }) => {
    // 记录切换前的内容长度
    const contentBeforeSwitch = await page.locator('body').textContent()
    const lengthBeforeSwitch = contentBeforeSwitch?.length ?? 0
    console.log(`[THINKING] 切换前内容长度: ${lengthBeforeSwitch}`)

    // When: 点击"新建分析"切走（不中断 SSE，仅跳过 UI 更新）
    await page.getByRole('button', { name: /新建分析/ }).click()
    await page.waitForTimeout(2000)
    console.log('[THINKING] 已切换到新会话')

    // When: 等待 10 秒（SSE 在后台持续接收）
    console.log('[THINKING] 等待 10 秒，SSE 后台持续接收...')
    await page.waitForTimeout(10_000)

    // When: 切回原会话
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    const target = sessions.find(s => s.session_id === sessionId)
    if (!target) throw new Error('未找到原会话')

    await page.getByText(target.display_name, { exact: false }).first().click()
    await page.waitForTimeout(3000)
    console.log('[THINKING] 已切回原会话')

    // Then: 切回后内容长度应大于切换前（agent 生成的内容未丢失）
    await page.waitForTimeout(2000)
    const contentAfterSwitch = await page.locator('body').textContent()
    const lengthAfterSwitch = contentAfterSwitch?.length ?? 0
    console.log(`[THINKING] 切回后内容长度: ${lengthAfterSwitch}`)
    console.log(`[THINKING] 增长字节数: ${lengthAfterSwitch - lengthBeforeSwitch}`)

    // 核心断言：切回后内容必须比切换前多
    expect(lengthAfterSwitch, '切回后思考内容应持续增长').toBeGreaterThan(lengthBeforeSwitch)

    // 额外断言：会话状态应为 running 或 completed（管线未中断）
    const detailResp = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`)
    const detail = await detailResp.json()
    console.log(`[THINKING] 会话状态: ${detail.status}`)
    expect(['running', 'completed', 'clarifying']).toContain(detail.status)
  })
})
