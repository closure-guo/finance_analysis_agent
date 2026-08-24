import { useCallback, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { UIMessage } from './types'

export interface ExportFormatMeta {
  key: string
  label: string
  icon: string
  apiFmt: string // POST /api/export 的 fmt 值
}

// 导出菜单：PDF / Word / Markdown（pptx 仅当 filePaths 存在时展示，不强制）
export const EXPORT_FORMATS: ExportFormatMeta[] = [
  { key: 'pdf', label: 'PDF', icon: 'fa-file-pdf', apiFmt: 'pdf' },
  { key: 'docx', label: 'Word', icon: 'fa-file-word', apiFmt: 'word' },
  { key: 'md', label: 'Markdown', icon: 'fa-file-code', apiFmt: 'markdown' },
]

const basename = (p?: string) => (p ? (String(p).split(/[\\/]/).pop() ?? '') : '')

export function ReportFileDrawer({ drawerMessage, onClose }: {
  drawerMessage: UIMessage | null
  onClose: () => void
}) {
  const [view, setView] = useState<'list' | 'preview'>('list')

  // Esc 关闭
  useEffect(() => {
    if (!drawerMessage) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerMessage, onClose])

  // 下载：已有文件直接跳 /api/files/<basename>；缺失文件先 POST /api/export 按需生成再下载
  const handleDownload = useCallback(async (fmt: ExportFormatMeta) => {
    if (!drawerMessage) return
    const existing = drawerMessage.filePaths?.[fmt.key]
    if (existing) {
      const a = document.createElement('a')
      a.href = `/api/files/${basename(existing)}`
      a.download = basename(existing)
      a.click()
      return
    }
    const resp = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: drawerMessage.sessionId, fmt: fmt.apiFmt }),
    })
    if (!resp.ok) return
    const data = await resp.json()
    const a = document.createElement('a')
    a.href = data.url
    a.download = data.file_name
    a.click()
  }, [drawerMessage])

  if (!drawerMessage) return null

  const fileList = [...EXPORT_FORMATS]
  if (drawerMessage.filePaths?.pptx) {
    fileList.push({ key: 'pptx', label: 'PPT', icon: 'fa-file-powerpoint', apiFmt: '' })
  }

  return (
    <div className="fixed inset-0 z-[60]" data-testid="export-drawer">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} data-testid="drawer-backdrop" />
      {/* 抽屉主体 */}
      <div className="absolute right-0 top-0 bottom-0 w-[420px] max-w-[90vw] flex flex-col"
        style={{ background: 'var(--bg-base)', borderLeft: '1px solid var(--border-neutral-l1)' }}>
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
          <span className="text-sm font-semibold" style={{ color: 'var(--text-default)' }}>全部文件</span>
          <div className="flex items-center gap-3">
            {/* 预览面板：抽屉级单一入口（预览 reportMarkdown 正文） */}
            <button onClick={() => setView('preview')} data-testid="preview-open"
              className="text-xs px-2 py-1 rounded" style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-default)' }}>
              预览
            </button>
            <button onClick={onClose} data-testid="drawer-close"
              className="text-[var(--icon-secondary)] hover:text-[var(--text-default)]">
              <i className="fas fa-times"></i>
            </button>
          </div>
        </div>

        {view === 'list' ? (
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {fileList.map(fmt => {
              const existing = drawerMessage.filePaths?.[fmt.key]
              return (
                <div key={fmt.key} className="flex items-center gap-3 p-3 rounded-lg"
                  style={{ background: 'var(--bg-base-secondary)' }}>
                  <i className={`fas ${fmt.icon} text-sm`} style={{ color: 'var(--text-brand)' }}></i>
                  <span className="flex-1 text-sm font-medium" style={{ color: 'var(--text-default)' }}>
                    {fmt.label}
                  </span>
                  {fmt.key !== 'pptx' && (
                    // 已有文件：直接渲染可下载链接；缺失文件：按钮触发 POST /api/export 后下载
                    existing ? (
                      <a href={`/api/files/${basename(existing)}`} download={basename(existing)}
                        data-testid={`download-${fmt.key}`}
                        className="text-xs px-2 py-1 rounded no-underline"
                        style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}>
                        <i className="fas fa-download mr-1"></i>下载
                      </a>
                    ) : (
                      <button onClick={() => handleDownload(fmt)} data-testid={`download-${fmt.key}`}
                        className="text-xs px-2 py-1 rounded"
                        style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}>
                        <i className="fas fa-download mr-1"></i>下载
                      </button>
                    )
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-4 py-3" data-testid="drawer-preview" style={{ maxHeight: 'calc(100vh - 56px)' }}>
            <button onClick={() => setView('list')} className="text-xs mb-2" style={{ color: 'var(--text-brand)' }}>
              <i className="fas fa-arrow-left mr-1"></i>返回文件列表
            </button>
            <div className="prose prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}
                components={{ img: () => null, a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>
                {drawerMessage.reportMarkdown || ''}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}