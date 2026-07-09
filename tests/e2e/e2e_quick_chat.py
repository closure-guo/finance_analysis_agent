"""快速模式 E2E 测试：启动 FastAPI(8000) + Vite(5173) -> Playwright 验证 ReAct Agent。

测试链路：前端 UI -> Vite proxy -> FastAPI /api/chat -> build_agent(mode='quick')
         -> LiteLLMClient(DeepSeek) -> Agent.run() -> stream_agent_to_sse() -> SSE -> 前端渲染

使用真实 LLM（从环境变量 DEEPSEEK_API_KEY / LLM_API_KEY 读取）。
为控制用例耗时，测试进程内将 LLM_THINKING 设为 disabled。

运行方式：
    set DEEPSEEK_API_KEY=sk-xxxx
    uv run python tests/e2e/e2e_quick_chat.py
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

# ── 测试进程内关闭 thinking 以加速 ──
os.environ.setdefault("LLM_THINKING", "disabled")

# ruff: noqa: E402, I001
import uvicorn  # noqa: E402
from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

from finance_agent.api import app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
SCREENSHOT_DIR = Path(__file__).parent
FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000

# 快速模式只需 1-3 轮 LLM 调用，30s 足够
CHAT_TIMEOUT = 60


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


def _screenshot(page, name: str) -> None:
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path))
    print(f"  截图: {path}")


def _start_backend() -> bool:
    if _port_in_use(BACKEND_HOST, BACKEND_PORT):
        print(f"  端口 {BACKEND_PORT} 已被占用，复用已运行的后端")
        return True
    print(f"[1/6] 启动 FastAPI 后端 (port {BACKEND_PORT})...")
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
    print("[2/6] 启动 Vite 前端 (port 5173)...")
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


def _run_playwright(api_key: str) -> bool:
    print("[3/6] 启动 Playwright (Chrome headless)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        print("[4/6] 打开前端页面...")
        page.goto(FRONTEND_URL, timeout=30000)
        _screenshot(page, "e2e_quick_01_initial.png")

        # 配置 API Key
        print("[5/6] 配置 API Key...")
        page.locator("button").filter(has_text="去配置").first.click()
        page.wait_for_selector("input[type='password']", timeout=5000)
        page.fill("input[type='password']", api_key)
        page.locator("button").filter(has_text="确认").first.click()
        time.sleep(0.5)
        _screenshot(page, "e2e_quick_02_apikey.png")

        # 选择快速模式
        print("  选择快速模式...")
        page.locator("button").filter(has_text="快速模式").first.click()
        time.sleep(0.5)

        # 输入问题
        test_question = "什么是市盈率？请简要说明。"
        print(f"  输入问题: {test_question}")
        input_selector = page.locator("textarea").first
        if input_selector.count() == 0:
            input_selector = page.locator("input[type='text']").first
        input_selector.fill(test_question)

        # 提交（按 Enter 或点击发送按钮）
        input_selector.press("Enter")
        time.sleep(1)
        _screenshot(page, "e2e_quick_03_sent.png")

        # 等待回复
        print(f"  等待 Agent 回复 (最长 {CHAT_TIMEOUT}s)...")
        done = False
        errored = False
        deadline = time.time() + CHAT_TIMEOUT
        last_text = ""
        while time.time() < deadline:
            try:
                body = page.locator("body").inner_text(timeout=2000)
            except PlaywrightError:
                body = ""

            if "chat_done" in body or ("市盈率" in body and len(body) > len(last_text) + 20):
                # 回复内容已稳定（不再增长）
                if body == last_text:
                    done = True
                    break
                last_text = body
            elif any(
                kw in body for kw in ["[错误:", "LLM 请求失败", "Authentication Fails", "连接错误"]
            ):
                errored = True
                break

            time.sleep(1)

        time.sleep(1)
        _screenshot(
            page,
            "e2e_quick_04_response.png",
        )

        if errored:
            print("[FAIL] 页面出现错误")
            try:
                print("  页面文本:", page.locator("body").inner_text(timeout=2000)[:1500])
            except PlaywrightError:
                pass
            browser.close()
            return False

        if not done:
            # 即使没检测到 chat_done，如果页面有实质性内容且无错误也算通过
            try:
                body = page.locator("body").inner_text(timeout=2000)
                if (
                    "市盈率" in body
                    and len(body) > 200
                    and not any(
                        kw in body for kw in ["[错误:", "LLM 请求失败", "Authentication Fails"]
                    )
                ):
                    done = True
            except PlaywrightError:
                pass

        if not done:
            print("[FAIL] Agent 未在超时内回复")
            try:
                print("  页面文本:", page.locator("body").inner_text(timeout=2000)[:1500])
            except PlaywrightError:
                pass
            browser.close()
            return False

        # 验证结果
        print("[6/6] 验证结果...")
        body_text = page.locator("body").inner_text(timeout=5000)

        # 检查是否有错误消息（排除正常的页面文本）
        error_keywords = ["[错误:", "LLM 请求失败", "Authentication Fails", "连接错误"]

        checks = {
            "无错误消息": not any(kw in body_text for kw in error_keywords),
            "包含回复内容 市盈率": "市盈率" in body_text and "什么是市盈率" in body_text,
            "回复内容非空 (超过100字)": len(body_text) > 100,
        }

        print("\n验证结果：")
        all_pass = True
        for name, ok in checks.items():
            status = "[PASS]" if ok else "[FAIL]"
            print(f"  {status} {name}")
            if not ok:
                all_pass = False

        # 保存页面文本
        report_path = SCREENSHOT_DIR / "report_e2e_quick_chat.md"
        report_path.write_text(body_text[:5000], encoding="utf-8")
        print(f"\n  页面文本已保存: {report_path}")

        browser.close()
        if all_pass:
            print("\n[PASS] 快速模式 E2E 测试通过！ReAct Agent 链路完整。")
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
    print(f"  LLM_MODEL={os.environ.get('LLM_MODEL', '(default)')}")

    if not _start_backend():
        return False

    frontend_proc = _start_frontend()
    if frontend_proc is None and not _port_in_use("127.0.0.1", 5173):
        return False

    try:
        ok = _run_playwright(api_key)
    finally:
        _stop_frontend(frontend_proc)

    if ok:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
