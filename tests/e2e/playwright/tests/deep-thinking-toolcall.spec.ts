import { test, expect } from '@playwright/test'

/**
 * 深度模式澄清阶段工具调用轮次 reasoning_content 回传 @live（enable-deepseek-thinking-mode Task 7.5）
 *
 * 标记 @live：依赖真实 LLM 产生 reasoning_content 与工具调用轮次。
 * 历史故障：DeepSeek 思考模式 + 工具调用时，后续请求未回传
 * reasoning_content → API 返回 400（design.md Context 节）。
 * 本 spec 验证：深度模式澄清 ReAct（思考 → search_stock 工具调用 → 继续思考）
 * 全程无 400 错误，管线正常触发。
 *
 * 前置条件：
 *   - 后端运行在 http://localhost:8000（不带 TESTING=1，LLM_* env 指向可用端点）
 *   - 前端运行在 http://localhost:5173
 *   - 环境变量 LLM_API_KEY / DEEPSEEK_API_KEY 至少一个可用
 *
 * Selector 约定：深度模式默认；「工具调用」横幅由 tool_call TimelineItem 渲染；
 * 管线触发后出现「分析进度」或 run_deep_analysis 工具横幅。
 */

const API_KEY = process.env.LLM_API_KEY || process.env.DEEPSEEK_API_KEY || ''

test.describe('深度模式思考+工具调用 @live', () => {
  test('7.5 澄清阶段工具调用轮次 reasoning_content 正确回传，无 400 错误', async ({ page }) => {
    test.skip(!API_KEY, 'LLM_API_KEY / DEEPSEEK_API_KEY 未设置，跳过 @live 用例')
    // 真实 LLM：澄清 ReAct（多轮）+ 5 层管线，放宽到 6 分钟
    test.setTimeout(360_000)
    await page.goto('/')
    await page.evaluate(k => localStorage.setItem('fa_api_key', k), API_KEY)
    await page.reload()

    // 深度模式（默认）发送，触发澄清 ReAct：思考 → search_stock → run_deep_analysis
    await page.getByPlaceholder(/输入股票名称或代码/).fill('分析一下宁德时代')
    await page.getByTestId('send-button').click()

    // 关键断言 1：澄清阶段出现工具调用横幅（search_stock / 识别股票）
    // —— 工具调用轮次的 reasoning_content 必须被回传，否则后续请求 400，
    //    错误会以「错误: 运行时错误: ...400...」消息形式出现在对话流
    await expect(
      page.getByText(/识别股票|search_stock/).first(),
    ).toBeVisible({ timeout: 120_000 })

    // 关键断言 2：全程无 400 错误（历史故障的直接症状）
    await expect(
      page.getByText(/错误.*400/),
    ).toHaveCount(0)

    // 关键断言 3：管线被触发（run_deep_analysis 工具横幅或分析进度 UI 出现）
    await expect(
      page.getByText(/run_deep_analysis|分析进度/).first(),
    ).toBeVisible({ timeout: 240_000 })

    // 关键断言 4：管线触发后仍无错误
    await expect(
      page.getByText(/错误.*400/),
    ).toHaveCount(0)
  })
})
