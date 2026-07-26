import { test, expect } from '@playwright/test'

/**
 * F3a 流式核心链路：快速模式 SSE 流式渲染
 * 基于 StubLLMClient 的确定性输出
 *
 * Selector 调整说明（相对 plan 原稿）：
 * 初始 appState='empty'，渲染的是 EmptyState 组件，其模式切换是"模式："下拉菜单
 * （选项 label="快速模式"），而非 ChatInputBar 的"快速对话"按钮（该按钮仅在发送
 * 消息、appState 切换到非 empty 后才渲染）。因此将 plan 中
 * `getByRole('button', { name: /快速对话/ }).click()` 调整为两步下拉菜单操作：
 *   1) 点击 "模式：" 按钮展开下拉
 *   2) 点击 "快速模式" 选项切换 mode
 * 其余 selector（getByPlaceholder(/输入问题/)、getByTestId('send-button')）与
 * 实际 DOM 一致，保持不变。
 */
test.describe('F3a streaming: 快速模式流式渲染', () => {
  test('流式增量渲染 + 指示器生命周期', async ({ page }) => {
    // 先配置 API Key（localStorage）
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 切换到快速模式（EmptyState 下拉菜单）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    // 输入并发送
    await page.getByPlaceholder(/输入问题/).fill('测试问题')
    await page.getByTestId('send-button').click()

    // 流式状态指示器出现
    await expect(page.getByTestId('stream-status')).toBeVisible()

    // 流式输出累积内容（stub 首个 chunk 需等后端 ReAct Agent 初始化 + SSE 传输，给足 timeout）
    const streamOutput = page.getByTestId('stream-output')
    await expect(streamOutput).toContainText('这是', { timeout: 15_000 })

    // 流式状态指示器消失（流结束）
    await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 15_000 })
  })

  test('流式中断显示错误', async ({ page }) => {
    // 配置 API Key
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 拦截 /api/chat 请求模拟断连
    await page.route('**/api/chat', route => route.abort())

    // 切换到快速模式并发送
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()
    await page.getByPlaceholder(/输入问题/).fill('测试')
    await page.getByTestId('send-button').click()

    // 错误提示可见
    await expect(page.getByTestId('stream-error')).toBeVisible({ timeout: 10_000 })
  })

  test('完整流式回复内容累积', async ({ page }) => {
    // 配置 API Key
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 快速模式发送
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()
    await page.getByPlaceholder(/输入问题/).fill('测试')
    await page.getByTestId('send-button').click()

    // 等待完整回复（stub 的全部 chunk）
    const streamOutput = page.getByTestId('stream-output')
    await expect(streamOutput).toContainText('固定回复', { timeout: 15_000 })
    await expect(streamOutput).toContainText('增量累积', { timeout: 15_000 })
  })
})
