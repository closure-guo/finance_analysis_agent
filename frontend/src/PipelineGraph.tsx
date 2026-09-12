// 管线 graph 视图（add-pipeline-graph-view Task 3）。
// React Flow DAG 渲染：状态着色节点 + 耗时 + 迭代徽标 + FM→Trader 回边动画 + 点击悬浮卡片。
// 数据来自 graphModel 纯函数（消费 pipelineTree 状态树，与列表视图同源）。

import { useCallback, useMemo, useState } from 'react'
import {
  ReactFlow,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { LayerNode, NodeStatus } from './pipelineTree'
import { buildGraphModel, type GraphNode } from './graphModel'

// ── 状态样式（与 PipelineTimeline.StatusIcon 同色系：CSS 变量，不做明暗硬编码）──

const STATUS_BG: Record<NodeStatus, string> = {
  pending: 'var(--bg-overlay-l1)',
  running: 'var(--bg-brand-soft, var(--bg-overlay-l1))',
  completed: 'var(--status-success-bg, var(--bg-overlay-l1))',
  failed: 'var(--status-error-bg, var(--bg-overlay-l1))',
}
const STATUS_BORDER: Record<NodeStatus, string> = {
  pending: 'var(--border-neutral-l2)',
  running: 'var(--bg-brand)',
  completed: 'var(--status-success-default)',
  failed: 'var(--status-error-default)',
}
const STATUS_TEXT: Record<NodeStatus, string> = {
  pending: 'var(--text-tertiary)',
  running: 'var(--bg-brand)',
  completed: 'var(--status-success-default)',
  failed: 'var(--status-error-default)',
}

const STATUS_LABEL: Record<NodeStatus, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
}

function formatDuration(ms?: number): string {
  if (ms === undefined) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ── 自定义节点 ──

function PipelineNode({ data }: NodeProps) {
  const node = data as GraphNode
  const running = node.status === 'running'
  return (
    <div
      data-testid={`graph-node-${node.id}`}
      data-status={node.status}
      className="relative rounded-lg px-3 py-2 cursor-pointer transition-shadow"
      style={{
        width: 176,
        height: 52,
        background: STATUS_BG[node.status],
        border: `1.5px solid ${STATUS_BORDER[node.status]}`,
        boxShadow: running ? '0 0 0 2px var(--bg-brand-soft, var(--bg-overlay-l1))' : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div className="flex items-center gap-1.5">
        {running && (
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }} />
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }} />
          </span>
        )}
        <span className="text-xs font-medium truncate" style={{ color: running ? STATUS_TEXT.running : 'var(--text-primary)' }}>
          {node.label}
        </span>
        {node.status === 'completed' && <i className="fas fa-check-circle text-[10px] flex-shrink-0" style={{ color: 'var(--status-success-default)' }} />}
        {node.status === 'failed' && <i className="fas fa-times-circle text-[10px] flex-shrink-0" style={{ color: 'var(--status-error-default)' }} />}
      </div>
      <div className="flex items-center justify-between mt-0.5">
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
          {formatDuration(node.durationMs)}
        </span>
      </div>
      {node.iterations >= 2 && (
        <span
          data-testid={`graph-iterations-${node.id}`}
          className="absolute -top-2 -right-2 px-1.5 py-0.5 rounded-full text-[10px] font-mono text-white"
          style={{ background: 'var(--bg-brand)' }}
        >
          ×{node.iterations}
        </span>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes = { pipeline: PipelineNode }

// ── 组件 ──

export interface PipelineGraphProps {
  tree: LayerNode[]
  startCounts: Record<string, number>
  onViewDetails: (layerId: string) => void
}

export function PipelineGraph({ tree, startCounts, onViewDetails }: PipelineGraphProps) {
  const [selected, setSelected] = useState<GraphNode | null>(null)

  const { nodes, edges } = useMemo(() => buildGraphModel(tree, startCounts), [tree, startCounts])

  const rfNodes: Node[] = useMemo(
    () => nodes.map((n) => ({ id: n.id, type: 'pipeline', position: n.position, data: n as unknown as Record<string, unknown> })),
    [nodes],
  )

  const rfEdges: Edge[] = useMemo(
    () =>
      edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        animated: e.animated,
        style:
          e.kind === 'return'
            ? { stroke: 'var(--bg-brand)', strokeDasharray: e.animated ? undefined : '5 4', opacity: e.animated ? 1 : 0.45 }
            : { stroke: 'var(--border-neutral-l2)' },
      })),
    [edges],
  )

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelected(node.data as unknown as GraphNode)
  }, [])

  return (
    <div className="relative" style={{ height: 480 }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        minZoom={0.4}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        zoomOnScroll={false}
      >
        {/* bg 色点阵仅装饰，@xyflow 默认即可，无需额外组件 */}
      </ReactFlow>

      {selected && (
        <div
          data-testid="graph-details-card"
          className="absolute right-3 top-3 z-10 w-64 rounded-xl p-4 shadow-lg"
          style={{ background: 'var(--bg-primary)', border: '1px solid var(--border-neutral-l1)' }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
              {selected.label}
            </span>
            <button
              type="button"
              aria-label="关闭"
              className="text-[10px] px-1"
              style={{ color: 'var(--text-tertiary)' }}
              onClick={() => setSelected(null)}
            >
              ✕
            </button>
          </div>
          <div className="text-xs mb-1" style={{ color: STATUS_TEXT[selected.status] }}>
            {STATUS_LABEL[selected.status]}
            {selected.status === 'running' && selected.durationMs !== undefined ? ` · 已运行 ${formatDuration(selected.durationMs)}` : ''}
            {selected.durationMs !== undefined && selected.status !== 'running' ? ` · 耗时 ${formatDuration(selected.durationMs)}` : ''}
          </div>
          {selected.iterations >= 2 && (
            <div className="text-xs mb-1" style={{ color: 'var(--bg-brand)' }}>
              已重跑 {selected.iterations - 1} 次
            </div>
          )}
          {selected.summary && (
            <div data-testid="graph-details-summary" className="text-xs leading-relaxed mb-2" style={{ color: 'var(--text-secondary)' }}>
              {selected.summary}
            </div>
          )}
          <button
            type="button"
            data-testid="graph-details-view"
            className="text-xs px-2 py-1 rounded-md w-full"
            style={{ background: 'var(--bg-overlay-l1)', color: 'var(--text-secondary)' }}
            onClick={() => onViewDetails(selected.layerId)}
          >
            查看详情
          </button>
        </div>
      )}
    </div>
  )
}
