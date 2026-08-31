// add-citation-display Task 2.1/2.2/2.3 组件测试：
// 行内引用上标渲染、hover 预览卡（懒渲染）、引用与校验列表状态色标、旧报告兼容。
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReportCard } from '../App'
import type { UIMessage, Citation } from '../types'

const CITED_MD = '2024 年末资产负债率为 62.5%[[cite-1]]，毛利率同比提升[[cite-2]]，行业景气度处于上行区间[[cite-3]]。'

function makeCitations(): Citation[] {
  return [
    { id: 'cite-1', claim: '2024 年末资产负债率为 62.5%', source: 'solvency_metrics.资产负债率.2024', verdict: 'verified', detail: '重算值 62.5；偏差 0' },
    { id: 'cite-2', claim: '毛利率同比提升', source: 'profitability_metrics.毛利率.2024 vs 2023', verdict: 'failed', detail: '重算值 31.2；偏差 -0.8' },
    { id: 'cite-3', claim: '行业景气度处于上行区间', source: 'unknown.metric', verdict: 'unchecked', detail: '指标未注册重算覆盖（覆盖缺口）' },
  ]
}

function makeReportMsg(over: Partial<UIMessage> = {}): UIMessage {
  return {
    id: 'r1', type: 'report', content: '',
    reportMarkdown: CITED_MD,
    citations: makeCitations(),
    ...over,
  }
}

describe('行内引用上标（add-citation-display）', () => {
  it('正文引用标记渲染为上标，编号与后端 id 对应', () => {
    render(<ReportCard msg={makeReportMsg()} />)
    expect(screen.getByTestId('citation-sup-cite-1')).toBeInTheDocument()
    expect(screen.getByTestId('citation-sup-cite-2')).toBeInTheDocument()
    expect(screen.getByTestId('citation-sup-cite-3')).toBeInTheDocument()
    expect(screen.getByTestId('citation-sup-cite-1').textContent).toBe('1')
    // 原始标记不残留
    expect(document.body.textContent).not.toContain('[[cite-1]]')
  })

  it('hover 上标懒渲染预览卡：claim/来源/校验状态', () => {
    render(<ReportCard msg={makeReportMsg()} />)
    // 未 hover 时不挂载预览卡
    expect(screen.queryByTestId('citation-preview-cite-2')).toBeNull()
    fireEvent.mouseEnter(screen.getByTestId('citation-sup-cite-2'))
    const preview = screen.getByTestId('citation-preview-cite-2')
    expect(preview.textContent).toContain('毛利率同比提升')
    expect(preview.textContent).toContain('profitability_metrics.毛利率.2024')
    expect(preview.textContent).toContain('校验未通过')
    // 移出后卸载（懒渲染）
    fireEvent.mouseLeave(screen.getByTestId('citation-sup-cite-2'))
    expect(screen.queryByTestId('citation-preview-cite-2')).toBeNull()
  })
})

describe('引用与校验列表（add-citation-display）', () => {
  it('按编号列出来源与校验状态，failed 红色可辨', () => {
    render(<ReportCard msg={makeReportMsg()} />)
    expect(screen.getByTestId('citation-list')).toBeInTheDocument()
    // 三条引用均在列表中
    for (const id of ['cite-1', 'cite-2', 'cite-3']) {
      expect(screen.getByTestId(`citation-item-${id}`)).toBeInTheDocument()
    }
    // 状态标签
    expect(screen.getByTestId('citation-verdict-cite-1').textContent).toContain('已验证')
    expect(screen.getByTestId('citation-verdict-cite-2').textContent).toContain('校验未通过')
    expect(screen.getByTestId('citation-verdict-cite-3').textContent).toContain('未校验')
    // failed 红色 / verified 绿色（计算样式）
    const failed = screen.getByTestId('citation-verdict-cite-2')
    expect(failed).toHaveStyle({ color: 'var(--status-error-default)' })
    const verified = screen.getByTestId('citation-verdict-cite-1')
    expect(verified).toHaveStyle({ color: 'var(--status-success-default)' })
  })
})

describe('旧报告兼容（add-citation-display）', () => {
  it('无 citations 的旧报告不渲染上标与列表，标记按原文处理不崩溃', () => {
    render(<ReportCard msg={makeReportMsg({ citations: undefined })} />)
    expect(screen.queryByTestId('citation-list')).toBeNull()
    expect(screen.queryByTestId('citation-sup-cite-1')).toBeNull()
    expect(screen.getByText(/62.5%/)).toBeInTheDocument() // 正文正常渲染
  })

  it('流式中的报告不渲染引用列表（report_ready 前无完整数据）', () => {
    render(<ReportCard msg={makeReportMsg({ streaming: true })} />)
    expect(screen.queryByTestId('citation-list')).toBeNull()
  })

  it('标记指向不存在的引用 id 时不渲染上标也不崩溃', () => {
    render(<ReportCard msg={makeReportMsg({
      citations: [{ id: 'cite-9', claim: 'x', source: 'y', verdict: 'verified', detail: '' }],
    })} />)
    expect(screen.queryByTestId('citation-sup-cite-1')).toBeNull()
    expect(screen.getByTestId('citation-list')).toBeInTheDocument()
  })
})
