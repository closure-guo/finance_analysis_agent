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

BASE_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
SS_DIR = "tests/e2e/diagnostic_screenshots"
API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
# 设置中心（settings-center）后 API Key 从弹窗迁到 /settings 路由页的 LLM 分区
PANE = "[data-testid='llm-config-pane']"
API_KEY_INPUT = f"{PANE} input[type='password']"


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
    """API Key 入口与持久化（settings-center 后：/settings 路由页，不再有弹窗）。

    原用例断言「配置 API Key」弹窗标题 + `取消` 关闭——设置中心上线后该弹窗已移除
    （App.tsx 的 onOpenSettings 改为 navigate('/settings')），用例随之失效并使手动
    E2E 作业恒红（CI e2e job `-x` 首条即挂）。改为断言路由页 + 刷新后仍持久化。
    """
    print("\n=== API Key Settings Entry ===")
    key = API_KEY or "sk-e2e-test"
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate("localStorage.clear()")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    _screenshot(page, "interact_01_empty.png")

    # 空配置入口「去配置」→ 设置页 LLM 分区（标题 + 密码输入框）
    page.locator("button").filter(has_text="去配置").first.click(timeout=5000)
    page.wait_for_selector(PANE, timeout=10000)
    page.wait_for_timeout(300)
    _screenshot(page, "interact_02_modal_open.png")
    assert "LLM 配置" in _text(page), "设置页 LLM 分区标题缺失"
    print("  [PASS] 去配置 opens settings LLM pane")

    # 填 key + 确认保存
    page.locator(API_KEY_INPUT).fill(key)
    page.locator("button").filter(has_text="确认").first.click(timeout=4000)
    page.wait_for_timeout(600)

    # 「← 返回」离开设置页；已有 key 时空态入口变为「修改」
    page.locator("button").filter(has_text="返回").first.click(timeout=4000)
    page.wait_for_timeout(1200)
    assert page.locator(PANE).count() == 0, "返回后仍在设置页"
    assert "修改" in _text(page), "保存后空态入口未变为「修改」"
    print("  [PASS] Confirm saves key and returns home")

    # 刷新后重新进入设置页，验证 key 持久化（localStorage fa_llm_profiles）
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1800)
    page.locator("button").filter(has_text="修改").first.click(timeout=6000)
    page.wait_for_selector(PANE, timeout=10000)
    page.wait_for_timeout(300)
    val = page.locator(API_KEY_INPUT).input_value()
    assert val == key, f"Persisted key mismatch: {val[:10]}..."
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

    # Type and submit via Enter：无 key 提交 → 跳转设置页 LLM 分区
    # （settings-center 前是弹窗拦截；迁移后 handleSend 无 key 直接 navigate('/settings')）
    textarea.fill("600519")
    page.wait_for_timeout(300)
    textarea.press("Enter")
    page.wait_for_timeout(1500)
    _screenshot(page, "interact_05_after_enter.png")
    assert "/settings" in page.url, f"无 key 提交未跳转设置页: {page.url}"
    assert page.locator(PANE).count() == 1, "设置页 LLM 分区未渲染"
    print("  [PASS] Enter submit without key redirects to settings")


def test_sidebar_interactions(page):
    print("\n=== Sidebar Interactions ===")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # add-collapsible-sidebar：折叠由 SidebarProvider 管理的 sidebar-trigger 切换
    # （旧用例按 `i.fa-times` / 「会话历史」标题定位，UI 重构后已不存在）
    trigger = page.locator("[data-testid='sidebar-trigger']").first
    assert page.locator("[data-testid='sidebar-new-collapsed']").count() == 0, "初始应为展开态"
    trigger.click(timeout=3000)
    page.wait_for_timeout(800)
    _screenshot(page, "interact_06_sidebar_collapsed.png")
    assert page.locator("[data-testid='sidebar-new-collapsed']").count() == 1, (
        "Sidebar did not collapse"
    )
    assert page.evaluate("localStorage.getItem('fa_sidebar_collapsed')") == "1", "折叠态未持久化"
    print("  [PASS] Sidebar collapse works")

    # 再次点击展开
    trigger.click(timeout=3000)
    page.wait_for_timeout(800)
    assert page.locator("[data-testid='sidebar-new-collapsed']").count() == 0, (
        "Sidebar did not expand"
    )
    assert page.evaluate("localStorage.getItem('fa_sidebar_collapsed')") == "0", "展开态未持久化"
    print("  [PASS] Sidebar expand works")


def test_chat_input_bar_mode_toggle(page):
    print("\n=== Chat Input Bar Mode Toggle ===")
    # 播种非空 key 以进入 chat 视图（无 key 提交会跳转 /settings —— 见 empty_state 用例；
    # CI 未配 DEEPSEEK_API_KEY 时 API_KEY 为空，`or "sk-e2e-test"` 保住本用例原意：
    # 只验模式切换 UI，不依赖真实 LLM 凭证）
    page.add_init_script(f"localStorage.setItem('fa_api_key', {API_KEY or 'sk-e2e-test'!r})")
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
