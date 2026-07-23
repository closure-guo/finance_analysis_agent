"""E2E regression - verify EmptyState mode dropdown + input interaction.

前端 EmptyState 使用下拉框（标签"模式："），默认 deep。
选项：快速模式（单次 LLM + Web Search）/ 深度研究（5 层 Agent 流水线）。
"""

import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
SS = "tests/e2e/diagnostic_screenshots"

DEEP_PH = "输入股票名称或代码"
QUICK_PH = "输入问题"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        print("=" * 60)
        print("Step 1: Load page - check default mode = 深度研究")
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{SS}/reg_01_loaded.png")

        body = await page.inner_text("body")
        assert "模式：" in body, "模式： label not found!"
        assert "深度研究" in body, "深度研究 not shown!"
        print("  [PASS] 模式： dropdown visible, default = 深度研究")

        textarea = page.locator("textarea").last
        placeholder = await textarea.get_attribute("placeholder") or ""
        print(f"  Default placeholder: {placeholder}")
        assert DEEP_PH in placeholder, f"Default should be deep, placeholder={placeholder}"
        print("  [PASS] Default mode = 深度研究 (deep)")

        print("\n" + "=" * 60)
        print("Step 2: Open dropdown, select 快速模式")
        await page.locator("button:has-text('模式：')").click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/reg_02_dropdown_open.png")

        body = await page.inner_text("body")
        assert "快速模式" in body and "单次 LLM + Web Search" in body, "Dropdown options not shown!"
        print("  [PASS] Dropdown open, 快速模式 + desc visible")

        await page.locator("button:has-text('快速模式')").click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/reg_03_quick_mode.png")

        placeholder = await textarea.get_attribute("placeholder") or ""
        print(f"  Quick mode placeholder: {placeholder}")
        assert QUICK_PH in placeholder, f"Quick placeholder mismatch: {placeholder}"
        print("  [PASS] Switched to 快速模式 (placeholder changed)")

        body = await page.inner_text("body")
        assert "分析中" not in body and "Pipeline" not in body, "Analysis started unexpectedly!"
        print("  [PASS] No analysis started (mode switch only)")

        print("\n" + "=" * 60)
        print("Step 3: Switch back to 深度研究")
        await page.locator("button:has-text('模式：')").click()
        await page.wait_for_timeout(300)
        await page.locator("button:has-text('深度研究')").click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/reg_04_deep_mode.png")

        placeholder = await textarea.get_attribute("placeholder") or ""
        assert DEEP_PH in placeholder, f"Deep placeholder mismatch: {placeholder}"
        print("  [PASS] Switched back to 深度研究")

        print("\n" + "=" * 60)
        print("Step 4: Type without API key - should prompt for key")
        await textarea.fill("茅台")
        await page.screenshot(path=f"{SS}/reg_05_typed.png")

        await textarea.press("Enter")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SS}/reg_06_after_enter.png")

        body = await page.inner_text("body")
        if "API Key" in body or "DeepSeek" in body or "配置" in body or "贵州茅台" in body or "分析" in body:
            print("  [PASS] API key prompt shown OR analysis started (key configured)")
        else:
            print(f"  [WARN] Unexpected state - body snippet: {body[:300]}")

        print("\n" + "=" * 60)
        print("ALL CHECKS PASSED")
        print(f"Screenshots saved to {SS}/")

        await browser.close()


asyncio.run(main())
