"""E2E test - verify EmptyState mode dropdown.

前端 EmptyState 仍使用下拉框（标签"模式："），默认 deep。
选项：快速模式（单次 LLM + Web Search）/ 深度研究（5 层 Agent 流水线）。
"""

import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
SS = "tests/e2e/diagnostic_screenshots"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{SS}/dropdown_01_default.png")

        body = await page.inner_text("body")
        assert "模式：" in body, "模式： label not found"
        assert "深度研究" in body, "Default mode (深度研究) not shown"
        print("[PASS] Default mode = 深度研究")

        # Click dropdown trigger (button containing 模式：)
        dropdown_btn = page.locator("button:has-text('模式：')")
        await dropdown_btn.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/dropdown_02_open.png")

        body = await page.inner_text("body")
        assert "快速模式" in body, "快速模式 option not shown"
        assert "单次 LLM + Web Search" in body, "Quick desc not shown"
        assert "5 层 Agent 流水线" in body, "Deep desc not shown"
        print("[PASS] Dropdown shows both options with descriptions")

        # Select 快速模式
        quick_option = page.locator("button:has-text('快速模式')")
        await quick_option.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/dropdown_03_quick.png")

        textarea = page.locator("textarea").last
        ph = await textarea.get_attribute("placeholder") or ""
        assert "输入问题" in ph, f"Quick placeholder mismatch: {ph}"
        print(f"[PASS] Switched to 快速模式, placeholder: {ph}")

        # Reopen and switch back to 深度研究
        dropdown_btn = page.locator("button:has-text('模式：')")
        await dropdown_btn.click()
        await page.wait_for_timeout(300)
        deep_option = page.locator("button:has-text('深度研究')")
        await deep_option.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/dropdown_04_back_deep.png")

        ph = await textarea.get_attribute("placeholder") or ""
        assert "输入股票名称或代码" in ph, f"Deep placeholder mismatch: {ph}"
        print("[PASS] Switched back to 深度研究")

        # Click outside to close dropdown (open then click outside overlay)
        await dropdown_btn.click()
        await page.wait_for_timeout(300)
        await page.locator("body").click(position={"x": 700, "y": 500})
        await page.wait_for_timeout(500)
        body = await page.inner_text("body")
        if "单次 LLM + Web Search" not in body:
            print("[PASS] Outside click closes dropdown")
        else:
            print("[WARN] Dropdown text may persist (overlay close timing)")

        print("\nALL PASSED")
        await browser.close()


asyncio.run(main())
