import { test, expect } from '@playwright/test'

/**
 * F3a 前后端契约：验证 POST /api/chat 请求体和 SSE 响应
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
 *
 * 另：waitForResponse 的 SSE 验证需注意，POST /api/chat 在前端被解析为一个 EventSource
 * 请求（fetch + ReadableStream），Playwright 会捕获该请求与响应。响应 headers 的
 * content-type 应为 text/event-stream。
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
  const reqPromise = page.waitForRequest(r => r.url().includes('/api/chat'))
  const respPromise = page.waitForResponse(
    r => r.url().includes('/api/chat') && r.status() === 200
  )

  // 输入并发送
  await page.getByPlaceholder(/输入问题/).fill('测试问题')
  await page.getByTestId('send-button').click()

  // 验证请求体包含 message/user_id/api_key
  const req = await reqPromise
  expect(req.postDataJSON()).toMatchObject({
    message: '测试问题',
  })
  expect(req.postDataJSON()).toHaveProperty('user_id')
  expect(req.postDataJSON()).toHaveProperty('api_key')

  // 验证响应是 SSE（content-type 含 text/event-stream）
  const resp = await respPromise
  expect(resp.headers()['content-type']).toContain('text/event-stream')
})
