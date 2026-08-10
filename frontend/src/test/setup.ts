import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'
import { resetStreamStore } from '../stores/streamStore'

// StreamStore 为模块级单例：跨测试用例共享会导致流状态泄漏（前一个用例的
// session 消息污染后一个用例的视图）。每个用例前重置，保证隔离。
beforeEach(() => {
  resetStreamStore()
})
