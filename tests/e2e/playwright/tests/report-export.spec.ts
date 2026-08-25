import { test, expect } from '@playwright/test'

/**
 * 报告导出入口 E2E（update-file-export-entry delta Task 7）
 *
 * 覆盖：深度分析完成后 → 报告卡标题「贵州茅台（600519）」→ 会话级三入口
 * （报告名横幅 report-name-banner / 全部文件横幅 conversation-files-banner /
 * 顶部栏按钮 topbar-files-button）均可见 → 点击顶部栏按钮打开导出抽屉 → 文件列表
 * 列出已生成文件（download-file-<fmt>）→ 关闭后经「全部文件」横幅再开一次（双入口等价）。
 *
 * 环境：这是「5 层深度分析管线」E2E，必须在 STUB_SCENARIO=pipeline 的后端下运行——
 * 仅 StubLLMClient 吐 run_deep_analysis 工具调用才能触发真实管线并产出 report_ready
 * 与 file_paths（generate_file 为真实图节点，md/docx/pptx 必然成功写盘 REPORTS_DIR；
 * stub 只接管外部 LLM 调用）。因此本 spec 与其它管线 spec（pipeline-eta-banner 等）一致：
 *   - 导航到管线专用前端端点 http://localhost:5175（VITE_API_TARGET → 8002，STUB_SCENARIO=pipeline）
 *   - 由 playwright.timeline.config.ts 拉起该端口对；从默认 playwright.config.ts 的 testIgnore 排除
 *
 * Selector 来源：真实已提交前端 DOM（App.tsx ReportCard / ReportEntryBanners.tsx /
 * ReportFileDrawer.tsx），与 Task 5/6 契约一致：
 *   - 报告卡 <h3>：formatReportTitle 输出「名称（代码）」组合标题
 *   - report-name-banner：每份已完成报告的报告名横幅（点击打开该报告文件抽屉）
 *   - conversation-files-banner：会话尾部「全部文件」横幅（打开最后一份可导出报告）
 *   - topbar-files-button：顶部栏「查看全部文件」按钮
 *   - export-drawer / drawer-close / drawer-file-list / download-file-<fmt>
 *   - open-files-banner：旧报告头部「全部文件」导出按钮已移除，断言 toHaveCount(0) 确保不存在
 *
 * 口径 B：报告完成（streaming=false）且 file_paths 含至少一个已生成文件时三入口才渲染。
 * stub 管线下 generate_file 是真实图节点、必然成功写盘（本机实测 md/docx/pptx 均生成，
 * 文件名含「名称_代码」前缀），故三入口可见、抽屉文件列表非空。
 */

test.setTimeout(240_000)

test.describe('报告导出入口', () => {
  test('深度分析完成后新三入口可见、抽屉列出已生成文件、关闭后双入口等价重开', async ({ page }) => {
    // 1. 进入应用并注入测试 API Key（管线 spec 端口对：5175 前端 → 8002 STUB_SCENARIO=pipeline 后端）
    await page.goto('http://localhost:5175')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-report-export')
    })
    await page.reload()

    // 2. 显式选中「深度研究 … 5 层 Agent 流水线」模式（EmptyState 两步下拉）——管线后端依赖 deep 模式
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()

    // 3. 输入并发送（与 pipeline-eta-banner 等管线 spec 相同文案，确定性触发 search_stock → run_deep_analysis）
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()

    // 4. 报告完成后的稳定终态：报告卡标题出现「贵州茅台（600519）」组合
    await expect(page.getByText('贵州茅台（600519）')).toBeVisible({ timeout: 150_000 })

    // 5. 报告卡头部不再有「全部文件」导出按钮（旧入口已移除）
    await expect(page.getByTestId('open-files-banner')).toHaveCount(0)

    // 6. 会话级入口：报告名横幅、全部文件横幅、顶部栏按钮均可见
    await expect(page.getByTestId('report-name-banner')).toBeVisible()
    await expect(page.getByTestId('conversation-files-banner')).toBeVisible()
    await expect(page.getByTestId('topbar-files-button')).toBeVisible()

    // 7. 点击顶部栏按钮打开抽屉，文件列表包含已生成文件（文件名含 名称_代码 前缀 + _report.md/.docx 后缀，时间戳不可固定）
    await page.getByTestId('topbar-files-button').click()
    await expect(page.getByTestId('export-drawer')).toBeVisible()
    await expect(page.getByTestId('drawer-file-list')).toBeVisible()
    await expect(page.locator('[data-testid^="download-file-"]').first()).toBeVisible()

    // 8. 关闭抽屉后经「全部文件」横幅再开一次（双入口等价）
    await page.getByTestId('drawer-close').click()
    await expect(page.getByTestId('export-drawer')).toHaveCount(0)
    await page.getByTestId('conversation-files-banner').click()
    await expect(page.getByTestId('export-drawer')).toBeVisible()
  })
})
