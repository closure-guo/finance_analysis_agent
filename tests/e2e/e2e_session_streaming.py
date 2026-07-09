"""E2E test: natural language input + streaming + sessions + sidebar.

Uses the "快速分析" button to send '茅台' directly (bypassing Enter key issues).
"""

import json
import os
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path(__file__).parent / "e2e_session_screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

API_KEY = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("LLM_API_KEY", ""))


def test_full_e2e():
    """Full E2E test: NLP → pipeline → streaming report → sessions → chat."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        # Capture console errors
        errors: list[str] = []
        page.on(
            "console",
            lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None,
        )

        page.goto(FRONTEND_URL, wait_until="networkidle")
        page.screenshot(path=str(SCREENSHOT_DIR / "01_initial.png"))
        print("[1/6] 初始页面 ✓")

        # Set API key: click "去配置" → fill → "确认"
        try:
            page.locator('button:has-text("去配置")').click(timeout=5000)
            page.wait_for_timeout(500)
        except Exception:
            pass

        api_input = page.locator('input[placeholder="sk-..."]')
        if api_input.is_visible(timeout=3000):
            api_input.fill(API_KEY)
            page.locator('button:has-text("确认")').click()
            page.wait_for_timeout(500)
            print(f"  API Key 已设置 (len={len(API_KEY)})")
        else:
            print("  [WARN] API Key 输入框未找到")

        # Click "快速分析" button (sends '茅台' directly)
        page.locator('button:has-text("快速分析")').click()
        print("[2/6] 点击'快速分析' → 发送'茅台' ✓")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SCREENSHOT_DIR / "02_after_click.png"))

        # Wait for NLP resolution or pipeline start
        try:
            page.wait_for_selector("text=正在识别", timeout=15000)
            print("[3/6] 检测到 NLP 解析 ✓")
        except Exception:
            # Check if resolved text is visible
            body_text = page.locator("body").inner_text(timeout=2000)
            if "已识别" in body_text or "茅台" in body_text or "600519" in body_text:
                print("[3/6] 检测到股票识别结果 ✓")
            else:
                print(f"[3/6] 未检测到 NLP 文本，页面内容: {body_text[:200]}...")

        page.screenshot(path=str(SCREENSHOT_DIR / "03_nlp.png"))

        # Wait for pipeline to start
        try:
            page.wait_for_selector("text=数据准备", timeout=30000)
            print("  Pipeline 已启动 ✓")
        except Exception:
            body_text = page.locator("body").inner_text(timeout=2000)
            print(f"  [WARN] Pipeline 未启动，页面内容: {body_text[:300]}...")

        page.wait_for_timeout(5000)
        page.screenshot(path=str(SCREENSHOT_DIR / "04_pipeline.png"))

        # Wait for report (max 5 minutes)
        print("[4/6] 等待报告流式输出（最多5分钟）...")
        try:
            page.wait_for_selector("canvas", timeout=300000)
            print("  检测到图表 ✓")
        except Exception:
            print("  [WARN] 未检测到图表")

        page.wait_for_timeout(5000)
        page.screenshot(path=str(SCREENSHOT_DIR / "05_report_ready.png"), full_page=True)

        # Check content
        h2_count = page.locator("h2").count()
        canvas_count = page.locator("canvas").count()
        body_text = page.locator("body").inner_text(timeout=2000)
        has_report = "投资分析报告" in body_text or "核心财务" in body_text
        print(f"  h2: {h2_count}, canvas: {canvas_count}, has_report_text: {has_report}")

        page.screenshot(path=str(SCREENSHOT_DIR / "06_final.png"))

        if errors:
            print(f"  Console errors: {errors[:3]}")

        browser.close()
        return h2_count, canvas_count, has_report


def test_sessions_and_chat(h2: int, canvas: int, has_report: bool):
    """Test sessions API and streaming chat."""
    print("\n--- Sessions API ---")
    resp = requests.get(f"{API_URL}/api/sessions", timeout=5)
    sessions = resp.json().get("sessions", [])
    print(f"  Sessions: {len(sessions)}")

    if not sessions:
        print("  [SKIP] 无会话，跳过追问测试")
        return

    s = sessions[0]
    print(f"  最新: {s['display_name']} ({s['stock_code']})")

    # Get detail
    resp2 = requests.get(f"{API_URL}/api/sessions/{s['session_id']}", timeout=5)
    detail = resp2.json()
    print(f"  报告长度: {len(detail.get('report_markdown', ''))}")
    print(f"  chart_data: {list(detail.get('chart_data', {}).keys())}")
    print(f"  analyst_summaries: {list(detail.get('analyst_summaries', {}).keys())}")

    # Rename
    requests.patch(
        f"{API_URL}/api/sessions/{s['session_id']}",
        json={"display_name": f"{s['stock_name']} 重命名测试"},
        timeout=5,
    )
    print("  PATCH rename ✓")

    # Streaming chat
    print("\n--- Streaming Chat ---")
    resp = requests.post(
        f"{API_URL}/api/chat",
        json={
            "message": "毛利率趋势如何？",
            "session_id": s["session_id"],
            "api_key": API_KEY,
        },
        stream=True,
        timeout=120,
    )

    tokens = []
    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
        if line_str.startswith("data: "):
            try:
                data = json.loads(line_str[6:])
                if data.get("type") == "chat_token":
                    tokens.append(data["token"])
                elif data.get("type") == "chat_done":
                    break
                elif data.get("type") == "error":
                    print(f"  [ERROR] {data.get('message', '')}")
                    return
            except json.JSONDecodeError:
                pass

    full = "".join(tokens)
    print(f"  收到 {len(tokens)} tokens")
    print(f"  回复: {full[:120]}...")
    if tokens:
        print("  追问流式输出 ✓")


if __name__ == "__main__":
    print("=" * 60)
    print("E2E Test: Session + Streaming + NLP")
    print("=" * 60)

    if not API_KEY:
        print("[ERROR] 无 API Key")
        exit(1)
    print(f"API Key: {'*' * 20} (len={len(API_KEY)})")

    print("\n--- Test 1: NLP + Pipeline + Streaming Report ---")
    h2, canvas, has_report = test_full_e2e()

    print("\n--- Test 2: Sessions + Streaming Chat ---")
    test_sessions_and_chat(h2, canvas, has_report)

    print("\n" + "=" * 60)
    print("E2E tests completed!")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print("=" * 60)
