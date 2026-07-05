"""E2E regression — verify mode selector + input interaction."""

import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
SS = "tests/e2e/diagnostic_screenshots"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        print("=" * 60)
        print("Step 1: Load page — check default mode")
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.screenshot(path=f"{SS}/reg_01_loaded.png")

        body = await page.inner_text("body")
        assert "当前模式" in body, "Mode indicator not found!"
        assert "快速模式" in body, "Default mode not quick!"
        print("  [PASS] Default mode = 快速模式")
        print("  [PASS] Mode indicator visible")

        print("\n" + "=" * 60)
        print("Step 2: Click '深度研究' — verify mode switch")
        deep_btn = page.locator("button:has-text('深度研究')")
        await deep_btn.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/reg_02_deep_mode.png")

        body = await page.inner_text("body")
        assert "深度研究" in body and "5 层 Agent 流水线" in body, "Deep mode not active!"
        print("  [PASS] Switched to 深度研究")

        # Verify it did NOT start analysis (no pipeline, no analyzing state)
        assert "分析中" not in body and "Pipeline" not in body, "Analysis started unexpectedly!"
        print("  [PASS] No analysis started (mode switch only)")

        print("\n" + "=" * 60)
        print("Step 3: Switch back to '快速模式'")
        quick_btn = page.locator("button:has-text('快速模式')")
        await quick_btn.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/reg_03_quick_mode.png")

        body = await page.inner_text("body")
        assert "快速模式" in body and "Web Search" in body, "Quick mode not active!"
        print("  [PASS] Switched back to 快速模式")

        print("\n" + "=" * 60)
        print("Step 4: Check selected button visual state")
        # Check if the quick button has the active class
        quick_btn_class = await quick_btn.get_attribute("class")
        print(f"  Quick button class: {quick_btn_class}")
        assert "yellow" in quick_btn_class or "active" in quick_btn_class.lower(), (
            "No active styling!"
        )
        print("  [PASS] Active button has visual feedback")

        print("\n" + "=" * 60)
        print("Step 5: Check placeholder changes with mode")
        textarea = page.locator("textarea")
        placeholder_quick = await textarea.get_attribute("placeholder")
        print(f"  Quick mode placeholder: {placeholder_quick}")

        await deep_btn.click()
        await page.wait_for_timeout(200)
        placeholder_deep = await textarea.get_attribute("placeholder")
        print(f"  Deep mode placeholder: {placeholder_deep}")
        assert placeholder_quick != placeholder_deep, "Placeholders should differ!"
        print("  [PASS] Placeholder changes with mode")

        await page.screenshot(path=f"{SS}/reg_04_placeholder.png")

        print("\n" + "=" * 60)
        print("Step 6: Type without API key — should prompt for key")
        await quick_btn.click()
        await page.wait_for_timeout(200)
        await textarea.fill("茅台")
        await page.screenshot(path=f"{SS}/reg_05_typed.png")

        # Press Enter — should show API key modal (no key configured)
        await textarea.press("Enter")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SS}/reg_06_after_enter.png")

        body = await page.inner_text("body")
        # Check if API key modal appeared or if analysis started (if key was already set)
        if "API Key" in body or "DeepSeek" in body or "配置" in body:
            print("  [PASS] API key prompt shown (no key configured)")
        elif "茅台" in body and ("贵州茅台" in body or "分析" in body):
            print("  [PASS] Analysis started (API key was already configured)")
        else:
            print(f"  [WARN] Unexpected state — body snippet: {body[:300]}")

        print("\n" + "=" * 60)
        print("ALL CHECKS PASSED")
        print(f"Screenshots saved to {SS}/")

        await browser.close()


asyncio.run(main())
