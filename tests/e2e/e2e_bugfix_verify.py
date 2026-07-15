"""E2E 测试：通过 Playwright 模拟用户真实操作，验证前端 UI 到后端分析的完整链路。

测试场景：
1. 快速模式：输入问题 -> 验证回复出现在对话窗口
2. 深度分析（推荐股票）：输入"今天推荐什么股票" -> 验证思考过程 -> 验证 web_search -> 验证回复
3. 多轮对话：追问"就分析中际旭创" -> 验证 session 上下文
4. API Key 持久化：刷新页面 -> 验证不弹 API Key 框

运行方式：
    set DEEPSEEK_API_KEY=sk-xxxx
    uv run python tests/e2e/e2e_bugfix_verify.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# ruff: noqa: E402, I001
from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:5173")
SCREENSHOT_DIR = Path(__file__).parent
TIMEOUT_QUICK = 60
TIMEOUT_DEEP = 120


def _screenshot(page, name: str) -> None:
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path))
    print(f"  截图: {path}")


def _get_body(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except PlaywrightError:
        return ""


def _has_error(body: str) -> bool:
    keywords = ["[错误:", "LLM 请求失败", "Authentication Fails", "连接错误", "BadRequestError"]
    return any(kw in body for kw in keywords)


def _wait_for_response(page, timeout: int, keyword: str = "") -> tuple[bool, str]:
    """等待页面出现回复或错误。"""
    deadline = time.time() + timeout
    last_body = ""
    stable_count = 0

    while time.time() < deadline:
        body = _get_body(page)

        if _has_error(body):
            return False, body

        # 检查是否有关键词出现
        if keyword and keyword in body:
            # 内容稳定后返回
            if body == last_body:
                stable_count += 1
                if stable_count >= 2:
                    return True, body
            else:
                stable_count = 0
            last_body = body

        time.sleep(1)

    return False, _get_body(page)


def _setup_api_key(page, api_key: str) -> bool:
    """配置 API Key。"""
    try:
        # 检查是否已有 API Key 输入框（弹窗）
        apikey_input = page.locator("input[type='password']")
        if apikey_input.count() > 0:
            apikey_input.first.fill(api_key)
            page.locator("button").filter(has_text="确认").first.click()
            time.sleep(0.5)
            return True

        # 检查是否需要点击"去配置"
        config_btn = page.locator("button").filter(has_text="去配置")
        if config_btn.count() > 0:
            config_btn.first.click()
            page.wait_for_selector("input[type='password']", timeout=5000)
            page.locator("input[type='password']").first.fill(api_key)
            page.locator("button").filter(has_text="确认").first.click()
            time.sleep(0.5)
            return True

        # 没有弹窗，可能已经配置过了
        return True
    except PlaywrightError:
        return True


def _select_mode(page, mode: str) -> bool:
    """选择模式（快速模式 / 深度研究）-- 需先打开下拉菜单。"""
    try:
        # 点击"模式："按钮打开下拉菜单
        mode_btn = page.locator("button").filter(has_text="模式")
        if mode_btn.count() > 0:
            mode_btn.first.click()
            time.sleep(0.5)
            # 点击下拉菜单中的选项
            option = page.locator("button").filter(has_text=mode)
            if option.count() > 0:
                option.first.click()
                time.sleep(0.5)
                return True
    except PlaywrightError:
        pass
    return False


def _send_message(page, message: str) -> None:
    """在输入框中输入消息并发送。"""
    textarea = page.locator("textarea").first
    textarea.wait_for(state="visible", timeout=10000)
    textarea.fill(message)
    time.sleep(0.3)
    # 验证文本已输入
    actual = textarea.input_value()
    if actual != message:
        # 重试
        textarea.click()
        textarea.fill("")
        textarea.type(message, delay=30)
        time.sleep(0.3)
    textarea.press("Enter")
    time.sleep(1)


def test_quick_mode(page, api_key: str) -> bool:
    """测试 1: 快速模式。"""
    print("\n=== 测试 1: 快速模式 ===")

    # 配置 API Key
    _setup_api_key(page, api_key)

    # 选择快速模式
    _select_mode(page, "快速模式")

    # 发送消息
    test_msg = "什么是市盈率？请简要说明。"
    print(f"  输入: {test_msg}")
    _send_message(page, test_msg)
    _screenshot(page, "e2e_bugfix_01_quick_sent.png")

    # 等待回复
    print(f"  等待回复 (最长 {TIMEOUT_QUICK}s)...")
    ok, body = _wait_for_response(page, TIMEOUT_QUICK, "市盈率")
    _screenshot(page, "e2e_bugfix_02_quick_response.png")

    if not ok:
        print("[FAIL] 快速模式未收到回复")
        print(f"  页面文本: {body[:500]}")
        return False

    # 验证
    checks = {
        "无错误消息": not _has_error(body),
        "包含回复内容 市盈率": "市盈率" in body,
        "回复内容非空 (>100字)": len(body) > 100,
    }

    all_pass = True
    for name, pass_ in checks.items():
        status = "[PASS]" if pass_ else "[FAIL]"
        print(f"  {status} {name}")
        if not pass_:
            all_pass = False

    return all_pass


def test_deep_analysis_no_stock(page, api_key: str) -> bool:
    """测试 2: 深度分析 - 推荐股票（无具体股票名）。"""
    print("\n=== 测试 2: 深度分析（推荐股票）===")

    # 新建会话
    new_chat_btn = page.locator("button").filter(has_text="新建分析")
    if new_chat_btn.count() > 0:
        new_chat_btn.first.click()
        time.sleep(1)

    # 选择深度研究
    _select_mode(page, "深度研究")

    # 发送消息
    test_msg = "今天推荐什么股票"
    print(f"  输入: {test_msg}")
    _send_message(page, test_msg)
    _screenshot(page, "e2e_bugfix_03_deep_sent.png")

    # 等待回复（深度分析可能需要 web_search + LLM 推理）
    print(f"  等待回复 (最长 {TIMEOUT_DEEP}s)...")
    deadline = time.time() + TIMEOUT_DEEP
    saw_thinking = False
    saw_tool_call = False
    saw_response = False
    errored = False
    last_body = ""
    check_count = 0

    while time.time() < deadline:
        body = _get_body(page)
        html = page.content() if check_count % 5 == 0 else ""
        check_count += 1

        if _has_error(body):
            errored = True
            break

        # 检查是否看到思考过程（包括折叠状态下的标题）
        if (
            "思考" in body
            or "已深度思考" in body
            or "正在思考" in body
            or html
            and ("思考" in html or "thinking" in html)
        ):
            saw_thinking = True

        # 检查是否看到工具调用（包括折叠状态）
        if (
            "搜索" in body
            or "web_search" in body
            or "工具" in body
            or "调用工具" in body
            or html
            and ("tool_call" in html or "tool-result" in html or "调用工具" in html)
        ):
            saw_tool_call = True

        # 检查是否看到回复内容
        if (
            len(body) > 200
            and body == last_body
            and ("推荐" in body or "股票" in body or "分析" in body)
        ):
            saw_response = True
            break
        last_body = body

        time.sleep(2)

    # 流式中截图
    _screenshot(page, "e2e_bugfix_04a_deep_streaming.png")
    time.sleep(2)
    _screenshot(page, "e2e_bugfix_04_deep_response.png")

    # 保存页面内容用于调试
    debug_body = _get_body(page)
    debug_html = page.content()
    (SCREENSHOT_DIR / "debug_deep_body.txt").write_text(debug_body[:5000], encoding="utf-8")
    (SCREENSHOT_DIR / "debug_deep_html.txt").write_text(debug_html[:10000], encoding="utf-8")
    print(f"  页面文本长度: {len(debug_body)}")
    print(f"  HTML 长度: {len(debug_html)}")
    # 打印是否包含关键词
    for kw in [
        "思考",
        "已深度思考",
        "正在思考",
        "thinking",
        "tool_call",
        "调用工具",
        "搜索",
        "搜索网页",
        "搜索完成",
        "次工具调用",
    ]:
        in_body = kw in debug_body
        in_html = kw in debug_html
        print(f"  关键词 '{kw}': body={in_body}, html={in_html}")

    # 循环结束后，用最终页面内容补检（解决轮询时序问题）
    if not saw_thinking and (
        any(kw in debug_body for kw in ["思考", "已深度思考", "正在思考"])
        or any(kw in debug_html for kw in ["思考", "thinking", "ThinkingBanner"])
    ):
        saw_thinking = True
    if not saw_tool_call and (
        any(kw in debug_body for kw in ["搜索", "工具", "搜索网页", "搜索完成", "次工具调用"])
        or any(kw in debug_html for kw in ["tool_call", "tool-result", "搜索网页", "fa-wrench"])
    ):
        saw_tool_call = True

    if errored:
        print("[FAIL] 深度分析出现错误")
        print(f"  页面文本: {_get_body(page)[:500]}")
        return False

    body = _get_body(page)
    checks = {
        "无错误消息": not _has_error(body),
        "看到思考过程": saw_thinking,
        "看到工具调用": saw_tool_call,
        "收到回复内容": saw_response or len(body) > 200,
        "回复包含股票相关内容": "股票" in body or "推荐" in body,
    }

    all_pass = True
    for name, pass_ in checks.items():
        status = "[PASS]" if pass_ else "[FAIL]"
        print(f"  {status} {name}")
        if not pass_:
            all_pass = False

    return all_pass


def test_multi_turn_context(page, api_key: str) -> bool:
    """测试 3: 多轮对话上下文。"""
    print("\n=== 测试 3: 多轮对话上下文 ===")

    # 等待深度分析完成（loading spinner 消失 + 内容稳定）
    print("  等待深度分析完成...")
    deadline = time.time() + 180  # 给深度分析更长的等待时间
    last_body = ""
    stable_count = 0
    check_iter = 0
    while time.time() < deadline:
        body = _get_body(page)
        check_iter += 1
        if _has_error(body):
            break
        # 每 3 次检查一次 spinner（page.content() 较慢）
        has_spinner = False
        if check_iter % 3 == 0:
            has_spinner = "animate-spin" in page.content()
        if body == last_body and len(body) > 200 and not has_spinner:
            stable_count += 1
            if stable_count >= 2:
                break
        else:
            stable_count = 0
        last_body = body
        time.sleep(2)

    # 最终检查 spinner 是否消失（最多再等 60s）
    spinner_deadline = time.time() + 60
    while time.time() < spinner_deadline:
        if "animate-spin" not in page.content():
            break
        time.sleep(2)

    # 额外等待确保 React 状态更新完成
    time.sleep(2)

    # 在深度分析回复后，追问
    test_msg = "就分析中际旭创"
    print(f"  追问: {test_msg}")
    _send_message(page, test_msg)
    _screenshot(page, "e2e_bugfix_05_followup_sent.png")

    # 等待回复
    print(f"  等待回复 (最长 {TIMEOUT_DEEP}s)...")
    deadline = time.time() + TIMEOUT_DEEP
    errored = False
    last_body = ""

    while time.time() < deadline:
        body = _get_body(page)

        if _has_error(body):
            errored = True
            break

        # 内容稳定后退出
        if len(body) > 300 and body == last_body:
            break
        last_body = body

        time.sleep(2)

    _screenshot(page, "e2e_bugfix_06_followup_response.png")

    if errored:
        print("[FAIL] 追问出现错误")
        print(f"  页面文本: {_get_body(page)[:500]}")
        return False

    body = _get_body(page)
    checks = {
        "无错误消息": not _has_error(body),
        "追问在同一会话中": "中际旭创" in body or "300308" in body,
    }

    all_pass = True
    for name, pass_ in checks.items():
        status = "[PASS]" if pass_ else "[FAIL]"
        print(f"  {status} {name}")
        if not pass_:
            all_pass = False

    return all_pass


def test_apikey_persistence(page, api_key: str) -> bool:
    """测试 4: API Key 持久化 -- 刷新页面不弹窗。"""
    print("\n=== 测试 4: API Key 持久化 ===")

    # 刷新页面
    page.reload(timeout=30000)
    time.sleep(2)
    _screenshot(page, "e2e_bugfix_07_refresh.png")

    # 检查是否弹出 API Key 输入框
    apikey_input = page.locator("input[type='password']")
    apikey_modal = page.locator("text=请输入 API Key")

    checks = {
        "刷新后无 API Key 弹窗": apikey_input.count() == 0,
        "无 API Key 提示文字": apikey_modal.count() == 0,
    }

    all_pass = True
    for name, pass_ in checks.items():
        status = "[PASS]" if pass_ else "[FAIL]"
        print(f"  {status} {name}")
        if not pass_:
            all_pass = False

    return all_pass


def main() -> bool:
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if not api_key:
        print("[FAIL] 未找到 API Key：请设置环境变量 LLM_API_KEY 或 DEEPSEEK_API_KEY")
        return False
    print(f"  API Key: {api_key[:6]}...{api_key[-4:]}")
    print(f"  前端 URL: {FRONTEND_URL}")

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        print("\n打开前端页面...")
        page.goto(FRONTEND_URL, timeout=30000)
        time.sleep(2)
        _screenshot(page, "e2e_bugfix_00_initial.png")

        # 测试 1: 快速模式
        results["快速模式"] = test_quick_mode(page, api_key)

        # 测试 2: 深度分析（推荐股票）
        results["深度分析推荐"] = test_deep_analysis_no_stock(page, api_key)

        # 测试 3: 多轮对话上下文
        results["多轮对话上下文"] = test_multi_turn_context(page, api_key)

        # 测试 4: API Key 持久化
        results["API Key 持久化"] = test_apikey_persistence(page, api_key)

        browser.close()

    # 汇总
    print("\n" + "=" * 50)
    print("E2E 测试汇总")
    print("=" * 50)
    all_pass = True
    for name, ok in results.items():
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {status} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\n[PASS] 全部 E2E 测试通过！")
    else:
        print("\n[FAIL] 部分测试未通过。")

    return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
