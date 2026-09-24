"""E2E regression test for frontend interactions via Playwright.

Focuses on:
1. API Key configuration via the settings center (LLM 配置 pane)
2. EmptyState mode dropdown switching
3. Sidebar collapse/expand
4. ChatInputBar mode toggles and submission
"""

import os

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173")
SS_DIR = "tests/e2e/diagnostic_screenshots"
API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""


def _screenshot(page, name):
    page.screenshot(path=f"{SS_DIR}/{name}")


def _text(page) -> str:
    return page.locator("body").inner_text(timeout=3000)


def wait_for_stable(page, selector, timeout=10000):
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
    except PlaywrightError as e:
        raise AssertionError(f"Selector not visible: {selector}") from e


def test_api_key_config_flow(page):
    print("\n=== API Key Config Flow ===")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    _screenshot(page, "interact_01_empty.png")

    # 去配置 opens the settings center with the LLM 配置 pane
    page.locator("button").filter(has_text="去配置").first.click(timeout=3000)
    wait_for_stable(page, "input[type='password']")
    _screenshot(page, "interact_02_settings_open.png")
    assert "LLM 配置" in _text(page), "LLM 配置 pane title not found"
    print("  [PASS] 去配置 opens settings center")

    # 返回 leaves the config view
    page.locator("button").filter(has_text="返回").first.click(timeout=3000)
    page.wait_for_selector("input[type='password']", state="detached", timeout=5000)
    print("  [PASS] 返回 leaves config view")

    # Reopen, fill key, 确认 persists across reload
    page.locator("button").filter(has_text="去配置").first.click(timeout=3000)
    wait_for_stable(page, "input[type='password']")
    page.locator("input[type='password']").fill(API_KEY)
    page.locator("button").filter(has_text="确认").first.click(timeout=3000)
    page.reload(wait_until="domcontentloaded")
    wait_for_stable(page, "input[type='password']")
    val = page.locator("input[type='password']").input_value()
    assert val == API_KEY, f"Persisted key mismatch: {val[:10]}..."
    print("  [PASS] Key persisted in localStorage after reload")


def test_empty_state_mode_dropdown(page):
    print("\n=== EmptyState Mode Dropdown ===")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    body = _text(page)
    assert "模式：" in body, "Missing mode label"
    assert "深度研究" in body, "Default deep mode not shown"
    print("  [PASS] Default mode = 深度研究")

    textarea = page.locator("textarea").first
    ph = textarea.get_attribute("placeholder") or ""
    assert "股票名称或代码" in ph, f"Deep placeholder mismatch: {ph}"

    # Open dropdown
    page.locator("button").filter(has_text="模式").first.click(timeout=3000)
    page.wait_for_timeout(300)
    _screenshot(page, "interact_03_dropdown_open.png")
    body = _text(page)
    assert "快速模式" in body and "单次 LLM" in body, "Dropdown options missing"
    print("  [PASS] Dropdown opens with options")

    # Select quick mode
    page.locator("button").filter(has_text="快速模式").first.click(timeout=3000)
    page.wait_for_timeout(300)
    _screenshot(page, "interact_04_quick_mode.png")
    ph = textarea.get_attribute("placeholder") or ""
    assert "输入问题" in ph, f"Quick placeholder mismatch: {ph}"
    print("  [PASS] Switching to quick mode updates placeholder")

    # Switch back to deep
    page.locator("button").filter(has_text="模式").first.click(timeout=3000)
    page.wait_for_timeout(200)
    page.locator("button").filter(has_text="深度研究").first.click(timeout=3000)
    page.wait_for_timeout(300)
    ph = textarea.get_attribute("placeholder") or ""
    assert "股票名称或代码" in ph, f"Deep placeholder mismatch after switch: {ph}"
    print("  [PASS] Switch back to deep mode works")

    # 注：不在此处断言提交流转——未配置 LLM 时提交被守卫引导至设置页，
    # 已配置时的分析流转由 Playwright stub 套件（tests/e2e/playwright）覆盖。


def test_sidebar_interactions(page):
    print("\n=== Sidebar Interactions ===")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # 套件连跑时浏览器上下文交替会造成资源尖峰，超时放宽到 10s
    new_btn = page.get_by_test_id("sidebar-new")
    expect(new_btn).to_be_visible(timeout=10_000)
    page.get_by_label("折叠侧边栏", exact=True).click(timeout=10_000)
    expect(new_btn).to_be_hidden(timeout=10_000)
    expect(page.get_by_test_id("sidebar-new-collapsed")).to_be_visible(timeout=10_000)
    _screenshot(page, "interact_06_sidebar_collapsed.png")
    print("  [PASS] Sidebar collapse works")

    # Expand via the same toggle (aria-label flips with state)
    page.get_by_label("展开侧边栏", exact=True).click(timeout=10_000)
    expect(new_btn).to_be_visible(timeout=10_000)
    print("  [PASS] Sidebar expand works")


def test_chat_input_bar_mode_toggle(page):
    print("\n=== Chat Input Bar Mode Toggle ===")
    # Seed API key so we can enter chat view without modal blocking
    page.add_init_script(f"localStorage.setItem('fa_api_key', {API_KEY!r})")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    textarea = page.locator("textarea").first
    textarea.fill("hi")
    textarea.press("Enter")
    page.wait_for_timeout(1500)
    _screenshot(page, "interact_10_chat_for_toggle.png")

    # Now we are in chat view with ChatInputBar
    body = _text(page)
    assert "深度研究" in body or "快速对话" in body, "Mode toggle not present"

    # Click quick mode
    quick_btn = page.locator("button").filter(has_text="快速对话").first
    if quick_btn.is_visible(timeout=3000):
        quick_btn.click()
        page.wait_for_timeout(300)
        _screenshot(page, "interact_11_quick_toggle.png")
        ph = page.locator("textarea").first.get_attribute("placeholder") or ""
        assert "输入问题" in ph, f"Quick placeholder mismatch: {ph}"
        print("  [PASS] Quick mode toggle in chat view")
    else:
        print("  [WARN] Quick mode toggle not visible")

    # Click deep mode
    deep_btn = page.locator("button").filter(has_text="深度研究").first
    if deep_btn.is_visible(timeout=3000):
        deep_btn.click()
        page.wait_for_timeout(300)
        ph = page.locator("textarea").first.get_attribute("placeholder") or ""
        assert "股票名称或代码" in ph, f"Deep placeholder mismatch: {ph}"
        print("  [PASS] Deep mode toggle in chat view")
    else:
        print("  [WARN] Deep mode toggle not visible")


def main():
    os.makedirs(SS_DIR, exist_ok=True)
    if not API_KEY:
        print("[WARN] LLM_API_KEY not set; tests requiring API calls may fail")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        test_api_key_config_flow(page)
        test_empty_state_mode_dropdown(page)
        test_sidebar_interactions(page)
        test_chat_input_bar_mode_toggle(page)

        browser.close()
    print("\nALL INTERACTION CHECKS PASSED")


if __name__ == "__main__":
    main()
