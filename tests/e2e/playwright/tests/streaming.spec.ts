import { test, expect } from '@playwright/test'

/**
 * F3a 流式核心链路：快速模式流式渲染（AG-UI 通道）
 *
 * 通道迁移说明（2026-09-01）：quick 模式自 add-assistant-ui-thread（#93）
 * 起走 assistant-ui Thread + POST /api/agui/quick，旧 /api/chat 通道仅服务
 * 深度模式。本 spec 的断言同步迁移到 AG-UI 渲染路径：
 *   - 流式指示器：agui-stream-status（ThreadPrimitive.If running）
 *   - 流式正文：agui-assistant-message（assistant-ui Message 渲染）
 *   - 错误：App 级 warning toast（QuickThread onError → showWarning，3s 自动消失）
 * 渲染契约与 agui-chat.spec.ts 一致；stub 确定性输出见 StubLLMClient 默认场景：
 *   reasoning = "## 分析思路\n..."，answer = "这是一段测试用的固定回复。…增量累积。"
 *
 * Selector 约定：初始 appState='empty'，EmptyState 的模式切换是"模式："
 * 下拉菜单（选项 label="快速模式"），两步操作。
 */

/** 配置测试 Key → 切快速模式（EmptyState 两步下拉） */
async function prepareQuickMode(page: import('@playwright/test').Page) {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /快速模式/ }).click()
}

test.describe('F3a streaming: 快速模式流式渲染', () => {
  test('流式增量渲染 + 指示器生命周期', async ({ page }) => {
    await prepareQuickMode(page)

    // 输入并发送
    await page.getByPlaceholder(/输入问题/).fill('测试问题')
    await page.getByTestId('send-button').click()

    // 流式状态指示器出现（RUN_STARTED → running=true）
    await expect(page.getByTestId('agui-stream-status')).toBeVisible()

    // 流式输出累积内容（stub 首个 chunk 需等后端 ReAct Agent 初始化 + SSE 传输，给足 timeout）
    const assistantMessage = page.getByTestId('agui-assistant-message')
    await expect(assistantMessage).toContainText('这是', { timeout: 15_000 })

    // 流式状态指示器消失（RUN_FINISHED → running=false）
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })
  })

  test('流式中断显示错误', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 拦截 AG-UI 请求模拟断连（transport 层 abort，非业务响应 mock）
    await page.route('**/api/agui/quick', route => route.abort())

    // 切换到快速模式并发送
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()
    await page.getByPlaceholder(/输入问题/).fill('测试')
    await page.getByTestId('send-button').click()

    // 错误提示可见（QuickThread onError → App warning toast，3s 自动消失，
    // 但断连后即时出现，toBeVisible 轮询可捕获；文案为 fetch 错误或兜底"生成失败"）
    await expect(page.locator('text=/失败|Failed/i').first()).toBeVisible({ timeout: 10_000 })
  })

  test('完整流式回复内容累积', async ({ page }) => {
    await prepareQuickMode(page)

    // 快速模式发送
    await page.getByPlaceholder(/输入问题/).fill('测试')
    await page.getByTestId('send-button').click()

    // 等待完整回复（stub 的全部 chunk 累积到同一条 assistant 消息）
    const assistantMessage = page.getByTestId('agui-assistant-message')
    await expect(assistantMessage).toContainText('固定回复', { timeout: 15_000 })
    await expect(assistantMessage).toContainText('增量累积', { timeout: 15_000 })
  })

  // Bug 复现（旧通道已修复；迁移到 AG-UI 通道后作为回归守卫保留）：
  // 第二轮追问输出完毕后，流式指示器（agui-stream-status）应正常消失。
  test('第二轮追问后流式指示器也应消失', async ({ page }) => {
    await prepareQuickMode(page)

    // 第一轮：快速模式发送，指示器正常出现并消失
    await page.getByPlaceholder(/输入问题/).fill('第一轮问题')
    await page.getByTestId('send-button').click()
    await expect(page.getByTestId('agui-stream-status')).toBeVisible()
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })

    // 第二轮：同会话追问（Thread 内经 composer 发送；parentId 链尾保证上下文）
    await page.getByPlaceholder(/输入问题/).fill('第二轮问题')
    await page.getByTestId('send-button').click()
    await expect(page.getByTestId('agui-stream-status')).toBeVisible()
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })

    // 两轮 assistant 消息均完整落位
    await expect(page.getByTestId('agui-assistant-message')).toHaveCount(2)
  })
})
