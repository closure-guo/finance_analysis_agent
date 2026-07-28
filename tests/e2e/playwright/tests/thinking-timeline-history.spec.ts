import { test, expect } from '@playwright/test'

/**
 * 历史会话恢复：agentTimeline 重建 E2E（agent-turn-box-display delta task 5.6）
 *
 * 验证目标：
 * 加载已有会话时，前端 selectSession 调 buildTimelineFromHistory(h.thinking, h.tool_calls)
 * 从 chat_history 的 thinking + tool_calls 重建 agentTimeline：
 *   - 思考在前（单 thinking item -> ThinkingBanner）
 *   - 工具调用在后（非搜索类工具 -> ToolCallBanner）
 *   - 搜索类工具被跳过，不还原到工具调用横幅
 *
 * 确定性方案（TESTING=1，不依赖真实 LLM）：
 *   - 后端 /api/test/seed（TESTING=1 才注册）经 session_store 真实写入
 *     含 thinking + 非搜索 tool_call（search_stock）的 chat_history
 *   - 前端侧边栏点选该会话触发 selectSession -> GET /api/sessions/{id}
 *   - 断言渲染出思考横幅 + 工具调用横幅，且思考横幅在工具调用横幅上方
 *
 * Selector 约定：
 *   - 侧边栏会话项以 display_name 文本定位
 *   - 思考横幅 getByRole('button', { name: /思考已完成/ })；历史恢复 streaming=false 故为"思考已完成"
 *   - 工具调用横幅 getByRole('button', { name: /工具调用/ })；历史恢复 done=true 故为"工具调用"
 */

test.describe('历史会话恢复 agentTimeline 重建', () => {
  // 确定性种子数据（TESTING=1 后端 /api/test/seed），无需真实 API key。

  test('加载历史会话时思考横幅在工具调用横幅上方', async ({ page }) => {
    // 1. 经后端 /api/test/seed 造一个含 thinking + 非搜索 tool_call 的会话
    //    （搜索类工具会被 buildTimelineFromHistory 跳过，无法断言"工具调用在后"，故用 search_stock）
    const seedResp = await page.request.post('http://localhost:8001/api/test/seed', {
      data: {
        display_name: '历史恢复E2E会话',
        session_type: 'chat',
        chat_history: [
          { role: 'user', content: '帮我分析一下茅台' },
          {
            role: 'assistant',
            content: '茅台是白酒龙头，基本面稳健。',
            thinking: '先理解用户意图：分析茅台基本面，再查询股票代码。',
            tool_calls: [
              {
                name: 'search_stock',
                args: { query: '茅台' },
                result_text: '600519 贵州茅台',
                done: true,
              },
            ],
          },
        ],
      },
    })
    expect(seedResp.ok()).toBeTruthy()
    const seedBody = await seedResp.json()
    expect(seedBody.session_id).toBeTruthy()

    // 2. 前端加载，侧边栏点选该会话（触发 selectSession）
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 侧边栏点选刚造好的会话（display_name 文本定位；
    // 复跑时库里可能有同名旧会话，用精确文本 + first 锁定最新一条）
    await page.getByText('历史恢复E2E会话', { exact: true }).first().click()

    // 3. 断言：该助手消息渲染出思考横幅 + 工具调用横幅
    const thinkingBanner = page.getByRole('button', { name: /思考已完成/ })
    await expect(thinkingBanner).toBeVisible({ timeout: 10_000 })

    // 工具调用横幅（历史恢复 done=true，文案为"工具调用"）
    const toolCallBanner = page.getByRole('button', { name: /工具调用/ })
    await expect(toolCallBanner).toBeVisible({ timeout: 10_000 })

    // 4. 时序断言：思考横幅在工具调用横幅上方（boundingBox.y 比较）
    const thinkingBox = await thinkingBanner.boundingBox()
    const toolCallBox = await toolCallBanner.boundingBox()
    expect(thinkingBox).not.toBeNull()
    expect(toolCallBox).not.toBeNull()
    expect(thinkingBox!.y).toBeLessThan(toolCallBox!.y)
  })
})
