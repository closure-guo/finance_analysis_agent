"""E2E: ReAct search via frontend Playwright.

Previously this test directly called POST /api/analyze, which is an integration
 test, not an E2E test. This version drives the browser like a real user:
 - configures API key if not persisted
 - selects deep mode
 - enters a fuzzy query
 - waits for stock resolution / analysis start
 - asserts that the conversation transitions out of empty state.
"""

import os
import time

import pytest

API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
BASE_URL = "http://127.0.0.1:5173"


def _configure_api_key(page):
    """Open settings modal and fill the API key if not already persisted."""
    if page.locator("button").filter(has_text="去配置").count() > 0:
        page.locator("button").filter(has_text="去配置").first.click(timeout=5000)
    else:
        page.locator("button").filter(has_text="设置").first.click(timeout=5000)
    page.locator("input[type='password']").fill(API_KEY)
    page.locator("button").filter(has_text="确认").first.click(timeout=5000)
    page.wait_for_timeout(300)


def test_react_search(browser):
    if not API_KEY:
        pytest.skip("LLM_API_KEY / DEEPSEEK_API_KEY not set")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)

        # 1. Configure API key if needed
        body = page.locator("body").inner_text(timeout=3000)
        if "LLM API 已配置" not in body:
            _configure_api_key(page)

        # 2. Select deep mode (if not already)
        if "深度研究" not in body:
            page.locator("button").filter(has_text="模式").first.click(timeout=3000)
            page.wait_for_timeout(200)
        page.locator("button").filter(has_text="深度研究").first.click(timeout=3000)
        page.wait_for_timeout(200)

        # 3. Enter fuzzy query and submit
        textarea = page.locator("textarea").first
        textarea.fill("分析一下光模块龙头企业")
        page.wait_for_timeout(300)
        textarea.press("Enter")

        # 4. Wait for stock resolution / analysis start (up to 120s because ReAct may
        #    search and then start the deep pipeline; no real LLM mock here).
        deadline = time.time() + 120
        resolved = False
        while time.time() < deadline:
            body = page.locator("body").inner_text(timeout=3000)
            if (
                "开始分析" in body
                or "已识别" in body
                or "深度分析进行中" in body
                or "正在识别" in body
            ):
                resolved = True
                break
            if "错误" in body or "连接错误" in body:
                raise AssertionError(f"UI showed error: {body[:500]}")
            time.sleep(1)

        assert resolved, "UI did not transition to analysis/clarification within 120s"
    finally:
        context.close()
