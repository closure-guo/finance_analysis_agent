// 管线分层时间轴状态树（redesign-pipeline-hierarchical-timeline Task 2.2）。
// 纯函数模型：node_start/node_complete 事件驱动 6 层 layer → 子节点的状态流转，
// 供 PipelineTimeline 组件纯渲染。状态单调流转：pending → running → completed（无回退）。

// ── 类型 ──

export type NodeStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface ChildNodeState {
  nodeId: string
  label: string
  status: NodeStatus
  startedAt?: number
  completedAt?: number
  durationMs?: number
  output?: { summary?: string; [k: string]: unknown }
}

export interface LayerNode {
  id: string
  label: string
  status: NodeStatus
  children: ChildNodeState[]
  startedAt?: number
  completedAt?: number
  durationMs?: number
}

// ── 静态配置：6 层 → 子节点映射（与后端 pipeline_runner.LAYER_TREE_CONFIG 对齐）──

interface ChildConfig {
  nodeId: string
  label: string
}

interface LayerConfig {
  id: string
  label: string
  children: ChildConfig[]
}

export const LAYER_TREE_CONFIG: LayerConfig[] = [
  {
    id: 'prep',
    label: 'PREP',
    children: [
      { nodeId: 'check_cache', label: '数据准备' },
      { nodeId: 'fetch_data', label: '获取数据' },
      { nodeId: 'validate_financials', label: '勾稽校验' },
      { nodeId: 'compute_metrics', label: '指标计算' },
      { nodeId: 'verify_citations', label: '引用校验' },
    ],
  },
  {
    id: 'layer1',
    label: 'Layer I',
    children: [
      { nodeId: 'fundamental_analyst', label: '基本面' },
      { nodeId: 'technical_analyst', label: '技术面' },
      { nodeId: 'macro_analyst', label: '宏观' },
      { nodeId: 'sentiment_analyst', label: '舆情' },
    ],
  },
  {
    id: 'layer2',
    label: 'Layer II',
    children: [
      { nodeId: 'bull_r1', label: '看多 R1' },
      { nodeId: 'bear_r1', label: '看空 R1' },
      { nodeId: 'bull_r2', label: '看多 R2' },
      { nodeId: 'bear_r2', label: '看空 R2' },
      { nodeId: 'research_manager', label: '研究结论' },
    ],
  },
  {
    id: 'trader',
    label: 'Trader',
    children: [{ nodeId: 'trader', label: '交易决策' }],
  },
  {
    id: 'risk',
    label: 'Risk',
    children: [
      { nodeId: 'aggressive_r1', label: '激进风控 R1' },
      { nodeId: 'conservative_r1', label: '保守风控 R1' },
      { nodeId: 'neutral_r1', label: '中性风控 R1' },
      { nodeId: 'aggressive_r2', label: '激进风控 R2' },
      { nodeId: 'conservative_r2', label: '保守风控 R2' },
      { nodeId: 'neutral_r2', label: '中性风控 R2' },
      { nodeId: 'risk_judge', label: '风控裁决' },
    ],
  },
  {
    id: 'fund',
    label: 'Fund',
    children: [
      { nodeId: 'fund_manager', label: '基金经理' },
      { nodeId: 'generate_report', label: '报告生成' },
      { nodeId: 'generate_file', label: '文件导出' },
    ],
  },
]

// node_id → (layerId, childIndex) 索引（静态预计算）
const NODE_INDEX: Record<string, { layerId: string }> = Object.fromEntries(
  LAYER_TREE_CONFIG.flatMap((l) => l.children.map((c) => [c.nodeId, { layerId: l.id }])),
)

// ── 构建初始树 ──

export function buildLayerTree(): LayerNode[] {
  return LAYER_TREE_CONFIG.map((l) => ({
    id: l.id,
    label: l.label,
    status: 'pending',
    children: l.children.map((c) => ({ nodeId: c.nodeId, label: c.label, status: 'pending' as NodeStatus })),
  }))
}

// ── 事件应用 ──

interface NodeEventLike {
  type: 'node_start' | 'node_complete' | 'node_timing'
  node_id: string
  output?: { summary?: string; [k: string]: unknown }
  // 后端真实生命周期时间戳（fix-node-timer-real-lifecycle）：
  // node_start 携带 server_start_ts；node_timing 携带完整三元组（node_end 到达时下发）
  server_start_ts?: number
  server_end_ts?: number
  server_duration_ms?: number
}

