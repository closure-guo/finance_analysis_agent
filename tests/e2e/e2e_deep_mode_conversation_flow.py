"""端到端测试：深度分析模式交互流（验证 DSML 泄漏修复 + 管线 UI 不过早出现）。

复用已运行的 Docker 服务（FastAPI:8000 + Vite:5173，含 loop.py/App.tsx 热重载），
Playwright 驱动 Chrome headless 模拟用户真实输入。

验证三个修复点：
  1. 无 DSML 文本泄漏：页面不应出现 `<｜｜DSML｜｜tool_calls>` 等标记
  2. search_stock 走对话流而非管线 UI：澄清/解析阶段不出现管线进度卡片
     （"深度分析进行中"、"Layer"、"节点"、"数据准备" 等管线专属文案）
  3. 澄清通过普通对话进行：Agent 以聊天消息反问，而非直接出现分析管线

使用真实 LLM（从 LLM_API_KEY / DEEPSEEK_API_KEY 读取）。
运行方式：
    python tests/e2e/e2e_deep_mode_conversation_flow.py
"""

from __future__ import annotations

import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # 读取 .env 中的 LLM_API_KEY（配置到前端 UI）

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = Path(__file__).parent
FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000

CLARIFY_TIMEOUT = 120

# 管线 UI 专属文案（仅 run_deep_analysis 触发后才应出现）
PIPELINE_MARKERS = [
    "深度分析进行中",
    "开始深度分析",
    "Layer 0",
    "Layer 1",
    "数据准备",
    "节点完成",
    "基本面分析",
    "宏观分析",
    "舆情分析",
    "技术面分析",
    "报告生成中",
    "分析完成",
]
# DSML 泄漏标记
DSML_MARKERS = ["DSML", "｜｜", "invoke name=", "tool_calls>"]
# 澄清反问关键词
CLARIFY_KEYWORDS = [
    "哪个",
    "哪只",
    "具体",
    "确认",
    "是否",
    "想关注",
    "方面",
    "标的",
    "分析",
    "请",
    "？",
]


def _resolve_api_key() -> str:
    return os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""


