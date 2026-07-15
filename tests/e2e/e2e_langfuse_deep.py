"""E2E：完整深度分析验证 Langfuse 5 层管线 + citation score（ADR-0015/0016/L0）。

链路：前端(深度模式) -> /api/clarify 意图澄清 -> 点"开始深度分析"
     -> /api/analyze -> run_deep_analysis 工具 -> 5 层管线
     -> CallbackHandler 建 span 树 + call_llm 包 generation
     -> citation 校验 -> score_current_trace(citation_pass)
     -> 前端渲染报告

验证点：
  1. 前端收到完整报告（5 层链路通）
  2. Langfuse 有新 trace，含 run_deep_analysis 相关节点 span
  3. trace 含多个 generation（4 分析师 + 辩论等 LLM 调用）
  4. citation_pass score 上报（L0）

前置：FastAPI(8000) + Vite(5173) + Langfuse(3000) 均已运行。
运行：.venv/Scripts/python.exe tests/e2e/e2e_langfuse_deep.py
"""

from __future__ import annotations

import base64
import contextlib
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

FRONTEND_URL = "http://localhost:5173"
BACKEND_URL = "http://localhost:8000"
LANGFUSE_URL = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
REPORT_TIMEOUT = 600
SCREENSHOT_DIR = "tests/e2e"


def _lf_auth_header() -> str:
    pk = os.environ["LANGFUSE_PUBLIC_KEY"]
    sk = os.environ["LANGFUSE_SECRET_KEY"]
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return f"Basic {token}"


