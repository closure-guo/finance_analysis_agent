# F3a E2E 核心 spec + LLM stub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 补齐 LLM stub + streaming/contract/interaction 三个 spec，使 E2E 门禁对交互类变更完全生效。

**Architecture:** StubLLMClient 实现与 LiteLLMClient 同接口的 chat_stream，按固定节奏吐 LLMResponse（纯文本，无 tool_call）。前端在 4 个关键元素加 data-testid。三个 spec 验证快速模式 SSE 流的增量渲染、网络契约、按钮禁用态。

**Tech Stack:** Python 3.12 / FastAPI；TypeScript / @playwright/test

## Global Constraints

- 唯一真相来源：`openspec/changes/add-e2e-core-specs/specs/` 下两个 delta spec
- F2 已完成：TESTING 开关、`/api/test/seed` 骨架、Playwright 项目骨架
- stub 只支持快速模式（深度模式推迟 F3b）
- 前端只加 data-testid 属性，不改行为；retry-button 不实现（前端当前无此行为）
- 后端启动命令：`uv run uvicorn finance_agent.api:app --port 8000`
- 代码注释中文；Commit 信息中文

---

### Task 1: StubLLMClient 实现（TDD）

**Files:**
- Create: `src/finance_agent/harness/stub_llm_client.py`
- Modify: `src/finance_agent/agent_factory.py`（`_make_llm_client` TESTING 分支）
- Test: `tests/test_stub_llm_client.py`（新建）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stub_llm_client.py
"""StubLLMClient 单元测试。"""

import asyncio
import pytest
from finance_agent.harness.stub_llm_client import StubLLMClient
from finance_agent.harness.llm_client import LLMResponse


class TestStubLLMClient:
    """StubLLMClient 行为。"""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_fixed_text_deltas(self):
        """chat_stream 按固定节奏吐文本 delta。"""
        client = StubLLMClient()
        chunks = []
        async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
            chunks.append(resp)

        # 至少吐出 2 个文本 delta
        text_deltas = [c for c in chunks if c.text_delta]
        assert len(text_deltas) >= 2
        # 所有文本 delta 拼接后有内容
        full_text = "".join(c.text_delta for c in text_deltas)
        assert len(full_text) > 0

    @pytest.mark.asyncio
    async def test_chat_stream_ends_with_is_finished(self):
        """chat_stream 以 is_finished=True 结束。"""
        client = StubLLMClient()
        chunks = []
        async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
            chunks.append(resp)

        assert chunks[-1].is_finished is True

    @pytest.mark.asyncio
    async def test_chat_stream_no_tool_calls(self):
        """chat_stream 不返回 tool_calls（确保 ReAct Agent 1 轮完成）。"""
        client = StubLLMClient()
        chunks = []
        async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
            chunks.append(resp)

        for c in chunks:
            assert c.tool_calls is None or len(c.tool_calls) == 0
