import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { UIMessage } from './types'
import { Button } from './components/ui/button'

const basename = (p?: string) => (p ? (String(p).split(/[\\/]/).pop() ?? '') : '')

// 文件图标按扩展名映射
const FILE_ICONS: Record<string, string> = {
  pdf: 'fa-file-pdf',
  docx: 'fa-file-word',
  md: 'fa-file-code',
  pptx: 'fa-file-powerpoint',
}
const extIcon = (name: string) => {
  const ext = (name.split('.').pop() ?? '').toLowerCase()
  return FILE_ICONS[ext] || 'fa-file'
}

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

  if (!drawerMessage) return null

  // 自上而下列出 filePaths 中已生成的文件，仅展示可下载条目（无 basename 的路径过滤掉）
  const fileEntries = Object.entries(drawerMessage.filePaths || {})
    .map(([fmt, path]) => ({ fmt, name: basename(path) }))
    .filter((e) => e.name)

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
            <Button onClick={() => setView('preview')} data-testid="preview-open" variant="secondary" size="sm" className="h-7">
              预览
            </Button>
            <Button onClick={onClose} data-testid="drawer-close" variant="ghost" size="icon" className="h-6 w-6">
              <i className="fas fa-times"></i>
            </Button>
          </div>
        </div>

        {view === 'list' ? (
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2" data-testid="drawer-file-list">
            {fileEntries.length === 0 ? (
              <p className="text-xs py-3 text-center" style={{ color: 'var(--text-tertiary)' }}>
                暂无已生成文件
              </p>
            ) : (
              fileEntries.map(({ fmt, name }) => (
                <div key={fmt} data-testid={`file-row-${fmt}`}
                  className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-base-secondary)' }}>
                  <i className={`fas ${extIcon(name)} text-sm`} style={{ color: 'var(--text-brand)' }}></i>
                  <span className="flex-1 text-sm font-medium truncate" style={{ color: 'var(--text-default)' }}>{name}</span>
                  <a href={`/api/files/${name}`} download={name} data-testid={`download-file-${fmt}`}
                    className="text-xs px-2 py-1 rounded no-underline"
                    style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}>
                    <i className="fas fa-download mr-1"></i>下载
                  </a>
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-4 py-3" data-testid="drawer-preview" style={{ maxHeight: 'calc(100vh - 56px)' }}>
            <Button onClick={() => setView('list')} variant="link" className="mb-2 h-auto p-0 text-xs">
              <i className="fas fa-arrow-left mr-1"></i>返回文件列表
            </Button>
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