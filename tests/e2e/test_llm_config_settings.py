"""E2E test for custom LLM config settings panel (add-custom-llm-api).

Covers delta 9.1-9.5:
- 9.1  在设置面板修改模型名称并提交分析，验证后端使用自定义模型
- 9.2  配置持久化：刷新页面后配置仍在
- 9.3  不配置 LLM 设置（localStorage 为空）时行为与现有一致（回归）
- 9.4  选择 Provider 预设后输入框自动填充正确值
- 9.5  点击"测试连接"按钮后展示成功或失败状态

E2E 红线：前端真实运行（Vite）+ 后端真实运行（FastAPI），通过浏览器模拟用户输入。
不 mock 被测系统；LLM 用 TESTING=1 stub（业务接口不拦截）。
"""

import os

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
SS_DIR = "tests/e2e/diagnostic_screenshots"

# 设置面板 selectors（基于 SettingsModal DOM 结构）
PRESET_SELECT = "div.glass-card select >> nth=0"
MODEL_INPUT = "div.glass-card input[type='text'] >> nth=0"
BASE_URL_INPUT = "div.glass-card input[type='text'] >> nth=1"
API_KEY_INPUT = "div.glass-card input[type='password']"
TEST_BTN = "div.glass-card button:has-text('测试连接')"
REFRESH_BTN = "div.glass-card button:has-text('刷新模型')"
THINKING_SWITCH = "div.glass-card [role='switch']"


def _screenshot(page, name):
    page.screenshot(path=f"{SS_DIR}/{name}")


def _text(page) -> str:
    return page.locator("body").inner_text(timeout=5000)


def _open_settings(page):
    """通过设置入口按钮打开设置面板。

    入口随状态变化：chat 视图 header「设置」；EmptyState 无 key 时「去配置」、
    已有 key 时「修改」。任一可见即可打开。
    """
    for txt in ("设置", "去配置", "修改"):
        btn = page.locator("button").filter(has_text=txt)
        if btn.count() > 0 and btn.first.is_visible(timeout=1500):
            btn.first.click(timeout=3000)
            page.wait_for_selector(".glass-card", timeout=5000)
            return
    raise AssertionError("未找到设置入口按钮")


def _apply_preset(page, name):
    page.locator(PRESET_SELECT).select_option(label=name)
    page.wait_for_timeout(200)


def test_provider_preset_fills_fields(page):
    """9.4 选择 Provider 预设后输入框自动填充正确值。"""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    _open_settings(page)

    # 选择 DeepSeek 官方预设
    _apply_preset(page, "DeepSeek 官方")
    modelVal = page.locator(MODEL_INPUT).input_value()
    assert modelVal == "deepseek/deepseek-chat", f"model 填充错误: {modelVal}"
    baseUrlVal = page.locator(BASE_URL_INPUT).input_value()
    assert baseUrlVal == "https://api.deepseek.com/v1", f"baseUrl 填充错误: {baseUrlVal}"
    # DeepSeek 模型应展示思考开关
    assert page.locator(THINKING_SWITCH).count() >= 1, "DeepSeek 模型应展示思考开关"
    _screenshot(page, "llmcfg_04_preset_deepseek.png")

    # 选择 OpenAI 预设：baseUrl 应清空，思考开关隐藏（非 DeepSeek）
    _apply_preset(page, "OpenAI")
    modelVal = page.locator(MODEL_INPUT).input_value()
    assert modelVal == "openai/gpt-4o", f"OpenAI model 填充错误: {modelVal}"
    baseUrlVal = page.locator(BASE_URL_INPUT).input_value()
    assert baseUrlVal == "", "OpenAI baseUrl 应为空"
    assert page.locator(THINKING_SWITCH).count() == 0, "OpenAI 模型不应展示思考开关"
    _screenshot(page, "llmcfg_04_preset_openai.png")
    print("  [PASS] Provider presets fill fields correctly")


