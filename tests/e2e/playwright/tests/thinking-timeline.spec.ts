import { test, expect } from '@playwright/test'

/**
 * 思考-搜索-思考 时间序列 E2E（agent-turn-box-display delta 复现测试，确定性进 CI 门禁）
 *
 * 验证目标（delta spec 要修复的两个 bug）：
 * 1. "思考 -> web search -> 思考" 序列中，两次思考应渲染为两个独立的思考横幅，
 *    而非合并在同一个 ThinkingBanner 框体里（当前 bug：只有 1 个思考横幅）
 * 2. 工具执行期间，SearchBanner 显示"正在搜索网页"、思考横幅不再一律显示"思考中"
 *    （当前 bug：整个流期间思考横幅都显示"思考中"）
 *
 * 确定性方案（TESTING=1 + STUB_SCENARIO=tool_call，不依赖真实 LLM，进 CI 门禁）：
 *   - 后端 StubLLMClient 走工具调用场景：第 1 轮吐思考1 + tool_call(web_search)，
 *     第 2 轮吐思考2 + 回答（见 stub_llm_client.py）
 *   - 后端 TESTING=1 注册 stub web_search 工具，返回带"STUB 搜索结果"固定标记、
 *     可被 parse_search_output 解析的结果，不调真实 Tavily
 *   - 前端通过 playwright.timeline.config.ts 的独立前后端对（8001/5174）运行
 *
 * Selector 约定（与 streaming/search-banner spec 一致）：
 *   初始 appState='empty'，EmptyState 模式切换为"模式："下拉菜单两步操作。
 *   思考横幅按钮通过 getByRole('button') + name 精确定位。
 *
 * 当前状态说明：Scenario 1/2/4 在当前实现下预期失败（复现 bug），delta 实施后通过。
 */

test.describe('思考-搜索-思考 时间序列', () => {
  // 确定性 stub（TESTING=1 + STUB_SCENARIO=tool_call），无需真实 API key。

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 切换到快速模式（EmptyState 下拉菜单，两步操作）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    // 输入并发送（stub 场景固定返回"思考1 -> web search -> 思考2 -> 回答"）
    await page.getByPlaceholder(/输入问题/).fill('茅台最新消息')
    await page.getByTestId('send-button').click()
  })

  test('1. 思考-web search-思考 产生两个独立的思考横幅（复现 bug：当前合并为 1 个）', async ({ page }) => {
    // 等待搜索完成（stub web_search 返回"STUB 搜索结果"固定标记 -> search_result 事件）
    const searchBanner = page.locator('text=/正在搜索|搜索了/')
    await expect(searchBanner).toBeVisible({ timeout: 30_000 })

    // 等待整个流结束（stream-status 消失）
    await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 30_000 })

    // 核心断言：思考横幅数量应为 2（思考1 + 思考2 各自独立横幅）
    // 当前 bug：所有思考 token 累加进同一 thinkingContent，只渲染 1 个 ThinkingBanner
    const thinkingBanners = page.getByRole('button', { name: /思考已完成|思考中/ })
    await expect(thinkingBanners).toHaveCount(2, { timeout: 10_000 })
  })

  test('2. 时间序列顺序：思考1 -> 搜索 -> 思考2 -> response', async ({ page }) => {
    const searchBanner = page.locator('text=/正在搜索|搜索了/')
    await expect(searchBanner).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 30_000 })

    // 在 stream-output 内验证 DOM 垂直顺序：思考1(y最小) -> 搜索 -> 思考2 -> response
    const streamOutput = page.getByTestId('stream-output').last()
    const thinkingBanners = streamOutput.getByRole('button', { name: /思考已完成|思考中/ })
    const count = await thinkingBanners.count()
    // 前置：应有两个思考横幅（与 Scenario 1 一致的复现断言）
    expect(count).toBe(2)

    // JUSTIFIED: 时间序列正是本测试目标，nth(0)=思考1、nth(1)=思考2 的位置语义即断言对象
    const firstThinking = thinkingBanners.nth(0)
    const secondThinking = thinkingBanners.nth(1)
    // JUSTIFIED: 取首个搜索横幅作为时序锚点（本流程仅一次 web search）
    const search = streamOutput.locator('text=/正在搜索|搜索了/').first()

    const firstBox = await firstThinking.boundingBox()
    const searchBox = await search.boundingBox()
    const secondBox = await secondThinking.boundingBox()
    expect(firstBox).not.toBeNull()
    expect(searchBox).not.toBeNull()
    expect(secondBox).not.toBeNull()

    // 时间序列：思考1 在搜索上方，搜索在思考2 上方
    expect(firstBox!.y).toBeLessThan(searchBox!.y)
    expect(searchBox!.y).toBeLessThan(secondBox!.y)
  })

  test('4. web search 执行期间显示"正在搜索网页"，思考1显示"思考已完成"而非"思考中"', async ({ page }) => {
    // 等待搜索执行中状态出现（search_start 后、search_result 前，stub 搜索有 5s 窗口）
    // 兼容现有"正在搜索：{query}"与目标文案"正在搜索网页"
    const searchingBanner = page.locator('text=/正在搜索网页|正在搜索/')
    await expect(searchingBanner).toBeVisible({ timeout: 30_000 })

    // 等思考1横幅先渲染出来（思考1在 tool_call 前已吐完，搜索执行期间应已渲染）
    const thinkingBanner = page.getByRole('button', { name: /思考已完成|思考中/ }).first()
    await expect(thinkingBanner).toBeVisible({ timeout: 10_000 })

    // 搜索执行期间的确切窗口内断言：
    // 1) 搜索尚未完成（"搜索了 N 个网页"尚不可见）-> 锁定"搜索执行中"时间窗
    // 2) 思考1横幅应显示"思考已完成"（agent 已转去执行搜索，不再"思考中"）
    // 当前 bug：streaming = !!msg.streaming && !msg.chatResponse 整个流期间为 true，
    // 导致搜索执行期间思考1横幅仍显示"思考中"（探针已实证）
    const searchDone = page.locator('text=/搜索了 \\d+ 个网页|搜索了\\d+个网页/')
    await expect(searchDone).toHaveCount(0)
    // 正面断言：思考1应显示"思考已完成"（bug 时显示"思考中"，此断言失败复现 bug）
    await expect(thinkingBanner).toHaveText(/思考已完成/)

    // 等待流结束，避免后续状态污染
    await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 30_000 })
  })
})
