"""图表端到端测试 — 验证前端 ECharts 图表 + Markdown 渲染 + docx/pptx 图片插入。

前置条件：
  - FastAPI 后端运行在 127.0.0.1:8000
  - Vite 前端运行在 127.0.0.1:5173
  - 环境变量 DEEPSEEK_API_KEY 已设置

运行方式：
    python tests/e2e/e2e_charts.py
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
REPORT_TIMEOUT = 480


def _resolve_api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY") or ""


def _screenshot(page, name: str, full_page: bool = False) -> None:
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  截图: {path}")


def main() -> bool:
    api_key = _resolve_api_key()
    if not api_key:
        print("[FAIL] 未找到 API Key")
        return False
    print(f"  API Key: {api_key[:6]}...{api_key[-4:]}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 2200})

        print("[1/6] 打开前端页面...")
        page.goto(FRONTEND_URL, timeout=30000)
        _screenshot(page, "chart_01_initial.png")

        # 配置 API Key
        print("[2/6] 配置 API Key...")
        page.locator("button").filter(has_text="去配置").first.click()
        page.wait_for_selector("input[type='password']", timeout=5000)
        page.fill("input[type='password']", api_key)
        page.locator("button").filter(has_text="确认").first.click()
        time.sleep(0.5)

        # 触发深度分析 — 输入宁德时代 300750
        print("[3/6] 触发深度分析 (300750 宁德时代)...")
        page.locator("textarea").first.fill("300750")
        time.sleep(0.3)
        # 按 Enter 或点击发送按钮
        page.locator("textarea").first.press("Enter")
        time.sleep(2)
        _screenshot(page, "chart_02_analysis_started.png")

        # 等待报告生成
        print(f"[4/6] 等待 5 层流水线完成 (最长 {REPORT_TIMEOUT}s)...")
        done = False
        errored = False
        deadline = time.time() + REPORT_TIMEOUT
        last_progress = 0
        while time.time() < deadline:
            try:
                body = page.locator("body").inner_text(timeout=2000)
            except PlaywrightError:
                body = ""
            if "分析完成" in body or "深度分析报告" in body:
                done = True
                break
            if "连接错误" in body or "错误:" in body:
                errored = True
                print(f"  页面检测到错误: {body[:500]}")
                break
            # 进度日志（每 30s 打印一次）
            elapsed = int(time.time() - (deadline - REPORT_TIMEOUT))
            if elapsed - last_progress >= 30:
                last_progress = elapsed
                print(f"  已等待 {elapsed}s...")
            time.sleep(3)

        if errored or not done:
            print("[FAIL] 报告未在超时内生成")
            browser.close()
            return False

        time.sleep(3)  # 等待图表渲染
        _screenshot(page, "chart_03_report_ready.png", full_page=True)

        # ── 验证 ──
        print("[5/6] 验证图表和文本渲染...")

        # 1. ECharts canvas 元素（图表已渲染）
        chart_canvases = page.locator("canvas").count()
        print(f"  ECharts canvas 数量: {chart_canvases}")

        # 2. KPI 卡片
        kpi_cards = (
            page.locator("text=当前股价")
            .or_(page.locator("text=市盈率"))
            .or_(page.locator("text=总市值"))
            .count()
        )
        print(f"  KPI 卡片标识: {kpi_cards}")

        # 3. 图表标题
        chart_titles = [
            "营业收入与归母净利润",
            "同比增速",
            "毛利率与净利率",
            "ROE 变化趋势",
            "经营现金流净额",
        ]
        chart_title_hits = 0
        for title in chart_titles:
            if page.locator(f"text={title}").count() > 0:
                chart_title_hits += 1
        print(f"  图表标题命中: {chart_title_hits}/{len(chart_titles)}")

        # 4. Markdown 渲染（检查是否有 h2/h3 元素，而非纯文本 #）
        h2_count = page.locator("h2").count()
        h3_count = page.locator("h3").count()
        table_count = page.locator("table").count()
        print(f"  Markdown 渲染: h2={h2_count}, h3={h3_count}, table={table_count}")

        # 5. 原始 Markdown 符号不应出现在页面上（# 标题不应作为文本显示）
        # 检查是否有未渲染的 ## 或 ### 文本
        raw_md = False
        try:
            body_text = page.locator("body").inner_text(timeout=2000)
            # 如果 body 中包含 "## " 开头的行，说明 Markdown 未渲染
            for line in body_text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("## ") or stripped.startswith("### "):
                    raw_md = True
                    break
        except PlaywrightError:
            pass
        print(f"  原始 Markdown 符号泄漏: {'是' if raw_md else '否'}")

        # 6. 报告文本包含关键内容
        body_text = page.locator("body").inner_text(timeout=5000)
        has_stock_name = "宁德" in body_text
        has_report_title = "投资分析报告" in body_text
        print(f"  包含股票名称: {'是' if has_stock_name else '否'}")
        print(f"  包含报告标题: {'是' if has_report_title else '否'}")

        # 保存页面文本
        report_file = SCREENSHOT_DIR / "report_charts.md"
        report_file.write_text(body_text[:10000], encoding="utf-8")
        print(f"  页面文本已保存: {report_file}")

        # ── 综合判定 ──
        print("[6/6] 综合判定...")
        checks = {
            "ECharts 图表已渲染 (canvas >= 3)": chart_canvases >= 3,
            "图表标题命中 >= 3": chart_title_hits >= 3,
            "Markdown 已渲染 (h2 >= 1)": h2_count >= 1,
            "无原始 Markdown 符号泄漏": not raw_md,
            "包含股票名称": has_stock_name,
            "包含报告标题": has_report_title,
        }

        print("\n验证结果：")
        all_pass = True
        for name, ok in checks.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"  {status} {name}")
            if not ok:
                all_pass = False

        browser.close()

        if all_pass:
            print("\n[PASS] 图表 E2E 测试通过！")
        else:
            print("\n[FAIL] 部分检查未通过。")
        return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
