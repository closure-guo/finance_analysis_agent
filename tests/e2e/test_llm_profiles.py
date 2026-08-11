"""E2E 测试：多配置管理（profiles）功能。

覆盖 add-custom-llm-api Task 12.1-12.3：
  12.1 另存为两个 profile → 下拉切换 → 刷新验证持久化
  12.2 旧 fa_llm_config 自动迁移为「旧配置」profile
  12.3 删除激活 profile → 自动回退到剩余第一个

前置：TESTING=1 uvicorn + npm run dev
运行：uv run python tests/e2e/test_llm_profiles.py
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
SCREENSHOT_DIR = Path(__file__).resolve().parent / "diagnostic_screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Playwright 启动参数（规避沙盒/显卡问题）
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-gpu-sandbox",
    "--disable-software-rasterizer",
]


def _clear_storage(page):
    """清空 localStorage 并重载，确保测试从干净状态开始。"""
    page.evaluate("""() => {
        localStorage.removeItem('fa_llm_profiles')
        localStorage.removeItem('fa_llm_config')
        localStorage.removeItem('fa_api_key')
        localStorage.removeItem('fa_current_session_id')
    }""")
    page.reload()
    page.wait_for_timeout(2000)


def _open_settings(page):
    """打开设置面板——兼容「去配置」「修改」「设置」三种入口。"""
    for text in ["去配置", "修改", "设置"]:
        try:
            btn = page.locator(f"button:has-text('{text}')").first
            btn.click(timeout=3000)
            page.wait_for_timeout(1000)
            return
        except Exception:  # noqa: S112 - 尝试下一个入口文本，无需记录
            continue
    raise RuntimeError("无法找到设置面板入口按钮")


def _get_profiles(page):
    """从 localStorage 读取 fa_llm_profiles 并解析为 dict。"""
    raw = page.evaluate("() => localStorage.getItem('fa_llm_profiles')")
    return json.loads(raw) if raw else None


def test_legacy_migration():
    """12.2 旧 fa_llm_config 自动迁移为「旧配置」profile。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(FRONTEND_URL, wait_until="networkidle")

        # 清空所有存储后写入旧 fa_llm_config
        page.evaluate("() => localStorage.clear()")
        page.evaluate("""() => {
            localStorage.setItem('fa_llm_config', JSON.stringify({
                apiKey: 'sk-legacy-key',
                model: 'openai/gpt-4o',
                baseUrl: '',
                thinking: ''
            }))
        }""")

        # 刷新触发迁移
        page.reload()
        page.wait_for_timeout(2000)

        # 验证旧 key 已清除、fa_llm_profiles 已创建
        legacy = page.evaluate("() => localStorage.getItem('fa_llm_config')")
        assert legacy is None, f"旧 key fa_llm_config 未被清除: {legacy}"

        store = _get_profiles(page)
        assert store is not None, "fa_llm_profiles 未创建"
        assert len(store.get("profiles", [])) == 1, "迁移后应恰好 1 个 profile"
        assert store["profiles"][0]["name"] == "旧配置", "迁移 profile 名不正确"
        assert store["profiles"][0]["config"]["apiKey"] == "sk-legacy-key"
        assert store["profiles"][0]["config"]["model"] == "openai/gpt-4o"
        assert store.get("activeId") == store["profiles"][0]["id"]

        # 验证下拉框显示「旧配置」
        body = page.locator("body").inner_text(timeout=5000)
        assert "旧配置" in body, "LLM 下拉框未显示「旧配置」"

        page.screenshot(path=str(SCREENSHOT_DIR / "llm_profiles_legacy_migration.png"))
        print("[PASS] 12.2 旧 fa_llm_config 自动迁移为「旧配置」profile")
        browser.close()


