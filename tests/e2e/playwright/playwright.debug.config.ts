import { defineConfig } from '@playwright/test'

/**
 * 调试配置：复用 Docker 中已运行的服务（后端 8000 / 前端 5173）
 * 不启动 webServer，避免端口冲突
 */
export default defineConfig({
  testDir: './tests',
  testMatch: ['debug-*.spec.ts'],
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
