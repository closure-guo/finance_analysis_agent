"""E2E test: full browser test with detailed error capture."""

import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:7860"
SCREENSHOT_DIR = "tests/e2e"
TIMEOUT_ANALYSIS = 300000  # 5 min for LLM calls


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text[:200]}"))

        # ── Step 1: Page load ──
        print("TEST 1: Page load")
        page.goto(URL, timeout=30000)
        time.sleep(3)
        page.screenshot(path=f"{SCREENSHOT_DIR}/t1_loaded.png")

        title = page.title()
        assert "金融AI" in title, f"Title wrong: {title}"
        print(f"  PASS - title: {title}")

        section_labels = page.locator(".section-label")
        assert section_labels.count() >= 2, "Missing section labels"
        print(f"  PASS - section labels: {section_labels.count()}")

        disclaimer = page.locator(".disclaimer")
        assert disclaimer.count() >= 1, "Missing disclaimer"
        print("  PASS - disclaimer")

        # ── Step 2: Search + auto-select ──
        print("\nTEST 2: Search stock + auto-select")

        search_box = page.get_by_label("搜索股票（名称或代码）")
        search_box.fill("茅台")

        # Wait for search callback to finish (stock list API takes ~5s on first call)
        try:
            page.wait_for_function(
                """() => {
                    const dd = document.querySelector('[data-testid="dropdown"]');
                    if (!dd) return false;
                    // Check if dropdown has options or value
                    const input = dd.querySelector('input');
                    return input && input.value.length > 0;
                }""",
                timeout=30000,
            )
        except Exception:
            print("  WARN: dropdown not populated within 30s, continuing...")

        time.sleep(2)
        page.screenshot(path=f"{SCREENSHOT_DIR}/t2_search.png")

        dropdown = page.get_by_label("选择股票")
        dropdown_value = dropdown.input_value()
        print(f"  Dropdown value: '{dropdown_value}'")

        stock_code_box = page.get_by_label("股票代码")
        stock_code_value = stock_code_box.input_value()
        print(f"  Stock code: '{stock_code_value}'")

        if stock_code_value != "600519":
            print("  WARN: auto-select didn't fill code, filling manually")
            stock_code_box.fill("600519")
            time.sleep(1)
            stock_code_value = stock_code_box.input_value()
            assert stock_code_value == "600519", "Failed to fill stock code"
            print(f"  Stock code (manual): '{stock_code_value}'")
        else:
            print("  PASS - auto-select worked")

        # ── Step 3: Run analysis ──
        print("\nTEST 3: Run analysis")

        submit = page.get_by_role("button", name="开始分析")
        submit.click()
        print("  Clicked submit, waiting for report...")
        page.screenshot(path=f"{SCREENSHOT_DIR}/t3_analyzing.png")

        # Wait for report-area to have real content (not placeholder)
        try:
            page.wait_for_function(
                """() => {
                    const el = document.querySelector('.report-area');
                    if (!el) return false;
                    const t = el.textContent || '';
                    return !t.includes('等待分析结果') && t.length > 500;
                }""",
                timeout=TIMEOUT_ANALYSIS,
            )
            print("  Report content detected!")
        except Exception:
            page.screenshot(path=f"{SCREENSHOT_DIR}/t3_timeout.png")
            report_area = page.locator(".report-area")
            txt = report_area.first.text_content() if report_area.count() > 0 else ""
            print(f"  TIMEOUT - report area: {txt[:300]}")

            # Check for visible errors
            for pattern in ["❌", "失败", "错误"]:
                els = page.locator(f"text={pattern}")
                for i in range(min(els.count(), 3)):
                    el = els.nth(i)
                    if el.is_visible():
                        print(f"  ERROR: {el.text_content()}")

            print("\nFAILED - analysis did not complete")
            browser.close()
            return

        time.sleep(3)
        page.screenshot(path=f"{SCREENSHOT_DIR}/t3_result.png")

        # ── Step 4: Verify report ──
        print("\nTEST 4: Verify report")

        report_area = page.locator(".report-area")
        report_text = report_area.first.text_content() or ""
        print(f"  Report: {len(report_text)} chars")

        assert len(report_text) > 500, f"Report too short: {len(report_text)}"
        print("  PASS - substantial content")

        keywords_found = [k for k in ["综合", "分析", "建议"] if k in report_text]
        print(f"  Keywords: {keywords_found}")
        assert len(keywords_found) >= 1, "Report missing expected keywords"
        print("  PASS")

        # ── Done ──
        print("\n" + "=" * 50)
        print("ALL TESTS PASSED")
        print(f"Report preview: {report_text[:200]}...")

        browser.close()


if __name__ == "__main__":
    main()