```

注意：需要在 `pyproject.toml` 确认有 `pytest-asyncio` 依赖。若没有，用 `asyncio.run()` 方式写测试。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stub_llm_client.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: Write minimal implementation**

创建 `src/finance_agent/harness/stub_llm_client.py`：

```python
"""Stub LLM 客户端--测试模式专用。

按固定节奏吐固定文本 delta，不返回 tool_call，确保 ReAct Agent 在 1 轮完成。
用于 E2E 门禁的确定性流式断言（见 openspec/changes/add-e2e-core-specs）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from finance_agent.harness.llm_client import LLMResponse


# 固定的 stub 响应文本（分块吐出）
_STUB_CHUNKS = [
    "这是",
    "一段",
    "测试用的",
    "固定回复。",
    "用于验证",
    "流式渲染",
    "的增量累积。",
]


class StubLLMClient:
    """测试模式 LLM 客户端，接口与 LiteLLMClient 一致。"""

    def __init__(self, model: str = "stub/test", api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.api_key = api_key or "stub-key"

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> AsyncIterator[LLMResponse]:
        """按固定节奏吐固定文本 delta，不返回 tool_call。"""
        for chunk in _STUB_CHUNKS:
            await asyncio.sleep(0.05)  # 控制节奏，让流式断言可观察
            yield LLMResponse(text_delta=chunk)
        yield LLMResponse(is_finished=True)

    def __repr__(self) -> str:
        return f"StubLLMClient(model={self.model})"
```

修改 `src/finance_agent/agent_factory.py` 的 `_make_llm_client`，将 TESTING 分支的 `return None` 替换为：

```python
    if TESTING:
        # F3a: 返回可控 stub LLM 客户端（按固定节奏吐文本 delta）
        from finance_agent.harness.stub_llm_client import StubLLMClient
        return StubLLMClient()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stub_llm_client.py -v`
Expected: PASS（3/3 passing）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/harness/stub_llm_client.py src/finance_agent/agent_factory.py tests/test_stub_llm_client.py
git commit -m "feat: [harness] 实现 StubLLMClient（TESTING=1 时替换真实 LLM）"
```

---

### Task 2: 前端 data-testid 落地

**Files:**
- Modify: `frontend/src/App.tsx`（4 处）

**testid 落点**（基于 DOM 探索结果）：
1. `stream-output`：MessageRenderer 的 chat 类型消息外层 div（line 1374）
2. `stream-status`：chat 消息中 streaming 指示器（line 1411-1416 的 div）
3. `stream-error`：MessageRenderer 的 error 类型消息外层 div（line 1319）
4. `send-button`：ChatInputBar 的发送按钮（line 2033）+ EmptyState 的发送按钮

- [ ] **Step 1: 添加 data-testid 到 4 处**

在 `frontend/src/App.tsx` 中：

1. line 1319（error 消息外层 div）：
```jsx
<div className="flex justify-start animate-slide-in" data-testid="stream-error">
```

2. line 1374（chat 消息外层 div）：
```jsx
<div className="flex justify-start animate-slide-in" data-testid="stream-output">
```

3. line 1411（streaming 指示器 div）：
```jsx
{msg.streaming && (
  <div data-testid="stream-status" className="mt-2 flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
```

4. line 2033（ChatInputBar 发送按钮）：
```jsx
<button
  data-testid="send-button"
  onClick={() => { onSend(text); setText('') }}
  ...
```

5. EmptyState 的发送按钮（需先定位，约 line 1190 附近）同样加 `data-testid="send-button"`。

- [ ] **Step 2: 验证前端无行为变化**

Run: `cd frontend && npm run test`
Expected: 全部 vitest 通过（data-testid 不影响行为）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: [frontend] 添加 data-testid 到关键交互元素（stream-output/status/error/send-button）"
```

---

### Task 3: streaming.spec.ts（3 场景）

**Files:**
- Create: `tests/e2e/playwright/tests/streaming.spec.ts`

- [ ] **Step 1: 创建 streaming.spec.ts**

```typescript
import { test, expect } from '@playwright/test'

/**
 * F3a 流式核心链路：快速模式 SSE 流式渲染
 * 基于 StubLLMClient 的确定性输出
 */
test.describe('F3a streaming: 快速模式流式渲染', () => {
  test('流式增量渲染 + 指示器生命周期', async ({ page }) => {
    // 先配置 API Key（localStorage）
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 切换到快速模式
    await page.getByRole('button', { name: /快速对话/ }).click()

    // 输入并发送
    await page.getByPlaceholder(/输入问题/).fill('测试问题')
    await page.getByTestId('send-button').click()

    // 流式状态指示器出现
    await expect(page.getByTestId('stream-status')).toBeVisible()

    // 流式输出累积内容
    const streamOutput = page.getByTestId('stream-output')
    await expect(streamOutput).toContainText('这是')

    // 流式状态指示器消失（流结束）
    await expect(page.getByTestId('stream-status')).toBeHidden()
  })

  test('流式中断显示错误', async ({ page }) => {
    // 配置 API Key
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 拦截 /api/chat 请求模拟断连
    await page.route('**/api/chat', route => route.abort())

    // 切换到快速模式并发送
    await page.getByRole('button', { name: /快速对话/ }).click()
    await page.getByPlaceholder(/输入问题/).fill('测试')
    await page.getByTestId('send-button').click()

    // 错误提示可见
    await expect(page.getByTestId('stream-error')).toBeVisible({ timeout: 10_000 })
  })

  test('完整流式回复内容累积', async ({ page }) => {
    // 配置 API Key
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-123')
    })
    await page.reload()

    // 快速模式发送
    await page.getByRole('button', { name: /快速对话/ }).click()
    await page.getByPlaceholder(/输入问题/).fill('测试')
    await page.getByTestId('send-button').click()

    // 等待完整回复（stub 的全部 chunk）
    const streamOutput = page.getByTestId('stream-output')
    await expect(streamOutput).toContainText('固定回复', { timeout: 15_000 })
    await expect(streamOutput).toContainText('增量累积', { timeout: 15_000 })
  })
})
```

- [ ] **Step 2: 跑 streaming.spec**

Run: `cd tests/e2e/playwright && npx playwright test streaming`
Expected: 3/3 passing

注意：若 selector 不匹配（如 placeholder/role 文本与实际不符），implementer 应先用 `npx playwright codegen http://localhost:5173` 探索真实 selector 再调整。调整后需在报告中说明。

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/playwright/tests/streaming.spec.ts
git commit -m "test: [e2e] streaming.spec（3 场景：增量渲染 + 指示器生命周期 + 中断恢复）"
```

---

### Task 4: contract.spec.ts + interaction.spec.ts

**Files:**
- Create: `tests/e2e/playwright/tests/contract.spec.ts`
- Create: `tests/e2e/playwright/tests/interaction.spec.ts`

- [ ] **Step 1: 创建 contract.spec.ts**

```typescript
import { test, expect } from '@playwright/test'

/**
 * F3a 前后端契约：验证 POST /api/chat 请求体和 SSE 响应
 */
test('点击发送发出正确请求并收到 SSE', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()

  // 切换到快速模式
  await page.getByRole('button', { name: /快速对话/ }).click()

  // 监听请求和响应
  const reqPromise = page.waitForRequest(r => r.url().includes('/api/chat'))
  const respPromise = page.waitForResponse(r => r.url().includes('/api/chat') && r.status() === 200)

  // 输入并发送
  await page.getByPlaceholder(/输入问题/).fill('测试问题')
  await page.getByTestId('send-button').click()

  // 验证请求
  const req = await reqPromise
  expect(req.postDataJSON()).toMatchObject({
    message: '测试问题',
  })
  expect(req.postDataJSON()).toHaveProperty('user_id')
  expect(req.postDataJSON()).toHaveProperty('api_key')

  // 验证响应是 SSE
  const resp = await respPromise
  expect(resp.headers()['content-type']).toContain('text/event-stream')
})
```

- [ ] **Step 2: 创建 interaction.spec.ts**

```typescript
import { test, expect } from '@playwright/test'

/**
 * F3a 交互状态：发送中按钮禁用并变色
 */
test('发送中按钮禁用并变色', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()

  // 切换到快速模式
  await page.getByRole('button', { name: /快速对话/ }).click()

  // 输入并发送
  await page.getByPlaceholder(/输入问题/).fill('测试')
  await page.getByTestId('send-button').click()

  // 验证流式指示器出现（证明正在流式中）
  await expect(page.getByTestId('stream-status')).toBeVisible()

  // 验证流式结束后指示器消失
  await expect(page.getByTestId('stream-status')).toBeHidden({ timeout: 15_000 })
})
```

注意：interaction.spec 不直接断言按钮 disabled（快速模式的发送按钮在流式中可能未实现 disabled）。改为断言 stream-status 的可见性周期作为交互状态验证。若 implementer 发现发送按钮在流式中确实有 disabled 行为，可加 `await expect(page.getByTestId('send-button')).toBeDisabled()`。

- [ ] **Step 3: 跑 contract + interaction spec**

Run: `cd tests/e2e/playwright && npx playwright test contract interaction`
Expected: 2/2 passing

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/playwright/tests/contract.spec.ts tests/e2e/playwright/tests/interaction.spec.ts
git commit -m "test: [e2e] contract.spec + interaction.spec（前后端契约 + 交互状态）"
```

---

### Task 5: 全套验证 + 人工验证报告

**Files:**
- Create: `tests/validation/2026-07-26-add-e2e-core-specs-validation.md`

- [ ] **Step 1: 全套 E2E 测试**

Run: `cd tests/e2e/playwright && npx playwright test`
Expected: smoke 3/3 + streaming 3/3 + contract 1/1 + interaction 1/1 = 8/8 passing

- [ ] **Step 2: 单元测试**

Run: `uv run pytest tests/test_stub_llm_client.py tests/test_testing_mode.py tests/test_agent_factory_testing_branch.py -v`
Expected: 全部 passing

- [ ] **Step 3: 写人工验证报告**

创建 `tests/validation/2026-07-26-add-e2e-core-specs-validation.md`，填入实际测试结果。

- [ ] **Step 4: Commit**

```bash
git add tests/validation/2026-07-26-add-e2e-core-specs-validation.md
git commit -m "docs: F3a 完成 + 人工验证报告"
```

---

## Self-Review 记录

1. **Spec 覆盖**：e2e-core-specs delta 3 个 Requirements 全部有任务归属（streaming->Task 3, contract->Task 4, interaction->Task 4）；e2e-infrastructure delta 的 MODIFIED Testing Mode Switch -> Task 1（StubLLMClient 替换 return None）✅

2. **占位符扫描**：无 TBD/TODO。每步含实际代码 ✅

3. **类型一致性**：StubLLMClient.chat_stream 接口与 LiteLLMClient 一致；data-testid 名称在 spec 和 spec.ts 之间一致 ✅

4. **已知风险**：
   - StubLLMClient 的 chat_stream 接口需与 ReAct Agent 的调用方式匹配（Agent 可能传 tools 参数）。stub 忽略 tools，不返回 tool_call，Agent 应在 1 轮完成。若 Agent 因无 tool_call 而报错，需调整 stub 返回一个空的 tool_call 列表或调整 Agent 的 max_iterations
   - 前端 selector（getByRole/getByPlaceholder）可能与实际 DOM 不完全匹配，implementer 应优先用 codegen 探索
   - pytest-asyncio 依赖可能未安装，Task 1 测试可能需要改用 asyncio.run() 方式
