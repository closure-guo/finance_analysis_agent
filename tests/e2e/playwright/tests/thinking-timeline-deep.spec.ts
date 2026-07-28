import { test, expect } from '@playwright/test'

/**
 * 深度模式澄清阶段：思考-搜索-思考 时间序列 E2E（agent-turn-box-display delta task 5.4）
 *
 * 验证目标：
 * 1. 深度模式澄清阶段（pipelineMsgRef 为空、未进入完整管线）的 thinking_token
 *    走对话流 agentTimeline，"思考 -> web search -> 思考"渲染为两个独立思考横幅
 * 2. 时间序列顺序：思考1 -> 搜索 -> 思考2 -> response
 *
 * 确定性方案（TESTING=1 + STUB_SCENARIO=tool_call，不依赖真实 LLM）：
 *   - 后端 StubLLMClient 走工具调用场景：第 1 轮吐思考1 + tool_call(web_search)，
 *     第 2 轮吐思考2 + 回答；StubLLMClient 不调 run_deep_analysis，天然停留在澄清阶段
 *   - 后端 deep 分支 TESTING=1 注册 stub web_search（与 quick 同一逻辑，不调真实 Tavily）
 *   - 输入必须避开时效性关键词（"最新/今天/热点"等会触发 api.py 预搜索走真实 Tavily），
 *     用"帮我分析一下茅台"而非"茅台最新消息"
 *   - 前端通过 playwright.timeline.config.ts 的独立前后端对（8001/5174）运行
 *
 * Selector 约定：与 thinking-timeline.spec.ts 一致；EmptyState 模式切换为
 * "模式："下拉菜单两步操作，深度模式菜单项文案为"深度研究"。
 */

test.describe('深度模式澄清阶段 思考-搜索-思考 时间序列', () => {
  // 确定性 stub（TESTING=1 + STUB_SCENARIO=tool_call），无需真实 API key。

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 切换到深度模式（EmptyState 下拉菜单，两步操作；菜单项含"5 层 Agent 流水线"描述，触发按钮无此文案）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()

    // 输入并发送（避开时效性关键词，防止 api.py 预搜索走真实 Tavily；
    // stub 场景固定返回"思考1 -> web search -> 思考2 -> 回答"；
    // deep 模式 placeholder 为"输入股票名称或代码"，故用通用 /输入/ 匹配）
    await page.getByPlaceholder(/输入/).fill('帮我分析一下茅台')
    await page.getByTestId('send-button').click()
  })

  test('1. 澄清阶段 思考-web search-思考 产生两个独立的思考横幅', async ({ page }) => {
    // 等待搜索完成（stub web_search 返回"STUB 搜索结果"固定标记 -> search_result 事件）
    const searchBanner = page.locator('text=/正在搜索|搜索了/')
    await expect(searchBanner).toBeVisible({ timeout: 30_000 })

    // 等待整个流结束（stream-status 消失）
    await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 30_000 })

    // 核心断言：思考横幅数量应为 2（思考1 + 思考2 各自独立横幅）
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
    // 前置：应有两个思考横幅（与 Scenario 1 一致的断言）
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
})
