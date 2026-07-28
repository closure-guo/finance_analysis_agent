import { test, expect } from '@playwright/test'

/**
 * 管线模式：PipelineCard 按 agent 阶段分组渲染 timeline（agent-turn-box-display delta task 5.5）
 *
 * 验证目标：
 * 1. 完整 5 层深度分析管线运行期间，各 agent 节点（技术面分析师/多头分析师/Trader 等）
 *    的思考 token 带 node 字段，前端 PipelineCard 按 node 分组渲染出多个角色名标题
 * 2. 每个分组内渲染该 agent 的思考横幅（"思考中/思考已完成"）
 * 3. node 字段经 run_deep_analysis 工具 -> StreamEvent.think(metadata) -> SSE thinking_token
 *    全链路透传（delta 修复的真实 bug：此前 custom 分支丢弃 chunk["node"]）
 *
 * 确定性方案（TESTING=1 + STUB_SCENARIO=pipeline，不依赖真实 LLM/AKShare，进 CI 门禁）：
 *   - 后端 StubLLMClient 走 pipeline 场景：tool_call(search_stock) -> tool_call(run_deep_analysis) -> 回答
 *   - 管线内部：call_llm_streaming 的 TESTING 分支按 node 产出合法 JSON answer + 带图节点名的
 *     思考 token；fetch_data 的 TESTING 分支返回确定性三大报表（勾稽校验 PASS）
 *   - 前端通过 playwright.timeline.config.ts 的独立管线端口对（后端 8002 / 前端 5175）运行，
 *     本 spec 用 page.goto('http://localhost:5175') 指向管线前端（config baseURL 是 5174，
 *     用于其他 timeline spec，故此处用绝对 URL）
 */

// 管线全链路（含真实 graph 执行）耗时较长，放宽超时
test.setTimeout(180_000)

test.describe('管线模式 PipelineCard 按 agent 阶段分组', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-pipeline')
    })
    await page.reload()

    // 切换到深度模式（EmptyState 下拉菜单，两步操作）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()

    // 输入并发送（stub pipeline 场景：search_stock -> run_deep_analysis -> 回答）
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()
  })

  test('1. PipelineCard 出现多个 agent 分组标题（技术面分析师/Trader/基金经理）', async ({ page }) => {
    // 分组标题用 nodeDisplayName 输出（NODE_DISPLAY_NAMES 映射的中文角色名）。
    // 注意：nodeTimelines 是流式中间态，report_ready 后管线卡隐藏、分组消失，故并行等待
    // （首个断言完成前管线卡未消失即捕获其余），且聚焦"按 node 分组"这一核心：
    // 多个不同 agent（技术面/Trader/基金经理）各自成为独立分组标题。
    // 若 node 字段丢失（delta 修复前的 bug），所有管线思考归入 nodeTimelines['']，
    // 不会渲染任何 nodeDisplayName 分组标题——本断言正是对该 bug 的回归防护。
    await Promise.all([
      expect(page.getByText('技术面分析师', { exact: true })).toBeVisible({ timeout: 120_000 }),
      expect(page.getByText('Trader', { exact: true })).toBeVisible({ timeout: 120_000 }),
      expect(page.getByText('基金经理', { exact: true })).toBeVisible({ timeout: 120_000 }),
    ])
  })

  test('2. 分组内渲染该 agent 的思考横幅', async ({ page }) => {
    // 管线分组区域的思考横幅（"思考中/思考已完成"）。用 Promise.all 在管线卡可见窗口内
    // 同时捕获分组标题与横幅，避免流式中间态窗口短导致的串行断言竞态。
    await Promise.all([
      expect(page.getByText('技术面分析师', { exact: true })).toBeVisible({ timeout: 120_000 }),
      expect(
        page.getByRole('button', { name: /思考已完成|思考中/ }).first()
      ).toBeVisible({ timeout: 120_000 }),
    ])
  })

  test('3. 管线最终产出报告（report_ready），全链路确定推进', async ({ page }) => {
    // 管线走完 generate_report -> report_ready -> 前端进入 report 态，出现报告标题
    await expect(page.getByText(/投资分析报告/).first()).toBeVisible({ timeout: 150_000 })
  })
})
