import '@testing-library/jest-dom/vitest'
import { beforeEach, vi } from 'vitest'
import { resetStreamStore } from '../stores/streamStore'

// jsdom 缺 matchMedia（PipelineCard 窄屏监听、@xyflow/react 均可能调用）：
// 全局 stub，默认「非窄屏」；个别用例可按需覆盖返回值。
beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  }
})

// StreamStore 为模块级单例：跨测试用例共享会导致流状态泄漏（前一个用例的
// session 消息污染后一个用例的视图）。每个用例前重置，保证隔离。
beforeEach(() => {
  resetStreamStore()
})
