// 管线分层时间轴组件（redesign-pipeline-hierarchical-timeline Task 3.2）。
// 6 层 layer 节点 + 可展开子节点列表：状态图标（等待/运行/完成/失败）、
// 层/节点耗时、当前运行节点高亮与实时思考摘要内联。
// 展开默认策略：运行层展开、完成层折叠、未到层折叠；用户手动操作覆盖默认（会话内记忆）。

import { useEffect, useRef, useState } from 'react'
import type { LayerNode, ChildNodeState, NodeStatus } from './pipelineTree'
import { findRunningNode } from './pipelineTree'
import { formatDurationMs } from './eta'

// ── 状态图标 ──

function StatusIcon({ status }: { status: NodeStatus }) {
  if (status === 'completed') {
    return <i className="fas fa-check-circle" style={{ color: 'var(--status-success-default)', fontSize: '13px' }} />
  }
  if (status === 'running') {
    return (
      <span className="relative flex h-2.5 w-2.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }} />
        <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: 'var(--bg-brand)' }} />
      </span>
    )
  }
  if (status === 'failed') {
    return <i className="fas fa-times-circle" style={{ color: 'var(--status-error-default)', fontSize: '13px' }} />
  }
  // pending
  return <span className="inline-block rounded-full" style={{ width: '9px', height: '9px', border: '1.5px solid var(--border-neutral-l2)' }} />
}

// ── 子节点行 ──

function ChildRow({
  child,
  isCurrent,
  nowMs,
  thinkingPreview,
  onToggle,
  expanded,
}: {
  child: ChildNodeState
  isCurrent: boolean
  nowMs: number
  thinkingPreview?: string
  onToggle?: () => void
  expanded?: boolean
}) {
  // 当前运行节点的已运行时长；已完成节点显示总耗时
  const timeText =
    child.status === 'running' && child.startedAt !== undefined
      ? formatDurationMs(Math.max(0, nowMs - child.startedAt))
      : child.status === 'completed' && child.durationMs !== undefined
        ? formatDurationMs(child.durationMs)
        : null

  return (
    <div
      data-current={isCurrent ? 'true' : undefined}
      data-node-id={child.nodeId}
      className="rounded-lg transition-colors"
      style={{
        background: isCurrent ? 'var(--bg-brand-popup)' : 'transparent',
        borderLeft: isCurrent ? '2px solid var(--bg-brand)' : '2px solid transparent',
      }}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-2.5 py-1.5 text-left"
        style={{ cursor: onToggle ? 'pointer' : 'default' }}
      >
        <StatusIcon status={child.status} />
        <span
          className="text-xs flex-1 min-w-0 truncate"
          style={{
            color: child.status === 'pending' ? 'var(--text-tertiary)' : 'var(--text-secondary)',
            fontWeight: isCurrent ? 600 : 400,
          }}
        >
          {child.label}
        </span>
        {timeText && (
          <span
            className="text-[10px] font-mono flex-shrink-0"
            style={{ color: child.status === 'running' ? 'var(--status-warning-default)' : 'var(--text-tertiary)' }}
          >
            {timeText}
          </span>
        )}
        {child.status === 'completed' && child.output?.summary && (
          <span className="text-[10px] flex-shrink-0 truncate max-w-[40%]" style={{ color: 'var(--text-tertiary)' }}>
            {child.output.summary}
          </span>
        )}
      </button>
      {/* 当前节点内联实时思考摘要（单行预览） */}
      {isCurrent && thinkingPreview && (
        <div className="px-2.5 pb-1.5 pl-8">
          <p className="text-[11px] truncate" style={{ color: 'var(--text-tertiary)' }}>
            {thinkingPreview}
          </p>
        </div>
      )}
      {/* 展开的完整 timeline 由父层渲染（expanded 时） */}
      {expanded && <div className="px-2.5 pb-2" />}
    </div>
  )
}

// ── Layer 行 ──

