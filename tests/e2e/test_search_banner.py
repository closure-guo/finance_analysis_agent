"""E2E 测试：搜索横幅在快速模式中的渲染。

前置条件：后端运行在 http://localhost:8000，前端运行在 http://localhost:5173。
禁止使用 mock 数据，通过前端模拟用户真实输入验证完整链路。
"""


def test_quick_mode_search_banner_visible(page):
    """快速模式下搜索横幅可见且可展开。"""
    page.goto("http://localhost:5173")
    page.wait_for_selector("textarea")

    # 切换到快速模式
    page.click("button:has-text('模式')")
    page.click("button:has-text('快速模式')")

    # 输入问题并发送
    page.fill("textarea", "茅台怎么样")
    page.press("textarea", "Enter")

    # 等待搜索横幅出现（正在搜索 或 搜索了 N 个网页）
    page.wait_for_selector("text=/正在搜索|搜索了/", timeout=30000)

    # 验证搜索横幅可见
    banner = page.locator("text=/正在搜索|搜索了/")
    assert banner.is_visible()


def test_quick_mode_search_banner_expandable(page):
    """快速模式搜索完成后可展开查看结果列表。"""
    page.goto("http://localhost:5173")
    page.wait_for_selector("textarea")

    # 切换到快速模式
    page.click("button:has-text('模式')")
    page.click("button:has-text('快速模式')")

    # 输入问题并发送
    page.fill("textarea", "宁德时代怎么样")
    page.press("textarea", "Enter")

    # 等待搜索完成
    page.wait_for_selector("text=/搜索了/", timeout=30000)

    # 点击展开搜索横幅
    page.click("text=/搜索了/")

    # 验证结果列表可见（至少出现一个结果链接）
    page.wait_for_selector("a[href*='http']", timeout=5000)
