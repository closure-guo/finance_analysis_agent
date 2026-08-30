import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { toast } from 'sonner'
import type { ExportFileInfo, DownloadType } from '../../types'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../../components/ui/dialog'
import { FileRow } from './FileRow'

const TYPE_TABS: { key: DownloadType | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'docx', label: 'Word' },
  { key: 'pptx', label: 'PPT' },
  { key: 'pdf', label: 'PDF' },
  { key: 'md', label: 'Markdown' },
]

export function DownloadCenter({ onBack }: { onBack: () => void }) {
  // null = 加载中；error = 接口失败（与空态严格区分，失败不得以空态冒充）
  const [files, setFiles] = useState<ExportFileInfo[] | null>(null)
  const [error, setError] = useState(false)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<DownloadType | 'all'>('all')
  const [pendingDelete, setPendingDelete] = useState<ExportFileInfo | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)
  const reduced = useReducedMotion()

  const load = useCallback(async () => {
    setError(false)
    setFiles(null)
    try {
      const resp = await fetch('/api/files')
      if (!resp.ok) throw new Error(String(resp.status))
      setFiles((await resp.json()) as ExportFileInfo[])
    } catch {
      setError(true)
      toast.error('文件列表加载失败')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(
    () =>
      (files ?? []).filter(
        f =>
          (tab === 'all' || f.file_type === tab) &&
          f.file_name.toLowerCase().includes(search.trim().toLowerCase()),
      ),
    [files, tab, search],
  )

  const handleDownload = (f: ExportFileInfo) => {
    if (downloading) return
    setDownloading(f.file_name)
    const a = document.createElement('a')
    a.href = `/api/files/${encodeURIComponent(f.file_name)}`
    a.download = f.file_name
    document.body.appendChild(a)
    a.click()
    a.remove()
    // 下载触发即认为开始，恢复按钮并反馈（文件由浏览器接管保存）
    setTimeout(() => {
      setDownloading(null)
      toast.success('已开始下载')
    }, 200)
  }

  const handleConfirmDelete = async () => {
    const target = pendingDelete
    setPendingDelete(null)
    if (!target) return
    // 乐观移除（动画先行），失败按 created_at 回滚到原位
    setFiles(prev => (prev ?? []).filter(f => f.file_name !== target.file_name))
    try {
      const resp = await fetch(`/api/files/${encodeURIComponent(target.file_name)}`, { method: 'DELETE' })
      if (!resp.ok) throw new Error(String(resp.status))
      toast.success('已删除')
    } catch {
      setFiles(prev => {
        const rest = (prev ?? []).filter(f => f.file_name !== target.file_name)
        return [...rest, target].sort((a, b) => b.created_at - a.created_at)
      })
      toast.error('删除失败，请重试')
    }
  }

  return (
    <div className="flex flex-col h-screen" data-testid="download-center">
      {/* 标题栏（固定） */}
      <div className="shrink-0 px-6 pt-5 pb-4 border-b border-border" style={{ background: 'var(--background)' }}>
        <div className="flex items-center gap-2">
          <i className="fas fa-download text-sm" style={{ color: 'var(--primary)' }}></i>
          <h1 className="text-base font-semibold text-foreground">下载管理</h1>
        </div>
        <p className="text-xs text-muted-foreground mt-1">管理已生成的报告导出文件（docx / pptx / pdf / md）</p>
        {/* 搜索 + 类型筛选（叠加过滤） */}
        <div className="flex items-center gap-3 mt-3">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索文件..."
            data-testid="downloads-search"
            className="h-8 flex-1 max-w-xs rounded-md border border-input bg-background px-3 text-xs outline-none focus:ring-1 focus:ring-ring"
          />
          <div className="flex items-center gap-1" data-testid="downloads-tabs">
            {TYPE_TABS.map(t => (
              <button
                key={t.key}
                data-testid={`filter-tab-${t.key}`}
                onClick={() => setTab(t.key)}
                className={`px-3 h-7 rounded-full text-xs transition-colors ${
                  tab === t.key ? 'bg-accent text-accent-foreground font-medium' : 'text-muted-foreground hover:bg-muted'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 列表区（内部滚动） */}
      <div className="flex-1 overflow-y-auto" style={{ background: 'var(--background)' }}>
        {error ? (
          <div data-testid="downloads-error" className="flex flex-col items-center justify-center py-24 gap-3">
            <i className="fas fa-triangle-exclamation text-2xl text-destructive"></i>
            <p className="text-sm text-muted-foreground">文件列表加载失败</p>
            <button
              onClick={load}
              className="px-3 h-8 rounded-md text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              重试
            </button>
          </div>
        ) : files === null ? (
          <div data-testid="downloads-skeleton" className="px-4 py-2">
            {[0, 1, 2, 3, 4].map(i => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-border">
                <div className="w-8 h-8 rounded animate-pulse" style={{ background: 'var(--muted)' }} />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-1/3 rounded animate-pulse" style={{ background: 'var(--muted)' }} />
                  <div className="h-2 w-1/5 rounded animate-pulse" style={{ background: 'var(--muted)' }} />
                </div>
              </div>
            ))}
          </div>
        ) : files.length === 0 ? (
          <div data-testid="downloads-empty" className="flex flex-col items-center justify-center py-24 gap-3">
            <i className="fas fa-file-arrow-down text-3xl text-muted-foreground"></i>
            <p className="text-sm text-muted-foreground">暂无导出文件</p>
            <button
              onClick={onBack}
              className="px-3 h-8 rounded-md text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              返回聊天
            </button>
          </div>
        ) : (
          <motion.ul
            data-testid="file-list"
            initial={reduced ? false : 'hidden'}
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.03 } } }}
          >
            <AnimatePresence initial={false}>
              {filtered.map(f => (
                <FileRow
                  key={f.file_name}
                  file={f}
                  downloading={downloading === f.file_name}
                  onDownload={handleDownload}
                  onDelete={setPendingDelete}
                />
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
      </div>

      {/* 删除确认对话框（shadcn Dialog 原语） */}
      <Dialog open={!!pendingDelete} onOpenChange={o => { if (!o) setPendingDelete(null) }}>
        <DialogContent data-testid="delete-confirm" className="max-w-[360px]">
          <DialogHeader>
            <DialogTitle className="text-sm">删除文件</DialogTitle>
            <DialogDescription className="text-xs break-all">
              确定删除「{pendingDelete?.file_name}」吗？此操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <button
              data-testid="delete-cancel"
              onClick={() => setPendingDelete(null)}
              className="px-3 h-8 rounded-md text-xs border border-input hover:bg-muted transition-colors"
            >
              取消
            </button>
            <button
              data-testid="delete-ok"
              onClick={handleConfirmDelete}
              className="px-3 h-8 rounded-md text-xs bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
            >
              删除
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
