import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DownloadCenter } from '../../pages/downloads/DownloadCenter'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

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
  { file_name: '茅台分析报告.docx', file_type: 'docx', size_bytes: 1024, created_at: 1_700_000_000_000 },
  { file_name: '宁德分析报告.pptx', file_type: 'pptx', size_bytes: 2048, created_at: 1_700_000_100_000 },
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

describe('下载中心交互（add-download-center Task 3）', () => {
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  async function renderList(deleteStatus = 200) {
    const fetchMock = mockFetch(deleteStatus)
    vi.stubGlobal('fetch', fetchMock)
    render(<DownloadCenter onBack={() => {}} />)
    await screen.findAllByTestId('download-row')
    return fetchMock
  }

  function deleteCalls(fetchMock: ReturnType<typeof mockFetch>) {
    return fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')
  }

  it('搜索与类型筛选叠加生效', async () => {
    await renderList()
    fireEvent.click(screen.getByTestId('filter-tab-docx'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(1))
    fireEvent.click(screen.getByTestId('filter-tab-all'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(2))
    fireEvent.change(screen.getByTestId('downloads-search'), { target: { value: '宁德' } })
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(1))
    expect(screen.getByTestId('download-row').getAttribute('data-file-name')).toBe('宁德分析报告.pptx')
    // 叠加：类型 PPT + 搜索「茅台」→ 空
    fireEvent.click(screen.getByTestId('filter-tab-pptx'))
    fireEvent.change(screen.getByTestId('downloads-search'), { target: { value: '茅台' } })
    await waitFor(() => expect(screen.queryByTestId('download-row')).toBeNull())
  })

  it('下载按钮 loading 后恢复并 toast「已开始下载」', async () => {
    await renderList()
    const row = screen.getAllByTestId('download-row')[0]
    fireEvent.click(row.querySelector('[aria-label="下载"]')!)
    const btn = row.querySelector('[aria-label="下载"]') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    const { toast } = await import('sonner')
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已开始下载'), { timeout: 1500 })
    await waitFor(() => expect(btn.disabled).toBe(false))
  })

  it('千行列表增量渲染：首屏 50 行，加载更多后翻页', async () => {
    const many = Array.from({ length: 120 }, (_, i) => ({
      file_name: `报告_${String(i).padStart(3, '0')}.docx`,
      file_type: 'docx',
      size_bytes: 1024,
      created_at: 1_700_000_000_000 + i,
    }))
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/files') return Promise.resolve(new Response(JSON.stringify(many), { status: 200 }))
      return Promise.resolve(new Response('', { status: 200 }))
    }))
    render(<DownloadCenter onBack={() => {}} />)
    // 首屏只渲染 PAGE_SIZE=50 行，而非 120 行全量 DOM + 全量动画节点
    await screen.findAllByTestId('download-row')
    expect(screen.getAllByTestId('download-row')).toHaveLength(50)
    expect(screen.getByTestId('load-more').textContent).toContain('剩余 70 个')
    fireEvent.click(screen.getByTestId('load-more'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(100))
    fireEvent.click(screen.getByTestId('load-more'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(120))
    // 加载完所有行后入口消失
    expect(screen.queryByTestId('load-more')).toBeNull()
  })

  it('取消删除不发出请求', async () => {
    const fetchMock = await renderList()
    fireEvent.click(screen.getAllByTestId('row-delete')[0])
    expect(screen.getByTestId('delete-confirm')).toBeTruthy()
    fireEvent.click(screen.getByTestId('delete-cancel'))
    await waitFor(() => expect(screen.queryByTestId('delete-confirm')).toBeNull())
    expect(deleteCalls(fetchMock)).toHaveLength(0)
    expect(screen.getAllByTestId('download-row')).toHaveLength(2)
  })

  it('确认删除成功：行乐观移除后不再出现', async () => {
    const fetchMock = await renderList()
    fireEvent.click(screen.getAllByTestId('row-delete')[0])
    fireEvent.click(screen.getByTestId('delete-ok'))
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(1))
    expect(deleteCalls(fetchMock)).toHaveLength(1)
    const { toast } = await import('sonner')
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已删除'))
    // 回滚不发生：行数保持 1
    await new Promise(r => setTimeout(r, 50))
    expect(screen.getAllByTestId('download-row')).toHaveLength(1)
  })

  it('确认删除接口失败：行恢复 + toast 报错', async () => {
    const fetchMock = await renderList(500)
    fireEvent.click(screen.getAllByTestId('row-delete')[0])
    fireEvent.click(screen.getByTestId('delete-ok'))
    // 失败回滚：行重新出现
    await waitFor(() => expect(screen.getAllByTestId('download-row')).toHaveLength(2))
    expect(deleteCalls(fetchMock)).toHaveLength(1)
    const { toast } = await import('sonner')
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('删除失败，请重试'))
  })
})
