import { test, expect } from '@playwright/test'

/**
 * F3a 前后端契约：验证快速模式发送的请求体和 SSE 响应
 *
 * 通道迁移说明（2026-09-01）：quick 模式对话自 add-assistant-ui-thread（#93）
 * 起改走 assistant-ui Thread + POST /api/agui/quick（AG-UI RunAgentInput →
 * SSE 事件流），旧 /api/chat 通道仅服务深度模式。本 spec 同步迁移到 AG-UI
 * 契约：
 *   - 请求体为 RunAgentInput：messages 末条为用户文本，forwardedProps.apiKey
 *     透传 LLM key（aguiAgent.ts 的 prepareRunAgentInput 注入），threadId
 *     字段存在（新会话为空串，服务端建会话后经 RUN_STARTED 回传）
 *   - 响应 content-type 为 text/event-stream
 *
 * Selector 约定（与其他 spec 一致）：初始 appState='empty'，EmptyState 的
 * 模式切换是"模式："下拉菜单（选项 label="快速模式"），两步操作。
 */
test('点击发送发出正确请求并收到 SSE', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()

  // 切换到快速模式（EmptyState 下拉菜单，两步操作）
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /快速模式/ }).click()

  // 监听请求和响应（在点击发送前注册，避免竞态）
  const reqPromise = page.waitForRequest(r => r.url().includes('/api/agui/quick'))
  const respPromise = page.waitForResponse(
    r => r.url().includes('/api/agui/quick') && r.status() === 200
  )

  // 输入并发送
  await page.getByPlaceholder(/输入问题/).fill('测试问题')
  await page.getByTestId('send-button').click()

  // 验证请求体为 AG-UI RunAgentInput：用户文本 + apiKey 透传 + threadId 字段
  const req = await reqPromise
  const body = req.postDataJSON() as {
    threadId?: string
    // AG-UI Message.content 两种形态：纯文本串 或 ContentPart 数组
    messages?: Array<{ role: string; content: string | Array<{ type: string; text?: string }> }>
    forwardedProps?: { apiKey?: string }
  }
  expect(body).toHaveProperty('threadId')
  const lastMessage = body.messages?.[body.messages.length - 1]
  expect(lastMessage?.role).toBe('user')
  const text =
    typeof lastMessage?.content === 'string'
      ? lastMessage.content
      : lastMessage?.content?.[0]?.text
  expect(text).toBe('测试问题')
  expect(body.forwardedProps?.apiKey).toBe('stub-key-for-testing')

  // 验证响应是 SSE（content-type 含 text/event-stream）
  const resp = await respPromise
  expect(resp.headers()['content-type']).toContain('text/event-stream')
})