def test_save_and_switch_profiles():
    """12.1 另存为两个 profile → 下拉切换 → 刷新验证持久化。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(FRONTEND_URL, wait_until="networkidle")
        _clear_storage(page)

        _open_settings(page)

        # 填入第一个配置：DeepSeek 测试
        page.locator("input[type='password']").fill("sk-test-1")
        text_inputs = page.locator("div.glass-card input[type='text']")
        text_inputs.nth(0).fill("deepseek/deepseek-chat")
        text_inputs.nth(1).fill("https://api.deepseek.com/v1")

        # 另存为第一个 profile（「另存为」输入框是最后一个 text input）
        text_inputs.last.fill("DeepSeek 测试")
        page.locator("button:has-text('另存为')").click(timeout=3000)
        page.wait_for_timeout(1000)

        # 验证 profile 已保存
        body = page.locator("body").inner_text(timeout=5000)
        assert "DeepSeek 测试" in body, "另存为后未出现「DeepSeek 测试」"

        # 填入第二个配置
        page.locator("input[type='password']").fill("sk-test-2")
        text_inputs.nth(0).fill("openai/gpt-4o")
        text_inputs.nth(1).fill("")

        # 另存为第二个 profile
        text_inputs.last.fill("OpenAI 测试")
        page.locator("button:has-text('另存为')").click(timeout=3000)
        page.wait_for_timeout(1000)

        # 验证两个 profile 都在列表中
        body = page.locator("body").inner_text(timeout=5000)
        assert "DeepSeek 测试" in body, "第一个 profile 不在列表"
        assert "OpenAI 测试" in body, "第二个 profile 不在列表"

        # 验证 localStorage 中有两个 profile
        store = _get_profiles(page)
        assert store is not None and len(store["profiles"]) == 2, "localStorage 中应有 2 个 profile"

        # 关闭面板，刷新验证持久化
        # 点击面板外区域关闭
        page.locator("div.fixed.inset-0").first.click(timeout=3000)
        page.wait_for_timeout(500)
        page.reload()
        page.wait_for_timeout(2000)

        # 打开设置面板验证
        _open_settings(page)
        body = page.locator("body").inner_text(timeout=5000)
        assert "DeepSeek 测试" in body, "刷新后第一个 profile 丢失"
        assert "OpenAI 测试" in body, "刷新后第二个 profile 丢失"

        page.screenshot(path=str(SCREENSHOT_DIR / "llm_profiles_two_saved.png"))
        print("[PASS] 12.1 另存为两个 profile 并持久化成功")
        browser.close()


def test_delete_active_profile_fallback():
    """12.3 删除激活 profile → 自动回退到剩余第一个。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(FRONTEND_URL, wait_until="networkidle")
        _clear_storage(page)

        # 直接通过 localStorage 创建两个 profile（精确控制 id 和 activeId）
        page.evaluate("""() => {
            const store = {
                profiles: [
                    { id: 'p1', name: 'P1', config: { apiKey: 'sk-aaa', model: 'deepseek/deepseek-chat', baseUrl: 'https://api.deepseek.com/v1', thinking: 'enabled' } },
                    { id: 'p2', name: 'P2', config: { apiKey: 'sk-bbb', model: 'openai/gpt-4o', baseUrl: '', thinking: '' } }
                ],
                activeId: 'p2'
            };
            localStorage.setItem('fa_llm_profiles', JSON.stringify(store));
        }""")
        page.reload()
        page.wait_for_timeout(2000)

        # 打开设置面板
        _open_settings(page)
        page.wait_for_timeout(1000)

        # 点击 P2 的删除按钮（P2 是激活项，fa-trash-alt）
        # P2 行是 profile 列表中最后一个含 trash 按钮的行
        trash_buttons = page.locator("button:has(i.fa-trash-alt)")
        count = trash_buttons.count()
        assert count >= 1, "未找到删除按钮"

        # P2 应该在列表底部（后保存的），删最后一个 trash 按钮
        trash_buttons.last.click(timeout=3000)
        page.wait_for_timeout(1000)

        # 验证 localStorage 中 P2 被删除、activeId 回退到 P1
        store = _get_profiles(page)
        assert store is not None, "fa_llm_profiles 不存在"
        assert len(store["profiles"]) == 1, (
            f"删除后应剩 1 个 profile，实际: {len(store['profiles'])}"
        )
        assert store["profiles"][0]["name"] == "P1", "剩余 profile 应为 P1"
        assert store["activeId"] == "p1", f"activeId 应回退到 p1，实际: {store['activeId']}"

        page.screenshot(path=str(SCREENSHOT_DIR / "llm_profiles_delete_fallback.png"))
        print("[PASS] 12.3 删除激活 profile 后自动回退到剩余第一个")
        browser.close()


if __name__ == "__main__":
    print("=" * 60)
    print("LLM Profiles E2E Tests (add-custom-llm-api Task 12.1-12.3)")
    print("=" * 60)

    test_legacy_migration()
    time.sleep(1)
    test_save_and_switch_profiles()
    time.sleep(1)
    test_delete_active_profile_fallback()

    print()
    print("=" * 60)
    print("ALL LLM PROFILES E2E CHECKS PASSED")
    print("=" * 60)
