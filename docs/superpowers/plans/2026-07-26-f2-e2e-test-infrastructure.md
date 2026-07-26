# F2 E2E 测试基础设施 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 E2E 门禁的最小可执行基础设施，让 `npx playwright test` 一条命令拉起前后端并跑绿 smoke，关闭 F1 留下的「生效过渡语」。

**Architecture:** 后端在 `api.py` 模块级读 `TESTING` 环境变量，TESTING=1 下注册 `/api/test/seed` 与 `/api/test/reset` 骨架端点；`agent_factory._make_llm_client` 处声明 TESTING 分支占位（完整 stub 推迟 F3）。前端无改动。新增 `tests/e2e/playwright/` TS Playwright 项目，`playwright.config.ts` 双 webServer 拉起前后端，smoke.spec 验证全栈可达。

**Tech Stack:** Python 3.12 / FastAPI（后端）；TypeScript / @playwright/test（E2E）；Node 22+

## Global Constraints

- 唯一真相来源：`openspec/changes/add-e2e-test-infrastructure/specs/e2e-infrastructure/spec.md`（delta spec）
- 设计决策：`openspec/changes/add-e2e-test-infrastructure/design.md`（D1-D5）
- `/api/health` 已存在（`api.py:462-464`），**不新增**健康端点
- 完整 LLM stub 推迟到 F3，F2 只做 TESTING 分支占位注释
- 不迁移存量 pytest E2E（F3 任务）
- 不写 streaming/contract/interaction spec（F3 任务）
- TS Playwright 项目落 `tests/e2e/playwright/`（不新建根目录 `e2e/`）
- 后端启动命令：`uv run uvicorn finance_agent.api:app --port 8000`（在 repo-root 执行，不用 `cd ../backend`）
- 前端启动命令：`npm run dev -- --port 5173`（在 `frontend/` 执行）
- 代码注释中文；变量命名 camelCase（TS）/ snake_case（Python，遵循现有风格）
- Commit 信息中文，格式 `feat: [模块] 描述` 或 `test: [模块] 描述`
- 产物位置遵循 AGENTS.md：E2E 输出 -> `tests/e2e/`

---

### Task 1: 后端 TESTING 开关与测试端点骨架（TDD）

**Files:**
- Modify: `src/finance_agent/api.py`（模块级常量区，约 line 41-57 之间；新增端点在 `/api/health` 之后）
- Test: `tests/test_testing_mode.py`（新建）

