"""React + FastAPI 端到端测试：启动 FastAPI(8000) + Vite(5173) → Playwright 验证。

使用真实 LLM（从环境变量 DEEPSEEK_API_KEY / LLM_API_KEY 读取）。
为控制用例耗时，测试进程内将 LLM_THINKING 设为 disabled（仍走真实模型/Key，
仅关闭耗时的思考模式）。如需完整思考模式，请提前 `set LLM_THINKING=enabled`。

运行方式：
    uv run python tests/e2e/e2e_react_browser.py
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

# ── 测试进程内关闭 thinking 以加速（真实 Key + 真实模型，仅跳过昂贵推理）──
# 如外部已显式设置 LLM_THINKING，则尊重外部值。
os.environ.setdefault("LLM_THINKING", "disabled")

# ruff: noqa: E402, I001
import uvicorn  # noqa: E402
from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

from finance_agent.api import app  # noqa: E402
import contextlib

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
SCREENSHOT_DIR = Path(__file__).parent
FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000

# 真实 5 层流水线（多轮 LLM 调用 + AKShare 拉取）最长等待
REPORT_TIMEOUT = 360


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
    print(f"[1/7] 启动 FastAPI 后端 (port {BACKEND_PORT}, 真实 LLM)...")
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
    print("[2/7] 启动 Vite 前端 (port 5173, --strictPort)...")
    proc = subprocess.Popen(
        "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
        shell=True,
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_http(FRONTEND_URL, timeout=60):
        print("[FAIL] Vite 未在 60s 内就绪")
        _stop_frontend(proc)  # 避免孤儿进程
        return None
    print("  Vite 就绪")
    return proc


def _stop_frontend(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


def _run_playwright(api_key: str) -> bool:
    print("[3/7] 启动 Playwright (Chrome headless)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 2000})

        print("[4/7] 打开前端页面...")
        page.goto(FRONTEND_URL, timeout=30000)
        _screenshot(page, "01_react_initial.png")

        # ── 配置 API Key（前端要求有 key 才能开始分析）──
        print("[5/7] 配置 API Key (来自环境变量)...")
        page.locator("button").filter(has_text="去配置").first.click()
        page.wait_for_selector("input[type='password']", timeout=5000)
        page.fill("input[type='password']", api_key)
        page.locator("button").filter(has_text="确认").first.click()
        time.sleep(0.5)
        _screenshot(page, "02_apikey_set.png")

        # ── 触发深度分析（600519 贵州茅台）──
        # 前端 EmptyState 默认 deep；通过下拉框确保 deep 模式
        print("[6/7] 触发深度分析 (600519)...")
        try:
            page.locator("button").filter(has_text="模式").first.click(timeout=3000)
            time.sleep(0.5)
            page.locator("button").filter(has_text="深度研究").first.click(timeout=3000)
            time.sleep(0.5)
        except PlaywrightError:
            pass

        # 输入股票代码并发送
        print("  输入股票代码: 600519")
        textarea = page.locator("textarea").first
        textarea.fill("600519")
        time.sleep(0.3)
        textarea.press("Enter")
        time.sleep(1)
        _screenshot(page, "03_analysis_started.png")

        # 等待报告生成（真实 LLM 多轮调用）
        print(f"  等待 5 层流水线完成 (最长 {REPORT_TIMEOUT}s)...")
        done = False
        errored = False
        deadline = time.time() + REPORT_TIMEOUT
        last_progress = ""
        while time.time() < deadline:
            try:
                body = page.locator("body").inner_text(timeout=2000)
            except PlaywrightError:
                body = ""
            if "分析完成" in body or "深度分析报告" in body:
                done = True
                break
            if "连接错误" in body:
                errored = True
                break
            # 进度提示（pipeline 卡片当前节点描述）
            if body and body != last_progress:
                last_progress = body
            time.sleep(2)

        time.sleep(1)
        _screenshot(page, "04_report_ready.png", full_page=True)

        if errored or not done:
            print("[FAIL] 报告未在超时内生成")
            with contextlib.suppress(PlaywrightError):
                print("  页面文本:", page.locator("body").inner_text(timeout=2000)[:1500])
            browser.close()
            return False

        # ── 验证 ──
        print("[7/7] 验证结果...")
        body_text = page.locator("body").inner_text(timeout=5000)

        checks = {
            "包含股票名称 茅台": "茅台" in body_text,
            "包含报告标题": "投资分析报告" in body_text or "深度分析报告" in body_text,
            "包含交易决策": "决策" in body_text or "买入" in body_text,
            "包含 5 层架构标识": "5 层 Agent" in body_text or "Layer" in body_text,
        }

        print("\n验证结果：")
        all_pass = True
        for name, ok in checks.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"  {status} {name}")
            if not ok:
                all_pass = False

        report_md = SCREENSHOT_DIR / "report_react_browser.md"
        report_md.write_text(body_text[:8000], encoding="utf-8")
        print(f"\n  页面文本已保存: {report_md}")

        browser.close()
        if all_pass:
            print("\n[PASS] React + FastAPI 端到端测试通过！")
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
    print(f"  LLM_THINKING={os.environ.get('LLM_THINKING')}")

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
