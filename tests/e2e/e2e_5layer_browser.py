"""5 层架构浏览器端到端测试：启动 Gradio → Playwright 操作 UI → 截图 + 验证。

运行方式（真实 LLM + 真实 AKShare 数据）：
    set DEEPSEEK_API_KEY=your_key
    uv run python tests/e2e/e2e_5layer_browser.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# ruff: noqa: E402, I001
from playwright.sync_api import Error as PlaywrightError, sync_playwright
from finance_agent.app import demo

SCREENSHOT_DIR = Path(__file__).parent
GRADIO_URL = "http://127.0.0.1:7860"


def _screenshot(page, filename: str, full_page: bool = False) -> None:
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  截图: {path}")


def main() -> bool:
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    if os.path.exists("cache.db"):
        os.remove("cache.db")

    print("[1/6] 启动 Gradio 服务 (5 层架构)...")
    gradio_thread = threading.Thread(
        target=lambda: demo.launch(
            server_name="127.0.0.1",
            server_port=7860,
            prevent_thread_lock=False,
            show_error=True,
            quiet=True,
        ),
        daemon=True,
    )
    gradio_thread.start()
    time.sleep(5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="chrome")
            page = browser.new_page(viewport={"width": 1400, "height": 2400})

            print("[2/6] 打开 Gradio 页面...")
            page.goto(GRADIO_URL, timeout=30000)
            _screenshot(page, "01_5layer_initial.png")

            print("[3/6] 填写股票代码...")
            stock_input = page.get_by_placeholder("例：600519").first
            if stock_input.count() == 0:
                stock_input = page.locator("input[type='text']").nth(2)
            stock_input.fill("600519")
            time.sleep(0.5)
            _screenshot(page, "03_5layer_stock.png")

            print("[4/6] 提交分析请求...")
            submit_btn = page.locator("button").filter(has_text="开始分析")
            if submit_btn.count() == 0:
                submit_btn = page.locator("button.primary, button[type='submit']").first
            submit_btn.click()
            _screenshot(page, "04_5layer_submit.png")

            print("[5/6] 等待 5 层分析完成...")
            report_text = ""
            # Real LLM calls take longer — wait up to 5 minutes
            for _ in range(300):
                time.sleep(1)
                for selector in [
                    ".prose",
                    ".markdown",
                    "[data-testid='markdown']",
                    ".gradio-markdown",
                ]:
                    try:
                        el = page.locator(selector).first
                        if el.count() > 0:
                            txt = el.inner_text(timeout=500)
                            if txt and len(txt) > 50:
                                report_text = txt
                                break
                    except PlaywrightError:
                        continue
                if report_text:
                    break
                page_text = page.locator("body").inner_text(timeout=500)
                if "错误" in page_text or "失败" in page_text:
                    report_text = page_text
                    break
            time.sleep(1)
            _screenshot(page, "05_5layer_report.png", full_page=True)

            print("[6/6] 验证结果...")
            if not report_text:
                try:
                    report_text = page.locator("body").inner_text(timeout=5000)
                except Exception:
                    report_text = ""

            checks = {
                "页面有内容": len(report_text) > 50,
                "包含股票名称": "茅台" in report_text or "600519" in report_text,
                "包含分析文字": "分析" in report_text or "报告" in report_text,
            }

            print("\n验证结果：")
            all_pass = True
            for name, ok in checks.items():
                status = "[PASS]" if ok else "[FAIL]"
                print(f"  {status} {name}")
                if not ok:
                    all_pass = False

            report_md = SCREENSHOT_DIR / "report_5layer_browser.md"
            report_md.write_text(report_text[:5000], encoding="utf-8")
            print(f"\n  报告文本已保存: {report_md}")

            if all_pass:
                print("\n[PASS] 5 层架构浏览器端到端测试通过！")
            else:
                print("\n[FAIL] 部分检查未通过。")

            browser.close()
            return all_pass
    finally:
        pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
