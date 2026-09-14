"""E2E: ReAct search via frontend Playwright.

Previously this test directly called POST /api/analyze, which is an integration
 test, not an E2E test. This version drives the browser like a real user:
 - configures LLM（密钥 + 端点 + 模型，见下）
 - selects deep mode
 - enters a fuzzy query
 - asserts the conversation leaves the empty state and the ReAct path engages
   （`SearchBanner` 的「正在搜索」出现 = 搜索工具真在跑；或分析启动事件文案）

边界：不等待候选摘要最终产出（ReAct 澄清文案由模型生成，作为判据会误命中；
本用例只锚定事件/UI 驱动的状态迁移）。

凭证来源：仓库根 `.env`（本机 Ark Agent 网关）/ CI secret。Ark 网关（
`LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3`）上的 DeepSeek 为
`openai/deepseek-v4-flash`（与 judge 同款命名，可用 `LLM_E2E_MODEL` 覆盖）；
DeepSeek 官方 key（`sk-…`）+ 空 baseUrl 时走应用内置默认端点——本用例对两种
凭证都成立，故三个字段按 env 填充而非写死。
"""

import os
import sys
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
# Ark Agent 网关（ark- 前缀 key 或显式 baseUrl）用网关上的 DeepSeek
# `openai/deepseek-v4-flash`（与 judge 同款命名）；仅官方 key 时用官方模型名
# （否则官方端点会因未知模型名报错）。两者都可用 `LLM_E2E_MODEL` 覆盖。
_ARK = bool(LLM_BASE_URL) or API_KEY.startswith("ark-")
LLM_MODEL = os.environ.get("LLM_E2E_MODEL") or (
    "openai/deepseek-v4-flash" if _ARK else "deepseek/deepseek-chat"
)
BASE_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")


def _configure_api_key(page):
    """进入设置页 LLM 分区填「密钥 + 端点 + 模型」（settings-center 后为 /settings
    路由页），保存后「← 返回」回首页——否则后续步骤仍在设置页找输入框（旧用例在此挂）。"""
    if page.locator("button").filter(has_text="去配置").count() > 0:
        page.locator("button").filter(has_text="去配置").first.click(timeout=5000)
    else:
        page.locator("button").filter(has_text="设置").first.click(timeout=5000)
    page.wait_for_selector("[data-testid='llm-config-pane']", timeout=10000)
    pane = page.locator("[data-testid='llm-config-pane']")
    pane.locator("input[type='text']").nth(0).fill(LLM_MODEL)
    if LLM_BASE_URL:
        pane.locator("input[type='text']").nth(1).fill(LLM_BASE_URL)
    pane.locator("input[type='password']").fill(API_KEY)
    page.locator("button").filter(has_text="确认").first.click(timeout=5000)
    page.wait_for_timeout(500)
    page.locator("button").filter(has_text="返回").first.click(timeout=5000)
    page.wait_for_timeout(800)


def test_react_search(browser):
    if not API_KEY:
        pytest.skip("LLM_API_KEY / DEEPSEEK_API_KEY not set")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)

        # 1. Configure LLM（密钥 + 端点 + 模型）if needed
        body = page.locator("body").inner_text(timeout=3000)
        if "LLM API 已配置" not in body:
            _configure_api_key(page)
            body = page.locator("body").inner_text(timeout=3000)

        # 2. Select deep mode (if not already)
        if "深度研究" not in body:
            page.locator("button").filter(has_text="模式").first.click(timeout=3000)
            page.wait_for_timeout(200)
        page.locator("button").filter(has_text="深度研究").first.click(timeout=3000)
        page.wait_for_timeout(200)

        # 3. Enter fuzzy query and submit
        textarea = page.locator("textarea").first
        textarea.fill("分析一下光模块龙头企业")
        page.wait_for_timeout(300)
        textarea.press("Enter")

        # 4. 会话离开空态：稳定锚点 = thread-main 挂载 + 用户消息进入正文
        #    （空态分支渲染 empty-state，提交后切换为 thread-main）
        page.wait_for_selector("[data-testid='thread-main']", timeout=30_000)
        thread = page.locator("[data-testid='thread-main']")
        assert "分析一下光模块龙头企业" in thread.inner_text(), "用户消息未进入会话正文"

        # 5. ReAct 路径启动（真 LLM，最多 120s）。
        #    标记只取**事件/UI 驱动**的文案：`正在搜索`（SearchBanner，搜索工具真在跑）、
        #    `正在识别/已识别/开始分析/深度分析进行中`（来自后端 SSE 事件，见
        #    stores/streamStore/reduce.ts）——模型自述文本里的「候选/回复序号」会随
        #    reasoning 流秒级命中，判据无效（2026-09-14 实测 2s 误命中）。
        markers = ("正在搜索", "正在识别", "已识别", "开始分析", "深度分析进行中")
        deadline = time.time() + 120
        resolved = False
        last_body = ""
        while time.time() < deadline:
            last_body = page.locator("body").inner_text(timeout=3000)
            if any(m in last_body for m in markers):
                resolved = True
                break
            if "错误" in last_body or "连接错误" in last_body:
                raise AssertionError(f"UI showed error: {last_body[:500]}")
            time.sleep(1)

        # 失败时 dump 可见文案：真 LLM 端点（Ark/官方）偶发慢或限流，需可诊断
        assert resolved, (
            "UI did not transition to analysis/clarification within 120s；"
            f"最后可见文案：{last_body[-400:]}"
        )
    finally:
        context.close()
