import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    // aguiTestSetup：assistant-ui Viewport 依赖的 jsdom polyfill（ResizeObserver 等），
    // add-assistant-ui-thread 引入，避免改动既有测试文件
    setupFiles: ['./src/test/setup.ts', './src/test/chat/aguiTestSetup.ts'],
    css: true,
  },
})
