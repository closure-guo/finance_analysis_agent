import type { UIMessage } from './types'

// 报告名组合标题：名称缺失或等于代码时仅显示代码（不重复组合）
export function formatReportTitle(msg: UIMessage): string {
  const name = msg.stockName?.trim()
  const code = msg.stockCode?.trim()
  if (name && code && name !== code) return `${name}（${code}）`
  return name || code || ''
}

// 口径 B：已完成报告且 filePaths 含至少一个已生成文件
export function isExportableReport(msg: UIMessage): boolean {
  if (msg.type !== 'report' || msg.streaming) return false
  const fp = msg.filePaths || {}
  return Object.values(fp).some((p) => !!p)
}

const bannerClass =
  'w-full flex items-center gap-3 px-5 py-3 rounded-xl text-sm font-medium transition-colors hover:opacity-90'

export function ReportNameBanner({ msg, onOpen }: {
  msg: UIMessage
  onOpen: (msg: UIMessage) => void
}) {
  return (
    <button type="button" data-testid="report-name-banner" onClick={() => onOpen(msg)}
      className={bannerClass} style={{ background: 'var(--bg-base-secondary)', color: 'var(--text-default)' }}>
      <i className="fas fa-file-lines text-xs" style={{ color: 'var(--text-brand)' }}></i>
      <span className="flex-1 truncate">{formatReportTitle(msg)}</span>
      <i className="fas fa-chevron-right text-xs" style={{ color: 'var(--text-tertiary)' }}></i>
    </button>
  )
}

export function AllFilesBanner({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" data-testid="conversation-files-banner" onClick={onOpen}
      className={bannerClass} style={{ background: 'var(--bg-base-secondary)', color: 'var(--text-default)' }}>
      <i className="fas fa-folder-open text-xs" style={{ color: 'var(--text-brand)' }}></i>
      <span className="flex-1">全部文件</span>
      <i className="fas fa-chevron-right text-xs" style={{ color: 'var(--text-tertiary)' }}></i>
    </button>
  )
}