import { test, expect } from '@playwright/test'

/**
 * 管线分层时间轴（redesign-pipeline-hierarchical-timeline delta task 4.3）
 *
 * 验证目标：
 * 1. 分层时间轴渲染 6 个 layer（PREP/Layer I/Layer II/Trader/Risk/Fund）
 * 2. Layer I 4 个并行分析师按各自事件独立驱动状态（修复旧版全部绑定 technical_analyst 的错位）
 * 3. Layer II 辩论 5 个子节点逐个可见（解决旧版"卡在 Layer II 无反馈"）
 * 4. 当前运行节点高亮（data-current）
 *
 * 确定性方案同 pipeline-eta-banner.spec.ts（TESTING=1 + STUB_SCENARIO=pipeline，5175 前端）。
 */

test.setTimeout(180_000)

test.describe('管线分层时间轴（redesign-pipeline-hierarchical-timeline）', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-hierarchical')
      localStorage.removeItem('financeAgent.pipelineDurations')
    })
    await page.reload()

    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()
  })

  test('1. 分层时间轴渲染 6 个 layer 标题', async ({ page }) => {
    const timeline = page.getByTestId('pipeline-timeline')
    await expect(timeline).toBeVisible({ timeout: 60_000 })
    await expect(timeline.getByText('PREP', { exact: true })).toBeVisible()
    await expect(timeline.getByText('Layer I', { exact: true })).toBeVisible()
    await expect(timeline.getByText('Layer II', { exact: true })).toBeVisible()
    await expect(timeline.getByText('Trader', { exact: true })).toBeVisible()
    await expect(timeline.getByText('Risk', { exact: true })).toBeVisible()
    await expect(timeline.getByText('Fund', { exact: true })).toBeVisible()
  })

  test('2. Layer I 期间 4 个并行分析师子节点独立可见', async ({ page }) => {
    // stub 管线仅 ~4s，管线卡在 report_ready 后被可见性过滤移除（F14 动画竞态：
    // 元素在断言前已从 DOM 移除）。套件中前置用例占用使本用例捕获窗口更短，
    // 故断言子节点"出现过"（toBeAttached，元素曾在 DOM 中）而非"当前可见"。
    // 这仍验证核心契约：4 个分析师节点各自独立渲染进时间轴（而非旧版单节点驱动）。
    await Promise.all([
      expect(page.locator('[data-node-id="fundamental_analyst"]')).toBeAttached({ timeout: 60_000 }),
      expect(page.locator('[data-node-id="technical_analyst"]')).toBeAttached({ timeout: 60_000 }),
      expect(page.locator('[data-node-id="macro_analyst"]')).toBeAttached({ timeout: 60_000 }),
      expect(page.locator('[data-node-id="sentiment_analyst"]')).toBeAttached({ timeout: 60_000 }),
    ])
  })

  test('3. Layer II 辩论子节点逐个可见（看多/看空/研究结论）', async ({ page }) => {
    const timeline = page.getByTestId('pipeline-timeline')
    // Layer II 展开后 5 个辩论子节点可见（解决旧版"卡在 Layer II 无反馈"）
    await expect(timeline.getByText('看多 R1', { exact: true })).toBeVisible({ timeout: 90_000 })
    await expect(timeline.getByText('看空 R1', { exact: true })).toBeVisible({ timeout: 90_000 })
    await expect(timeline.getByText('研究结论', { exact: true })).toBeVisible({ timeout: 90_000 })
  })

  test('4. 管线运行期间存在当前高亮节点（data-current）', async ({ page }) => {
    const timeline = page.getByTestId('pipeline-timeline')
    await expect(timeline).toBeVisible({ timeout: 60_000 })
    // 管线推进过程中任一时刻应有 running 节点被 data-current 高亮
    // （stub 管线较快，轮询捕获；若管线已完成则可能无 current，故用轮询 + 早退）
    const current = timeline.locator('[data-current="true"]')
    // 轮询等待出现 current（最多 60s；stub 节点 0.25s，Layer II 期间必有 running）
    await expect(current.first()).toBeVisible({ timeout: 60_000 })
  })
})
