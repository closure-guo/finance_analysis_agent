// add-report-side-panel Task 1.1/1.2/2.2：报告右侧面板。
// - 右侧滑出（约 300ms transform 过渡）、可开合
// - 左边缘拖拽调节宽度（380–960px，localStorage 持久化，同会话内保持）
// - 顶部操作栏：导出（docx/pptx/pdf/md，复用既有 /api/files/<name> 下载契约）+ 关闭
// - 移动端不渲染（回退消息流内全宽展示，delta spec）
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { UIMessage } from '../types'

const PANEL_WIDTH_KEY = 'fa_report_panel_width'
const MIN_WIDTH = 380
const MAX_WIDTH = 960
const DEFAULT_WIDTH = 560

const basename = (p?: string) => (p ? (String(p).split(/[\\/]/).pop() ?? '') : '')

export function ReportSidePanel({ msg, onClose, isMobile = false, children }: {
  /** 面板展示的报告消息（null = 关闭） */
  msg: UIMessage | null
  onClose: () => void
  /** 移动端回退：不渲染面板（报告留在消息流） */
  isMobile?: boolean
  /** 面板内容（App 传入报告渲染，避免与 App 循环导入） */
  children?: ReactNode
}) {
  // 宽度持久化：初值读 localStorage（非法值回退默认）
  const [width, setWidth] = useState(() => {
    const raw = Number(localStorage.getItem(PANEL_WIDTH_KEY))
    return Number.isFinite(raw) && raw >= MIN_WIDTH && raw <= MAX_WIDTH ? raw : DEFAULT_WIDTH
  })
  // 滑出动画：挂载后下一帧置 open，触发 300ms transform 过渡
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!msg) return
    const raf = requestAnimationFrame(() => setOpen(true))
    return () => cancelAnimationFrame(raf)
  }, [msg])

  // Esc 关闭
  useEffect(() => {
    if (!msg) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [msg, onClose])

  // 左边缘拖拽调宽（Task 1.1 Resizable 语义：向左拖 → 变宽）。
  // widthRef 保存拖拽中的最新宽度：mouseup 时持久化（避免闭包读到过期 state）
  const widthRef = useRef(width)
  widthRef.current = width
  const draggingRef = useRef(false)
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    draggingRef.current = true
    const startX = e.clientX
    const startWidth = widthRef.current
    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + (startX - ev.clientX)))
      widthRef.current = next
      setWidth(next)
    }
    const onUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      localStorage.setItem(PANEL_WIDTH_KEY, String(widthRef.current))
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [])

  if (isMobile || !msg) return null

  // 导出条目：filePaths 中已生成文件（与 ReportFileDrawer 同契约 /api/files/<name>）
  const fileEntries = Object.entries(msg.filePaths || {})
    .map(([fmt, path]) => ({ fmt, name: basename(path) }))
    .filter((e) => e.name)

  return (
    <div
      data-testid="report-side-panel"
      data-state={open ? 'open' : 'opening'}
      className="fixed top-0 bottom-0 right-0 z-[55] flex flex-col shadow-2xl"
      style={{
        width,
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 300ms ease-out',
        background: 'var(--bg-base)',
        borderLeft: '1px solid var(--border-neutral-l1)',
      }}
    >
      {/* 左边缘拖拽热区 */}
      <div
        data-testid="panel-resize-handle"
        onMouseDown={onMouseDown}
        className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-brand/20"
        style={{ background: 'transparent' }}
      />
      {/* 顶部操作栏：标题 + 导出 + 关闭 */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}
      >
        <span className="text-sm font-semibold truncate" style={{ color: 'var(--text-default)' }}>
          完整报告
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          {fileEntries.map(({ fmt, name }) => (
            <a
              key={fmt}
              href={`/api/files/${name}`}
              download={name}
              data-testid={`panel-export-${fmt}`}
              className="text-[11px] px-2 py-1 rounded no-uppercase"
              style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}
            >
              <i className="fas fa-download mr-1"></i>{fmt.toUpperCase()}
            </a>
          ))}
          <button
            type="button"
            data-testid="panel-close"
            onClick={onClose}
            aria-label="关闭报告面板"
            className="h-6 w-6 rounded-md transition-colors hover:bg-muted flex items-center justify-center"
          >
            <i className="fas fa-times text-xs"></i>
          </button>
        </div>
      </div>
      {/* 内容区：App 传入的报告渲染（Markdown + ECharts + 引用标记） */}
      <div className="flex-1 overflow-y-auto" data-testid="panel-content">
        {children}
      </div>
    </div>
  )
}