function LayerRow({
  layer,
  expanded,
  onToggle,
  runningNodeId,
  nowMs,
  thinkingPreviewFor,
}: {
  layer: LayerNode
  expanded: boolean
  onToggle: () => void
  runningNodeId: string | null
  nowMs: number
  thinkingPreviewFor: (nodeId: string) => string | undefined
}) {
  const completedCount = layer.children.filter((c) => c.status === 'completed').length
  const total = layer.children.length

  const layerTimeText =
    layer.status === 'completed' && layer.durationMs !== undefined
      ? formatDurationMs(layer.durationMs)
      : layer.status === 'running' && layer.startedAt !== undefined
        ? formatDurationMs(Math.max(0, nowMs - layer.startedAt))
        : null

  return (
    <div data-layer-id={layer.id} className="mb-1">
      {/* Layer 标题行 */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left transition-colors"
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
      >
        <StatusIcon status={layer.status} />
        <span
          className="text-xs font-semibold flex-1"
          style={{ color: layer.status === 'pending' ? 'var(--text-tertiary)' : 'var(--text-secondary)' }}
        >
          {layer.label}
        </span>
        {layer.status !== 'pending' && (
          <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
            {completedCount}/{total}
          </span>
        )}
        {layerTimeText && (
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
            {layerTimeText}
          </span>
        )}
        <i
          className={`fas fa-chevron-down text-[9px] transition-transform ${expanded ? '' : 'rotate-[-90deg]'}`}
          style={{ color: 'var(--text-tertiary)' }}
        />
      </button>

      {/* 子节点列表（展开时） */}
      {expanded && (
        <div className="ml-4 mt-0.5 flex flex-col gap-0.5">
          {layer.children.map((child) => (
            <ChildRow
              key={child.nodeId}
              child={child}
              isCurrent={child.nodeId === runningNodeId}
              nowMs={nowMs}
              thinkingPreview={thinkingPreviewFor(child.nodeId)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── 主组件 ──

export function PipelineTimeline({
  tree,
  nowMs,
  thinkingPreviewFor,
}: {
  tree: LayerNode[]
  nowMs: number
  // 当前运行节点的实时思考单行预览（由父组件从 nodeTimelines 提取）
  thinkingPreviewFor?: (nodeId: string) => string | undefined
}) {
  const running = findRunningNode(tree)
  const runningNodeId = running?.nodeId ?? null

  // 展开状态：默认策略 = 非 pending 层（运行中/已完成）展开、未开始层折叠；
  // 用户手动操作覆盖（会话内记忆）。已完成层保持展开以便回看分析师结果与耗时。
  const [expandedOverride, setExpandedOverride] = useState<Record<string, boolean>>({})

  // 自动滚动定位当前节点（running 节点切换时平滑滚动；用户手动滚动 3s 内暂停）
  const containerRef = useRef<HTMLDivElement>(null)
  const lastUserScrollRef = useRef(0)
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const onScroll = () => { lastUserScrollRef.current = Date.now() }
    // 监听最近的可滚动祖先（消息列表容器），此处用容器自身代理用户滚轮/触摸意图
    container.addEventListener('wheel', onScroll, { passive: true })
    container.addEventListener('touchmove', onScroll, { passive: true })
    return () => {
      container.removeEventListener('wheel', onScroll)
      container.removeEventListener('touchmove', onScroll)
    }
  }, [])
  useEffect(() => {
    if (!runningNodeId) return
    if (Date.now() - lastUserScrollRef.current < 3000) return // 用户刚滚动过，暂停自动滚动
    const el = containerRef.current?.querySelector(`[data-node-id="${runningNodeId}"]`)
    // jsdom 等环境无 scrollIntoView，防御性调用
    el?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [runningNodeId])

  const isExpanded = (layer: LayerNode): boolean => {
    if (layer.id in expandedOverride) return expandedOverride[layer.id]
    return layer.status !== 'pending'
  }

  const toggle = (layer: LayerNode) => {
    setExpandedOverride((prev) => ({ ...prev, [layer.id]: !isExpanded(layer) }))
  }

  const preview = thinkingPreviewFor ?? (() => undefined)

  return (
    <div className="px-3 py-2" data-testid="pipeline-timeline" ref={containerRef}>
      {tree.map((layer) => (
        <LayerRow
          key={layer.id}
          layer={layer}
          expanded={isExpanded(layer)}
          onToggle={() => toggle(layer)}
          runningNodeId={runningNodeId}
          nowMs={nowMs}
          thinkingPreviewFor={preview}
        />
      ))}
    </div>
  )
}
