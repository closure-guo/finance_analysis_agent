import { test, expect } from '@playwright/test'

/**
 * F3a 交互状态：发送中流式指示器可见性周期（AG-UI 通道）
 *
 * 通道迁移说明（2026-09-01）：quick 模式自 add-assistant-ui-thread（#93）
 * 起走 assistant-ui Thread + /api/agui/quick，流式指示器为
 * agui-stream-status（ThreadPrimitive.If running）。
 *
 * 按 plan 注意事项，不直接断言按钮 disabled（快速模式的发送按钮在流式中可能未
 * 实现 disabled）。改为断言指示器的可见性周期（出现 -> 消失）作为交互状态验证。
 * 关键 timeout 放宽到 15_000，覆盖 ReAct Agent 初始化 + SSE 传输。
 */
test('发送中流式指示器可见性周期（出现 -> 消失）', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()

  // 切换到快速模式（EmptyState 下拉菜单，两步操作）
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /快速模式/ }).click()

  // 输入并发送
  await page.getByPlaceholder(/输入问题/).fill('测试')
  await page.getByTestId('send-button').click()

  // 验证流式指示器出现（证明正在流式中）
  await expect(page.getByTestId('agui-stream-status')).toBeVisible({ timeout: 15_000 })

  // 验证流式结束后指示器消失
  await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })
})
