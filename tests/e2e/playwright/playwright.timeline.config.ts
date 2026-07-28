import { defineConfig } from '@playwright/test'

/**
 * 思考-搜索-思考 时间序列专用 E2E 配置（agent-turn-box-display delta 复现测试）
 *
 * 与全局 playwright.config.ts 隔离，使用独立端口对（后端 8001 / 前端 5174），
 * 避免与全局 webServer（8000/5173）冲突，也避免 STUB_SCENARIO=tool_call
 * 影响其他确定性 spec（streaming/contract 等依赖 stub 1 轮完成）。
 *
 * 后端以 TESTING=1 STUB_SCENARIO=tool_call 启动：
 *   - StubLLMClient 走工具调用场景（思考1 -> tool_call(web_search) -> 思考2 -> 回答）
 *   - TESTING=1 时注册 stub web_search 工具（固定结果，不调真实 Tavily）
 * 前端通过 VITE_API_TARGET 指向 8001 后端。
 */
export default defineConfig({
  testDir: './tests',
  // 运行时间序列专用 spec（快速/深度/历史恢复三个场景）
  testMatch: 'thinking-timeline*.spec.ts',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: 'http://localhost:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  webServer: [
    {
      // 后端：TESTING=1 + STUB_SCENARIO=tool_call，确定性模拟思考-搜索-思考
      command: 'uv run uvicorn finance_agent.api:app --port 8001',
      env: { TESTING: '1', STUB_SCENARIO: 'tool_call' },
      url: 'http://localhost:8001/api/health',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      cwd: '../../../',
    },
    {
      // 前端：独立端口 5174，API 代理指向 8001 stub 后端
      command: 'npm run dev -- --port 5174',
      env: { VITE_API_TARGET: 'http://127.0.0.1:8001' },
      url: 'http://localhost:5174',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      cwd: '../../../frontend',
    },
    // ── 管线分组 E2E（agent-turn-box-display delta task 5.5）──
    // 独立端口对（后端 8002 / 前端 5175），STUB_SCENARIO=pipeline 确定性触发
    // 5 层深度分析管线（管线内部 LLM/数据由 _llm_utils/fetch 的 TESTING stub 接管）。
    // 与 tool_call 场景隔离：两组后端 STUB_SCENARIO 不同，不能共用端口。
    {
      command: 'uv run uvicorn finance_agent.api:app --port 8002',
      env: { TESTING: '1', STUB_SCENARIO: 'pipeline' },
      url: 'http://localhost:8002/api/health',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      cwd: '../../../',
    },
    {
      command: 'npm run dev -- --port 5175',
      env: { VITE_API_TARGET: 'http://127.0.0.1:8002' },
      url: 'http://localhost:5175',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      cwd: '../../../frontend',
    },
  ],
})