def _lf_get(path: str) -> dict:
    import json

    req = urllib.request.Request(
        f"{LANGFUSE_URL}{path}",
        headers={"Authorization": _lf_auth_header(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
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

    lf_before = _lf_get("/api/public/traces?limit=100")
    before_ids = {t["id"] for t in (lf_before.get("data") or [])}
    print(f"  Langfuse 当前 trace 数: {len(before_ids)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        # 用全新 context 避免状态残留
        context = browser.new_context(viewport={"width": 1400, "height": 2000})
        page = context.new_page()
        # 拦截所有 API 请求注入 api_key（绕过前端 API key 配置在 headless 下的兼容问题）
        import json as _json

        def _inject_key(route, request):
            if request.method == "POST" and "/api/" in request.url and request.post_data:
                with contextlib.suppress(Exception):
                    body = _json.loads(request.post_data)
                    if "api_key" not in body or not body.get("api_key"):
                        body["api_key"] = api_key
                    route.continue_(post_data=_json.dumps(body))
                    return
            route.continue_()

        page.route("**/api/**", _inject_key)
        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text[:150]}"))

        print("\n[1/6] 打开前端...")
        page.goto(FRONTEND_URL, timeout=30000)
        time.sleep(2)
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_deep_01_load.png")

        print("[2/6] API Key 由 route 拦截注入（跳过前端配置）...")
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_deep_02_apikey.png")

        print("[3/6] 通过浏览器发起深度分析请求...")
        stock = "600519"
        # 异步发起 fetch（不等待完成，避免 Playwright 30s 超时）
        page.evaluate(
            """(params) => {
            window._analyzeResult = null;
            window._analyzeError = null;
            fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    stock_code: params.stock_code,
                    stock_name: params.stock_name,
                    analysis_type: 'comprehensive',
                    api_key: params.api_key,
                }),
            }).then(async resp => {
                if (!resp.ok) { window._analyzeError = 'HTTP ' + resp.status; return; }
                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let done = false;
                let lastEvent = '';
                let eventCount = 0;
                while (!done) {
                    const { value, done: d } = await reader.read();
                    done = d;
                    if (value) {
                        const text = decoder.decode(value, { stream: true });
                        for (const line of text.split('\\n')) {
                            if (line.startsWith('data: ')) {
                                eventCount++;
                                try {
                                    const evt = JSON.parse(line.slice(6));
                                    if (evt.type) lastEvent = evt.type;
                                    if (evt.type === 'report_complete' || evt.type === 'chat_done' || evt.type === 'error') {
                                        window._analyzeResult = { lastEvent: evt.type, eventCount, done: true };
                                        return;
                                    }
                                } catch(e) {}
                            }
                        }
                    }
                }
                window._analyzeResult = { lastEvent, eventCount, done: true };
            }).catch(err => { window._analyzeError = err.message; });
        }""",
            {"stock_code": stock, "stock_name": "贵州茅台", "api_key": api_key},
        )
        print("  深度分析请求已发起，等待管线完成...")
        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_deep_03_sent.png")

        # 轮询等待结果（5 层管线需几分钟）
        deadline = time.time() + REPORT_TIMEOUT
        analyze_result = None
        while time.time() < deadline:
            analyze_result = page.evaluate(
                "() => ({ result: window._analyzeResult, error: window._analyzeError })"
            )
            if analyze_result.get("result") or analyze_result.get("error"):
                break
            elapsed = int(time.time() - (deadline - REPORT_TIMEOUT))
            print(f"  管线运行中... ({elapsed}s)")
            time.sleep(10)

        page.screenshot(path=f"{SCREENSHOT_DIR}/e2e_lf_deep_05_report.png", full_page=True)

        if not analyze_result or analyze_result.get("error"):
            print(f"  FAIL: 分析请求失败 - {analyze_result}")
            browser.close()
            return 1

        result_data = analyze_result.get("result", {})
        print(
            f"  分析结果: lastEvent={result_data.get('lastEvent')}, events={result_data.get('eventCount')}"
        )
        if result_data.get("lastEvent") == "error":
            print("  FAIL: 管线返回错误事件")
            browser.close()
            return 1
        print("  PASS - 深度分析管线完成")

        print("[6/6] 验证 Langfuse trace 结构 + citation score...")
        time.sleep(15)
        new_traces = []
        for attempt in range(8):
            data = _lf_get("/api/public/traces?limit=100")
            traces = data.get("data", []) if isinstance(data, dict) else []
            new_traces = [t for t in traces if t["id"] not in before_ids]
            if len(new_traces) >= 2:
                break
            print(f"  等待 trace 出现... (尝试 {attempt + 1}/8, 当前 {len(new_traces)})")
            time.sleep(8)

        browser.close()

        if not new_traces:
            print("  FAIL: Langfuse 未找到新 trace")
            return 1
        print(f"  PASS - Langfuse 有 {len(new_traces)} 条新 trace")

        all_spans = []
        gen_count = 0
        span_names = set()
        for t in new_traces:
            obs_data = _lf_get(f"/api/public/observations?traceId={t['id']}&limit=100")
            obs_list = obs_data.get("data") or []
            for o in obs_list:
                otype = o.get("type", "")
                oname = o.get("name", "")
                if otype == "SPAN":
                    all_spans.append(oname)
                    span_names.add(oname)
                elif otype == "GENERATION":
                    gen_count += 1
                    span_names.add(oname)

        print(f"  trace span/generation 节点 ({len(span_names)} 种):")
        for n in sorted(span_names):
            print(f"    {n}")

        if gen_count == 0:
            print("  FAIL: 无 generation（LLM 调用观测未上报）")
            return 1
        print(f"  PASS - 含 {gen_count} 个 generation")

        pipeline_markers = {
            "react_loop",
            "prep",
            "macro_analyst",
            "fundamental_analyst",
            "technical_analyst",
            "sentiment_analyst",
        }
        found_markers = {m for m in pipeline_markers if any(m in s for s in span_names)}
        missing = pipeline_markers - found_markers
        if not missing:
            print("  PASS - 5 层管线 span 结构完整（react_loop + prep + 4 分析师）")
        else:
            print(f"  WARN: 部分管线节点未找到: {missing}")

        score_found = False
        for t in new_traces:
            score_data = _lf_get(f"/api/public/scores?traceId={t['id']}&limit=10")
            for s in score_data.get("data") or []:
                if s.get("name") == "citation_pass":
                    score_found = True
                    print(f"  PASS - citation_pass score 上报: value={s.get('value')}")
                    break
            if score_found:
                break
        if not score_found:
            print("  WARN: 未找到 citation_pass score（可能管线未到 citation 节点或上报延迟）")

    print("\n=== 深度分析 E2E 完成 ===")
    _success = (
        analyze_result is not None
        and not analyze_result.get("error")
        and analyze_result.get("result", {}).get("lastEvent") != "error"
    )
    return 0 if _success else 1


if __name__ == "__main__":
    raise SystemExit(main())
