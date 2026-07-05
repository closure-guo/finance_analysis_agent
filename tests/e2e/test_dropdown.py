"""E2E test — verify mode dropdown."""

import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
SS = "tests/e2e/diagnostic_screenshots"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        await page.goto(BASE_URL, wait_until="networkidle")
        await page.screenshot(path=f"{SS}/dropdown_01_default.png")

        body = await page.inner_text("body")
        assert "模式：" in body, "Mode label not found"
        assert "快速模式" in body, "Default not quick"
        print("[PASS] Default = 快速模式")

        # Click dropdown
        dropdown_btn = page.locator("button:has-text('快速模式')")
        await dropdown_btn.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/dropdown_02_open.png")

        body = await page.inner_text("body")
        assert "单次 LLM + Web Search" in body, "Quick desc not shown"
        assert "5 层 Agent 流水线" in body, "Deep desc not shown"
        print("[PASS] Dropdown shows both options with descriptions")

        # Select deep
        deep_option = page.locator("button:has-text('深度研究')")
        await deep_option.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/dropdown_03_deep.png")

        body = await page.inner_text("body")
        assert "深度研究" in body, "Deep mode not selected"
        assert "快速模式" not in body.split("深度研究")[0][-50:], "Quick still showing"
        print("[PASS] Switched to 深度研究")

        # Check placeholder changed
        textarea = page.locator("textarea")
        ph = await textarea.get_attribute("placeholder")
        print(f"  Placeholder: {ph}")

        # Click outside to close dropdown
        await page.locator("body").click(position={"x": 600, "y": 400})
        await page.wait_for_timeout(200)

        # Reopen and switch back
        dropdown_btn = page.locator("button:has-text('深度研究')")
        await dropdown_btn.click()
        await page.wait_for_timeout(200)
        quick_option = page.locator("button:has-text('快速模式')")
        await quick_option.click()
        await page.wait_for_timeout(200)
        await page.screenshot(path=f"{SS}/dropdown_04_back_quick.png")

        body = await page.inner_text("body")
        assert "快速模式" in body, "Quick mode not restored"
        print("[PASS] Switched back to 快速模式")

        print("\nALL PASSED")
        await browser.close()


asyncio.run(main())
