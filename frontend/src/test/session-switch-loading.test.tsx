// 会话切换加载过渡（fix-session-switch-flash）：
// 点击历史会话时，switchSession 先把目标会话置 pending（messages 清空），
// loadSession 网络请求期间 deriveAppState 派生出 'empty' → 空态首页闪现。
// 期望：加载期间显示加载圈（session-switch-loading），不闪空态首页。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import App from '../App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('会话切换加载过渡', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  it('详情加载期间显示加载圈，不闪空态首页；加载完成后进入消息流', async () => {
    const detail = {
      session_id: 's1', stock_code: '600519', stock_name: '贵州茅台',
      display_name: '贵州茅台分析', status: 'completed', created_at: '2026-07-01T00:00:00Z',
      duration_ms: 60_000, session_type: 'analysis',
      report_markdown: '', chart_data: {}, analyst_reports: {}, agent_process: {},
      analyst_summaries: {},
      chat_history: [
        { role: 'user', content: '你好' },
        { role: 'assistant', content: '你好！' },
      ],
      pipeline_snapshot: null,
    }
    // 详情响应人为延迟 300ms，制造加载窗口
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'
      if (url === '/api/sessions' && method === 'GET') {
        return new Response(JSON.stringify({ sessions: [{ session_id: 's1', stock_code: '600519', stock_name: '贵州茅台', display_name: '贵州茅台分析', status: 'completed', created_at: '2026-07-01T00:00:00Z', duration_ms: 1, session_type: 'analysis' }] }), { status: 200 })
      }
      if (url.startsWith('/api/sessions/')) {
        await new Promise(r => setTimeout(r, 300))
        return new Response(JSON.stringify(detail), { status: 200 })
      }
      if (url === '/api/llm-config') {
        return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    }))

    render(<App />)
    const item = await screen.findByText('贵州茅台分析')
    fireEvent.click(item)

    // 加载窗口内：加载圈可见，空态首页不得出现
    await waitFor(() => expect(screen.getByTestId('session-switch-loading')).toBeInTheDocument())
    expect(screen.queryByTestId('empty-state')).toBeNull()
    expect(screen.queryByText('今天想研究什么？')).toBeNull()

    // 加载完成：加载圈退场，消息流出现
    await waitFor(() => expect(screen.queryByTestId('session-switch-loading')).toBeNull(), { timeout: 3000 })
    await waitFor(() => expect(screen.getByText('你好！')).toBeInTheDocument())
  })
})
