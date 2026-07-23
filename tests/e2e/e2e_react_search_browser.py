"""E2E 测试: 通过前端浏览器模拟用户输入"光模块龙头企业"。

按 project_rules.md E2E 约束：
  - 使用真实前端（Vite 5173）+ 真实后端（FastAPI 8080）
  - 通过 Playwright 模拟用户在浏览器中的真实操作（输入、点击、等待渲染）
  - 验证从前端 UI 到后端 ReAct 循环的完整链路

前置条件：
  - 后端运行在 http://127.0.0.1:8080
  - 前端运行在 http://127.0.0.1:5173
  - 环境变量 LLM_API_KEY 或 DEEPSEEK_API_KEY 已设置

运行方式：
  uv run python tests/e2e/e2e_react_search_browser.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
SCREENSHOT_DIR = Path(__file__).parent
# ReAct 循环（搜索 + 决策）应在 60s 内完成
REACT_TIMEOUT = 120


def _resolve_api_key() -> str:
    return os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""


def _screenshot(page, name: str) -> None:
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path), full_page=False)
    print(f"  截图: {path}")


def main() -> bool:
    api_key = _resolve_api_key()
    if not api_key:
        print("[FAIL] 未找到 API Key")
        return False

    SCREENSHOT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 2000})

        # ── 1. 打开前端页面 ──
        print("[1/6] 打开前端页面...")
        page.goto(FRONTEND_URL, timeout=30000)
        time.sleep(1)
        _screenshot(page, "01_react_initial.png")

        # ── 2. 配置 API Key ──
        print("[2/6] 配置 API Key...")
        try:
            page.locator("button").filter(has_text="去配置").first.click(timeout=5000)
            page.wait_for_selector("input[type='password']", timeout=5000)
            page.fill("input[type='password']", api_key)
            page.locator("button").filter(has_text="确认").first.click()
            time.sleep(1)
        except PlaywrightError:
            print("  API Key 可能已配置，跳过")
        _screenshot(page, "02_apikey_set.png")

        # ── 3. 切换到"深度研究"模式 ──
        print("[3/6] 切换到深度研究模式...")
        # EmptyState 下拉框：先点"模式："展开，再选"深度研究"（默认即 deep）
        try:
            page.locator("button").filter(has_text="模式").first.click(timeout=5000)
            time.sleep(0.5)
            page.locator("button").filter(has_text="深度研究").first.click(timeout=5000)
            time.sleep(0.5)
            page.keyboard.press("Escape")
            time.sleep(0.3)
        except PlaywrightError:
            print("  可能已是深度模式，继续")
        _screenshot(page, "03_mode_deep.png")

        # ── 4. 在输入框中输入查询 ──
        print('[4/6] 输入"分析一下光模块龙头企业"...')
        textarea = page.locator("textarea").first
        textarea.click()
        textarea.fill("分析一下光模块龙头企业")
        time.sleep(0.5)
        _screenshot(page, "04_input_filled.png")

        # ── 5. 点击提交按钮（向上箭头图标）──
        print("[5/6] 点击提交按钮...")
        # 提交按钮是带 fa-arrow-up 图标的按钮
        submit_btn = page.locator("button:has(i.fa-arrow-up)").first
        submit_btn.click()

        # ── 6. 等待 ReAct 循环事件显示 ──
        print(f"[6/6] 等待 ReAct 循环完成 (最长 {REACT_TIMEOUT}s)...")
        deadline = time.time() + REACT_TIMEOUT
        saw_thinking = False
        saw_tool_call = False
        saw_tool_result = False
        saw_resolved = False
        last_body = ""

        while time.time() < deadline:
            try:
                body = page.locator("body").inner_text(timeout=2000)
            except PlaywrightError:
                body = ""

            if not saw_thinking and (
                "分析" in body and ("需求" in body or "搜索" in body or "先" in body)
            ):
                saw_thinking = True
                print(f"  [{time.time():.0f}] ✓ thinking_token 出现")

            if not saw_tool_call and (
                "搜索" in body and ("工具" in body or "调用" in body or "stock" in body.lower())
            ):
                saw_tool_call = True
                print(f"  [{time.time():.0f}] ✓ tool_call (search_stock) 出现")

            if not saw_tool_result and ("中际旭创" in body or "300308" in body):
                saw_tool_result = True
                print(f"  [{time.time():.0f}] ✓ tool_result (找到中际旭创)")

            if (
                not saw_resolved
                and saw_tool_result
                and (
                    "深度分析" in body
                    or "分析报告" in body
                    or "流水线" in body
                    or "Layer" in body
                    or "层" in body
                )
            ):
                saw_resolved = True
                print(f"  [{time.time():.0f}] ✓ resolved (启动深度分析)")
                time.sleep(3)
                break

            if "错误" in body or "连接错误" in body:
                print(f"  [{time.time():.0f}] ✗ error 出现")
                break

            if body != last_body:
                last_body = body

            time.sleep(2)

        _screenshot(page, "04_react_result.png")
        _screenshot(page, "05_react_full.png")

        # ── 6. 验证 ──
        print("[6/6] 验证结果...")
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except PlaywrightError:
            body_text = ""

        checks = {
            "thinking_token 显示": saw_thinking,
            "ReAct 分析需求": "分析" in body_text and "需求" in body_text,
            "tool_result (中际旭创) 显示": saw_tool_result,
            "resolved (启动深度分析)": saw_resolved,
            "页面包含 中际旭创": "中际旭创" in body_text,
            "5 层流水线已启动": "Layer" in body_text or "流水线" in body_text,
        }

        print("\n验证结果：")
        all_pass = True
        for name, ok in checks.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"  {status} {name}")
            if not ok:
                all_pass = False

        # 保存页面文本
        report_md = SCREENSHOT_DIR / "report_react_search_browser.md"
        report_md.write_text(body_text[:8000], encoding="utf-8")
        print(f"\n  页面文本已保存: {report_md}")

        browser.close()

        if all_pass:
            print("\n[PASS] E2E 浏览器测试通过！")
        else:
            print("\n[FAIL] 部分检查未通过。")
        return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
