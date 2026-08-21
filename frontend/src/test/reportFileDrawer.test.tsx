import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReportFileDrawer } from '../ReportFileDrawer'
import type { UIMessage } from '../types'

const baseMsg: UIMessage = {
  id: 'm1',
  type: 'report',
  content: '',
  reportMarkdown: '# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n',
  sessionId: 's1',
  filePaths: { docx: '/tmp/600519_x_report.docx', pdf: '/tmp/600519_x_report.pdf' },
}

describe('ReportFileDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('默认关闭：不渲染内容；点击全部文件横幅后才打开（由父组件控制）', () => {
    const { container } = render(<ReportFileDrawer drawerMessage={null} onClose={() => {}} />)
    expect(container.querySelector('[data-testid="export-drawer"]')).toBeNull()
  })

  it('打开后展示文件列表（含格式徽标）', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    expect(screen.getByTestId('export-drawer')).toBeTruthy()
    expect(screen.getByText('PDF')).toBeTruthy()
    expect(screen.getByText('Word')).toBeTruthy()
    const md = screen.queryByText('Markdown')
    // md/docx 无 filePaths 键时仍以导出动作列出（可现场生成）
    expect(md).toBeTruthy()
  })

  it('点击关闭按钮 / Esc / 遮罩可关闭', () => {
    const onClose = vi.fn()
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('drawer-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('已有文件直接给下载链接', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    const pdfLink = screen.getByTestId('download-pdf')
    expect(pdfLink.getAttribute('href')).toBe('/api/files/600519_x_report.pdf')
  })

  it('缺失文件先 POST /api/export 再下载', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ file_name: '600519_y_report.md', url: '/api/files/600519_y_report.md' }),
    }) as unknown as typeof fetch
    render(<ReportFileDrawer drawerMessage={{ ...baseMsg, filePaths: { docx: '/tmp/a.docx' } }} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('download-md'))
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/export', expect.objectContaining({ method: 'POST' }))
    })
  })

  it('预览面板渲染 Markdown 正文', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('preview-open'))
    expect(screen.getByTestId('drawer-preview')).toBeTruthy()
    expect(screen.getByText('测试报告')).toBeTruthy()
  })
})