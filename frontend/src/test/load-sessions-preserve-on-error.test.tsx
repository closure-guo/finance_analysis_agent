import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'

// Bug 复现：开始深度分析后刷新页面，历史会话列表被清空。
//
// 根因：深度分析运行期间后端事件循环被阻塞，刷新后 mount 时 GET /api/sessions
// 在有限重试窗口（~31.5s / 6 次）内持续失败，loadSessions 静默降级，
// sessions 停留初始空数组 []，侧边栏呈现"历史会话被清空"。
// 此外，即便某次拿到 200 但 body 缺 sessions 字段（代理/中间件异常），
// `data.sessions || []` 也会用空数组覆盖已加载的列表。
//
// 修复标准：
// 1. 刷新场景下，/api/sessions 持续失败时应持续重试（不限于 6 次），
//    后端恢复后列表自动出现。
// 2. 200 但 body 缺 sessions 字段时，视为失败并继续重试（不覆盖为 []）。

describe('分析运行期间刷新，会话列表恢复', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('/api/sessions 持续失败超过 6 次后恢复，列表仍应加载（重试不限次）', { timeout: 90000 }, async () => {
    vi.useRealTimers()

    let sessionsCallCount = 0

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()

      if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
        sessionsCallCount++
        // 前 8 次失败（模拟分析运行期间后端持续阻塞，超过原 6 次重试上限）
        if (sessionsCallCount <= 8) {
          return new Response('Service Unavailable', { status: 503 })
        }
        // 后端恢复
        return new Response(JSON.stringify({
          sessions: [
            { session_id: 's1', display_name: '贵州茅台分析', status: 'completed', created_at: '2026-08-02T10:00:00', session_type: 'analysis' },
          ]
        }), { status: 200 })
      }

      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 关键断言：即便失败次数超过原上限 6 次，后端恢复后列表仍应显示
    // 修复前：6 次后放弃重试，sessions 停留 []，列表永不出现
    // 修复后：持续重试，第 9 次成功，列表显示
    await waitFor(() => {
      expect(screen.getByText('贵州茅台分析')).toBeInTheDocument()
    }, { timeout: 80000 })

    expect(sessionsCallCount).toBeGreaterThan(8)
  })

  it('200 但 body 缺 sessions 字段时视为失败并继续重试', { timeout: 30000 }, async () => {
    vi.useRealTimers()

    let sessionsCallCount = 0

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()

      if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
        sessionsCallCount++
        // 前 2 次：200 但 body 异常（缺 sessions 字段，如代理异常返回 {}）
        if (sessionsCallCount <= 2) {
          return new Response(JSON.stringify({}), { status: 200 })
        }
        return new Response(JSON.stringify({
          sessions: [
            { session_id: 's1', display_name: '贵州茅台分析', status: 'completed', created_at: '2026-08-02T10:00:00', session_type: 'analysis' },
          ]
        }), { status: 200 })
      }

      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 关键断言：缺 sessions 字段的 200 不应被当作成功（否则列表为空且停止重试）
    await waitFor(() => {
      expect(screen.getByText('贵州茅台分析')).toBeInTheDocument()
    }, { timeout: 25000 })

    expect(sessionsCallCount).toBeGreaterThan(2)
  })
})
