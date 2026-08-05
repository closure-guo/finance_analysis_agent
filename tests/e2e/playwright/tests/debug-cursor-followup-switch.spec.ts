import { test, expect } from '@playwright/test'

/**
 * Bug 复现（调试中）：快速模式第二轮输出中途切走再切回，
 * 输出完毕后末尾加载游标（stream-status）不消失，再切换会话才消失。
 *
 * 链路：会话 A 第一轮 → 新建分析 → 会话 B 第一轮 → 切回 A →
 *       A 第二轮发送 → 流式中途点 B → 立即点回 A（快照恢复 + resumeStream）→
 *       等待 done → 游标应消失
 */
test('第二轮中途切换会话后游标也应消失', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()

  // 会话 A 第一轮
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /快速模式/ }).click()
  await page.getByPlaceholder(/输入问题/).fill('第一轮问题A')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 20_000 })

  // 新建分析 -> 会话 B 第一轮
  await page.getByRole('button', { name: /新建分析/ }).click()
  await page.getByPlaceholder(/输入问题/).fill('第一轮问题B')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 20_000 })

  // 切回会话 A（completed，从 chat_history 重建）
  await page.getByText('第一轮问题A').first().click()
  await expect(page.getByTestId('stream-output').first()).toBeVisible({ timeout: 10_000 })

  // 会话 A 第二轮（上海天气）
  await page.getByPlaceholder(/输入问题/).fill('第二轮问题A')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('stream-status')).toBeVisible({ timeout: 10_000 })

  // 流式中途切到 B 再立即切回 A（触发快照恢复 + resumeStream）
  await page.getByText('第一轮问题B').first().click()
  await page.getByText('第一轮问题A').first().click()

  // 第二轮输出完毕后游标应消失（修复前：resumeStream 路径下游标常驻）
  await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 20_000 })
})
