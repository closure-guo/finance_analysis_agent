import { test, expect } from '@playwright/test'
import * as path from 'path'

/**
 * 会话页 + 报告渲染态视觉基线截图采集（refactor-ui-design-system Task 1.2 补齐）
 *
 * 一次性采集工具，不属于常规 E2E 门禁断言：
 * - 仅在设置 BASELINE_DIR 环境变量时运行，否则整组跳过（避免污染日常门禁），
 *   与 visual-baseline.spec.ts 的采集模式一致
 * - 基线采集时前端源码须处于基线提交 cc00bc0（main）状态运行本 spec，
 *   重构后采集时前端源码处于本分支 HEAD 状态，同一 spec 两次运行产出可对比截图
 * - 必须在 playwright.timeline.config.ts 下运行（STUB_SCENARIO=pipeline 的
 *   5 层管线后端 8002 / 前端 5175），与 report-export.spec.ts 同环境
 *
 * 用法：
 *   BASELINE_DIR=<abs path> npx playwright test --config=playwright.timeline.config.ts visual-baseline-report.spec.ts
 *
 * 产出（fullPage）：
 * 1. session-page.png —— 会话页（对话流 + 管线时间轴可见，管线运行中）
 * 2. report-view.png  —— 报告渲染态（报告卡标题 + 报告正文 markdown 可见）
 *
 * Selector 口径与 report-export.spec.ts / pipeline-hierarchical-timeline.spec.ts 一致，
 * 在 cc00bc0 与本分支 HEAD 均成立（pipeline-timeline testid 与 formatReportTitle
 * 组合标题两版前端同在）：
 *   - pipeline-timeline：分层时间轴容器（管线启动后渲染）
 *   - h3「贵州茅台（600519）」：报告卡组合标题（formatReportTitle）
 */
const BASELINE_DIR = process.env.BASELINE_DIR ?? ''

test.setTimeout(240_000)

test.describe('视觉基线截图采集（会话页 + 报告渲染态，refactor-ui-design-system 1.2）', () => {
  // 未指定输出目录时跳过：本 spec 是一次性采集工具，不进常规门禁
  test.skip(!BASELINE_DIR, '需要 BASELINE_DIR 环境变量指定截图输出目录')

  test('采集管线会话页与报告渲染态截图', async ({ page }) => {
    // 1. 进入管线专用前端（5175 → 8002 STUB_SCENARIO=pipeline）并注入测试 API Key
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-visual-baseline-report')
    })
    await page.reload()

    // 2. 选中深度模式并发送（与 pipeline 系 spec 相同文案，确定性触发管线）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 3. 会话页截图：管线时间轴可见（对话流 + 分层时间轴）
    const timeline = page.getByTestId('pipeline-timeline')
    await expect(timeline).toBeVisible({ timeout: 60_000 })
    // 等 1s 让时间轴节点/流式指示器完成首帧渲染
    await page.waitForTimeout(1000)
    await page.screenshot({ fullPage: true, path: path.join(BASELINE_DIR, 'session-page.png') })

    // 4. 报告渲染态截图：报告卡标题 + 报告正文 markdown 可见
    await expect(
      page.getByRole('heading', { name: '贵州茅台（600519）' }),
    ).toBeVisible({ timeout: 150_000 })
    const reportBody = page.locator('.markdown-body').first()
    await expect(reportBody).toBeVisible({ timeout: 30_000 })
    // 等 1.5s 让 ECharts 图表（若渲染）与 markdown 排版稳定
    await page.waitForTimeout(1500)
    await page.screenshot({ fullPage: true, path: path.join(BASELINE_DIR, 'report-view.png') })
  })
})
