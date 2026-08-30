import { motion, useReducedMotion } from 'framer-motion'
import type { ExportFileInfo } from '../../types'

// 类型图标配色取自主题 CSS 变量（refactor-ui-design-system 令牌体系），不硬编码色值
const FILE_ICONS: Record<string, { icon: string; color: string }> = {
  docx: { icon: 'fa-file-word', color: 'var(--chart-sky)' },
  pptx: { icon: 'fa-file-powerpoint', color: 'var(--chart-coral)' },
  pdf: { icon: 'fa-file-pdf', color: 'var(--destructive)' },
  md: { icon: 'fa-file-code', color: 'var(--chart-violet)' },
}

export function formatBytes(n: number): string {
  if (n < 0) return '0 KB'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export function formatFileTime(ts: number, now = new Date()): string {
  const d = new Date(ts)
  const pad = (v: number) => String(v).padStart(2, '0')
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 入场 stagger 延迟上限：逐行 30ms 只对首屏有节奏意义，行数多时封顶，
// 避免千行列表时最后一行等 30s 才入场（配合 DownloadCenter 的增量渲染）
const MAX_STAGGER_DELAY = 0.6

export function FileRow({ file, index = 0, downloading, onDownload, onDelete }: {
  file: ExportFileInfo
  index?: number
  downloading: boolean
  onDownload: (f: ExportFileInfo) => void
  onDelete: (f: ExportFileInfo) => void
}) {
  const reduced = useReducedMotion()
  const meta = FILE_ICONS[file.file_type] ?? { icon: 'fa-file', color: 'var(--muted-foreground)' }
  return (
    <motion.li
      data-testid="download-row"
      data-file-name={file.file_name}
      className="overflow-hidden"
      custom={index}
      variants={
        reduced
          ? undefined
          : {
              hidden: { opacity: 0, y: 8 },
              show: (i: number) => ({
                opacity: 1,
                y: 0,
                transition: { delay: Math.min(i * 0.03, MAX_STAGGER_DELAY), duration: 0.2, ease: 'easeOut' },
              }),
            }
      }
      exit={reduced ? undefined : { height: 0, opacity: 0, transition: { duration: 0.2, ease: 'easeInOut' } }}
    >
      <div className="group flex items-center gap-3 px-4 py-3 border-b border-border">
        <span className="w-8 text-center text-lg" style={{ color: meta.color }}>
          <i className={`fas ${meta.icon}`}></i>
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm truncate text-foreground" title={file.file_name}>
            {file.file_name}
          </div>
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <span>{formatBytes(file.size_bytes)}</span>
            <span>{formatFileTime(file.created_at)}</span>
          </div>
        </div>
        <button
          aria-label="下载"
          data-testid="row-download"
          disabled={downloading}
          onClick={() => onDownload(file)}
          className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors motion-reduce:transition-none disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <i className={`fas ${downloading ? 'fa-circle-notch fa-spin' : 'fa-download'} text-sm`}></i>
        </button>
        <button
          aria-label="删除"
          data-testid="row-delete"
          onClick={() => onDelete(file)}
          className="p-2 rounded-md text-muted-foreground hover:text-destructive hover:bg-muted transition-colors motion-reduce:transition-none opacity-0 group-hover:opacity-100 focus:opacity-100"
        >
          <i className="fas fa-trash text-sm"></i>
        </button>
      </div>
    </motion.li>
  )
}
