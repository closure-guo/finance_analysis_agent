// add-collapsible-sidebar Task 1.1：shadcn/ui Sidebar 原语（精简版，collapsible="icon"）。
//
// 语义（delta spec）：
// - 展开约 256px / 收起约 52px 图标栏，宽度 200ms 过渡（消费方以 state 驱动主区 margin）
// - SidebarTrigger 按钮 + Ctrl/Cmd+B 快捷键切换
// - 折叠状态持久化（localStorage fa_sidebar_collapsed，刷新/重开保持）
// - <768px 抽屉态：默认隐藏，滑入 + 遮罩关闭；选中会话后由业务调 setOpenMobile(false)
// - 收起态图标 tooltip（TooltipProvider 由 Provider 统一挂载）
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useAnimationControls, motion } from 'framer-motion'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip'
import { MenuToggleIcon } from './menu-toggle-icon'
import { cn } from '../../lib/utils'

export type SidebarState = 'expanded' | 'collapsed'

interface SidebarContextValue {
  state: SidebarState
  isMobile: boolean
  openMobile: boolean
  setOpenMobile: (v: boolean) => void
  toggleSidebar: () => void
}

const SidebarContext = createContext<SidebarContextValue | null>(null)

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext)
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider')
  return ctx
}

const SIDEBAR_COLLAPSED_KEY = 'fa_sidebar_collapsed'

export function SidebarProvider({ children }: { children: ReactNode }) {
  // 折叠状态持久化：初值直接读 localStorage，避免首帧闪展开态
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1')
  // matchMedia 守卫：jsdom 测试环境无此 API（恒为桌面态）
  const mq: MediaQueryList | null =
    typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 767px)') : null
  const [isMobile, setIsMobile] = useState(() => mq?.matches ?? false)
  const [openMobile, setOpenMobile] = useState(false)

  useEffect(() => {
    const mq: MediaQueryList | null =
      typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 767px)') : null
    if (!mq) return
    const onChange = () => setIsMobile(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const toggleSidebar = () => {
    setCollapsed((v) => {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, v ? '0' : '1')
      return !v
    })
  }

  // Ctrl/Cmd + B 快捷键（delta spec: 折叠触发方式）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'b' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        toggleSidebar()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <SidebarContext.Provider
      value={{ state: collapsed ? 'collapsed' : 'expanded', isMobile, openMobile, setOpenMobile, toggleSidebar }}
    >
      <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
    </SidebarContext.Provider>
  )
}

// 收起态图标 tooltip 包装（展开态原样渲染 children）
export function SidebarIcon({ label, children }: { label: string; children: ReactNode }) {
  const { state } = useSidebar()
  if (state !== 'collapsed') return <>{children}</>
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}

// 侧边栏容器：桌面端固定左栏（宽度过渡 200ms）；移动端抽屉（遮罩 + 滑入）。
// 内容由业务传入（header/content/footer 三段），收起态由业务渲染图标栏形态。
export function Sidebar({
  expandedRail,
  collapsedRail,
  className,
}: {
  /** 展开态（及移动端抽屉）内容 */
  expandedRail: ReactNode
  /** 收起态图标栏内容（桌面端收起时渲染） */
  collapsedRail: ReactNode
  className?: string
}) {
  const { state, isMobile, openMobile, setOpenMobile } = useSidebar()

  if (isMobile) {
    if (!openMobile) return null
    return (
      <>
        {/* 遮罩：点击关闭（delta spec: 移动端遮罩关闭） */}
        <div
          data-testid="sidebar-overlay"
          className="fixed inset-0 z-40 bg-black/40"
          onClick={() => setOpenMobile(false)}
        />
        <aside
          data-state="mobile-open"
          className={cn(
            'fixed inset-y-0 left-0 z-50 flex w-64 flex-col animate-slide-in',
            className,
          )}
          style={{ background: 'var(--bg-base-secondary)', borderRight: '1px solid var(--border-neutral-l1)' }}
        >
          {expandedRail}
        </aside>
      </>
    )
  }

  const collapsed = state === 'collapsed'
  return (
    <aside
      data-state={state}
      data-testid="sidebar-rail"
      className={cn('fixed inset-y-0 left-0 z-50 flex flex-col overflow-hidden transition-[width] duration-200 ease-out', className)}
      style={{
        width: collapsed ? 52 : 256,
        background: 'var(--bg-base-secondary)',
        borderRight: '1px solid var(--border-neutral-l1)',
      }}
    >
      {collapsed ? collapsedRail : expandedRail}
    </aside>
  )
}

// 折叠触发按钮（Header 内使用；收起态图标栏自含展开按钮）。
// 图标为「汉堡 ⇄ X」形变（MenuToggleIcon，open 由侧边栏状态驱动）；
// 传入 children 可覆盖默认图标。
export function SidebarTrigger({ className, children }: { className?: string; children?: ReactNode }) {
  const { state, toggleSidebar } = useSidebar()
  return (
    <button
      type="button"
      data-testid="sidebar-trigger"
      aria-label="折叠/展开侧边栏"
      onClick={toggleSidebar}
      className={cn('inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors hover:bg-muted', className)}
    >
      {children ?? <MenuToggleIcon open={state === 'expanded'} className="size-5" />}
    </button>
  )
}

// ── 固定位置折叠按钮（悬浮视口左上，不随侧边栏展开/收起移动）──
// 动画三层：图标 spring 形变（MenuToggleIcon）+ 按钮弹跳 keyframes + 品牌色涟漪光环。
// 桌面端点击折叠/展开侧边栏；移动端点击开合抽屉。
export function SidebarFixedToggle() {
  const { state, toggleSidebar, isMobile, openMobile, setOpenMobile } = useSidebar()
  const expanded = state === 'expanded'
  const controls = useAnimationControls()
  const [rippleKey, setRippleKey] = useState(0)

  const handleToggle = () => {
    // 按钮弹跳（scale keyframes + 轻微 rotate），每次点击经 controls 重播
    void controls.start(
      { scale: [1, 0.8, 1.15, 1], rotate: [0, -10, 6, 0] },
      { type: 'spring', stiffness: 400, damping: 14 },
    )
    setRippleKey((k) => k + 1)
    if (isMobile) {
      setOpenMobile(!openMobile)
      return
    }
    toggleSidebar()
  }

  const iconOpen = isMobile ? openMobile : expanded
  const ariaLabel = isMobile
    ? openMobile ? '关闭侧边栏' : '打开侧边栏'
    : expanded ? '折叠侧边栏' : '展开侧边栏'

  return (
    <motion.button
      type="button"
      data-testid="sidebar-trigger"
      aria-label={ariaLabel}
      onClick={handleToggle}
      whileHover={{ scale: 1.08 }}
      animate={controls}
      className="fixed top-3 left-3 z-[52] flex h-10 w-10 items-center justify-center rounded-xl shadow-md"
      style={{
        background: 'var(--bg-base-default)',
        border: '1px solid var(--border-neutral-l1)',
        color: 'var(--text-secondary)',
      }}
    >
      {/* 涟漪光环：点击时渲染（key 递增触发播放），扩散一圈后淡出 */}
      {rippleKey > 0 && (
        <motion.span
          key={rippleKey}
          className="pointer-events-none absolute inset-0 rounded-xl"
          style={{ border: '2px solid var(--bg-brand)' }}
          initial={{ scale: 1, opacity: 0.7 }}
          animate={{ scale: 2, opacity: 0 }}
          transition={{ duration: 0.55, ease: 'easeOut' }}
        />
      )}
      <MenuToggleIcon open={iconOpen} className="size-5" />
    </motion.button>
  )
}
