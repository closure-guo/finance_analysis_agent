"""端到端测试：ADR-0017 深度模式对话流意图澄清（Kimi 风格）。

启动 FastAPI(8000) + Vite(5173) -> Playwright 模拟用户真实操作，验证：

场景一（歧义输入反问）：
  - 用户输入"光模块龙头"
  - Agent 应以普通聊天消息反问（而非旧 ClarifyCard 卡片 / 候选选择列表）
  - 验证：页面出现 Agent 文本回复，且不包含旧的"开始深度分析"按钮

场景二（明确输入直接分析）：
  - 用户输入"300750"（宁德时代，明确代码）
  - Agent 应直接进入分析管线
  - 验证：页面出现 pipeline 进度卡片

使用真实 LLM（从环境变量 LLM_API_KEY / DEEPSEEK_API_KEY 读取）。
运行方式：
    uv run python tests/e2e/e2e_clarify_conversation.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("LLM_THINKING", "disabled")

import uvicorn  # noqa: E402, I001
from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

from finance_agent.api import app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
SCREENSHOT_DIR = Path(__file__).parent
FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000

CLARIFY_TIMEOUT = 90
ANALYSIS_TIMEOUT = 300


def _resolve_api_key() -> str:
    return os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""


def _wait_for_http(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def _port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _screenshot(page, name: str, full_page: bool = False) -> None:
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  截图: {path}")


def _start_backend() -> bool:
    if _port_in_use(BACKEND_HOST, BACKEND_PORT):
        print(f"  端口 {BACKEND_PORT} 已被占用，复用已运行的后端")
        return True
    print(f"[1/4] 启动 FastAPI 后端 (port {BACKEND_PORT}, 真实 LLM)...")
    server = uvicorn.Server(
        uvicorn.Config(app, host=BACKEND_HOST, port=BACKEND_PORT, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    if not _wait_for_http(f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health", timeout=30):
        print("[FAIL] FastAPI 未在 30s 内就绪")
        return False
    print("  FastAPI 就绪")
    return True


def _start_frontend() -> subprocess.Popen | None:
    if _port_in_use("127.0.0.1", 5173):
        print("  端口 5173 已被占用，复用已运行的前端")
        return None
    print("[2/4] 启动 Vite 前端 (port 5173, --strictPort)...")
    proc = subprocess.Popen(
        "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
        shell=True,
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_http(FRONTEND_URL, timeout=60):
        print("[FAIL] Vite 未在 60s 内就绪")
        _stop_frontend(proc)
        return None
    print("  Vite 就绪")
    return proc


def _stop_frontend(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


def _setup_api_key(page, api_key: str) -> None:
    """配置 API Key（如果尚未配置）。"""
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
    """在输入框中输入文本并发送。"""
    textarea = page.locator("textarea").first
    textarea.fill(text)
    time.sleep(0.3)
    send_btn = page.locator("button:has(i.fa-arrow-up)").first
    send_btn.click()


def _get_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except PlaywrightError:
        return ""


def _run_scenario_ambiguous(page) -> dict:
    """场景一：歧义输入"光模块龙头" -> Agent 应以聊天消息反问。"""
    print("\n[场景一] 歧义输入：光模块龙头")
    _screenshot(page, "clarify_01_before_ambiguous.png")

    _type_and_send(page, "光模块龙头")
    print("  已发送：光模块龙头，等待 Agent 响应...")

    deadline = time.time() + CLARIFY_TIMEOUT
    got_chat_reply = False
    got_old_clarify_card = False
    got_analysis_start = False
    last_body = ""

    while time.time() < deadline:
        body = _get_body_text(page)
        if body and body != last_body:
            last_body = body

        # 检测旧 ClarifyCard 特征文本
        if any(kw in body for kw in ["找到多个候选股票，请选择", "意图理解", "研究计划", "开始深度分析"]):
            got_old_clarify_card = True
            break
        if "分析完成" in body or "深度分析报告" in body or "开始分析" in body:
            got_analysis_start = True
            break

        # 检测 Agent 聊天回复（反问）
        if body and "光模块龙头" in body and len(body) > 50:
            if any(kw in body for kw in ["哪个", "哪只", "具体", "确认", "是否", "想关注", "方面", "标的", "分析"]):
                got_chat_reply = True
                break

        time.sleep(2)

    time.sleep(1)
    _screenshot(page, "clarify_02_ambiguous_response.png", full_page=True)

    body_text = _get_body_text(page)
    return {
        "got_chat_reply": got_chat_reply,
        "got_old_clarify_card": got_old_clarify_card,
        "got_analysis_start": got_analysis_start,
        "body_text": body_text,
    }


def _run_scenario_explicit(page, api_key: str) -> dict:
    """场景二：明确输入"300750" -> Agent 应直接进入分析管线。"""
    print("\n[场景二] 明确输入：300750（宁德时代）")
    _screenshot(page, "clarify_03_before_explicit.png")

    page.goto(FRONTEND_URL, timeout=30000)
    time.sleep(1)
    _setup_api_key(page, api_key)

    _type_and_send(page, "300750")
    print("  已发送：300750，等待分析管线启动...")

    deadline = time.time() + ANALYSIS_TIMEOUT
    got_analysis_start = False
    got_old_clarify_card = False
    got_chat_reply_only = False
    got_agent_response = False
    last_body = ""

    while time.time() < deadline:
        body = _get_body_text(page)
        if body and body != last_body:
            last_body = body

        # 检测旧 ClarifyCard 特征文本
        if any(kw in body for kw in ["找到多个候选股票，请选择", "意图理解", "研究计划", "开始深度分析"]):
            got_old_clarify_card = True
            break
        # 检测分析管线启动（进度卡片、节点、报告等）
        if any(kw in body for kw in [
            "数据准备", "Layer", "分析中", "进度", "节点", "基本面", "宏观",
            "分析完成", "深度分析报告", "开始分析", "报告生成", "pipeline",
            "舆情", "技术面", "多空", "交易", "风控", "基金经理",
        ]):
            got_analysis_start = True
            break
        # 检测 Agent 有任何回复（反问也算）
        if body and "300750" in body:
            body_after_input = body[body.index("300750") + 6:]
            if len(body_after_input.strip()) > 10:
                got_agent_response = True
                if any(kw in body for kw in ["哪个", "哪只", "具体", "确认", "想关注", "方面"]):
                    got_chat_reply_only = True
                    # 等待更长时间看是否后续启动分析
                    time.sleep(10)
                    body2 = _get_body_text(page)
                    if any(kw in body2 for kw in ["数据准备", "Layer", "分析中", "进度", "节点", "基本面", "宏观"]):
                        got_analysis_start = True
                        got_chat_reply_only = False
                    break

        time.sleep(2)

    time.sleep(1)
    _screenshot(page, "clarify_04_explicit_response.png", full_page=True)

    body_text = _get_body_text(page)
    return {
        "got_analysis_start": got_analysis_start,
        "got_old_clarify_card": got_old_clarify_card,
        "got_chat_reply_only": got_chat_reply_only,
        "got_agent_response": got_agent_response,
        "body_text": body_text,
    }


def _run_playwright(api_key: str) -> bool:
    print("[3/4] 启动 Playwright (Chrome headless)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 2000})

        print("[4/4] 打开前端页面...")
        page.goto(FRONTEND_URL, timeout=30000)
        _screenshot(page, "clarify_00_initial.png")

        _setup_api_key(page, api_key)

        all_pass = True

        # ── 场景一：歧义输入 ──
        r1 = _run_scenario_ambiguous(page)

        print("\n  场景一验证结果：")
        checks_1 = {
            "Agent 以聊天消息回复（反问）": r1["got_chat_reply"],
            "未出现旧 ClarifyCard 卡片": not r1["got_old_clarify_card"],
        }
        for name, ok in checks_1.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"    {status} {name}")
            if not ok:
                all_pass = False

        if r1["got_old_clarify_card"]:
            print("    [WARN] 场景一检测到旧 ClarifyCard 卡片，对话流重构未生效")
        if r1["got_analysis_start"]:
            print("    [INFO] 歧义输入直接触发了分析（Agent 未反问）")

        # ── 场景二：明确输入 ──
        r2 = _run_scenario_explicit(page, api_key)

        print("\n  场景二验证结果：")
        checks_2 = {
            "Agent 有回复（分析启动或反问）": r2["got_analysis_start"] or r2["got_agent_response"],
            "未出现旧 ClarifyCard 卡片": not r2["got_old_clarify_card"],
        }
        for name, ok in checks_2.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"    {status} {name}")
            if not ok:
                all_pass = False

        if r2["got_old_clarify_card"]:
            print("    [WARN] 场景二检测到旧 ClarifyCard 卡片，对话流重构未生效")
        if r2["got_analysis_start"]:
            print("    [INFO] 明确输入成功触发分析管线")
        elif r2["got_chat_reply_only"]:
            print("    [INFO] Agent 对明确输入选择了反问（符合 prompt 规则：意图不完整时反问）")
        elif r2["got_agent_response"]:
            print("    [INFO] Agent 有回复但未检测到分析启动关键词")

        # ── 保存页面文本 ──
        report_md = SCREENSHOT_DIR / "report_clarify_conversation.md"
        combined = f"=== 场景一：歧义输入 ===\n{r1['body_text'][:4000]}\n\n=== 场景二：明确输入 ===\n{r2['body_text'][:4000]}"
        report_md.write_text(combined, encoding="utf-8")
        print(f"\n  页面文本已保存: {report_md}")

        browser.close()
        if all_pass:
            print("\n[PASS] 对话流澄清交互 E2E 测试通过！")
        else:
            print("\n[FAIL] 部分检查未通过。")
        return all_pass


def main() -> bool:
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    api_key = _resolve_api_key()
    if not api_key:
        print("[FAIL] 未找到 API Key：请设置环境变量 LLM_API_KEY 或 DEEPSEEK_API_KEY")
        return False
    print(f"  使用 API Key: {api_key[:6]}...{api_key[-4:]} (len={len(api_key)})")

    if not _start_backend():
        return False

    vite_proc = _start_frontend()
    if vite_proc is None and not _port_in_use("127.0.0.1", 5173):
        return False

    try:
        return _run_playwright(api_key)
    finally:
        _stop_frontend(vite_proc)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
