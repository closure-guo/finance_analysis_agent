import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReportFileDrawer } from '../ReportFileDrawer'
import type { UIMessage } from '../types'

const baseMsg: UIMessage = {
  id: 'm1',
  type: 'report',
  content: '',
  reportMarkdown: '# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n',
  sessionId: 's1',
  filePaths: {
    docx: '/tmp/贵州茅台_600519_x_report.docx',
    pdf: '/tmp/贵州茅台_600519_x_report.pdf',
  },
}

describe('ReportFileDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('默认关闭：drawerMessage 为 null 时不渲染', () => {
    const { container } = render(<ReportFileDrawer drawerMessage={null} onClose={() => {}} />)
    expect(container.querySelector('[data-testid="export-drawer"]')).toBeNull()
  })

  it('打开后自上而下仅列出 filePaths 已生成的可下载文件', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    expect(screen.getByTestId('export-drawer')).toBeTruthy()
    expect(screen.getByText('贵州茅台_600519_x_report.docx')).toBeTruthy()
    expect(screen.getByText('贵州茅台_600519_x_report.pdf')).toBeTruthy()
    const pdfLink = screen.getByTestId('download-file-pdf')
    expect(pdfLink.getAttribute('href')).toBe('/api/files/贵州茅台_600519_x_report.pdf')
    expect(pdfLink.getAttribute('download')).toBe('贵州茅台_600519_x_report.pdf')
  })

  it('不再显示 PDF/Word/Markdown 三格式行，无现场生成按钮', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    expect(screen.queryByText('PDF')).toBeNull()
    expect(screen.queryByText('Word')).toBeNull()
    expect(screen.queryByText('Markdown')).toBeNull()
    expect(screen.queryByTestId('download-md')).toBeNull()
    expect(screen.queryByTestId('download-pdf')).toBeNull() // 旧 testid 已废弃
  })

  it('filePaths 为空时展示空态提示', () => {
    render(<ReportFileDrawer drawerMessage={{ ...baseMsg, filePaths: {} }} onClose={() => {}} />)
    expect(screen.getByText('暂无已生成文件')).toBeTruthy()
  })

  it('点击关闭按钮 / Esc / 遮罩可关闭', () => {
    const onClose = vi.fn()
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('drawer-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('预览面板渲染 Markdown 正文', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('preview-open'))
    expect(screen.getByTestId('drawer-preview')).toBeTruthy()
    expect(screen.getByText('测试报告')).toBeTruthy()
  })
})