"""E2E 回归 - 验证侧边栏不再显示 "Invalid Date"。

对应 BUG #007 修复：后端迁移修复历史脏数据 + 前端 formatSessionTime 兜底。
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
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SS}/sidebar_after_fix.png", full_page=False)

        body = await page.inner_text("body")
        invalid_count = body.count("Invalid Date")
        unknown_count = body.count("未知时间")

        print(f"'Invalid Date' occurrences: {invalid_count}")
        print(f"'未知时间' occurrences (epoch fallback): {unknown_count}")

        assert invalid_count == 0, f"BUG #007 未修复：仍有 {invalid_count} 处 'Invalid Date'"
        print("[PASS] 侧边栏无 'Invalid Date'")

        await browser.close()


asyncio.run(main())
