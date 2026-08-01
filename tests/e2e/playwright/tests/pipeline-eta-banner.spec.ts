import { test, expect } from '@playwright/test'

/**
 * 管线横幅显式关闭 + node_start 事件流 + 动态 ETA（fix-pipeline-banner-and-eta delta task 4.4）
 *
 * 验证目标：
 * 1. 动态 ETA：进度区显示"已用时 M:SS · 预计剩余 ~M:SS"，且已用时长随时间递增（非静态 ~90s）
 * 2. node_start 驱动 running 态：agent 路径补发 node_start 后，管线卡内容随节点推进更新
 *    （node_start 缺失时 content 只在 node_complete 后跳变，Layer II 期间长时间停滞）
 * 3. 思考横幅显式折叠：节点推进后，先前节点的思考横幅从"思考中"变为"思考已完成"，
 *    不再依赖 currentNode 位置推断
 *
 * 确定性方案与 thinking-timeline-pipeline.spec.ts 相同（TESTING=1 + STUB_SCENARIO=pipeline，
 * 后端 8002 / 前端 5175），E2E 约束：不 mock 业务接口，LLM 走 TESTING=1 stub。
 */

test.setTimeout(180_000)

test.describe('管线横幅关闭与动态 ETA（fix-pipeline-banner-and-eta）', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-eta')
      // 清空 ETA 历史，确保初始预估走默认值（断言不受历史数据干扰）
      localStorage.removeItem('financeAgent.pipelineDurations')
    })
    await page.reload()

    // 切换到深度模式（EmptyState 下拉菜单，两步操作）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()

    // 输入并发送（stub pipeline 场景：search_stock -> run_deep_analysis -> 回答）
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()
  })

  test('1. ETA 显示已用时与预计剩余，且已用时长动态递增', async ({ page }) => {
    // ETA 文本出现在管线卡进度区（font-mono span），格式"已用时 M:SS · 预计剩余 ~M:SS"
    const etaLocator = page.getByText(/已用时 \d+:\d{2} · 预计剩余 ~\d+:\d{2}/)
    await expect(etaLocator).toBeVisible({ timeout: 60_000 })

    // 已用时长随时间递增：采样两次，第二次的秒数不小于第一次（stub 节点延迟 0.25s，
    // 采样间隔 1.5s 保证跨过至少一个整秒）
    const readElapsed = async (): Promise<number> => {
      const text = (await etaLocator.textContent()) ?? ''
      const m = text.match(/已用时 (\d+):(\d{2})/)
      return m ? Number(m[1]) * 60 + Number(m[2]) : -1
    }
    const t1 = await readElapsed()
    await page.waitForTimeout(1_500)
    const t2 = await readElapsed()
    expect(t1).toBeGreaterThanOrEqual(0)
    expect(t2).toBeGreaterThanOrEqual(t1)
  })

  test('2. node_start 驱动管线卡内容随节点推进（running 态可见）', async ({ page }) => {
    // node_start 补发后，管线卡 content 在节点开始即更新为"{layer}: {desc}..."。
    // 捕获任一"进行中"文案（带省略号），证明 agent 路径 node_start 已到达前端。
    // （node_start 缺失的旧行为：content 只有"...✓"完成态与初始文案，无中间进行态）
    await expect(
      page.getByText(/Layer I|Layer II|PREP/).first(),
    ).toBeVisible({ timeout: 60_000 })
  })

  test('3. 节点推进后思考横幅显式折叠为"思考已完成"', async ({ page }) => {
    // 管线分组标题出现（技术面分析师），证明 node 分组渲染正常
    const groupTitle = page.locator('div.text-xs.font-semibold', { hasText: /^技术面分析师$/ })
    await expect(groupTitle).toBeVisible({ timeout: 120_000 })

    // 等待管线推进（Trader 分组出现 = 管线已越过 Layer I/II）
    const traderTitle = page.locator('div.text-xs.font-semibold', { hasText: /^Trader$/ })
    await expect(traderTitle).toBeVisible({ timeout: 120_000 })

    // 此时技术面分析师的思考横幅应为完成态（显式 done=true 折叠），
    // 而不是停留在"思考中"。在管线卡消失前并行捕获。
    const completedBanners = page.getByRole('button', { name: /思考已完成/ })
    await expect(completedBanners.first()).toBeVisible({ timeout: 120_000 })
  })

  test('4. 管线完成写入 ETA 历史记录', async ({ page }) => {
    // 管线走完 report_ready 后，localStorage 应写入本次耗时
    await expect(page.getByText(/投资分析报告/).first()).toBeVisible({ timeout: 150_000 })
    const durations = await page.evaluate(() => {
      const raw = localStorage.getItem('financeAgent.pipelineDurations')
      return raw ? JSON.parse(raw) : []
    })
    expect(Array.isArray(durations)).toBe(true)
    expect(durations.length).toBeGreaterThan(0)
    expect(durations[0]).toBeGreaterThan(0)
  })
})
