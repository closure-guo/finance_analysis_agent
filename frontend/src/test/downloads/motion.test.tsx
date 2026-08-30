import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DownloadCenter } from '../../pages/downloads/DownloadCenter'

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
  Toaster: () => null,
}))

// 仅替换 useReducedMotion：系统开启「减弱动态效果」时动画应完全禁用
vi.mock('framer-motion', async importOriginal => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return { ...actual, useReducedMotion: () => true }
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

describe('下载中心动效降级（add-download-center Task 4）', () => {
  beforeEach(() => {
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
})
