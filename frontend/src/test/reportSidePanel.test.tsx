// add-report-side-panel Task 1.1/1.2/2.2/2.3/3.1 组件测试：
// 面板滑出/关闭/Esc、宽度拖拽与持久化、操作栏导出链接、摘要卡要点与打开按钮、移动端回退。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../App'
import { ReportCard, reportKeyPoints } from '../App'
import { ReportSidePanel } from '../components/ReportSidePanel'
import type { UIMessage } from '../types'

function makeReport(over: Partial<UIMessage> = {}): UIMessage {
  return {
    id: 'r1', type: 'report', content: '',
    reportMarkdown: '## 一、核心结论\n结论要点内容\n## 二、财务分析\n正文',
    chartData: undefined,
    stockName: '贵州茅台', stockCode: '600519',
    durationMs: 65000,
    filePaths: { docx: '/exports/贵州茅台.docx', md: '/exports/贵州茅台.md' },
    ...over,
  }
}

function stubAppFetch() {
  const detail = {
    session_id: 's1', stock_code: '600519', stock_name: '贵州茅台', display_name: '贵州茅台', status: 'completed',
    created_at: '2026-08-31T00:00:00Z', duration_ms: 65000,
    report_markdown: '## 一、核心结论\n结论要点内容',
    chart_data: null, analyst_reports: {}, agent_process: {}, analyst_summaries: {},
    chat_history: [
      { role: 'user', content: '分析茅台', ts: '2026-08-31T00:00:00Z' },
      { role: 'assistant', content: '回答', ts: '2026-08-31T00:01:00Z' },
    ],
    pipeline_snapshot: null, last_seq: 0, citations: null,
  }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'
    if (url === '/api/sessions' && method === 'GET') {
      return new Response(JSON.stringify({ sessions: [detail] }), { status: 200 })
    }
    if (url.startsWith('/api/sessions/') && method === 'GET') {
      return new Response(JSON.stringify(detail), { status: 200 })
    }
    if (url === '/api/llm-config') {
      return new Response(JSON.stringify({ model: '', base_url: '', thinking: 'enabled' }), { status: 200 })
    }
    return new Response('{}', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('报告右侧面板（add-report-side-panel）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('面板打开：滑出动画态、操作栏导出链接、关闭按钮', async () => {
    const msg = makeReport()
    const onClose = vi.fn()
    render(<ReportSidePanel msg={msg} onClose={onClose} />)
    const panel = screen.getByTestId('report-side-panel')
    // 挂载后下一帧进入 open 态（translateX(0)，300ms 过渡）
    await waitFor(() => expect(panel.getAttribute('data-state')).toBe('open'))
    expect(panel.style.transform).toBe('translateX(0)')
    // 导出条目（filePaths 已生成文件，同 /api/files 契约）
    expect(screen.getByTestId('panel-export-docx').getAttribute('href')).toBe('/api/files/贵州茅台.docx')
    expect(screen.getByTestId('panel-export-md')).toBeInTheDocument()
    // 关闭
    fireEvent.click(screen.getByTestId('panel-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Esc 关闭面板', () => {
    const onClose = vi.fn()
    render(<ReportSidePanel msg={makeReport()} onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('左边缘拖拽调节宽度并持久化', () => {
    const msg = makeReport()
    render(<ReportSidePanel msg={msg} onClose={vi.fn()} />)
    const panel = screen.getByTestId('report-side-panel')
    const handle = screen.getByTestId('panel-resize-handle')
    const before = parseInt(panel.style.width, 10)
    fireEvent.mouseDown(handle, { clientX: 800, preventDefault: () => {} })
    fireEvent.mouseMove(document, { clientX: 500 }) // 左拖 300px → 变宽
    fireEvent.mouseUp(document)
    const after = parseInt(panel.style.width, 10)
    expect(after).toBe(before + 300)
    expect(localStorage.getItem('fa_report_panel_width')).toBe(String(after))
  })

  it('宽度持久化：重挂载读取上次宽度', () => {
    localStorage.setItem('fa_report_panel_width', '700')
    render(<ReportSidePanel msg={makeReport()} onClose={vi.fn()} />)
    expect(screen.getByTestId('report-side-panel').style.width).toBe('700px')
  })

  it('isMobile=true 不渲染面板（移动端回退）', () => {
    const { container } = render(<ReportSidePanel msg={makeReport()} onClose={vi.fn()} isMobile />)
    expect(container.querySelector('[data-testid="report-side-panel"]')).toBeNull()
  })

  it('msg=null 不渲染面板', () => {
    const { container } = render(<ReportSidePanel msg={null} onClose={vi.fn()} />)
    expect(container.querySelector('[data-testid="report-side-panel"]')).toBeNull()
  })
})

describe('消息流摘要卡（add-report-side-panel）', () => {
  it('完成态 inline 报告收敛为摘要卡：要点 + 打开报告按钮', () => {
    const msg = makeReport()
    const onOpenPanel = vi.fn()
    render(<ReportCard msg={msg} onOpenPanel={onOpenPanel} />)
    // 摘要卡可见
    expect(screen.getByTestId('report-summary-card')).toBeInTheDocument()
    expect(screen.getByTestId('report-summary-card').textContent).toContain('一、核心结论')
    // 点击「打开报告」→ 回调携带消息
    fireEvent.click(screen.getByTestId('open-report-button'))
    expect(onOpenPanel).toHaveBeenCalledWith(msg)
    // 点击后消息流内完整区同步展开（移动端回退路径）
    const full = screen.getByTestId('report-full-section')
    expect(full.style.maxHeight).not.toBe('0')
  })

  it('完整区默认折叠但保留渲染（正文在 DOM 可查）', () => {
    render(<ReportCard msg={makeReport()} />)
    const full = screen.getByTestId('report-full-section')
    expect(full.style.maxHeight).toBe('0px')
    expect(full.textContent).toContain('结论要点内容')
  })

  it('reportKeyPoints：有二级标题取前 4；无标题回退首段；剥离引用标记', () => {
    const withHeadings = reportKeyPoints('## A\nx\n## B\ny\n## C\nz\n## D\nw\n## E\nv\n[[cite-1]]尾随')
    expect(withHeadings).toEqual(['A', 'B', 'C', 'D'])
    const noHeadings = reportKeyPoints('**第一段结论文字**\n第二行')
    expect(noHeadings[0]).toContain('第一段结论文字')
    expect(noHeadings[0]).not.toContain('[')
    const withMarks = reportKeyPoints('结论[[cite-1]]与[[cite-2]]')
    expect(withMarks[0]).not.toContain('cite-')
  })
})

describe('App 级组合：摘要卡 → 面板打开（add-report-side-panel）', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('选中完成会话 → 点摘要卡「打开报告」→ 右侧面板出现', async () => {
    stubAppFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('贵州茅台').length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByText('贵州茅台')[0])
    await waitFor(() => expect(screen.getByTestId('report-summary-card')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('open-report-button'))
    await waitFor(() => expect(screen.getByTestId('report-side-panel')).toBeInTheDocument())
    expect(screen.getByTestId('panel-content').textContent).toContain('结论要点内容')
  })
})
