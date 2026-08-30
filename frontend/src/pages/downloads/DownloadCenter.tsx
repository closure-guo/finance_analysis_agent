import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { toast } from 'sonner'
import type { ExportFileInfo, DownloadType } from '../../types'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../../components/ui/dialog'
import { Input } from '../../components/ui/input'
import { Button } from '../../components/ui/button'
import { FileRow } from './FileRow'

const TYPE_TABS: { key: DownloadType | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'docx', label: 'Word' },
  { key: 'pptx', label: 'PPT' },
  { key: 'pdf', label: 'PDF' },
  { key: 'md', label: 'Markdown' },
]

// 增量渲染：reports/ 下可能有上千个导出文件，一次性全量渲染 DOM +
// framer-motion 逐行 stagger（30ms/行）会导致页面卡死（千行级最后一行
// 要等 30s+ 才入场）。首屏只渲染 PAGE_SIZE 行，滚动到底自动加载下一页。
const PAGE_SIZE = 50
// 入场 stagger 延迟上限：只对首屏前 ~20 行有逐行节奏感，之后不再线性累加
const MAX_STAGGER_DELAY = 0.6

export function DownloadCenter({ onBack }: { onBack: () => void }) {
  // null = 加载中；error = 接口失败（与空态严格区分，失败不得以空态冒充）
  const [files, setFiles] = useState<ExportFileInfo[] | null>(null)
  const [error, setError] = useState(false)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<DownloadType | 'all'>('all')
  const [pendingDelete, setPendingDelete] = useState<ExportFileInfo | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)
  const reduced = useReducedMotion()
  // 列表数据首次就绪后置 true：入场 stagger 只在列表首挂载播一次，
  // 此后新挂载行（筛选切回/回滚）initial=false 不再重播入场动画。
  // 注意不能在组件 mount 的 effect 里翻转——首帧还是骨架屏，行要等 fetch 完成才挂载，
  // 若那时 entered 已为 true，首挂载 stagger 同样会被吞掉。
  const [entered, setEntered] = useState(false)
  useEffect(() => {
    if (files !== null) setEntered(true)
  }, [files])

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
  const [renderLimit, setRenderLimit] = useState(PAGE_SIZE)
  // 数据或筛选变化后重置增量窗口（保留当前窗口大小，避免来回筛选重复加载）
  useEffect(() => { setRenderLimit(PAGE_SIZE) }, [tab, search])
  const visibleFiles = useMemo(() => filtered.slice(0, renderLimit), [filtered, renderLimit])
  const remainingCount = filtered.length - visibleFiles.length

  // 滚动到底部附近自动加载下一页（经典 scroll 监听，所有环境可靠；
  // 「加载更多」按钮保留为兜底入口）
  const handleListScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      if (remainingCount <= 0) return
      const el = e.currentTarget
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 300) {
        setRenderLimit(limit => limit + PAGE_SIZE)
      }
    },
    [remainingCount],
  )

  const handleDownload = (f: ExportFileInfo) => {
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
          <Input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索文件..."
            data-testid="downloads-search"
            className="h-8 flex-1 max-w-xs text-xs motion-reduce:transition-none"
          />
          <div className="flex items-center gap-1" data-testid="downloads-tabs">
            {TYPE_TABS.map(t => (
              <button
                key={t.key}
                data-testid={`filter-tab-${t.key}`}
                onClick={() => setTab(t.key)}
                className={`px-3 h-7 rounded-full text-xs transition-colors motion-reduce:transition-none ${
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
      <div className="flex-1 overflow-y-auto" onScroll={handleListScroll} style={{ background: 'var(--background)' }}>
        {error ? (
          <div data-testid="downloads-error" className="flex flex-col items-center justify-center py-24 gap-3">
            <i className="fas fa-triangle-exclamation text-2xl text-destructive"></i>
            <p className="text-sm text-muted-foreground">文件列表加载失败</p>
            <Button onClick={load} variant="default" size="sm" className="motion-reduce:transition-none">
              重试
            </Button>
          </div>
        ) : files === null ? (
          <div data-testid="downloads-skeleton" className="px-4 py-2">
            {[0, 1, 2, 3, 4].map(i => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-border">
                <div className="w-8 h-8 rounded animate-pulse motion-reduce:animate-none" style={{ background: 'var(--muted)' }} />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-1/3 rounded animate-pulse motion-reduce:animate-none" style={{ background: 'var(--muted)' }} />
                  <div className="h-2 w-1/5 rounded animate-pulse motion-reduce:animate-none" style={{ background: 'var(--muted)' }} />
                </div>
              </div>
            ))}
          </div>
        ) : files.length === 0 ? (
          <div data-testid="downloads-empty" className="flex flex-col items-center justify-center py-24 gap-3">
            <i className="fas fa-file-arrow-down text-3xl text-muted-foreground"></i>
            <p className="text-sm text-muted-foreground">暂无导出文件</p>
            <Button onClick={onBack} variant="default" size="sm" className="motion-reduce:transition-none">
              返回聊天
            </Button>
          </div>
        ) : (
          <motion.ul
            data-testid="file-list"
            initial={reduced || entered ? false : 'hidden'}
            animate="show"
          >
            <AnimatePresence>
              {visibleFiles.map((f, i) => (
                <FileRow
                  key={f.file_name}
                  file={f}
                  index={i}
                  downloading={downloading === f.file_name}
                  onDownload={handleDownload}
                  onDelete={setPendingDelete}
                />
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
        {/* 加载更多：剩余数 > 0 时显示（滚动到底也会自动加载，此为兜底入口） */}
        {!error && files !== null && remainingCount > 0 && (
          <div className="flex justify-center py-4">
            <Button
              data-testid="load-more"
              variant="ghost"
              size="sm"
              className="text-muted-foreground motion-reduce:transition-none"
              onClick={() => setRenderLimit(limit => limit + PAGE_SIZE)}
            >
              加载更多（剩余 {remainingCount} 个）
            </Button>
          </div>
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
            <Button data-testid="delete-cancel" onClick={() => setPendingDelete(null)} variant="outline" size="sm" className="motion-reduce:transition-none">
              取消
            </Button>
            <Button data-testid="delete-ok" onClick={handleConfirmDelete} variant="destructive" size="sm" className="motion-reduce:transition-none">
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
