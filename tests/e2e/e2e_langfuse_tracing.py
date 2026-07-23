"""E2E：验证 Langfuse 集成（ADR-0015/0016/L0）。

链路：前端 UI -> Vite -> FastAPI /api/chat -> ReAct Agent (react_loop span)
     -> LiteLLMClient.chat_stream (generation) -> SSE -> 前端渲染
     -> Langfuse 接收 trace + generation

验证点：
  1. 前端收到 Agent 回复（链路通，集成未破坏）
  2. Langfuse 有对应 trace（tracing 集成工作）
  3. trace 含 generation（LLM 调用观测上报成功）

前置：FastAPI(8000) + Vite(5173) + Langfuse(3000) 均已运行。
运行：.venv/Scripts/python.exe tests/e2e/e2e_langfuse_tracing.py
"""

from __future__ import annotations

import base64
import os
import time
import urllib.request

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

FRONTEND_URL = "http://localhost:5173"
BACKEND_URL = "http://localhost:8000"
LANGFUSE_URL = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
CHAT_TIMEOUT = 90
SCREENSHOT_DIR = "tests/e2e"


def _lf_auth_header() -> str:
    pk = os.environ["LANGFUSE_PUBLIC_KEY"]
    sk = os.environ["LANGFUSE_SECRET_KEY"]
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return f"Basic {token}"


def _lf_get(path: str) -> dict:
    req = urllib.request.Request(
        f"{LANGFUSE_URL}{path}",
        headers={"Authorization": _lf_auth_header(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            import json

            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  [Langfuse API {e.code}] {path}: {body}")
        return {}


def _wait_service(url: str, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except OSError:
            time.sleep(1)
    return False


def main() -> int:
    print("[检查] 服务就绪...")
    if not _wait_service(f"{BACKEND_URL}/api/health", 5):
        print("  FAIL: 后端 8000 未就绪")
        return 1
    if not _wait_service(FRONTEND_URL, 5):
        print("  FAIL: 前端 5173 未就绪")
        return 1
    if not _wait_service(f"{LANGFUSE_URL}/api/public/health", 5):
        print("  FAIL: Langfuse 3000 未就绪")
        return 1
    print("  后端/前端/Langfuse 均就绪")

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if not api_key:
        print("  FAIL: 缺少 LLM_API_KEY")
        return 1

    lf_before = _lf_get("/api/public/traces?limit=50")
    before_ids = {t["id"] for t in (lf_before.get("data") or [])}
    print(f"  Langfuse 当前 trace 数: {len(before_ids)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text[:150]}"))

        print("\n[1/5] 打开前端...")
        page.goto(FRONTEND_URL, timeout=30000)
        time.sleep(2)
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_01_load.png")

        print("[2/5] 配置 API Key...")
        try:
            page.locator("button").filter(has_text="去配置").first.click(timeout=5000)
            page.wait_for_selector("input[type='password']", timeout=5000)
            page.fill("input[type='password']", api_key)
            page.locator("button").filter(has_text="确认").first.click()
            time.sleep(0.5)
        except Exception:
            print("  (API Key 可能已配置，跳过)")
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_02_apikey.png")

        print("[3/5] 选快速模式并提问...")
        # EmptyState 下拉框：先点"模式："展开，再选"快速模式"
        try:
            page.locator("button").filter(has_text="模式").first.click(timeout=5000)
            time.sleep(0.5)
            page.locator("button").filter(has_text="快速模式").first.click(timeout=3000)
            time.sleep(0.3)
            print("  已切换快速模式")
        except Exception:
            print("  (快速模式切换失败，尝试继续)")

        question = "什么是市盈率？请用一句话简要说明。"
        inp = page.locator("textarea").first
        if inp.count() == 0:
            inp = page.locator("input[type='text']").first
        inp.fill(question)
        inp.press("Enter")
        time.sleep(1)
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_03_sent.png")

        print(f"[4/5] 等待 Agent 回复 (最长 {CHAT_TIMEOUT}s)...")
        deadline = time.time() + CHAT_TIMEOUT
        got_reply = False
        errored = False
        body_len_sent = len(page.locator("body").inner_text())
        while time.time() < deadline:
            body = page.locator("body").inner_text()
            if "出错" in body or "error" in body.lower() or "失败" in body:
                errored = True
                break
            if len(body) > body_len_sent + 30 and any(
                k in body for k in ("市盈率", "PE", "每股收益", "股价", "盈利")
            ):
                got_reply = True
                break
            time.sleep(2)
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_04_reply.png")

        if errored:
            print("  FAIL: 前端显示错误")
            print(f"  console: {console_msgs[-5:]}")
            browser.close()
            return 1
        if not got_reply:
            print("  FAIL: 超时未收到回复")
            browser.close()
            return 1
        print("  PASS - 收到 Agent 回复")

        print("[5/5] 验证 Langfuse trace...")
        time.sleep(8)
        new_traces = []
        for attempt in range(6):
            data = _lf_get("/api/public/traces?limit=50")
            traces = data.get("data", []) if isinstance(data, dict) else []
            new_traces = [t for t in traces if t["id"] not in before_ids]
            if new_traces:
                break
            print(f"  等待新 trace 出现... (尝试 {attempt + 1}/6)")
            time.sleep(5)

        browser.close()

        if not new_traces:
            print("  FAIL: Langfuse 未找到新 trace（tracing 集成未生效）")
            return 1
        print(f"  PASS - Langfuse 有 {len(new_traces)} 条新 trace")

        has_generation = False
        has_react_span = False
        for t in new_traces:
            tname = t.get("name", "")
            print(f"    trace: {tname}  session={t.get('sessionId')}")
            if "react" in tname.lower():
                has_react_span = True
            obs_data = _lf_get(f"/api/public/observations?traceId={t['id']}&limit=50")
            for o in obs_data.get("data") or []:
                otype = o.get("type", "")
                oname = o.get("name", "")
                if otype == "GENERATION":
                    has_generation = True
                if "react" in oname.lower():
                    has_react_span = True
                print(f"      {otype}: {oname}")

        if not has_generation:
            print("  WARN: 无 generation（LLM 调用观测未上报）")
            return 1
        print("  PASS - 含 generation（LLM 调用观测上报成功）")
        if has_react_span:
            print("  PASS - 含 react_loop span（ADR-0015 集成机制工作）")
        else:
            print("  WARN: 未找到 react_loop span（可能 trace 命名不同）")

    print("\n=== E2E 全部通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
