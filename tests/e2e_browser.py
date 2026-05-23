"""浏览器端到端测试：启动 Gradio → Playwright 填表单 → 截图报告。

运行方式：
    export LLM_API_KEY=your_key   (或确保系统环境变量 Deepseek-Api-Key 已设)
    uv run python tests/e2e_browser.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path(__file__).parent / "e2e"
STOCK_CODE = "600519"
GRADIO_URL = "http://127.0.0.1:7860"


def main():
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    # 确保有 API Key
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("Deepseek-Api-Key")
    if not api_key:
        api_key = _read_system_env("Deepseek-Api-Key")
    if api_key:
        os.environ["LLM_API_KEY"] = api_key

    # 启动 Gradio
    print("[1/5] 启动 Gradio 服务...")
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "finance_agent.app"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="chrome")
            page = browser.new_page(viewport={"width": 1400, "height": 2400})

            # 打开页面
            print("[2/5] 打开 Gradio 页面...")
            page.goto(GRADIO_URL, timeout=30000)
            page.screenshot(path=str(SCREENSHOT_DIR / "01_form.png"))
            print(f"  截图: {SCREENSHOT_DIR / '01_form.png'}")

            # 填写表单
            print("[3/5] 填写表单...")
            # Gradio 5: 找到 label 含 "股票代码" 的容器下的 input
            stock_input = page.locator("input").first
            stock_input.fill(STOCK_CODE)

            # dropdown 保持默认 financial
            page.wait_for_timeout(500)

            # 截图填写后
            page.screenshot(path=str(SCREENSHOT_DIR / "02_filled.png"))
            print(f"  截图: {SCREENSHOT_DIR / '02_filled.png'}")

            # 点击提交
            print("[4/5] 提交分析请求，等待 LLM 生成报告（可能需要 1-2 分钟）...")
            page.keyboard.press("Escape")  # 关闭可能展开的 dropdown
            page.wait_for_timeout(500)
            submit_btn = page.locator("button.primary")
            submit_btn.click()

            # 等待报告出现（最多等 3 分钟）
            try:
                page.wait_for_selector("text=免责声明", timeout=180000)
            except Exception:
                page.wait_for_timeout(5000)

            page.screenshot(path=str(SCREENSHOT_DIR / "03_report.png"), full_page=True)
            print(f"  截图: {SCREENSHOT_DIR / '03_report.png'}")

            # 获取报告文本
            report_el = page.locator(".md, .markdown, [data-testid='markdown']")
            if report_el.count() > 0:
                report_text = report_el.last.inner_text()
                out_md = SCREENSHOT_DIR / "report_text.md"
                out_md.write_text(report_text, encoding="utf-8")
                print(f"  报告已保存: {out_md}")

            print("\n[5/5] 浏览器端到端测试完成！")
            print(f"  截图目录: {SCREENSHOT_DIR}")

            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _read_system_env(name: str) -> str | None:
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command",
             f"[System.Environment]::GetEnvironmentVariable('{name}', 'Machine')"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


if __name__ == "__main__":
    main()
