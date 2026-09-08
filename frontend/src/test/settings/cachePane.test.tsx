// CachePane 缓存管理分区（add-agent-settings-center Task 8）
// stub fetch 按 URL 分发，仿 trackRecordPage.test.tsx 范式
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CachePane } from '../../pages/settings/panes/CachePane'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

const statsBody = {
  data: { entries: 3, bytes: 100, expired: 1, permanent: 1,
          per_type: [{ category: 'kline', entries: 2, bytes: 50, earliest_expire: 123 }] },
  probe: { entries: 0, expired: 0 },
  monitor: { hits: 1, misses: 0, fails: {}, last_hit: 123 },
}

// 记录全部 fetch 调用（url + init），便于断言请求体
function stubFetch(calls: Array<{ url: string; init?: RequestInit }>) {
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/api/cache/stats')) {
      return Promise.resolve(new Response(JSON.stringify(statsBody)))
    }
    return Promise.resolve(new Response(JSON.stringify({ ok: true })))
  }))
}

describe('CachePane 缓存管理分区', () => {
  beforeEach(() => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    stubFetch(calls)
    ;(globalThis as unknown as { __calls?: Array<{ url: string; init?: RequestInit }> }).__calls = calls
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  function captureCalls() {
    return (globalThis as unknown as { __calls: Array<{ url: string; init?: RequestInit }> }).__calls
  }

  it('展示汇总统计与类别表格', async () => {
    render(<CachePane />)
    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByText('kline')).toBeInTheDocument()
  })

  it('按类别清空调用 /api/cache/clear', async () => {
    render(<CachePane />)
    fireEvent.click(await screen.findByText('清空该类'))
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/cache/clear', expect.any(Object)))
  })

  it('按类别清空提交 scope=type 与 data_type 并刷新统计', async () => {
    render(<CachePane />)
    await screen.findByText('kline')
    fireEvent.click(screen.getByText('清空该类'))
    await waitFor(() => {
      const call = captureCalls().find(c => c.url === '/api/cache/clear')
      expect(call).toBeTruthy()
      expect(JSON.parse(call!.init!.body as string)).toEqual({ scope: 'type', data_type: 'kline' })
    })
    // 操作后刷新 stats（初次挂载 + 清空后各一次）
    await waitFor(() => {
      expect(captureCalls().filter(c => c.url === '/api/cache/stats').length).toBeGreaterThanOrEqual(2)
    })
  })

  it('按股票代码清理提交 scope=code 与 code', async () => {
    render(<CachePane />)
    await screen.findByText('kline')
    fireEvent.change(screen.getByTestId('cache-code-input'), { target: { value: '600519' } })
    fireEvent.click(screen.getByTestId('cache-code-clear'))
    await waitFor(() => {
      const call = captureCalls().find(c => c.url === '/api/cache/clear' && c.init && /"code"/.test(c.init.body as string))
      expect(call).toBeTruthy()
      expect(JSON.parse(call!.init!.body as string)).toEqual({ scope: 'code', code: '600519' })
    })
  })

  it('代码为空时不发起清理请求', async () => {
    render(<CachePane />)
    await screen.findByText('kline')
    fireEvent.click(screen.getByTestId('cache-code-clear'))
    await waitFor(() => {
      // 允许环形等待：确认没有发出 clear 请求
      expect(captureCalls().filter(c => c.url === '/api/cache/clear')).toHaveLength(0)
    })
  })

  it('全部清空需输入「清空」确认：输入不符不请求，正确后调 scope=all confirm=true', async () => {
    render(<CachePane />)
    await screen.findByText('kline')
    fireEvent.click(screen.getByTestId('cache-clear-all'))
    // 确认框出现，未输入时提交按钮不可用
    expect(screen.getByTestId('cache-clear-all-confirm')).toBeInTheDocument()
    const submit = screen.getByTestId('cache-clear-all-submit')
    expect(submit).toBeDisabled()
    // 输入错误文本仍不可用
    fireEvent.change(screen.getByTestId('cache-clear-all-input'), { target: { value: '空' } })
    expect(submit).toBeDisabled()
    // 输入「清空」后可用，提交
    fireEvent.change(screen.getByTestId('cache-clear-all-input'), { target: { value: '清空' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await waitFor(() => {
      const call = captureCalls().find(c => c.url === '/api/cache/clear' && c.init && /"scope":"all"/.test(c.init.body as string))
      expect(call).toBeTruthy()
      expect(JSON.parse(call!.init!.body as string)).toEqual({ scope: 'all', confirm: true })
    })
    // 提交后关闭确认框
    await waitFor(() => {
      expect(screen.queryByTestId('cache-clear-all-confirm')).not.toBeInTheDocument()
    })
  })

  it('全部清空取消时不发起任何请求', async () => {
    render(<CachePane />)
    await screen.findByText('kline')
    fireEvent.click(screen.getByTestId('cache-clear-all'))
    fireEvent.click(screen.getByTestId('cache-clear-all-cancel'))
    await waitFor(() => {
      expect(captureCalls().filter(c => c.url === '/api/cache/clear')).toHaveLength(0)
    })
  })

  it('能力探测缓存一键清除调用 /api/cache/probe-cache/clear', async () => {
    render(<CachePane />)
    await screen.findByText('kline')
    fireEvent.click(screen.getByTestId('cache-probe-clear'))
    await waitFor(() => {
      expect(captureCalls().some(c => c.url === '/api/cache/probe-cache/clear')).toBe(true)
    })
  })
})