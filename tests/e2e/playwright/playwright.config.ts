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
      cwd: '../../../',
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