def _port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _wait_for_http(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def _screenshot(page, name: str, full_page: bool = False) -> None:
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  截图: {path}")


def _get_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except PlaywrightError:
        return ""


def _setup_api_key(page, api_key: str) -> None:
    try:
        body = page.locator("body").inner_text(timeout=3000)
    except PlaywrightError:
        body = ""
    if "去配置" in body:
        page.locator("button").filter(has_text="去配置").first.click()
        page.wait_for_selector("input[type='password']", timeout=5000)
        page.fill("input[type='password']", api_key)
        page.locator("button").filter(has_text="确认").first.click()
        time.sleep(0.5)
        print("  API Key 已配置")


def _type_and_send(page, text: str) -> None:
    textarea = page.locator("textarea").first
    textarea.fill(text)
    time.sleep(0.3)
    send_btn = page.locator("button:has(i.fa-arrow-up)").first
    send_btn.click()


def _check_services() -> bool:
    if not _port_in_use(BACKEND_HOST, BACKEND_PORT):
        print(f"[FAIL] 后端 {BACKEND_PORT} 未运行，请先 docker compose up -d")
        return False
    if not _port_in_use("127.0.0.1", 5173):
        print("[FAIL] 前端 5173 未运行，请先 docker compose up -d")
        return False
    if not _wait_for_http(f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health", timeout=10):
        print("[FAIL] 后端 health 检查失败")
        return False
    print("  复用运行中的 Docker 服务（含热重载代码）")
    return True


def _run_scenario(page, api_key: str, label: str, query: str) -> dict:
    """单个场景：发送输入，观察 Agent 响应是否符合对话流（非管线 UI）。"""
    print(f"\n[场景] {label}：输入「{query}」")
    page.goto(FRONTEND_URL, timeout=30000)
    time.sleep(1)
    _setup_api_key(page, api_key)
    _screenshot(page, f"deepflow_{label}_01_before.png")

    _type_and_send(page, query)
    print("  已发送，等待 Agent 响应...")

    deadline = time.time() + CLARIFY_TIMEOUT
    got_chat_reply = False
    got_pipeline = False
    got_dsml = False
    first_pipeline_time = None
    start = time.time()

    while time.time() < deadline:
        body = _get_body_text(page)

        # 检测 DSML 泄漏
        if any(m in body for m in DSML_MARKERS):
            got_dsml = True

        # 检测管线 UI 过早出现
        if any(m in body for m in PIPELINE_MARKERS):
            got_pipeline = True
            if first_pipeline_time is None:
                first_pipeline_time = time.time() - start

        # 检测 Agent 聊天回复（反问）
        if body and query in body:
            after = body[body.index(query) + len(query) :]
            if len(after.strip()) > 8 and any(k in after for k in CLARIFY_KEYWORDS):
                got_chat_reply = True

        if got_pipeline and got_dsml:
            break
        if got_chat_reply and time.time() - start > 8:
            # 已有聊天回复，再等几秒确认不会紧接着跳管线
            break

        time.sleep(2)

    time.sleep(1)
    _screenshot(page, f"deepflow_{label}_02_response.png", full_page=True)
    body_text = _get_body_text(page)

    return {
        "got_chat_reply": got_chat_reply,
        "got_pipeline": got_pipeline,
        "got_dsml": got_dsml,
        "first_pipeline_time": first_pipeline_time,
        "body_text": body_text,
    }


def _run_playwright(api_key: str) -> bool:
    print("[*] 启动 Playwright (Chrome headless)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 2000})
        page.goto(FRONTEND_URL, timeout=30000)
        _screenshot(page, "deepflow_00_initial.png")
        _setup_api_key(page, api_key)

        all_pass = True

        # 场景一：歧义输入（应触发 search_stock + 澄清反问，走对话流）
        r1 = _run_scenario(page, api_key, "ambiguous", "光模块龙头")

        print("\n  场景一（歧义输入）验证：")
        checks = {
            "无 DSML 文本泄漏": not r1["got_dsml"],
            "未过早出现管线 UI": not r1["got_pipeline"],
            "Agent 以聊天消息回复（反问）": r1["got_chat_reply"],
        }
        for name, ok in checks.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"    {status} {name}")
            if not ok:
                all_pass = False
        if r1["got_dsml"]:
            print("    [WARN] 检测到 DSML 标记泄漏")
        if r1["got_pipeline"]:
            print(f"    [WARN] 管线 UI 过早出现（{r1['first_pipeline_time']:.1f}s 后）")

        # 场景二：明确股票名称（应触发 search_stock 对话流展示，再澄清/分析）
        r2 = _run_scenario(page, api_key, "stockname", "贵州茅台")

        print("\n  场景二（股票名称）验证：")
        checks2 = {
            "无 DSML 文本泄漏": not r2["got_dsml"],
            "未过早出现管线 UI（search_stock 走对话流）": not r2["got_pipeline"],
            "Agent 有回复（反问或分析）": r2["got_chat_reply"] or r2["got_pipeline"],
        }
        for name, ok in checks2.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"    {status} {name}")
            if not ok:
                all_pass = False

        # 保存页面文本
        report = SCREENSHOT_DIR / "report_deep_mode_conversation_flow.md"
        combined = (
            f"# 深度模式对话流 E2E 报告\n\n"
            f"## 场景一：光模块龙头\n```\n{r1['body_text'][:3000]}\n```\n\n"
            f"## 场景二：贵州茅台\n```\n{r2['body_text'][:3000]}\n```\n"
        )
        report.write_text(combined, encoding="utf-8")
        print(f"\n  页面文本已保存: {report}")

        browser.close()
        if all_pass:
            print("\n[PASS] 深度模式对话流 E2E 测试通过！")
        else:
            print("\n[FAIL] 部分检查未通过。")
        return all_pass


def main() -> bool:
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    api_key = _resolve_api_key()
    if not api_key:
        print("[FAIL] 未找到 API Key：请设置 LLM_API_KEY 或 DEEPSEEK_API_KEY")
        return False
    print(f"  使用 API Key: {api_key[:6]}...{api_key[-4:]} (len={len(api_key)})")

    if not _check_services():
        return False

    return _run_playwright(api_key)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
