import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ReportNameBanner, AllFilesBanner, formatReportTitle, isExportableReport } from '../ReportEntryBanners'
import type { UIMessage } from '../types'

const reportMsg = (over: Partial<UIMessage>): UIMessage => ({
  id: 'r1',
  type: 'report',
  content: '',
  streaming: false,
  stockName: '贵州茅台',
  stockCode: '600519',
  filePaths: { md: '/tmp/贵州茅台_600519_x_report.md' },
  ...over,
})

describe('formatReportTitle', () => {
  it('名称+代码组合', () => {
    expect(formatReportTitle(reportMsg({}))).toBe('贵州茅台（600519）')
  })
  it('名称缺失时仅显示代码', () => {
    expect(formatReportTitle(reportMsg({ stockName: undefined }))).toBe('600519')
  })
  it('名称等于代码时不重复', () => {
    expect(formatReportTitle(reportMsg({ stockName: '600519' }))).toBe('600519')
  })
})

describe('isExportableReport', () => {
  it('已完成且 filePaths 有值 → true', () => {
    expect(isExportableReport(reportMsg({}))).toBe(true)
  })
  it('filePaths 为空对象 → false', () => {
    expect(isExportableReport(reportMsg({ filePaths: {} }))).toBe(false)
  })
  it('filePaths 值为空串 → false', () => {
    expect(isExportableReport(reportMsg({ filePaths: { md: '' } }))).toBe(false)
  })
  it('streaming 中 → false', () => {
    expect(isExportableReport(reportMsg({ streaming: true }))).toBe(false)
  })
  it('非 report 类型 → false', () => {
    expect(isExportableReport({ ...reportMsg({}), type: 'chat' } as UIMessage)).toBe(false)
  })
})

describe('ReportNameBanner / AllFilesBanner', () => {
  it('报告名横幅显示组合标题并可点击', () => {
    const msg = reportMsg({})
    const onOpen = vi.fn()
    render(<ReportNameBanner msg={msg} onOpen={onOpen} />)
    expect(screen.getByText('贵州茅台（600519）')).toBeTruthy()
    fireEvent.click(screen.getByTestId('report-name-banner'))
    expect(onOpen).toHaveBeenCalledWith(msg)
  })
  it('全部文件横幅可点击', () => {
    const onOpen = vi.fn()
    render(<AllFilesBanner onOpen={onOpen} />)
    expect(screen.getByText('全部文件')).toBeTruthy()
    fireEvent.click(screen.getByTestId('conversation-files-banner'))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})