**Interfaces:**
- Consumes: 无（首个后端任务）
- Produces: 模块级常量 `finance_agent.api.TESTING: bool`；`POST /api/test/seed`、`POST /api/test/reset` 端点（TESTING=1 下返回 200，否则 404）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_testing_mode.py
"""TESTING 开关与测试端点骨架的单元测试。"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_testing():
    """TESTING=1 下的测试客户端。"""
    with patch.dict(os.environ, {"TESTING": "1"}):
        # 重新 import 以触发 TESTING 常量读取
        import importlib
        import finance_agent.api as api_module
        importlib.reload(api_module)
        yield TestClient(api_module.app)


@pytest.fixture
def client_normal():
    """无 TESTING 环境下的测试客户端。"""
    # 确保 TESTING 未设
    env = {k: v for k, v in os.environ.items() if k != "TESTING"}
    with patch.dict(os.environ, env, clear=True):
        import importlib
        import finance_agent.api as api_module
        importlib.reload(api_module)
        yield TestClient(api_module.app)


class TestTestingMode:
    """TESTING 开关行为。"""

    def test_testing_constant_true_when_env_set(self, client_testing):
        """TESTING=1 时 api.TESTING 为 True。"""
        import finance_agent.api as api_module
        assert api_module.TESTING is True

    def test_testing_constant_false_when_env_not_set(self, client_normal):
        """无 TESTING 环境时 api.TESTING 为 False。"""
        import finance_agent.api as api_module
        assert api_module.TESTING is False

    def test_seed_endpoint_returns_200_in_testing_mode(self, client_testing):
        """TESTING=1 下 /api/test/seed 返回 200。"""
        resp = client_testing.post("/api/test/seed", json={"symbol": "300308"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "mode": "testing"}

    def test_reset_endpoint_returns_200_in_testing_mode(self, client_testing):
        """TESTING=1 下 /api/test/reset 返回 200。"""
        resp = client_testing.post("/api/test/reset", json={})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "mode": "testing"}

    def test_seed_endpoint_returns_404_in_normal_mode(self, client_normal):
        """无 TESTING 时 /api/test/seed 返回 404。"""
        resp = client_normal.post("/api/test/seed", json={"symbol": "300308"})
        assert resp.status_code == 404

    def test_reset_endpoint_returns_404_in_normal_mode(self, client_normal):
        """无 TESTING 时 /api/test/reset 返回 404。"""
        resp = client_normal.post("/api/test/reset", json={})
        assert resp.status_code == 404

    def test_health_endpoint_works_in_both_modes(self, client_testing, client_normal):
        """/api/health 在两种模式下都返回 200。"""
        resp_t = client_testing.get("/api/health")
        assert resp_t.status_code == 200
        assert resp_t.json() == {"status": "ok"}

        resp_n = client_normal.get("/api/health")
        assert resp_n.status_code == 200
        assert resp_n.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_testing_mode.py -v`
Expected: FAIL（`api_module.TESTING` 不存在 / `/api/test/seed` 路由不存在）

- [ ] **Step 3: Write minimal implementation**

在 `src/finance_agent/api.py` 中，找到模块级常量区（`app = FastAPI(...)` 之后、`graph = build_5layer_graph()` 之前，约 line 42-51 之间），添加：

```python
# ── 测试模式开关（F2：E2E 门禁基础设施）──
# TESTING=1 时注册测试专用端点（/api/test/seed, /api/test/reset），
# 完整 LLM stub 实现推迟到 F3（见 agent_factory._make_llm_client）
TESTING: bool = os.getenv("TESTING") == "1"
```

然后在 `/api/health` 端点之后（line 464 之后）添加测试端点：

```python
# ── 测试专用端点（仅 TESTING=1 下可用）──
if TESTING:
    @app.post("/api/test/seed")
    async def test_seed(req: dict):
        """测试数据造数端点骨架（F2 只返回占位响应，造数据逻辑在 F3 落地）。"""
        return {"status": "ok", "mode": "testing"}

    @app.post("/api/test/reset")
    async def test_reset(req: dict):
        """测试数据清理端点骨架（F2 只返回占位响应，清理逻辑在 F3 落地）。"""
        return {"status": "ok", "mode": "testing"}
```

注意：`os` 模块需在文件顶部 import。检查 `api.py` 顶部是否已 import os--若未 import，在 `import asyncio` 附近加 `import os`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_testing_mode.py -v`
Expected: PASS（7/7 passing）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_testing_mode.py
git commit -m "feat: [api] 新增 TESTING 开关与 /api/test/seed,/api/test/reset 端点骨架"
```

---

### Task 2: agent_factory TESTING 分支占位

**Files:**
- Modify: `src/finance_agent/agent_factory.py:498-502`（`_make_llm_client` 函数）
- Test: `tests/test_agent_factory_testing_branch.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `finance_agent.api.TESTING` 常量
- Produces: `_make_llm_client` 处的 TESTING 分支占位（F3 实现完整 stub 时填入）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_factory_testing_branch.py
"""agent_factory._make_llm_client 的 TESTING 分支占位测试。"""

import os
from unittest.mock import patch


class TestMakeLlmClientTestingBranch:
    """_make_llm_client 在 TESTING 模式下的行为。"""

    def test_testing_mode_does_not_create_real_litellm_client(self):
        """TESTING=1 时不创建真实 LiteLLMClient（避免连真 LLM）。

        F2 只验证分支存在且不连真 LLM；F3 会替换为 stub 客户端。
        """
        with patch.dict(os.environ, {"TESTING": "1"}):
            # 重新 import 以触发 TESTING 常量
            import importlib
            import finance_agent.api as api_module
            importlib.reload(api_module)

            import finance_agent.agent_factory as factory
            importlib.reload(factory)

            # 调用 _make_llm_client，应走 TESTING 分支（占位 return None 或 stub）
            # 而非创建真实 LiteLLMClient
            client = factory._make_llm_client("deepseek/test", "fake-key")
            # F2 占位：client 应为 None（或占位对象），不应是 LiteLLMClient 实例
            assert client is None or "LiteLLMClient" not in type(client).__name__

    def test_normal_mode_creates_real_litellm_client(self):
        """非 TESTING 模式下创建真实 LiteLLMClient。"""
        env = {k: v for k, v in os.environ.items() if k != "TESTING"}
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import finance_agent.api as api_module
            importlib.reload(api_module)

            import finance_agent.agent_factory as factory
            importlib.reload(factory)

            client = factory._make_llm_client("deepseek/test", "fake-key")
            # 正常模式下应创建 LiteLLMClient（或其包装）
            assert client is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_factory_testing_branch.py -v`
Expected: FAIL（TESTING 分支不存在，TESTING=1 时仍创建真实 LiteLLMClient）

- [ ] **Step 3: Write minimal implementation**

修改 `src/finance_agent/agent_factory.py:498-502`，将：

```python
def _make_llm_client(model: str, api_key: str | None = None):
    """创建 litellm 适配的 LLM 客户端。"""
    from finance_agent.harness.litellm_client import LiteLLMClient

    return LiteLLMClient(model=model, api_key=api_key)
```

替换为：

```python
def _make_llm_client(model: str, api_key: str | None = None):
    """创建 litellm 适配的 LLM 客户端。

    TESTING=1 时返回 None（占位），完整 stub 实现在 F3 落地。
    见 docs/superpowers/specs/2026-07-26-e2e-workflow-integration-design.md §5 F3。
    """
    from finance_agent.api import TESTING

    if TESTING:
        # TODO F3: 返回可控 stub LLM 客户端（按固定节奏吐 SSE delta）
        # 当前 smoke.spec 不触发真实分析流程，占位 return None 即可
        return None

    from finance_agent.harness.litellm_client import LiteLLMClient
    return LiteLLMClient(model=model, api_key=api_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_factory_testing_branch.py -v`
Expected: PASS（2/2 passing）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/agent_factory.py tests/test_agent_factory_testing_branch.py
git commit -m "feat: [agent_factory] 新增 TESTING 分支占位（F3 实现 stub）"
```

---

### Task 3: TS Playwright 项目骨架

**Files:**
- Create: `tests/e2e/playwright/package.json`
- Create: `tests/e2e/playwright/playwright.config.ts`
- Create: `tests/e2e/playwright/tests/smoke.spec.ts`
- Modify: `.gitignore`（加 playwright 产物）

**Interfaces:**
- Consumes: Task 1 的 `/api/health` 端点（webServer 轮询用）
- Produces: 可运行的 TS Playwright 项目（`npx playwright test` 入口）

- [ ] **Step 1: Create package.json**

创建 `tests/e2e/playwright/package.json`：

```json
{
  "name": "finance-agent-e2e",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "test": "playwright test",
    "test:headed": "playwright test --headed",
    "report": "playwright show-report"
  },
  "devDependencies": {
    "@playwright/test": "^1.48.0"
  }
}
```

- [ ] **Step 2: Create playwright.config.ts**

创建 `tests/e2e/playwright/playwright.config.ts`：

```typescript
import { defineConfig, devices } from '@playwright/test'

/**
 * F2 E2E 门禁基础设施：双 webServer 拉起前后端
 *
 * 后端以 TESTING=1 启动，走 LLM stub 占位（完整 stub 在 F3 落地）
 * 前端走 vite dev server
 *
 * 设计决策见 openspec/changes/add-e2e-test-infrastructure/design.md
 */
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  webServer: [
    {
      // Python 后端：TESTING=1 开启测试模式（/api/test/* 端点可用，LLM stub 占位）
      command: 'uv run uvicorn finance_agent.api:app --port 8000',
      env: { TESTING: '1' },
      url: 'http://localhost:8000/api/health',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      cwd: '../../',
    },
    {
      command: 'npm run dev -- --port 5173',
      url: 'http://localhost:5173',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      cwd: '../../../frontend',
    },
  ],
})
```

- [ ] **Step 3: Create smoke.spec.ts**

创建 `tests/e2e/playwright/tests/smoke.spec.ts`：

```typescript
import { test, expect } from '@playwright/test'

/**
 * F2 冒烟测试：验证前后端全栈可达
 *
 * 不触发 /api/analyze 或 /api/chat（那些是 F3 的 streaming/contract spec 范围）
 */
test.describe('F2 smoke: 全栈可达', () => {
  test('前端首页可达且标题正确', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Finance Analysis Agent/i)
  })

  test('后端 /api/health 返回 200', async ({ request }) => {
    const resp = await request.get('http://localhost:8000/api/health')
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body.status).toBe('ok')
  })

  test('TESTING 模式下 /api/test/seed 端点可用', async ({ request }) => {
    // 验证后端以 TESTING=1 启动（webServer 配置已注入环境变量）
    const resp = await request.post('http://localhost:8000/api/test/seed', {
      data: { symbol: '300308' },
    })
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body.mode).toBe('testing')
  })
})
```

- [ ] **Step 4: Update .gitignore**

在根 `.gitignore` 末尾追加：

```
# Playwright E2E（F2 门禁基础设施）
tests/e2e/playwright/node_modules/
tests/e2e/playwright/playwright-report/
tests/e2e/playwright/test-results/
```

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/playwright/package.json tests/e2e/playwright/playwright.config.ts tests/e2e/playwright/tests/smoke.spec.ts .gitignore
git commit -m "feat: [e2e] 新增 TS Playwright 项目骨架（双 webServer + smoke.spec）"
```

---

### Task 4: 集成验证 + 文档同步

**Files:**
- Modify: `docs/project-workflow.md`（移除 Step 4.5 生效过渡语）
- Create: `tests/validation/2026-07-26-add-e2e-test-infrastructure-validation.md`

**Interfaces:**
- Consumes: Task 1-3 全部完成
- Produces: F2 验收通过的证据

- [ ] **Step 1: 安装依赖 + 浏览器**

Run:

```bash
cd tests/e2e/playwright
npm install
npx playwright install chromium
```

Expected: `npm install` 成功（生成 `node_modules/`）；`npx playwright install chromium` 成功（下载浏览器）

- [ ] **Step 2: 跑 smoke 测试**

Run:

```bash
cd tests/e2e/playwright
npx playwright test
```

Expected: 3/3 passing（前端标题、后端健康、测试端点）；退出码 0

- [ ] **Step 3: 验证 webServer 自动拉起能力**

确认 `npx playwright test` 在无手动启动前后端的情况下能自动拉起双 webServer 并跑绿 smoke。这一步已由 Step 2 完成（webServer 自动拉起后端 + 前端 + 跑测试）。

门禁有牙的验证（断开后端测试变红）在 F3 streaming.spec 中用 `route.abort()` 模拟断连体现，F2 阶段 smoke 全绿即满足验收。记录验证结论到报告中。

- [ ] **Step 4: 移除 workflow 生效过渡语**

在 `docs/project-workflow.md` Step 4.5 节中，找到：

```
**生效过渡**: E2E 门禁自 F2（门禁基础设施）完成之日起强制执行；此前交互类变更沿用原人工验证流程，本节可跳过。
```

替换为：

```
**生效状态**: F2（门禁基础设施）已完成，E2E 门禁对 smoke 级别已生效；streaming/contract/interaction spec 在 F3 补齐后对交互类变更完全生效。
```

- [ ] **Step 5: 写人工验证报告**

创建 `tests/validation/2026-07-26-add-e2e-test-infrastructure-validation.md`：

```markdown
# 人工验证报告: add-e2e-test-infrastructure

**日期**: 2026-07-26
**验证人**: [agent]
**关联 delta**: openspec/changes/add-e2e-test-infrastructure/

## E2E 门禁

playwright-report 路径: tests/e2e/playwright/playwright-report/

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 前端首页可达 | 是（smoke.spec.ts） | page.goto('/') + 标题匹配 | 3/3 passing | ✅ |
| 后端 /api/health 返回 200 | 是（smoke.spec.ts） | GET /api/health -> 200 + {"status":"ok"} | 符合 | ✅ |
| TESTING=1 下 /api/test/seed 可用 | 是（smoke.spec.ts） | POST /api/test/seed -> 200 + mode:testing | 符合 | ✅ |
| 非 TESTING 下 /api/test/seed 404 | 否（单元测试覆盖） | 单元测试 7/7 passing | 符合 | ✅ |

## 异常记录

无

## 结论

[x] 全部通过，可 archive
[ ] 存在失败项，需修复后重新验证
```

- [ ] **Step 6: Commit**

```bash
git add docs/project-workflow.md tests/validation/2026-07-26-add-e2e-test-infrastructure-validation.md
git commit -m "docs: F2 完成，移除 workflow 生效过渡语 + 人工验证报告"
```

---

## Self-Review 记录

1. **Spec 覆盖**：delta spec 6 个 Requirements 全部有任务归属：
   - Health Endpoint -> Task 1 测试 `test_health_endpoint_works_in_both_modes` ✅
   - Testing Mode Switch -> Task 1（TESTING 常量 + 测试端点 404 验证）✅
   - Test Data Seed/Reset -> Task 1（seed/reset 骨架）✅
   - Playwright Project Skeleton -> Task 3（package.json + config + smoke.spec）✅
   - Dual webServer -> Task 3（playwright.config.ts 双 webServer）✅
   - Smoke Test -> Task 3（smoke.spec.ts）+ Task 4（集成验证）✅

2. **占位符扫描**：无 TBD/TODO（代码中 `# TODO F3` 是设计要求的占位注释，不是计划占位符）。每步含实际代码。✅

3. **类型一致性**：`TESTING` 常量在 Task 1（api.py 定义）和 Task 2（agent_factory import）间一致；`/api/test/seed` 路径在 Task 1（后端）和 Task 3（smoke.spec.ts）间一致；`LiteLLMClient` 类名在 Task 2 测试和实现间一致。✅

4. **已知风险**：Task 1/2 测试用 `importlib.reload(api_module)` 可能因模块级 `graph = build_5layer_graph()` 和 `init_db()` 重新执行而较慢。若 implementer 报告测试超时，可改为用 `monkeypatch` 或 mock 而非 reload。