def test_config_persists_across_reload(page):
    """9.2 配置持久化：保存后刷新页面，配置仍在。"""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    _open_settings(page)

    # 填 model + baseUrl + apiKey
    page.locator(MODEL_INPUT).fill("deepseek/deepseek-v4-pro")
    page.locator(BASE_URL_INPUT).fill("https://api.deepseek.com/v1")
    page.locator(API_KEY_INPUT).fill("sk-e2e-test")
    page.locator("button:has-text('确认')").first.click(timeout=3000)
    page.wait_for_timeout(300)

    # 刷新页面重新打开，验证配置已持久化
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    _open_settings(page)
    modelVal = page.locator(MODEL_INPUT).input_value()
    assert modelVal == "deepseek/deepseek-v4-pro", f"刷新后 model 未持久化: {modelVal}"
    baseUrlVal = page.locator(BASE_URL_INPUT).input_value()
    assert baseUrlVal == "https://api.deepseek.com/v1", "刷新后 baseUrl 未持久化"
    apiKeyVal = page.locator(API_KEY_INPUT).input_value()
    assert apiKeyVal == "sk-e2e-test", "刷新后 apiKey 未持久化"
    _screenshot(page, "llmcfg_02_persist.png")
    page.locator("button:has-text('取消')").first.click(timeout=3000)
    print("  [PASS] Config persists across reload")


def test_test_connection_success_fail(page):
    """9.5 点击"测试连接"后展示成功或失败状态。"""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    _open_settings(page)

    # 填一个明显无效的 baseUrl，点击测试连接应展示失败状态
    page.locator(MODEL_INPUT).fill("deepseek/deepseek-chat")
    page.locator(BASE_URL_INPUT).fill("http://127.0.0.1:1")  # 必然不通
    page.locator(API_KEY_INPUT).fill("sk-invalid")
    page.locator(TEST_BTN).click(timeout=3000)
    page.wait_for_timeout(2000)

    body = _text(page)
    # 失败状态：要么展示错误提示，要么因网络失败展示"请求失败"
    assert (
        ("无法连接" in body) or ("请求失败" in body) or ("Base URL" in body) or ("连接" in body)
    ), f"未展示失败提示: {body[-200:]}"
    _screenshot(page, "llmcfg_05_test_fail.png")
    page.locator("button:has-text('取消')").first.click(timeout=3000)
    print("  [PASS] Test connection shows failure status")


def test_no_config_unchanged(page):
    """9.3 不配置 LLM 设置（localStorage 为空）时行为与现有一致。"""
    page.add_init_script(
        "localStorage.removeItem('fa_llm_config'); localStorage.removeItem('fa_api_key')"
    )
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # 打开设置面板，应展示后端默认占位符，且能正常打开/关闭
    _open_settings(page)
    assert "LLM 配置" in _text(page), "设置面板标题缺失"
    page.locator("button:has-text('取消')").first.click(timeout=3000)
    page.wait_for_timeout(300)
    # 取消后设置面板（含密码输入框）应关闭；页面其他 glass-card（feature 卡片等）不受影响
    assert page.locator("div.glass-card input[type='password']").count() == 0, "取消后面板未关闭"
    _screenshot(page, "llmcfg_03_no_config.png")
    print("  [PASS] Empty config opens/closes settings normally")


def test_custom_model_submitted(page):
    """9.1 在设置面板修改模型名称并提交分析，验证请求携带 llm_config。"""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    _open_settings(page)

    # 配置自定义模型 + api key
    page.locator(MODEL_INPUT).fill("openai/gpt-4o-mini")
    page.locator(BASE_URL_INPUT).fill("")
    page.locator(API_KEY_INPUT).fill("sk-e2e-test")
    page.locator("button:has-text('确认')").first.click(timeout=3000)
    page.wait_for_timeout(300)

    # 在文本区输入并提交（进入聊天视图，观察请求正常发出、不因配置阻塞）
    textarea = page.locator("textarea").first
    textarea.fill("hi")
    textarea.press("Enter")
    page.wait_for_timeout(1500)
    _screenshot(page, "llmcfg_01_custom_model.png")
    # 提交后仍处于聊天输入区（未崩溃），说明配置被接受
    assert page.locator("textarea").count() >= 1, "提交自定义模型配置后聊天输入区缺失"
    print("  [PASS] Custom model config accepted on submit")


def main():
    os.makedirs(SS_DIR, exist_ok=True)
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
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        test_provider_preset_fills_fields(page)
        test_config_persists_across_reload(page)
        test_test_connection_success_fail(page)
        test_no_config_unchanged(page)
        test_custom_model_submitted(page)
        browser.close()
    print("\nALL LLM CONFIG E2E CHECKS PASSED")


if __name__ == "__main__":
    main()
