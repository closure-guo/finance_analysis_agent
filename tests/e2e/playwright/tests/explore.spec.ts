import { test } from '@playwright/test'

/**
 * DOM 探索工具--写 E2E spec 前先跑此文件获取可交互元素清单
 *
 * 用法：
 *   cd tests/e2e/playwright
 *   npx playwright test explore --reporter=list
 *
 * 输出所有 data-testid / button / input / textarea / role 元素，
 * agent 从中提取稳定 selector（data-testid > role+name > placeholder）
 *
 * 探索特定页面（需先在代码中修改 page.goto 路径）：
 *   npx playwright test explore -g "探索 /analysis"
 */
test.describe('DOM 探索', () => {
  test('探索首页可交互元素', async ({ page }) => {
    await page.goto('/')
    // 等待页面加载完成
    await page.waitForLoadState('networkidle')

    const elements = await page.locator(
      '[data-testid], button, input, textarea, [role], a[href], select'
    ).all()

    console.log('\n=== 首页可交互元素清单 ===')
    for (const el of elements) {
      const info = await el.evaluate((node: HTMLElement) => ({
        tag: node.tagName.toLowerCase(),
        testid: node.getAttribute('data-testid'),
        role: node.getAttribute('role'),
        name: node.getAttribute('name'),
        text: (node.textContent || '').trim().slice(0, 80),
        placeholder: node.getAttribute('placeholder'),
        ariaLabel: node.getAttribute('aria-label'),
        type: node.getAttribute('type'),
        href: node.getAttribute('href')?.slice(0, 50),
        disabled: node.hasAttribute('disabled'),
      }))
      // 只输出有标识信息的元素
      if (info.testid || info.role || info.placeholder || info.text || info.ariaLabel) {
        console.log(JSON.stringify(info))
      }
    }
    console.log('=== 探索完成 ===\n')
  })

  test('探索快速模式对话页可交互元素', async ({ page }) => {
    // 先配置 API Key
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 切换到快速模式（两步下拉菜单）
    const modeBtn = page.getByRole('button', { name: /模式/ })
    if (await modeBtn.isVisible().catch(() => false)) {
      await modeBtn.click()
      await page.getByRole('button', { name: /快速模式/ }).click()
    }

    // 输入并发送，触发对话流
    await page.getByPlaceholder(/输入问题/).fill('探索测试')
    await page.getByTestId('send-button').click()
    await page.waitForTimeout(2000) // 等待 UI 渲染

    const elements = await page.locator(
      '[data-testid], button, input, textarea, [role]'
    ).all()

    console.log('\n=== 快速模式对话页可交互元素清单 ===')
    for (const el of elements) {
      const info = await el.evaluate((node: HTMLElement) => ({
        tag: node.tagName.toLowerCase(),
        testid: node.getAttribute('data-testid'),
        role: node.getAttribute('role'),
        text: (node.textContent || '').trim().slice(0, 80),
        placeholder: node.getAttribute('placeholder'),
        visible: node.offsetParent !== null,
      }))
      if (info.testid || info.role || info.placeholder) {
        console.log(JSON.stringify(info))
      }
    }
    console.log('=== 探索完成 ===\n')
  })
})
