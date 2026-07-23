"""验证：报告卡片不再置顶（应位于首条用户消息之后），并回归模式下拉框。"""

import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
SS = "tests/e2e/diagnostic_screenshots"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SS}/verify_01_empty.png")

        # 回归：模式下拉框可打开且浮在最上层
        await page.locator("button:has-text('深度研究')").first.click()
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SS}/verify_02_dropdown.png")
        body = await page.inner_text("body")
        assert "单次 LLM + Web Search" in body, "dropdown content not visible on top"
        print("[PASS] 下拉框仍可正常打开并置顶")
        await page.locator("body").click(position={"x": 600, "y": 400})
        await page.wait_for_timeout(200)

        # 打开置顶验证会话
        target = page.locator("text=置顶验证-茅台")
        await target.first.click()
        await page.wait_for_timeout(800)
        await page.screenshot(path=f"{SS}/verify_03_session.png", full_page=True)

        # 取所有消息卡片的文本顺序
        msgs = await page.locator("div.flex.justify-start, div.flex.justify-end").all_inner_texts()
        joined = "\n".join(msgs)
        print("=== 渲染顺序 ===")
        for i, m in enumerate(msgs):
            snippet = " ".join(m.split())[:60]
            print(f"  [{i}] {snippet}")

        # 断言：用户问题出现在报告之前（报告不再置顶）
        user_idx = joined.find("茅台怎么样")
        report_idx = joined.find("贵州茅台深度分析报告")
        assert user_idx != -1, "用户问题未找到"
        assert report_idx != -1, "报告卡片未找到"
        assert user_idx < report_idx, f"报告仍置顶！user_idx={user_idx} report_idx={report_idx}"
        print("[PASS] 用户问题在报告之前，报告不再置顶")

        # 断言：报告出现在第一条 assistant 摘要之前（贴近触发问题）
        summary_idx = joined.find("已为你生成贵州茅台深度分析报告")
        assert report_idx < summary_idx, "报告应在首条摘要之前"
        print("[PASS] 报告紧随触发问题，顺序符合实时分析流程")

        print("\nALL PASSED")
        await browser.close()


asyncio.run(main())
