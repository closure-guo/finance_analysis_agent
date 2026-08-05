import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'

// Bug 复现：深度分析（含 ReAct 股票搜索/澄清阶段）进行中刷新页面，
// 前端丢失 currentSessionId（纯内存，未持久化），回到空状态首页，
// 必须手动点击侧边栏会话才能重新看到 agent 输出，用户感知「内容消失几秒」。
//
// 修复标准（delta spec: restore-session-on-refresh）：
// 1. currentSessionId 持久化到 localStorage（fa_current_session_id）。
// 2. mount 加载会话列表后，自动恢复持久化的进行中会话（无需手动点击）。
// 3. 持久化会话已删除时清除该项并回退空态首页。
// 4. 无持久化会话时保持空态首页（现有行为不回归）。

const runningSession = {
  session_id: 'sess-running',
  stock_code: '300308',
  stock_name: '中际旭创',
  display_name: '中际旭创 深度分析',
  status: 'running',
  session_type: 'analysis',
  created_at: '2026-08-03T10:00:00',
}

const runningSessionDetail = {
  ...runningSession,
  report_markdown: '',
  chart_data: {},
  analyst_reports: {},
  agent_process: {},
  analyst_summaries: {},
  pipeline_snapshot: null,
  pipeline_timelines: null,
  last_seq: 0,
  chat_history: [
    { role: 'user', content: '分析中际旭创', ts: '2026-08-03T10:00:00' },
    {
      role: 'assistant',
      content: '',
      ts: '2026-08-03T10:00:05',
      thinking: 'search_stock 返回唯一：中际旭创(300308)。直接调用 run_deep_analysis。',
      tool_calls: [{ name: 'search_stock', args: '{"query":"中际旭创"}', result_text: '中际旭创(300308)', done: true }],
    },
  ],
}

function buildFetchMock(options: {
  listSessions?: unknown[]
  sessionDetail?: unknown
  sessionDetailStatus?: number
}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()

    // 会话详情
    if (url.startsWith('/api/sessions/') && !url.endsWith('/stream')) {
      if ((options.sessionDetailStatus ?? 200) !== 200) {
        return new Response('Not Found', { status: options.sessionDetailStatus ?? 404 })
      }
      return new Response(JSON.stringify(options.sessionDetail ?? {}), { status: 200 })
    }

    // 会话列表
    if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
      return new Response(JSON.stringify({ sessions: options.listSessions ?? [] }), { status: 200 })
    }

    // SSE stream 等其他端点
    return new Response('', { status: 200 })
  })
}

describe('刷新后自动恢复当前会话', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('localStorage 有进行中会话时，mount 后自动恢复该会话视图（无需手动点击）', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    localStorage.setItem('fa_current_session_id', 'sess-running')
    vi.stubGlobal('fetch', buildFetchMock({
      listSessions: [runningSession],
      sessionDetail: runningSessionDetail,
    }))

    render(<App />)

    // 关键断言：自动恢复会话，重建用户消息与 assistant 思考内容
    // 修复前：停留空态首页（显示特性卡片），需手动点击
    // 修复后：自动 selectSession，显示会话消息
    await waitFor(() => {
      expect(screen.getByText('分析中际旭创')).toBeInTheDocument()
    }, { timeout: 10000 })

    // 不应停留在空态首页
    expect(screen.queryByText('AI 驱动的 A 股投研分析系统')).not.toBeInTheDocument()
  })

  it('持久化会话已被删除时，清除 localStorage 并回退空态首页', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    localStorage.setItem('fa_current_session_id', 'sess-deleted')
    // 列表中不含 sess-deleted
    vi.stubGlobal('fetch', buildFetchMock({ listSessions: [runningSession] }))

    render(<App />)

    // 停留空态首页
    await waitFor(() => {
      expect(screen.getByText('AI 驱动的 A 股投研分析系统')).toBeInTheDocument()
    }, { timeout: 10000 })

    // localStorage 项被清除
    expect(localStorage.getItem('fa_current_session_id')).toBeNull()
  })

  it('无持久化会话时保持空态首页（现有行为不回归）', { timeout: 20000 }, async () => {
    vi.useRealTimers()
    vi.stubGlobal('fetch', buildFetchMock({ listSessions: [runningSession] }))

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('AI 驱动的 A 股投研分析系统')).toBeInTheDocument()
    }, { timeout: 10000 })
  })
})
