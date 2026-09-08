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

  test('1. 思考-web search-思考 产生两个独立的思考横幅（复现 bug：当前合并为 1 个）', async ({
    page,
  }) => {
    // AG-UI 迁移后渲染（adopt-assistant-ui-chat）：思考为 reasoning 文本块 + 工具横幅
    // "调用工具 · web_search"——原 legacy 的 SearchBanner/ThinkingBanner 按钮已不渲染。
    // 复现目标（两条独立思考各自独立渲染而非合并）由两条思考文本都出现在消息内保证。
    await expect(page.getByText('我需要先搜索一下实时信息')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/调用工具 · web_search/)).toBeVisible({ timeout: 30_000 })

    // 等待整个流结束
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 30_000 })

    // 核心断言：思考1 + 思考2 各自独立渲染（两个 reasoning 文本块，非合并）
    await expect(page.getByText('我需要先搜索一下实时信息')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(/搜索结果显示茅台近期有提价动作/)).toBeVisible({ timeout: 10_000 })
    const assistant = page.getByTestId('agui-assistant-message')
    const thinkBlocks = assistant.locator('div.rounded-lg', {
      hasText: /实时信息|提价动作/,
    })
    await expect(thinkBlocks).toHaveCount(2, { timeout: 10_000 })
  })

  test('2. 时间序列顺序：思考1 -> 搜索 -> 思考2 -> response', async ({ page }) => {
    const assistant = page.getByTestId('agui-assistant-message')
    await expect(assistant.getByText('我需要先搜索一下实时信息')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 30_000 })

    // AG-UI 渲染：按到达序排列 reasoning1 -> 工具横幅 -> reasoning2 -> 回答；
    // 用 boundingBox 垂直顺序断言时间序列（思考1 在工具横幅上方，横幅在思考2 上方）。
    const firstThinking = assistant.getByText('我需要先搜索一下实时信息')
    const tool = assistant.getByText(/调用工具 · web_search/)
    const secondThinking = assistant.getByText(/搜索结果显示茅台近期有提价动作/)
    const answer = assistant.getByText(/固定回复/)

    const firstBox = await firstThinking.boundingBox()
    const toolBox = await tool.boundingBox()
    const secondBox = await secondThinking.boundingBox()
    const answerBox = await answer.boundingBox()
    expect(firstBox).not.toBeNull()
    expect(toolBox).not.toBeNull()
    expect(secondBox).not.toBeNull()
    expect(answerBox).not.toBeNull()

    expect(firstBox!.y).toBeLessThan(toolBox!.y)
    expect(toolBox!.y).toBeLessThan(secondBox!.y)
    expect(secondBox!.y).toBeLessThan(answerBox!.y)
  })

  test('4. web search 执行期间工具横幅可见（AG-UI 迁移后语义）', async ({ page }) => {
    // AG-UI 迁移后（adopt-assistant-ui-chat）：搜索执行期渲染工具横幅"调用工具 · web_search"，
    // 原 legacy 的"正在搜索网页/思考已完成"文案已不渲染。原意图（搜索进行中的中间状态可见）
    // 由工具横幅在回答完成前出现来保证。
    await expect(page.getByText(/调用工具 · web_search/)).toBeVisible({ timeout: 30_000 })

    // 搜索执行期间思考1已渲染（工具调用发生在思考1之后）
    await expect(page.getByText('我需要先搜索一下实时信息')).toBeVisible({ timeout: 10_000 })

    // 等待整个流结束，避免后续状态污染
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 30_000 })
    await expect(page.getByText(/固定回复/)).toBeVisible({ timeout: 10_000 })
  })

})