// 应用 node_start / node_complete / node_timing 事件，返回新树（不可变更新）。
// nowMs 为事件到达时间戳（ms epoch），由调用方注入以便测试。
// 时间戳优先级：后端 server_*（真实生命周期）> nowMs（到达时刻近似）。
export function applyNodeEvent(tree: LayerNode[], event: NodeEventLike, nowMs: number): LayerNode[] {
  const loc = NODE_INDEX[event.node_id]
  if (!loc) return tree

  return tree.map((layer) => {
    if (layer.id !== loc.layerId) return layer

    const children = layer.children.map((child) => {
      if (child.nodeId !== event.node_id) return child

      // node_timing：node_end 到达时下发，用后端真实耗时覆盖 updates 近似值。
      // 不受"completed 不回退"限制——它只更新时间戳/耗时，不改状态。
      if (event.type === 'node_timing') {
        const startedAt = event.server_start_ts ?? child.startedAt
        const durationMs =
          event.server_duration_ms ??
          (event.server_end_ts !== undefined && startedAt !== undefined
            ? Math.max(0, event.server_end_ts - startedAt)
            : child.durationMs)
        return {
          ...child,
          startedAt,
          completedAt: event.server_end_ts ?? child.completedAt,
          durationMs,
        }
      }

      // 状态单调：completed 不回退
      if (child.status === 'completed') return child
      if (event.type === 'node_start') {
        // 优先后端真实入口时间戳
        const startedAt = event.server_start_ts ?? child.startedAt ?? nowMs
        return { ...child, status: 'running' as NodeStatus, startedAt }
      }
      // node_complete：优先后端入口时间戳；耗时为近似值（node_timing 到达后被覆盖）
      const startedAt = event.server_start_ts ?? child.startedAt ?? nowMs
      return {
        ...child,
        status: 'completed' as NodeStatus,
        startedAt,
        completedAt: nowMs,
        durationMs: Math.max(0, nowMs - startedAt),
        output: event.output ?? child.output,
      }
    })

    // 推导 layer 状态：任一 running → running；全部 completed → completed
    const anyRunning = children.some((c) => c.status === 'running')
    const allCompleted = children.every((c) => c.status === 'completed')
    let status = layer.status
    if (status !== 'completed') {
      if (allCompleted && children.length > 0) status = 'completed'
      else if (anyRunning) status = 'running'
    }

    const layerStartedAt = layer.startedAt ?? (anyRunning || allCompleted ? nowMs : undefined)
    const layerCompletedAt = status === 'completed' ? (layer.completedAt ?? nowMs) : layer.completedAt
    const durationMs =
      status === 'completed' && layerStartedAt !== undefined && layerCompletedAt !== undefined
        ? Math.max(0, layerCompletedAt - layerStartedAt)
        : layer.durationMs

    return { ...layer, status, children, startedAt: layerStartedAt, completedAt: layerCompletedAt, durationMs }
  })
}

// ── 查询辅助 ──

// 当前运行节点（首个 running 子节点），用于自动滚动与高亮
export function findRunningNode(tree: LayerNode[]): { layerId: string; nodeId: string } | null {
  for (const layer of tree) {
    for (const child of layer.children) {
      if (child.status === 'running') return { layerId: layer.id, nodeId: child.nodeId }
    }
  }
  return null
}

// 已完成节点数 / 总节点数（整体进度）
export function treeProgress(tree: LayerNode[]): { completed: number; total: number } {
  let completed = 0
  let total = 0
  for (const layer of tree) {
    for (const child of layer.children) {
      total += 1
      if (child.status === 'completed') completed += 1
    }
  }
  return { completed, total }
}

// ── 序列化（会话快照持久化/恢复，resume-pipeline-across-sessions）──

// LayerNode 为纯数据，可直接 JSON；反序列化失败时回退初始树
export function serializeLayerTree(tree: LayerNode[]): string {
  return JSON.stringify(tree)
}

export function deserializeLayerTree(json: string | null | undefined): LayerNode[] {
  if (!json) return buildLayerTree()
  try {
    const data = JSON.parse(json)
    if (!Array.isArray(data)) return buildLayerTree()
    return data as LayerNode[]
  } catch {
    return buildLayerTree()
  }
}
