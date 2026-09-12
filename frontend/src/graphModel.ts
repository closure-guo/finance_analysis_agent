// 管线 graph 数据模型（add-pipeline-graph-view Task 1）。
// 纯函数：pipelineTree 状态树 + node_start 迭代计数 → React Flow nodes/edges。
// 迭代计数独立于状态机统计（pipelineTree 单调状态语义不动），两视图数据始终一致。

import dagre from 'dagre'
import type { NodeStatus } from './pipelineTree'
import { LAYER_TREE_CONFIG } from './pipelineTree'

// ── 静态边拓扑（与 LAYER_TREE_CONFIG 节点 id 对齐；r1→r2 同侧延续，四方→研究结论）──

export interface GraphEdgeSpec {
  source: string
  target: string
  kind: 'flow' | 'return'
}

export const RETURN_EDGE: GraphEdgeSpec = { source: 'fund_manager', target: 'trader', kind: 'return' }

const PREP_CHAIN = ['check_cache', 'fetch_data', 'validate_financials', 'compute_metrics', 'verify_citations']
const ANALYSTS = ['fundamental_analyst', 'technical_analyst', 'macro_analyst', 'sentiment_analyst']
const R1 = ['aggressive_r1', 'conservative_r1', 'neutral_r1']
const R2 = ['aggressive_r2', 'conservative_r2', 'neutral_r2']

function buildGraphEdges(): GraphEdgeSpec[] {
  const flow: GraphEdgeSpec[] = []
  const chain = (xs: string[]) => xs.slice(0, -1).map((s, i) => ({ source: s, target: xs[i + 1], kind: 'flow' as const }))
  const fan = (sources: string[], targets: string[]) =>
    sources.flatMap((s) => targets.map((t) => ({ source: s, target: t, kind: 'flow' as const })))
  flow.push(...chain(PREP_CHAIN))
  flow.push(...fan(['verify_citations'], ANALYSTS))
  flow.push(...fan(ANALYSTS, ['bull_r1', 'bear_r1']))
  flow.push({ source: 'bull_r1', target: 'bull_r2', kind: 'flow' })
  flow.push({ source: 'bear_r1', target: 'bear_r2', kind: 'flow' })
  flow.push(...fan(['bull_r1', 'bear_r1', 'bull_r2', 'bear_r2'], ['research_manager']))
  flow.push({ source: 'research_manager', target: 'trader', kind: 'flow' })
  flow.push(...fan(['trader'], R1))
  flow.push(...chain(R1))
  flow.push(...fan(R2, ['risk_judge']))
  flow.push({ source: 'risk_judge', target: 'fund_manager', kind: 'flow' })
  flow.push({ source: 'fund_manager', target: 'generate_report', kind: 'flow' })
  flow.push({ source: 'generate_report', target: 'generate_file', kind: 'flow' })
  return flow
}

export const GRAPH_EDGES: GraphEdgeSpec[] = [...buildGraphEdges(), RETURN_EDGE]

// ── 节点元数据（label/layerId 从 LAYER_TREE_CONFIG 单一来源推导）──

const NODE_META: Record<string, { label: string; layerId: string }> = Object.fromEntries(
  LAYER_TREE_CONFIG.flatMap((l) => l.children.map((c) => [c.nodeId, { label: c.label, layerId: l.id }])),
)

// ── 布局常量（dagre TB）──

const NODE_WIDTH = 176
const NODE_HEIGHT = 52
const RANKSEP = 48
const NODESEP = 28

// ── 模型 ──

export interface GraphNode {
  id: string
  label: string
  layerId: string
  status: NodeStatus
  durationMs?: number
  iterations: number
  summary?: string
  position: { x: number; y: number }
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  kind: 'flow' | 'return'
  animated?: boolean
}

export interface GraphModel {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface TreeChildLike {
  nodeId: string
  status: NodeStatus
  durationMs?: number
  output?: { summary?: string } | null
}

// LayerNode[] → React Flow nodes/edges（dagre TB 布局）。
// startCounts：node_id → node_start 累计次数（由 streamStore 维护，见 reduce.ts）。
export function buildGraphModel(tree: { id: string; children: TreeChildLike[] }[], startCounts: Record<string, number>): GraphModel {
  const statusById = new Map<string, TreeChildLike>()
  for (const layer of tree) for (const child of layer.children) statusById.set(child.nodeId, child)

  // dagre 布局
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', ranksep: RANKSEP, nodesep: NODESEP })
  g.setDefaultEdgeLabel(() => ({}))
  const ids = [...statusById.keys()]
  for (const id of ids) g.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  for (const e of GRAPH_EDGES) {
    if (ids.includes(e.source) && ids.includes(e.target)) g.setEdge(e.source, e.target)
  }
  dagre.layout(g)

  const nodes: GraphNode[] = ids.map((id) => {
    const meta = NODE_META[id] ?? { label: id, layerId: 'unknown' }
    const child = statusById.get(id)!
    const pos = g.node(id)
    return {
      id,
      label: meta.label,
      layerId: meta.layerId,
      status: child.status,
      durationMs: child.durationMs,
      iterations: startCounts[id] ?? 0,
      summary: child.output?.summary ?? undefined,
      // dagre 输出中心坐标 → React Flow 左上角坐标
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    }
  })

  const edges: GraphEdge[] = GRAPH_EDGES.filter((e) => ids.includes(e.source) && ids.includes(e.target)).map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    kind: e.kind,
    // 回边在发生重跑（迭代 ≥2）时动画化，静态存在但保持低调
    animated: e.kind === 'return' ? (startCounts[e.source] ?? 0) >= 2 || (startCounts[e.target] ?? 0) >= 2 : false,
  }))

  return { nodes, edges }
}
