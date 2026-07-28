import { test, expect } from '@playwright/test'

/**
 * 搜索横幅 E2E（add-search-banner delta Task 6）
 *
 * 标记 @live：依赖真实 LLM tool_call + Tavily 搜索。
 * StubLLMClient（TESTING=1）不吐 tool_call，无法触发 search_start/search_result 事件，
 * 因此本 spec 必须跑在真实服务上（nightly 回归防漂移）。
 *
 * 前置条件：
 *   - 后端运行在 http://localhost:8000（不带 TESTING=1，需真实 LLM + TAVILY_API_KEY）
 *   - 前端运行在 http://localhost:5173
 *   - 环境变量 LLM_API_KEY / DEEPSEEK_API_KEY 至少一个可用
 *
 * Selector 约定（与 streaming/interaction/contract spec 一致）：
 *   初始 appState='empty'，EmptyState 的模式切换是"模式："下拉菜单
 *   （选项 label="快速模式"），两步操作。
 */

const API_KEY = process.env.LLM_API_KEY || process.env.DEEPSEEK_API_KEY || ''

test.describe('搜索横幅 @live', () => {
  // 依赖真实 LLM tool_call + Tavily 搜索；StubLLMClient 不吐 tool_call，无法触发搜索事件。
  // 未配置 API key 时整体跳过；CI 默认不跑 @live（nightly 回归防漂移）。

  test('快速模式：搜索中显示"正在搜索"横幅', async ({ page }) => {
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    // 真实 LLM tool_call + Tavily 往返较慢，放宽单测总时长到 120s
    test.setTimeout(120_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    // 切换到快速模式（EmptyState 下拉菜单，两步操作）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    // 输入并发送
    await page.getByPlaceholder(/输入问题/).fill('茅台怎么样')
    await page.getByTestId('send-button').click()

    // 等待搜索横幅出现（正在搜索 或 搜索了 N 个网页）
    const banner = page.locator('text=/正在搜索|搜索了/')
    await expect(banner).toBeVisible({ timeout: 90_000 })
  })

  test('快速模式：搜索完成显示"搜索了 N 个网页"并可展开', async ({ page }) => {
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    test.setTimeout(120_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    await page.getByPlaceholder(/输入问题/).fill('茅台最新消息')
    await page.getByTestId('send-button').click()

    // 等待搜索完成
    const doneBanner = page.locator('text=/搜索了/')
    await expect(doneBanner).toBeVisible({ timeout: 90_000 })

    // 点击展开搜索横幅
    await doneBanner.click()

    // 验证结果列表可见（至少出现一个结果链接）
    await expect(page.locator('a[href*="http"]').first()).toBeVisible({ timeout: 5_000 })
  })

  test('快速模式：web search 时只显示搜索横幅，不显示工具调用横幅', async ({ page }) => {
    // 来源：hide-tool-use-banner-during-web-search delta
    // 验证搜索类工具调用仅由搜索横幅承载，不进入工具调用横幅，避免重复横幅
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    test.setTimeout(120_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    await page.getByPlaceholder(/输入问题/).fill('茅台最新消息')
    await page.getByTestId('send-button').click()

    // 等待搜索横幅出现（正在搜索 或 搜索了 N 个网页）
    const searchBanner = page.locator('text=/正在搜索|搜索了/')
    await expect(searchBanner).toBeVisible({ timeout: 90_000 })

    // 断言：同一助手消息中不出现工具调用横幅（"调用工具中"/"已调用工具"/"工具调用"）
    // 搜索进行中与完成后均不应出现工具调用横幅
    const toolCallBanner = page.locator('text=/调用工具中|已调用工具|工具调用/')
    await expect(toolCallBanner).toHaveCount(0)
  })
})
