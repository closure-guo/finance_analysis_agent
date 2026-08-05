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
  // 时间序列/管线 spec 需要专属 config（playwright.timeline.config.ts，STUB_SCENARIO=tool_call/pipeline/llm_failure），
  // 在默认 config 下排除，避免无 STUB_SCENARIO 时失败
  testIgnore: [
    'thinking-timeline*.spec.ts',
    'harden-react-path-resilience.spec.ts',
    'persist-full-session-timeline.spec.ts',
    'pipeline-eta-banner.spec.ts',
    'pipeline-hierarchical-timeline.spec.ts',
    'resume-pipeline-across-sessions.spec.ts',
    // 以下为前置技术债：使用 waitForTimeout 的时序依赖测试，在 CI 上不稳定，
    // 需专属 STUB_SCENARIO 或在 timeline config 内运行
    'session-switch-resumption.spec.ts',
    'debug-switch-during-response.spec.ts',
  ],
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
      // SESSIONS_DB_PATH 指向独立测试库：与生产 data/sessions.db 共用同一文件时，
      // 两个后端进程并发写会导致 SQLite 主库被 WAL 帧覆盖而彻底损坏（不可恢复）
      command: 'uv run uvicorn finance_agent.api:app --port 8000',
      env: { TESTING: '1', SESSIONS_DB_PATH: 'data/test-e2e-sessions.db' },
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
