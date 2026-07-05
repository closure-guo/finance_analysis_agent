"""浏览器端到端测试：启动 Gradio → Playwright 操作 UI → 截图 + 验证。

运行方式（真实 LLM + 真实 AKShare 数据）：
    set DEEPSEEK_API_KEY=your_key
    uv run python tests/e2e/e2e_browser.py
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

SCREENSHOT_DIR = Path(__file__).parent / "e2e"
GRADIO_URL = "http://127.0.0.1:7860"


def main() -> bool:
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    # Clear cache so check_cache returns MISS and real fetch_data is invoked
    if os.path.exists("cache.db"):
        os.remove("cache.db")

    # ── 1. Start Gradio in background thread ──
    print("[1/6] 启动 Gradio 服务...")
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
            # Use system-installed Chrome via channel (avoids downloading playwright browsers)
            browser = p.chromium.launch(headless=True, channel="chrome")
            page = browser.new_page(viewport={"width": 1400, "height": 2400})

            # ── 2. Open page ──
            print("[2/6] 打开 Gradio 页面...")
            page.goto(GRADIO_URL, timeout=30000)
            _screenshot(page, "01_initial.png")

            # ── 3. Fill stock code directly ──
            print("[3/6] 填写股票代码...")
            # Find stock code input by label
            stock_input = page.locator("input").filter(has_text="600519").first
            if stock_input.count() == 0:
                # Try finding by placeholder or label text
                stock_input = page.get_by_placeholder("例：600519").first
            if stock_input.count() == 0:
                # Fallback: fill the third input (search, dropdown, stock_code)
                stock_input = page.locator("input[type='text']").nth(2)
            stock_input.fill("600519")
            time.sleep(0.5)
            _screenshot(page, "03_stock_selected.png")

            # ── 4. Click submit ──
            print("[4/6] 提交分析请求...")
            submit_btn = page.locator("button").filter(has_text="开始分析")
            if submit_btn.count() == 0:
                submit_btn = page.locator("button.primary, button[type='submit']").first
            submit_btn.click()
            _screenshot(page, "04_submit_clicked.png")

            # ── 5. Wait for report ──
            print("[5/6] 等待分析报告生成...")
            report_text = ""
            # Wait for loading to finish (real LLM calls take longer)
            for _ in range(180):
                time.sleep(1)
                # Try multiple selectors for Gradio 5 Markdown output
                for selector in [
                    ".prose",
                    ".markdown",
                    "[data-testid='markdown']",
                    ".gradio-markdown",
                    "[class*='md']",
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
                # Also check if error message appeared
                page_text = page.locator("body").inner_text(timeout=500)
                if "错误" in page_text or "失败" in page_text or "请输入" in page_text:
                    report_text = page_text
                    break
            time.sleep(1)
            _screenshot(page, "05_report_full.png", full_page=True)

            # ── 6. Validate ──
            print("[6/6] 验证结果...")
            if not report_text:
                try:
                    report_text = page.locator("body").inner_text(timeout=5000)
                except Exception:
                    report_text = ""

            checks = {
                "页面有内容": len(report_text) > 50,
                "包含分析相关文字": "分析" in report_text
                or "茅台" in report_text
                or "股票" in report_text,
            }

            # Check if download buttons or report file links are visible
            has_download = False
            for txt in ["下载", "Word", "PPT", ".docx", ".pptx"]:
                try:
                    btns = page.locator("a, button, [class*='download'], [class*='file']").filter(
                        has_text=txt
                    )
                    if btns.count() > 0:
                        has_download = True
                        break
                except PlaywrightError:
                    continue
            # Also check if report text mentions download
            if not has_download:
                has_download = "下载" in report_text and ".docx" in report_text
            checks["下载按钮存在"] = has_download

            print("\n验证结果：")
            all_pass = True
            for name, ok in checks.items():
                status = "[PASS]" if ok else "[FAIL]"
                print(f"  {status} {name}")
                if not ok:
                    all_pass = False

            # Save report text
            report_md = SCREENSHOT_DIR / "report_browser.md"
            report_md.write_text(report_text[:5000], encoding="utf-8")
            print(f"\n  报告文本已保存: {report_md}")

            if all_pass:
                print(f"\n[PASS] 浏览器端到端测试通过！截图目录: {SCREENSHOT_DIR}")
            else:
                print(f"\n[FAIL] 部分检查未通过。截图目录: {SCREENSHOT_DIR}")

            browser.close()
            return all_pass
    finally:
        # Gradio daemon thread will die when main exits
        pass


def _screenshot(page, filename: str, full_page: bool = False) -> None:
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  截图: {path}")


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
