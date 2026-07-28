import { test, expect } from '@playwright/test'

/**
 * 思考横幅 E2E（thinking-stream-banner-display delta Task 5.1-5.4）
 *
 * 标记 @live：依赖真实 LLM 输出思考内容与标题生成策略。
 * StubLLMClient（TESTING=1）只吐纯文本不按策略生成 ## 标题，无法验证标题分支，
 * 因此本 spec 必须跑在真实服务上（nightly 回归防漂移）。
 *
 * 前置条件：
 *   - 后端运行在 http://localhost:8000（不带 TESTING=1，需真实 LLM）
 *   - 前端运行在 http://localhost:5173
 *   - 环境变量 LLM_API_KEY / DEEPSEEK_API_KEY 至少一个可用
 *
 * Selector 约定（与 search-banner/streaming spec 一致）：
 *   初始 appState='empty'，EmptyState 模式切换为下拉菜单两步操作。
 *   思考横幅按钮通过 getByRole('button') + name 精确定位，
 *   避免与 stream-status 的"思考中..."（getByTestId('stream-status')）冲突。
 *
 * 时机说明：
 *   思考横幅完成（显示"思考已完成"）= chatResponse 出现（thinking_to_answer 后）
 *   stream-status 消失 = chat_done（整个流结束）
 *   两者不同步，本测试以思考横幅按钮文案为锚点，不依赖 stream-status。
 */

const API_KEY = process.env.LLM_API_KEY || process.env.DEEPSEEK_API_KEY || ''

test.describe('思考横幅 @live', () => {
  // 依赖真实 LLM 思考输出；未配置 API key 时整体跳过。
  // StubLLMClient 只吐纯文本不按策略生成 ## 标题，无法验证标题分支。

  test('5.1 快速模式：query 后思考横幅流式展示"思考中"，完成后显示"思考已完成"', async ({ page }) => {
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    // 真实 LLM 思考往返较慢，放宽到 120s
    test.setTimeout(120_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    // 切换到快速模式（EmptyState 下拉菜单）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    // 输入并发送（构造多要点 query 提升标题命中率）
    await page.getByPlaceholder(/输入问题/).fill('茅台近期的财务表现和估值情况如何')
    await page.getByTestId('send-button').click()

    // 等待思考横幅出现：思考中态（按钮 name 精确为"思考中"，不含省略号）
    const thinkingBtn = page.getByRole('button', { name: '思考中' })
    await expect(thinkingBtn).toBeVisible({ timeout: 60_000 })

    // 等待思考完成：横幅按钮文案切换为"思考已完成"或标题文本
    // 完成态横幅不再显示"思考中"
    await expect(thinkingBtn).toBeHidden({ timeout: 90_000 })

    // 完成态横幅应显示"思考已完成"（展开态默认）或具体标题文本（折叠态有标题时）
    // 二选一：断言"思考已完成"可见（展开态默认显示）
    const completedBtn = page.getByRole('button', { name: '思考已完成' })
    await expect(completedBtn).toBeVisible({ timeout: 10_000 })
  })

  test('5.3 快速模式：思考横幅点击展开/折叠交互', async ({ page }) => {
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    test.setTimeout(120_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    await page.getByPlaceholder(/输入问题/).fill('对比茅台和五粮液的财务表现')
    await page.getByTestId('send-button').click()

    // 等待思考完成（按钮从"思考中"切换为"思考已完成"）
    const thinkingBtn = page.getByRole('button', { name: '思考中' })
    await expect(thinkingBtn).toBeVisible({ timeout: 60_000 })
    await expect(thinkingBtn).toBeHidden({ timeout: 90_000 })

    // 完成态：横幅按钮显示"思考已完成"（展开态默认）
    const completedBtn = page.getByRole('button', { name: '思考已完成' })
    await expect(completedBtn).toBeVisible({ timeout: 10_000 })

    // 点击横幅折叠
    await completedBtn.click()
    // 折叠后再次点击展开
    await page.getByRole('button', { name: /思考已完成|思考中/ }).first().click()

    // 展开后横幅仍显示"思考已完成"
    await expect(page.getByRole('button', { name: '思考已完成' })).toBeVisible()
  })

  test('5.4 快速模式：切换会话后历史会话思考横幅恢复', async ({ page }) => {
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    test.setTimeout(180_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /快速模式/ }).click()

    // 第一轮对话：产生思考内容
    await page.getByPlaceholder(/输入问题/).fill('茅台最新财报分析')
    await page.getByTestId('send-button').click()

    // 等待思考完成（按钮切换为"思考已完成"）
    const thinkingBtn = page.getByRole('button', { name: '思考中' })
    await expect(thinkingBtn).toBeVisible({ timeout: 60_000 })
    await expect(thinkingBtn).toBeHidden({ timeout: 90_000 })
    await expect(page.getByRole('button', { name: '思考已完成' })).toBeVisible({ timeout: 10_000 })

    // 等待整个流结束（stream-status 消失，确保回复已持久化）
    await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 60_000 })

    // 点击"新建分析"重置状态
    await page.getByRole('button', { name: /新建分析/ }).click()

    // 侧边栏应出现刚才的会话，点击切换回该会话
    // 用精确 query 文本匹配，避免误点其他"茅台"开头的会话
    const sessionItem = page.locator('text=/茅台最新财报分析/').first()
    await expect(sessionItem).toBeVisible({ timeout: 5_000 })
    await sessionItem.click()

    // 历史会话恢复后，思考横幅应恢复完成态（显示"思考已完成"，不显示"思考中"）
    await expect(page.getByRole('button', { name: '思考已完成' })).toBeVisible({ timeout: 15_000 })
    // 不应处于流式态
    await expect(page.getByRole('button', { name: '思考中' })).toHaveCount(0)
  })
})
