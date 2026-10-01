import { test, expect } from '@playwright/test'

/**
 * 报告右侧面板与主顶栏层叠 E2E（fix-report-panel-header-overlay 复现测试）
 *
 * 用户报告（2026-09-29）：面板打开后，主顶栏（查看全部文件 / 设置 / 圆形装饰占位）
 * 与面板顶部操作栏（完整报告 + 导出芯片 + 关闭）在同一视口行交叠叠字；且主顶栏
 * 右侧存在无交互的圆形装饰 div（w-7 h-7 rounded-full），意义不明、不可点击。
 *
 * 根因（真实 Chromium 复现 + elementFromPoint/盒模型探针证实）：面板根节点背景
 * 使用了主题中不存在的令牌 var(--bg-base)（index.css 只定义了 --bg-base-default）
 * → 背景无效为透明。面板 z-55 > 顶栏 z-50、hit-test 归面板（顶栏按钮因此点不到），
 * 但顶栏整行透过透明背景可见，两层文字/芯片互相叠刻——面板半透明是「重叠」与
 * 「头像框不可点击」的共同根因；圆形装饰占位另按用户要求移除。
 *
 * 契约（openspec/specs/frontend/spec.md「报告右侧面板」「面板操作栏」）：
 * 面板打开后 SHALL 从右侧滑出展示完整报告，面板顶部 SHALL 固定操作栏（导出 + 关闭）。
 * 面板为全高覆盖层，其操作栏行内不得出现任何不属于面板的主顶栏元素。
 *
 * 环境：依赖 STUB_SCENARIO=pipeline 的 5 层管线后端（8002/5175），由
 * playwright.timeline.config.ts 拉起；默认 config 从 testIgnore 排除（同 report-export.spec.ts）。
 *
 * Selector 来源（真实 DOM / 前端源码已提交事实）：
 * - report-side-panel / panel-close / panel-export-<fmt>：ReportSidePanel.tsx
 * - open-report-button：App.tsx ReportCard 摘要卡
 * - header 内圆形装饰：App.tsx 主顶栏 `div.w-7.h-7.rounded-full`
 */

test.setTimeout(240_000)

/** 采样一行 y 上的最顶层元素是否全部属于面板（面板工具栏行不得被外部元素覆盖） */
async function toolbarRowCoveredByPanel(page: import('@playwright/test').Page): Promise<boolean> {
  return page.evaluate(() => {
    const panel = document.querySelector('[data-testid="report-side-panel"]')
    const close = document.querySelector('[data-testid="panel-close"]')
    if (!panel || !close) return false
    const pr = panel.getBoundingClientRect()
    const cr = close.getBoundingClientRect()
    const y = cr.y + cr.height / 2
    if (pr.width === 0 || pr.height === 0) return false
    // 面板工具栏行内从左到右均匀采样（含面板左缘内 2px），任意一点顶层元素不属于面板即为重叠
    const xs = [pr.x + 2, pr.x + pr.width * 0.25, pr.x + pr.width * 0.5, pr.x + pr.width * 0.75, cr.x + cr.width / 2]
    for (const x of xs) {
      const top = document.elementFromPoint(x, y)
      if (!top || !(panel === top || panel.contains(top))) return false
    }
    return true
  })
}

test.describe('报告面板与主顶栏层叠', () => {
  test('面板打开后操作栏行不被主顶栏覆盖，且主顶栏无圆形装饰占位', async ({ page }) => {
    // 1. 进入应用并注入测试 API Key（同 report-export.spec：5175 → 8002 pipeline stub）
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-panel-overlay')
    })
    await page.reload()

    // 2. 深度模式触发管线（EmptyState 两步下拉）
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 3. 报告完成稳定终态（stub 每节点 1.5s，整管线留足超时）
    await expect(
      page.getByRole('heading', { name: '贵州茅台（600519）' }),
    ).toBeVisible({ timeout: 150_000 })

    // 4. 打开右侧面板并等滑出完成（data-state=open，300ms transform 终态）
    await page.getByTestId('open-report-button').click()
    const panel = page.getByTestId('report-side-panel')
    await expect(panel).toBeVisible()
    await expect(panel).toHaveAttribute('data-state', 'open')

    // 5. 面板操作栏渲染完整（导出芯片 + 关闭按钮可达）
    await expect(page.getByTestId('panel-export-md')).toBeVisible()
    await expect(page.getByTestId('panel-close')).toBeVisible()

    // 6. 核心契约一：面板根背景必须不透明——根因回归锚点。
    //    2026-09-29 重叠事故根因：面板根节点用了不存在的令牌 var(--bg-base)，
    //    背景无效 → 透明，主顶栏整行透出与面板操作栏叠字。注意 elementFromPoint
    //    层叠采样对透明背景不敏感（hit-test 不看绘制），故背景断言独立存在。
    await expect(panel).not.toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
    await expect(panel).not.toHaveCSS('background-color', 'transparent')

    // 7. 核心契约二：面板工具栏行内任意采样点的最顶层元素都属于面板——
    //    主顶栏（查看全部文件 / 设置）不得绘制在面板操作栏之上（z 序契约）
    await expect
      .poll(() => toolbarRowCoveredByPanel(page), { timeout: 5_000 })
      .toBe(true)

    // 8. 主顶栏不再渲染无交互的圆形装饰占位（w-7 h-7 rounded-full 空 div）
    await expect(page.locator('header div.w-7.h-7.rounded-full')).toHaveCount(0)
  })
})
