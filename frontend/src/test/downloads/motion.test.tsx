import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DownloadCenter } from '../../pages/downloads/DownloadCenter'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

// 仅替换 useReducedMotion：按用例切换「减弱动态效果」（模块级可变标志 + vi.hoisted 供 mock 工厂安全引用）
const motionState = vi.hoisted(() => ({ reduced: true }))
vi.mock('framer-motion', async importOriginal => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return { ...actual, useReducedMotion: () => motionState.reduced }
})

// 非 reduced 分支下 framer-motion 运行真实动画，jsdom 需 matchMedia 兜底
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (q: string) => ({
        matches: false, media: q, onchange: null,
        addListener: () => {}, removeListener: () => {},
        addEventListener: () => {}, removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    })
  }
})

const files = [
  { file_name: 'a.docx', file_type: 'docx' as const, size_bytes: 1024, created_at: 1_700_000_000_000 },
  { file_name: 'b.pptx', file_type: 'pptx' as const, size_bytes: 2048, created_at: 1_700_000_100_000 },
]

function mockFetch(deleteStatus = 200) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (init?.method === 'DELETE') {
      return Promise.resolve(new Response(JSON.stringify({ deleted: 'x' }), { status: deleteStatus }))
    }
    if (url === '/api/files') {
      return Promise.resolve(new Response(JSON.stringify(files), { status: 200 }))
    }
    return Promise.resolve(new Response('', { status: 200 }))
  })
}

function rowOpacity(row: Element): number {
  return Number((row as HTMLElement).style.opacity || '1')
}

describe('下载中心动效降级（add-download-center Task 4）', () => {
  beforeEach(() => {
    motionState.reduced = true
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('reduced-motion 下列表正常渲染，删除即时切换无动画残留', async () => {
    vi.stubGlobal('fetch', mockFetch())
    render(<DownloadCenter onBack={() => {}} />)
    // 列表照常渲染（入场动画被禁用不阻塞可见性）
    const rows = await screen.findAllByTestId('download-row')
    expect(rows).toHaveLength(2)

    // 删除：exit 动画被禁用，行应即时移除（无等待期）
    fireEvent.click(screen.getAllByTestId('row-delete')[0])
    fireEvent.click(screen.getByTestId('delete-ok'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(1))
  })

  it('非 reduced-motion：首挂载 stagger 入场被调度，筛选切回不重播入场动画', async () => {
    motionState.reduced = false
    vi.stubGlobal('fetch', mockFetch())
    render(<DownloadCenter onBack={() => {}} />)

    // 首挂载：入场动画被调度（行以 opacity < 1 起始，而非直接到位），随后 stagger 渐入全部可见
    const rows = await screen.findAllByTestId('download-row')
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(rowOpacity(row)).toBeLessThan(1)
    }
    await waitFor(() => {
      for (const row of rows) expect(rowOpacity(row)).toBe(1)
    })

    // 筛选切到 Word 再切回全部：新挂载行（b.pptx）不得重播 200ms 入场动画，
    // 行为级断言——切换后立即渲染且不进入 opacity 0 的起始态（无闪烁期）
    fireEvent.click(screen.getByTestId('filter-tab-docx'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(1))
    fireEvent.click(screen.getByTestId('filter-tab-all'))
    const rowsAfter = screen.getAllByTestId('download-row')
    expect(rowsAfter).toHaveLength(2)
    for (const row of rowsAfter) {
      expect(rowOpacity(row)).toBe(1)
    }
  })
})
