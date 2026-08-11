"""手动验证脚本：确认修复后 baseUrl 改变会导致模型发现结果变化。

验证 bug 修复：修复前端发 snake_case 被后端忽略、永远回退环境变量的问题。
改 baseUrl 为不存在的端点，刷新模型应返回错误而非固定的环境变量端点模型列表。
"""

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5173"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-software-rasterizer",
            ],
        )
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # 打开设置面板
        for txt in ("设置", "去配置", "修改"):
            btn = page.locator("button").filter(has_text=txt)
            if btn.count() > 0 and btn.first.is_visible(timeout=1500):
                btn.first.click(timeout=3000)
                break
        page.wait_for_selector(".glass-card", timeout=5000)

        # 改 baseUrl 为不存在的端点，apiKey 清空
        page.locator("div.glass-card input[type='text'] >> nth=1").fill("http://127.0.0.1:9999/v1")
        page.locator("div.glass-card input[type='password']").fill("")
        page.locator("button:has-text('刷新模型')").click(timeout=3000)
        page.wait_for_timeout(2500)

        body = page.locator("body").inner_text(timeout=5000)
        # 修复后：baseUrl 透传，本地不存在端点应返回连接失败错误（后端透传 error 原文）
        # 修复前：baseUrl 被忽略，永远回退环境变量端点，返回固定模型列表
        assert (
            "ConnectError" in body
            or "connection attempts failed" in body
            or "连接超时" in body
            or "无法连接" in body
            or "不支持模型自动发现" in body
        ), f"期望看到连接失败提示（证明 baseUrl 已透传），实际: {body[-300:]}"
        assert "发现 25 个可用模型" not in body, (
            "BUG 未修复：仍返回固定 25 个模型（baseUrl 未透传）"
        )
        page.screenshot(path="tests/e2e/diagnostic_screenshots/llmcfg_baseurl_fix_verify.png")
        print("[PASS] baseUrl 改变后模型发现不再返回固定 25 个模型（baseUrl 已正确透传）")

        # 决策 A：清空 baseUrl（自定义预设场景），刷新模型应提示配置，而非回退环境变量拉模型
        page.locator("div.glass-card input[type='text'] >> nth=1").fill("")
        page.locator("button:has-text('刷新模型')").click(timeout=3000)
        page.wait_for_timeout(2500)
        body2 = page.locator("body").inner_text(timeout=5000)
        assert "请先配置 API Base URL" in body2 or "请先配置" in body2, (
            f"决策 A 失败：空 baseUrl 应提示配置，实际: {body2[-300:]}"
        )
        assert "发现 25 个可用模型" not in body2, "决策 A 失败：空 baseUrl 仍回退环境变量拉取模型"
        page.screenshot(path="tests/e2e/diagnostic_screenshots/llmcfg_empty_baseurl_verify.png")
        print("[PASS] 决策 A：空 baseUrl 刷新模型提示配置，不回退环境变量")
        browser.close()


if __name__ == "__main__":
    main()
