import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'

// Bug 复现：docker compose up 后后端需要 ~4 秒才就绪，前端 depends_on 只等
// service_started，导致首次 loadSessions 的 fetch 失败（502/连接拒绝），
// sessions 保持空数组，用户看不到历史会话，需要手动刷新才能看到。
//
// 修复标准：loadSessions 首次失败时应自动重试（退避），后端就绪后重试成功，
// sessions 列表自动显示，无需手动刷新。

describe('首次加载失败后自动重试 loadSessions', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('首次 /api/sessions 失败后重试，最终显示历史会话', { timeout: 20000 }, async () => {
    vi.useRealTimers()

    let sessionsCallCount = 0

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()

      // /api/sessions：首次返回 502（后端未就绪），第二次返回 200（后端就绪）
      if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
        sessionsCallCount++
        if (sessionsCallCount === 1) {
          // 首次：模拟后端未就绪（nginx 返回 502）
          return new Response('Bad Gateway', { status: 502 })
        }
        // 重试：返回 2 个历史会话
        return new Response(JSON.stringify({
          sessions: [
            { session_id: 's1', display_name: '贵州茅台分析', status: 'completed', created_at: '2026-08-02T10:00:00', session_type: 'analysis' },
            { session_id: 's2', display_name: '中际旭创分析', status: 'completed', created_at: '2026-08-02T09:00:00', session_type: 'analysis' },
          ]
        }), { status: 200 })
      }

      // 其他请求默认返回空
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    // 关键断言：首次失败后，重试应成功，历史会话最终显示在侧边栏
    // 修复前：首次 502 -> catch -> sessions 保持空数组 -> 不重试 -> 侧边栏空
    // 修复后：首次 502 -> catch -> 退避重试 -> 第二次 200 -> sessions 更新 -> 侧边栏显示
    await waitFor(() => {
      expect(screen.getByText('贵州茅台分析')).toBeInTheDocument()
      expect(screen.getByText('中际旭创分析')).toBeInTheDocument()
    }, { timeout: 15000 })

    // 验证确实发生了重试（至少 2 次 /api/sessions 请求）
    expect(sessionsCallCount).toBeGreaterThanOrEqual(2)
  })
})
