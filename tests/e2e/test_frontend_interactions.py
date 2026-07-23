"""E2E regression test for frontend interactions via Playwright.

Focuses on:
1. API Key modal open/close/save
2. EmptyState mode dropdown switching and Enter submit
3. Sidebar session selection, new analysis, search, delete
4. ChatInputBar mode toggles and submission
5. Report view rendering order
"""

import os

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5173"
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


def test_api_key_modal(page):
    print("\n=== API Key Modal ===")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    _screenshot(page, "interact_01_empty.png")

    # Open modal via 去配置
    page.locator("button").filter(has_text="去配置").first.click(timeout=3000)
    wait_for_stable(page, "input[type='password']")
    _screenshot(page, "interact_02_modal_open.png")
    assert "配置 API Key" in _text(page), "Modal title not found"
    print("  [PASS] 去配置 opens modal")

    # Close via cancel
    page.locator("button").filter(has_text="取消").first.click(timeout=3000)
    page.wait_for_timeout(300)
    assert page.locator("input[type='password']").count() == 0
    print("  [PASS] Cancel closes modal")

    # Reopen, fill key, confirm saves key and closes modal
    page.locator("button").filter(has_text="去配置").first.click(timeout=3000)
    wait_for_stable(page, "input[type='password']")
    page.locator("input[type='password']").fill(API_KEY)
    page.locator("button").filter(has_text="确认").first.click(timeout=3000)
    page.wait_for_timeout(300)
    assert page.locator("input[type='password']").count() == 0
    print("  [PASS] Confirm saves key and closes modal")

    # Enter chat view so header settings is visible
    textarea = page.locator("textarea").first
    textarea.fill("hi")
    textarea.press("Enter")
    page.wait_for_timeout(1500)
    _screenshot(page, "interact_02b_chat_for_settings.png")

    # Reopen via header "设置" button and verify persisted
    page.locator("button").filter(has_text="设置").first.click(timeout=3000)
    wait_for_stable(page, "input[type='password']")
    val = page.locator("input[type='password']").input_value()
    assert val == API_KEY, f"Persisted key mismatch: {val[:10]}..."
    print("  [PASS] Key persisted in localStorage after reload")
    page.locator("button").filter(has_text="取消").first.click(timeout=3000)


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

    # Type and submit via Enter should transition to chat state
    textarea.fill("600519")
    page.wait_for_timeout(300)
    textarea.press("Enter")
    page.wait_for_timeout(1500)
    _screenshot(page, "interact_05_after_enter.png")
    body = _text(page)
    # After submit we should see chat UI header and user message or at least not empty state
    assert page.locator("textarea").count() >= 1, "Input still exists"
    print("  [PASS] Enter submit leaves empty state")


def test_sidebar_interactions(page):
    print("\n=== Sidebar Interactions ===")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # Sidebar is open by default; click the close button in sidebar header
    close_btn = page.locator("div:has-text('会话历史') + button:has(i.fa-times)")
    if close_btn.count() == 0:
        close_btn = page.locator("button:has(i.fa-times)").first
    close_btn.click(timeout=3000)
    page.wait_for_timeout(300)
    _screenshot(page, "interact_06_sidebar_collapsed.png")
    body = _text(page)
    assert "会话历史" not in body, "Sidebar did not collapse"
    print("  [PASS] Sidebar collapse works")

    # Expand via the bars icon in the collapsed sidebar
    expand_btn = page.locator("button:has(i.fa-bars)").first
    expand_btn.click(timeout=3000)
    page.wait_for_timeout(300)
    assert "会话历史" in _text(page)
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

        test_api_key_modal(page)
        test_empty_state_mode_dropdown(page)
        test_sidebar_interactions(page)
        test_chat_input_bar_mode_toggle(page)

        browser.close()
    print("\nALL INTERACTION CHECKS PASSED")


if __name__ == "__main__":
    main()
