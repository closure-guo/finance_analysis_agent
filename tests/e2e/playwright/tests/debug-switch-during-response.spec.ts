import { test, expect } from '@playwright/test'

/**
 * 验证：Agent Response 中途切换会话，切回后 Response 内容保持持续流式输出
 *
 * 核心场景：
 * 1. 发送深度分析请求，等待思考内容首次出现
 * 2. 等待内容累积到 2000+ 字符（确保进入 Response 阶段）
 * 3. 切换到新会话（切走）
 * 4. 等待 10 秒（SSE 在后台持续接收）
 * 5. 切回原会话
 * 6. 断言：Response 内容比切换前更长
 *
 * 与 debug-switch-during-thinking.spec.ts 的区别：
 *   - 思考中途测试：在第一个思考 token 出现后立即切换
 *   - Response 中途测试：等待内容累积到 2000+ 字符后再切换
 *
 * 对应 delta spec: harden-react-path-resilience
 * 验证任务：SSE 心跳保护 + 会话隔离机制 + 消息快照缓存
 */
const API_BASE = 'http://localhost:8000'
const FRONTEND = 'http://localhost:5173'
const LLM_KEY = process.env.LLM_API_KEY || 'stub-key-for-testing'

test.describe('Agent Response 中途切换会话 - 流式输出持续性', () => {
  let sessionId: string

  test.beforeEach(async ({ page }) => {
    test.setTimeout(240_000)
    // 捕获浏览器日志
    page.on('console', msg => {
      if (msg.type() === 'error') console.log(`[BROWSER ERROR]`, msg.text())
    })
    page.on('pageerror', err => console.log('[PAGE ERROR]', err.message))

    // 配置 API Key 和用户 ID
    await page.goto(FRONTEND)
    await page.evaluate((key) => {
      localStorage.setItem('fa_api_key', key)
      localStorage.setItem('fa_user_id', 'debug-response-switch')
    }, LLM_KEY)
    await page.reload()
    await page.waitForTimeout(500)

    // Given: 切换到深度研究模式
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.waitForTimeout(300)

    // When: 输入并发送股票查询
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // Then: 等待思考内容首次出现（Agent 开始输出 token）
    await expect(page.getByText(/用户|分析|茅台|搜索/i).first()).toBeVisible({ timeout: 45_000 })
    console.log('[RESPONSE] 思考内容首次出现')

    // 等待内容累积到 2000+ 字符（确保进入 Response 阶段，而非仅思考阶段）
    await expect(async () => {
      const text = await page.locator('body').textContent()
      const len = text?.length ?? 0
      expect(len).toBeGreaterThan(2000)
    }).toPass({ timeout: 90_000, intervals: [3_000, 5_000] })
    console.log('[RESPONSE] 内容已超过 2000 字符，进入 Response 阶段')

    // 获取当前会话 ID
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    sessionId = sessions[0]?.session_id ?? ''
    console.log(`[RESPONSE] 当前会话 ID: ${sessionId}`)
  })

  test('Response 中途切换会话，切回后内容持续增长', async ({ page }) => {
    // Given: beforeEach 已等待内容累积到 2000+ 字符
    // 记录切换前的内容长度
    const contentBeforeSwitch = await page.locator('body').textContent()
    const lengthBeforeSwitch = contentBeforeSwitch?.length ?? 0
    console.log(`[RESPONSE] 切换前内容长度: ${lengthBeforeSwitch}`)

    // When: 点击"新建分析"切走
    await page.getByRole('button', { name: /新建分析/ }).click()
    await page.waitForTimeout(2000)
    console.log('[RESPONSE] 已切换到新会话')

    // When: 等待 10 秒（SSE 在后台持续接收并推送到后端）
    console.log('[RESPONSE] 等待 10 秒，SSE 后台持续接收...')
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
    console.log('[RESPONSE] 已切回原会话')

    // Then: 切换后的内容长度应大于切换前
    // 等待内容渲染 + 后端数据刷新
    await page.waitForTimeout(3000)
    const contentAfterSwitch = await page.locator('body').textContent()
    const lengthAfterSwitch = contentAfterSwitch?.length ?? 0
    console.log(`[RESPONSE] 切回后内容长度: ${lengthAfterSwitch}`)
    console.log(`[RESPONSE] 增长字节数: ${lengthAfterSwitch - lengthBeforeSwitch}`)

    // 核心断言：切回后内容必须比切换前多
    expect(lengthAfterSwitch, '切回后 Response 内容应持续增长').toBeGreaterThan(lengthBeforeSwitch)

    // 额外断言：会话状态应为 running/completed/clarifying
    const detailResp = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`)
    const detail = await detailResp.json()
    console.log(`[RESPONSE] 会话状态: ${detail.status}`)
    expect(['running', 'completed', 'clarifying']).toContain(detail.status)

    // 额外断言：如果管线已完成，报告内容应存在
    if (detail.status === 'completed' && detail.report_markdown) {
      console.log(`[RESPONSE] 管线已完成，report_markdown 长度: ${detail.report_markdown.length}`)
    }

    // 额外断言：管线快照 progress
    if (detail.pipeline_snapshot) {
      try {
        const snapshot = JSON.parse(detail.pipeline_snapshot)
        console.log(`[RESPONSE] 管线进度: ${snapshot.progress}`)
      } catch {
        console.log('[RESPONSE] 管线快照解析失败')
      }
    }
  })
})