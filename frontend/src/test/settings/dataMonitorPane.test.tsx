// DataMonitorPane 数据监控分区（add-agent-settings-center Task 11）
// stub fetch 按 URL 分发，仿 cachePane.test.tsx 范式。
// /api/data-source/status 响应形状与真实后端契约一致：
// { monitor: { hits, misses, fails, last_hit }, freshness: { entries, ..., per_type } }，
// 其中 freshness 为 data_cache.stats 形状（含 bytes/expired/permanent），per_type 含 earliest_expire。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DataMonitorPane } from '../../pages/settings/panes/DataMonitorPane'

// 真实后端契约形状：monitor + freshness(=data_cache.stats)
interface StatusBody {
  monitor: { hits: number; misses: number; fails: Record<string, number>; last_hit: number | null }
  freshness: {
    entries: number
    bytes: number
    expired: number
    permanent: number
    per_type: Array<{ category: string; entries: number; bytes: number | null; earliest_expire: number | null }>
  }
}

const statusBody: StatusBody = {
  monitor: { hits: 5, misses: 2, fails: { kline: 1 }, last_hit: null },
  freshness: {
    entries: 3,
    bytes: 100,
    expired: 1,
    permanent: 0,
    per_type: [{ category: 'kline', entries: 2, bytes: 50, earliest_expire: null }],
  },
}

// 记录全部 fetch 调用（url），便于断言请求。
// 通过全局 __statusFailAt 让第 N 次 /api/data-source/status 请求返回 500（0/缺省 = 永不失败）；
// 通过全局 __statusBody 覆盖返回体（便于构造已过期场景）。
function stubFetch(calls: Array<{ url: string }>) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    calls.push({ url })
    if (url.endsWith('/api/data-source/status')) {
      const failAt = (globalThis as unknown as { __statusFailAt?: number }).__statusFailAt ?? 0
      const count = calls.filter((c) => c.url === '/api/data-source/status').length
      if (failAt > 0 && count === failAt) {
        return Promise.resolve(new Response(JSON.stringify({ error: 'boom' }), { status: 500 }))
      }
      const body = (globalThis as unknown as { __statusBody?: StatusBody }).__statusBody ?? statusBody
      return Promise.resolve(new Response(JSON.stringify(body)))
    }
    return Promise.resolve(new Response(JSON.stringify({ ok: true })))
  }))
}

describe('DataMonitorPane 数据监控分区', () => {
  beforeEach(() => {
    const calls: Array<{ url: string }> = []
    stubFetch(calls)
    ;(globalThis as unknown as { __calls?: Array<{ url: string }> }).__calls = calls
    ;(globalThis as unknown as { __statusFailAt?: number }).__statusFailAt = 0
    ;(globalThis as unknown as { __statusBody?: StatusBody }).__statusBody = undefined
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('挂载即拉取 /api/data-source/status', async () => {
    render(<DataMonitorPane />)
    await screen.findByText('5')
    const calls = (globalThis as unknown as { __calls: Array<{ url: string }> }).__calls
    expect(calls.filter((c) => c.url === '/api/data-source/status').length).toBeGreaterThanOrEqual(1)
  })

  it('展示命中/未命中/失败计数与新鲜度', async () => {
    render(<DataMonitorPane />)
    // 命中 5、未命中 2
    expect(await screen.findByText('5')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    // 失败计数（fails 求和 = 1）与新鲜度类别可见
    expect(screen.getByText('kline')).toBeInTheDocument()
    // 数据新鲜度列表标题
    expect(screen.getByText('数据新鲜度')).toBeInTheDocument()
  })

  it('对最早过期时间已过的类别标记已过期', async () => {
    // earliest_expire 为远早于当前的时间戳（1970 年）→ 应标记已过期
    ;(globalThis as unknown as { __statusBody: StatusBody }).__statusBody = {
      monitor: { hits: 0, misses: 0, fails: {}, last_hit: null },
      freshness: {
        entries: 1, bytes: 10, expired: 1, permanent: 0,
        per_type: [{ category: 'kline', entries: 1, bytes: 10, earliest_expire: 1000 }],
      },
    }
    render(<DataMonitorPane />)
    expect(await screen.findByTestId('freshness-expired-kline')).toBeInTheDocument()
  })

  it('未过期类别不显示已过期标记', async () => {
    // 混合：kline 无过期时间（永久/未过期），daily 为未来时间戳
    ;(globalThis as unknown as { __statusBody: StatusBody }).__statusBody = {
      monitor: { hits: 0, misses: 0, fails: {}, last_hit: null },
      freshness: {
        entries: 2, bytes: 20, expired: 0, permanent: 1,
        per_type: [
          { category: 'kline', entries: 1, bytes: 10, earliest_expire: null },
          { category: 'daily', entries: 1, bytes: 10, earliest_expire: 4102444800 }, // 2100 年
        ],
      },
    }
    render(<DataMonitorPane />)
    await screen.findByText('kline')
    expect(screen.queryByTestId('freshness-expired-kline')).not.toBeInTheDocument()
    expect(screen.queryByTestId('freshness-expired-daily')).not.toBeInTheDocument()
  })

  it('加载失败渲染错误态，点重试后恢复展示', async () => {
    ;(globalThis as unknown as { __statusFailAt: number }).__statusFailAt = 1
    render(<DataMonitorPane />)
    expect(await screen.findByTestId('data-monitor-pane-error')).toBeInTheDocument()
    expect(screen.getByText('数据监控加载失败')).toBeInTheDocument()
    // 首次失败停在错误态（不是「加载中…」）
    expect(screen.queryByText('数据监控加载中…')).not.toBeInTheDocument()
    const retry = screen.getByTestId('data-monitor-retry')
    expect(retry).toBeInTheDocument()
    // 点重试 → 重新加载成功 → 恢复展示，错误态消失
    fireEvent.click(retry)
    expect(await screen.findByText('kline')).toBeInTheDocument()
    expect(screen.queryByTestId('data-monitor-pane-error')).not.toBeInTheDocument()
  })
})
