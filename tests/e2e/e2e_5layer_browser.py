"""5 层架构浏览器端到端测试：启动 Gradio → Playwright 操作 UI → 截图 + 验证。

运行方式（Mock LLM，无需 API Key）：
    uv run python tests/e2e/e2e_5layer_browser.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
import json
from pathlib import Path


# ── Mock LLM（必须在 app import 之前设置）──


def _mock_llm(prompt: str, system: str = "", **kwargs) -> str:
    s = system.lower() if system else ""
    if "技术面" in system:
        return json.dumps(
            {
                "agent_name": "technical",
                "summary": "技术面偏多，MA5 上穿 MA20，MACD 金叉",
                "key_findings": ["MA5 上穿 MA20", "MACD 金叉", "RSI 58 中性偏强"],
                "claims": [],
                "markdown": "## 技术面分析\n短期趋势向上，MA5 上穿 MA20 形成金叉。",
            },
            ensure_ascii=False,
        )
    if "fund manager" in s:
        return json.dumps(
            {"decision": "approve", "reasoning": "风险可控，建议执行"}, ensure_ascii=False
        )
    if "research manager" in s:
        return "综合多空观点，贵州茅台基本面强劲但估值不低，建议逢低布局。"
    if "bull" in s:
        return json.dumps(
            {
                "role": "bull",
                "round": 1,
                "content": "基本面强劲，ROE 28%+，负债率仅 40%，建议买入",
                "key_arguments": ["ROE 持续高于 25%", "资产负债率低"],
            },
            ensure_ascii=False,
        )
    if "bear" in s:
        return json.dumps(
            {
                "role": "bear",
                "round": 1,
                "content": "估值偏高，PE 25 倍处于历史中高位，需警惕回调",
                "key_arguments": ["PE 处于历史 70 分位"],
            },
            ensure_ascii=False,
        )
    if "trader" in s:
        return json.dumps(
            {
                "action": "buy",
                "confidence": 0.7,
                "reasoning": "基本面强劲，技术面偏多",
                "position_size": "moderate",
            },
            ensure_ascii=False,
        )
    if "aggressive" in s:
        return json.dumps(
            {
                "role": "aggressive",
                "round": 1,
                "content": "上行空间大",
                "key_arguments": ["趋势向好"],
            },
            ensure_ascii=False,
        )
    if "conservative" in s:
        return json.dumps(
            {
                "role": "conservative",
                "round": 1,
                "content": "需控制仓位",
                "key_arguments": ["估值偏高"],
            },
            ensure_ascii=False,
        )
    if "neutral" in s:
        return json.dumps(
            {
                "role": "neutral",
                "round": 1,
                "content": "中性偏多",
                "key_arguments": ["风险收益均衡"],
            },
            ensure_ascii=False,
        )
    if "risk judge" in s:
        return json.dumps(
            {
                "action": "buy",
                "confidence": 0.65,
                "reasoning": "综合风险辩论，建议轻仓买入",
                "position_size": "light",
            },
            ensure_ascii=False,
        )
    return '{"error": "unknown"}'


def _mock_fetch_data(state: dict, cache=None, client=None) -> dict:
    """返回预置财务数据 + K 线，避免 AKShare 网络调用。"""
    import pandas as pd

    code = state.get("stock_code", "")
    n = 30
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
        "kline": pd.DataFrame(
            {
                "日期": pd.date_range("2024-01-02", periods=n, freq="B"),
                "开盘": [float(i) for i in range(10, 10 + n)],
                "收盘": [float(i) for i in range(11, 11 + n)],
                "最高": [float(i) for i in range(11, 11 + n)],
                "最低": [float(i) for i in range(10, 10 + n)],
                "成交量": [1000 + i * 100 for i in range(n)],
            }
        ),
    }


def _setup_mock() -> None:
    """Monkey-patch LLM 和数据获取，避免外部 API 调用。"""
    import finance_agent.llm
    import finance_agent.nodes.analysts
    import finance_agent.nodes.debate
    import finance_agent.nodes.research_manager
    import finance_agent.nodes.trader
    import finance_agent.nodes.risk
    import finance_agent.nodes.fund_manager
    import finance_agent.nodes.fetch

    finance_agent.llm.call_llm = _mock_llm
    finance_agent.nodes.analysts.call_llm = _mock_llm
    finance_agent.nodes.debate.call_llm = _mock_llm
    finance_agent.nodes.research_manager.call_llm = _mock_llm
    finance_agent.nodes.trader.call_llm = _mock_llm
    finance_agent.nodes.risk.call_llm = _mock_llm
    finance_agent.nodes.fund_manager.call_llm = _mock_llm
    finance_agent.nodes.fetch.fetch_data = _mock_fetch_data


# ── Monkey-patch LLM and data before app import ──
_setup_mock()

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

            # Fill API key field (dummy — LLM is mocked)
            print("[3.5/6] 填写 API Key (mock)...")
            api_input = page.get_by_label("DeepSeek API Key").first
            if api_input.count() == 0:
                api_input = page.locator("input[type='password']").first
            if api_input.count() == 0:
                api_input = page.locator("input[type='text']").nth(3)
            api_input.fill("sk-mock-key-for-e2e-test")
            time.sleep(0.3)
            _screenshot(page, "03_5layer_stock.png")

            print("[4/6] 提交分析请求...")
            submit_btn = page.locator("button").filter(has_text="开始分析")
            if submit_btn.count() == 0:
                submit_btn = page.locator("button.primary, button[type='submit']").first
            submit_btn.click()
            _screenshot(page, "04_5layer_submit.png")

            print("[5/6] 等待 5 层分析完成...")
            report_text = ""
            for _ in range(90):
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
