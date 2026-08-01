import { defineConfig } from '@playwright/test'

/**
 * 临时配置：复用已运行的前后端服务，不自动启动 webServer。
 * 用于手动验证会话切换 bug 修复。
 */
export default defineConfig({
  testDir: './tests',
  testIgnore: 'thinking-timeline*.spec.ts',
  timeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
