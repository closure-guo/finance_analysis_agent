import { test, expect } from '@playwright/test'

/**
 * expose-decision-outcomes Task 5：/decisions 决策战绩页 E2E 门禁
 *
 * stub 后端使用独立测试库（SESSIONS_DB_PATH 隔离），decision_log 初始为空 → 天然空态。
 * 侧边栏折叠态入口（fa_sidebar_collapsed）固定折叠后可见；展开态无底部导航（前端重构后
 * 入口只保留在折叠态图标栏，与下载管理同构）。
 *
 * 覆盖：
 * 1. 折叠态侧边栏「决策战绩」入口 → URL 变为 /decisions 且渲染页面
 * 2. 直达 /decisions → 渲染 + 空态提示 + 「返回聊天」回跳会话页
 *
 * 红线约束：不 mock /api/decisions 业务接口（E2E 禁止 route.fulfill 被测系统）；
 * 数据行渲染/过滤等细节由组件测试（frontend/src/test/decisions/）覆盖。
 */
test.describe('expose-decision-outcomes: 决策战绩页', () => {
  // 全量套件 8 worker 并发时本机后端事件循环与 vite 代理可能被压出无响应窗口
  //（与 downloads.spec.ts 同因），文件级重试兜底
  test.describe.configure({ retries: 2 })

  test('折叠态侧边栏「决策战绩」入口跳转 /decisions 并渲染页面', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('fa_sidebar_collapsed', '1'))
    await page.goto('/')
    const entry = page.getByTestId('sidebar-decisions-collapsed')
    await expect(entry).toBeVisible()
    await entry.click()
    await expect(page).toHaveURL(/\/decisions$/)
    await expect(page.getByTestId('decision-center')).toBeVisible()
  })

  test('直达 /decisions 渲染页面并显示空态，可返回聊天', async ({ page }) => {
    test.setTimeout(240_000)
    await page.goto('/decisions')
    await expect(page.getByTestId('decision-center')).toBeVisible()
    const empty = page.getByTestId('decisions-empty')
    const maxAttempts = 6
    let visible = false
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        await expect(empty).toBeVisible({ timeout: 20_000 })
        visible = true
        break
      } catch {
        if (attempt < maxAttempts - 1) {
          await page.reload({ timeout: 20_000 }).catch(() => {})
        }
      }
    }
    expect(visible, '轮询 6 次后空态仍未出现：/api/decisions 在全量套件负载下持续无响应窗口').toBe(true)
    await empty.getByRole('button', { name: '返回聊天' }).click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: '今天想研究什么？' })).toBeVisible()
  })
})
