import { test, expect } from '@playwright/test'

/**
 * 报告导出抽屉 E2E（add-report-export delta Task 8）
 *
 * 覆盖：报告头部「全部文件」横幅 → 打开导出抽屉 → 格式下载列表 →
 * 预览正文面板 → 关闭抽屉（关闭按钮 → 隐藏）。
 *
 * 环境：这是「5 层深度分析管线」E2E，必须在 STUB_SCENARIO=pipeline 的后端下运行——
 * 仅 StubLLMClient 吐 run_deep_analysis 工具调用才能触发真实管线并产出 report_ready
 * 与 file_paths 四键。因此本 spec 与其它管线 spec（pipeline-eta-banner 等）一致：
 *   - 导航到管线专用前端端点 http://localhost:5175（VITE_API_TARGET → 8002，STUB_SCENARIO=pipeline）
 *   - 由 playwright.timeline.config.ts 拉起该端口对；从默认 playwright.config.ts 的 testIgnore 排除
 *
 * Selector 来源：真实已提交前端 DOM（ReportFileDrawer.tsx / App.tsx ReportCard），
 * 与 Task 6/7 契约一致：
 *   - open-files-banner：报告 streaming=false 时才渲染的「全部文件」横幅按钮
 *   - export-drawer / drawer-backdrop / drawer-close / preview-open / drawer-preview
 *   - download-pdf / download-docx / download-md：格式下载项（缺文件时为 <button>，有文件时为 <a href>）
 *
 * 平台无关性说明：stub 管线预生成文件与否随平台而异（本机实测 file_paths 为空 → 三格式
 * 均为 <button> 走 POST /api/export 按需导出；CI Linux 下 md/docx 可能预生成 → <a href>）。
 * 两者皆为合法渲染，故下载项断言只断言「行存在」，不断言平台相关的 href/请求行为。
 */

test.setTimeout(240_000)

test.describe('报告导出抽屉', () => {
  test('深度分析完成后可打开全部文件抽屉、预览正文并关闭', async ({ page }) => {
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

    // 4. 稳定终态：管线跑完报告完成后，「全部文件」横幅可见（streaming=false 才渲染）
    await expect(page.getByTestId('open-files-banner')).toBeVisible({ timeout: 150_000 })

    // 5. 打开导出抽屉
    await page.getByTestId('open-files-banner').click()
    await expect(page.getByTestId('export-drawer')).toBeVisible()

    // 6. 格式下载列表稳定呈现（PDF/Word/Markdown 恒列出）。
    //    注：stub 管线预生成文件与否随平台而异（本机实测 file_paths 为空 → 三格式均为
    //    <button> 走 POST /api/export 按需导出；CI Linux 下 md/docx 可能预生成 → <a href>）。
    //    两者皆为合法渲染，因此只断言「行存在且可点击」，不断言平台相关的 href/请求行为
    //    （按需导出接口行为由后端单测 Task 5 与前端单测覆盖）。
    await expect(page.getByTestId('download-pdf')).toBeVisible()
    await expect(page.getByTestId('download-docx')).toBeVisible()
    await expect(page.getByTestId('download-md')).toBeVisible()

    // 7. 预览面板渲染报告正文
    await page.getByTestId('preview-open').click()
    await expect(page.getByTestId('drawer-preview')).toBeVisible()

    // 8. 关闭抽屉（关闭按钮 → 抽屉隐藏）
    await page.getByTestId('drawer-close').click()
    await expect(page.getByTestId('export-drawer')).toBeHidden()
  })
})
