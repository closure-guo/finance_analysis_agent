"""E2E test — diagnose frontend interaction issues with screenshots."""

import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
SCREENSHOT_DIR = "tests/e2e/diagnostic_screenshots"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        print("=" * 60)
        print("Step 1: Load page")
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.screenshot(path=f"{SCREENSHOT_DIR}/01_loaded.png")
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")

        # Check what's on the page
        body_text = await page.inner_text("body")
        print(f"  Body text (first 500): {body_text[:500]}")

        # Check for input field
        inputs = await page.query_selector_all("input, textarea")
        print(f"  Input fields: {len(inputs)}")
        for i, inp in enumerate(inputs):
            placeholder = await inp.get_attribute("placeholder")
            print(f"    [{i}] placeholder={placeholder}")

        # Check for buttons
        buttons = await page.query_selector_all("button")
        print(f"  Buttons: {len(buttons)}")
        for i, btn in enumerate(buttons):
            text = await btn.inner_text()
            print(f"    [{i}] text={text}")

        print("\n" + "=" * 60)
        print("Step 2: Check API key modal")
        # Check if API key modal is visible
        api_key_input = await page.query_selector(
            "input[placeholder*='API'], input[type='password']"
        )
        if api_key_input:
            print("  API key input found — need to enter key first")
            await api_key_input.fill("test-key")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/02_api_key.png")
        else:
            print("  No API key input found")

        print("\n" + "=" * 60)
        print("Step 3: Find and click mode buttons")
        # Look for mode toggle buttons
        all_elements = await page.query_selector_all("*")
        mode_related = []
        for el in all_elements:
            text = await el.inner_text()
            if any(
                kw in text for kw in ["快速模式", "深度研究", "快速分析", "深度报告", "同业对比"]
            ):
                tag = await el.evaluate("el => el.tagName")
                if tag in ["BUTTON", "DIV", "SPAN"]:
                    mode_related.append((el, text.strip()[:30], tag))

        print(f"  Mode-related elements: {len(mode_related)}")
        for _el, text, tag in mode_related[:10]:
            print(f"    <{tag}> {text}")

        print("\n" + "=" * 60)
        print("Step 4: Try clicking '快速模式' button")
        quick_btn = None
        for el, text, _tag in mode_related:
            if "快速" in text:
                quick_btn = el
                break

        if quick_btn:
            await quick_btn.click()
            await page.wait_for_timeout(500)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/03_after_quick_click.png")
            print("  Clicked '快速模式' button")

            # Check if anything changed
            body_text_after = await page.inner_text("body")
            if body_text_after != body_text:
                print("  Page content changed after click")
            else:
                print("  Page content did NOT change after click")
        else:
            print("  '快速模式' button not found")

        print("\n" + "=" * 60)
        print("Step 5: Try typing in input and submitting")
        # Find the main input
        main_input = None
        for inp in inputs:
            ph = await inp.get_attribute("placeholder") or ""
            if "股票" in ph or "代码" in ph or "输入" in ph:
                main_input = inp
                break

        if main_input:
            await main_input.fill("茅台")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/04_typed.png")
            print("  Typed '茅台' in input")

            # Try pressing Enter
            await main_input.press("Enter")
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/05_after_enter.png")
            print("  Pressed Enter")

            # Check what happened
            body_after = await page.inner_text("body")
            if len(body_after) > len(body_text) + 50:
                print(
                    f"  Content grew by {len(body_after) - len(body_text)} chars — something happened"
                )
            else:
                print("  No significant content change after Enter")
        else:
            print("  Main input not found")

        print("\n" + "=" * 60)
        print("Step 6: Check for JS console errors")
        page.on("console", lambda msg: print(f"  CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"  PAGE ERROR: {err}"))
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/06_after_reload.png")

        await browser.close()
        print("\nDone — screenshots saved to", SCREENSHOT_DIR)


asyncio.run(main())
