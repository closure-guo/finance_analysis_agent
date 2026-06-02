"""浏览器端到端测试：启动 Gradio → Playwright 操作 UI → 截图 + 验证。

运行方式（Mock LLM，无需 API Key，快速）：
    uv run python tests/e2e_browser.py

运行方式（真实 LLM，需要 Deepseek-Api-Key）：
    set Deepseek-Api-Key=your_key
    uv run python tests/e2e_browser.py --no-mock
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path


# ── Mock LLM before any app imports ──
def _mock_llm(
    prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 4096
) -> str:
    if "综合" in prompt or "synthesis" in prompt.lower():
        return (
            "**综合结论**：贵州茅台作为中国白酒行业龙头，财务基本面极为稳健。"
            "偿债能力优秀（资产负债率仅 40%），盈利能力突出（ROE 长期维持 28%+），"
            "现金流充沛（经营现金流/净利润 >1.4）。投资分析角度，当前 PE 约 25 倍，"
            "低于行业平均 30 倍，具备一定估值安全边际。GARP 四条件全部通过，"
            "属于典型的优质成长蓝筹。综合来看，建议**买入并长期持有**，"
            "适合价值型和成长型投资者。关键风险：消费税政策调整、行业库存周期、"
            "宏观经济下行影响高端消费。"
        )
    if "摘要" in prompt or "summary" in prompt.lower() or "执行摘要" in system:
        return (
            "本报告对贵州茅台进行了全面的财务与投资分析。"
            "公司财务基本面极为稳健，四维度指标均表现优异，健康度评分 95/100（健康）。"
            "投资角度，当前估值处于合理偏低区间，PE 低于行业平均，GARP 筛选全部通过。"
            "建议买入并长期持有，关键关注消费税政策和高端消费景气度变化。"
        )
    # Default body text for both FA and IA
    return (
        "## 第3章：核心指标分析\n\n"
        "公司偿债能力优秀，资产负债率仅 40%，流动比率 1.67，均处于优良区间。"
        "盈利能力突出，ROE 长期维持 28%+，毛利率 40%，净利率 17%。"
        "运营效率稳定，存货周转率 6.32 次。现金流健康，经营现金流/净利润 1.47。\n\n"
        "## 第4章：杜邦归因分析\n\n"
        "ROE = 净利率(17%) × 总资产周转率(1.05) × 权益乘数(1.67) = 29.7%。"
        "净利率是 ROE 的核心驱动因素，权益乘数适中，财务杠杆稳健。\n\n"
        "## 第5章：同业对比\n\n"
        "无同业对比数据。\n\n"
        "## 第6章：风险提示\n\n"
        "无红灯指标触发。\n\n"
        "## 第7章：结论与评级\n\n"
        "健康度评分：95/100 🟢 健康。建议买入并长期持有。"
    )


def _mock_fetch_data(state: dict, cache=None, client=None) -> dict:
    """Return canned financial data so e2e works without AKShare network."""
    import pandas as pd

    code = state.get("stock_code", "")
    return {
        "balance_sheet": pd.DataFrame(
            {
                "报告日": ["20241231", "20231231", "20221231"],
                "货币资金": [200.0, 180.0, 150.0],
                "存货": [100.0, 90.0, 80.0],
                "流动资产合计": [500.0, 450.0, 400.0],
                "固定资产净值": [300.0, 280.0, 260.0],
                "累计折旧": [120.0, 100.0, 80.0],
                "非流动资产合计": [500.0, 450.0, 400.0],
                "资产总计": [1000.0, 900.0, 800.0],
                "短期借款": [80.0, 70.0, 60.0],
                "应付账款": [60.0, 50.0, 45.0],
                "应收账款": [40.0, 35.0, 30.0],
                "一年内到期的非流动负债": [20.0, 15.0, 10.0],
                "流动负债合计": [300.0, 280.0, 260.0],
                "长期借款": [50.0, 40.0, 30.0],
                "应付债券": [30.0, 20.0, 20.0],
                "非流动负债合计": [100.0, 70.0, 60.0],
                "负债合计": [400.0, 350.0, 320.0],
                "所有者权益(或股东权益)合计": [600.0, 550.0, 480.0],
                "实收资本(或股本)": [125.0, 125.0, 125.0],
                "未分配利润": [200.0, 170.0, 140.0],
            }
        ),
        "income_statement": pd.DataFrame(
            {
                "报告日": ["20241231", "20231231", "20221231"],
                "营业收入": [1000.0, 900.0, 800.0],
                "营业成本": [600.0, 550.0, 500.0],
                "销售费用": [50.0, 45.0, 40.0],
                "管理费用": [60.0, 55.0, 50.0],
                "研发费用": [30.0, 25.0, 20.0],
                "财务费用": [22.0, 20.0, 18.0],
                "利息费用": [20.0, 18.0, 16.0],
                "营业利润": [200.0, 180.0, 160.0],
                "利润总额": [200.0, 180.0, 160.0],
                "所得税费用": [30.0, 27.0, 24.0],
                "净利润": [170.0, 153.0, 136.0],
                "归属于母公司所有者的净利润": [168.0, 151.0, 134.0],
            }
        ),
        "cash_flow_statement": pd.DataFrame(
            {
                "报告日": ["20241231", "20231231", "20221231"],
                "经营活动产生的现金流量净额": [250.0, 220.0, 200.0],
                "购建固定资产、无形资产和其他长期资产所支付的现金": [80.0, 70.0, 60.0],
                "投资活动产生的现金流量净额": [-100.0, -90.0, -80.0],
                "分配股利、利润或偿付利息所支付的现金": [50.0, 45.0, 40.0],
                "筹资活动产生的现金流量净额": [-30.0, -20.0, -10.0],
            }
        ),
        "financial_indicators": pd.DataFrame(
            {
                "日期": ["2024-12-31", "2023-12-31", "2022-12-31"],
                "销售毛利率(%)": [40.0, 38.89, 37.5],
                "销售净利率(%)": [17.0, 17.0, 17.0],
                "净资产收益率(%)": [28.33, 27.82, 28.33],
                "总资产净利润率(%)": [17.0, 17.0, 17.0],
                "存货周转率(次)": [6.32, 6.47, 6.58],
                "应收账款周转率(次)": [None, None, None],
                "总资产周转率(次)": [1.05, 1.06, 1.05],
                "流动比率": [1.67, 1.61, 1.54],
                "速动比率": [1.33, 1.29, 1.23],
                "资产负债率(%)": [40.0, 38.89, 40.0],
                "利息支付倍数": [11.0, 11.0, 11.0],
            }
        ),
        "industry_info": {"industry": "白酒", "name": "贵州茅台"},
        "stock_quote": {
            "name": "贵州茅台",
            "code": code,
            "PE": 25.0,
            "PB": 8.0,
            "price": 1700.0,
            "market_cap": 21000.0,
        },
        "peer_financials": None,
    }


def _setup_mock() -> None:
    """Monkey-patch LLM and data fetch to avoid external APIs during e2e."""
    import finance_agent.llm
    import finance_agent.nodes.fa
    import finance_agent.nodes.fetch
    import finance_agent.nodes.ia
    import finance_agent.nodes.merge

    finance_agent.llm.call_llm = _mock_llm
    finance_agent.nodes.fa.call_llm = _mock_llm
    finance_agent.nodes.ia.call_llm = _mock_llm
    finance_agent.nodes.merge.call_llm = _mock_llm
    finance_agent.nodes.fetch.fetch_data = _mock_fetch_data


# ── Parse args before importing app (import triggers graph build) ──
parser = argparse.ArgumentParser()
parser.add_argument("--no-mock", action="store_true", help="Use real LLM (requires API key)")
args = parser.parse_args()

if not args.no_mock:
    _setup_mock()

# Now safe to import app
from playwright.sync_api import sync_playwright  # noqa: E402

from finance_agent.app import demo  # noqa: E402

SCREENSHOT_DIR = Path(__file__).parent / "e2e"
GRADIO_URL = "http://127.0.0.1:7860"


def main() -> bool:
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    # Clear cache so check_cache returns MISS and mock fetch_data is invoked
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
            # Wait for loading to finish
            for _ in range(60):
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
                    except Exception:
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
                except Exception:
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
