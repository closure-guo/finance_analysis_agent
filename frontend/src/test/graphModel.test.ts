// graphModel 纯函数测试（add-pipeline-graph-view Task 1，TDD 先行）
// 覆盖：LayerNode[] → nodes/edges 映射、dagre 布局坐标、迭代计数、回边生成、空树
import { describe, expect, it } from 'vitest'
import { buildLayerTree, applyNodeEvent, type LayerNode } from '../pipelineTree'
import { buildGraphModel, GRAPH_EDGES, RETURN_EDGE } from '../graphModel'

// 事件快捷构造器
const start = (nodeId: string) => ({ type: 'node_start' as const, node_id: nodeId })
const complete = (nodeId: string, summary?: string) => ({
  type: 'node_complete' as const,
  node_id: nodeId,
  ...(summary ? { output: { summary } } : {}),
})

// 推进若干事件得到一棵真实状态树
function runTree(events: Parameters<typeof applyNodeEvent>[1][]): LayerNode[] {
  let tree = buildLayerTree()
  for (const e of events) tree = applyNodeEvent(tree, e, 1000)
  return tree
}

describe('GRAPH_EDGES 静态拓扑', () => {
  it('覆盖全部 26 个节点（有边可达）', () => {
    const nodesInEdges = new Set(GRAPH_EDGES.flatMap((e) => [e.source, e.target]))
    const configNodes = new Set(
      // 从初始树取全部 nodeId，避免与 LAYER_TREE_CONFIG 双源不一致
      buildLayerTree().flatMap((l) => l.children.map((c) => c.nodeId)),
    )
    for (const n of configNodes) expect(nodesInEdges.has(n), `节点 ${n} 不在任何边上`).toBe(true)
  })

  it('包含 FM→Trader 条件回边且 kind=return', () => {
    expect(RETURN_EDGE.source).toBe('fund_manager')
    expect(RETURN_EDGE.target).toBe('trader')
    expect(GRAPH_EDGES).toContainEqual(RETURN_EDGE)
  })

  it('不存在指向不存在的节点的边', () => {
    const known = new Set(buildLayerTree().flatMap((l) => l.children.map((c) => c.nodeId)))
    for (const e of GRAPH_EDGES) {
      expect(known.has(e.source), `未知 source ${e.source}`).toBe(true)
      expect(known.has(e.target), `未知 target ${e.target}`).toBe(true)
    }
  })
})

describe('GRAPH_EDGES 风控层拓扑', () => {
  // 复现 2026-10-08 用户反馈：R1→R2 边缺失使 R2 子图成孤岛（dagre 摆右列，
  // 视觉上呈「交易决策向右 T 型分支」）；chain(R1) 把并行三方画成串行竖链
  it('flow 边有向可达：从 check_cache 沿 flow 边可到达全部其余节点（回边除外）', () => {
    // 有向语义：DAG 数据流连通。无向遍历会被 FM→Trader 回边桥接，
    // 掩盖 R2 孤岛（10-08 实际病灶），故必须按 kind=flow 有向遍历
    const all = buildLayerTree().flatMap((l) => l.children.map((c) => c.nodeId))
    const adj = new Map<string, string[]>(all.map((n) => [n, []]))
    for (const e of GRAPH_EDGES) {
      if (e.kind === 'flow') adj.get(e.source)!.push(e.target)
    }
    const seen = new Set(['check_cache'])
    const queue = ['check_cache']
    while (queue.length) {
      const cur = queue.shift()!
      for (const nxt of adj.get(cur) ?? []) {
        if (!seen.has(nxt)) {
          seen.add(nxt)
          queue.push(nxt)
        }
      }
    }
    for (const n of all) expect(seen.has(n), `节点 ${n} 沿 flow 边不可达`).toBe(true)
  })

  it('风控三方 R1→R2 同侧延续（对齐多空辩论层 bull_r1→bull_r2 写法）', () => {
    expect(GRAPH_EDGES).toContainEqual({ source: 'aggressive_r1', target: 'aggressive_r2', kind: 'flow' })
    expect(GRAPH_EDGES).toContainEqual({ source: 'conservative_r1', target: 'conservative_r2', kind: 'flow' })
    expect(GRAPH_EDGES).toContainEqual({ source: 'neutral_r1', target: 'neutral_r2', kind: 'flow' })
  })

  it('风控三方 R1 并行非串行：不存在 R1→R1 链边', () => {
    const r1 = ['aggressive_r1', 'conservative_r1', 'neutral_r1']
    for (const s of r1) {
      for (const t of r1) {
        if (s === t) continue
        expect(GRAPH_EDGES, `${s}→${t} 不应存在（三方并行）`).not.toContainEqual({
          source: s,
          target: t,
          kind: 'flow',
        })
      }
    }
  })

  it('风控三方同层并行渲染：R1 三节点 y 相同、R2 三节点 y 相同', () => {
    const { nodes } = buildGraphModel(buildLayerTree(), {})
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const r1 = ['aggressive_r1', 'conservative_r1', 'neutral_r1'].map((id) => byId.get(id)!)
    const r2 = ['aggressive_r2', 'conservative_r2', 'neutral_r2'].map((id) => byId.get(id)!)
    expect(new Set(r1.map((n) => n.position.y)).size).toBe(1)
    expect(new Set(r1.map((n) => n.position.x)).size).toBe(3)
    expect(new Set(r2.map((n) => n.position.y)).size).toBe(1)
    expect(new Set(r2.map((n) => n.position.x)).size).toBe(3)
  })
})

describe('buildGraphModel: 节点映射', () => {
  it('空树（无节点状态）仍产出全部节点 pending', () => {
    const { nodes } = buildGraphModel(buildLayerTree(), {})
    const total = buildLayerTree().reduce((acc, l) => acc + l.children.length, 0)
    expect(nodes.length).toBe(total)
    expect(nodes.every((n) => n.status === 'pending')).toBe(true)
  })

  it('状态与耗时来自状态树，摘要来自 output.summary', () => {
    const tree = runTree([start('fundamental_analyst'), complete('fundamental_analyst', '基本面结论：中性')])
    const { nodes } = buildGraphModel(tree, {})
    const fa = nodes.find((n) => n.id === 'fundamental_analyst')!
    expect(fa.status).toBe('completed')
    expect(fa.durationMs).toBe(0) // 同一 nowMs，耗时 0
    expect(fa.summary).toBe('基本面结论：中性')
    const ta = nodes.find((n) => n.id === 'technical_analyst')!
    expect(ta.status).toBe('pending')
  })

  it('每个节点有 dagre 布局坐标且并行层 y 相同', () => {
    const { nodes } = buildGraphModel(buildLayerTree(), {})
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const analysts = ['fundamental_analyst', 'technical_analyst', 'macro_analyst', 'sentiment_analyst'].map(
      (id) => byId.get(id)!,
    )
    expect(analysts.every((n) => n.position.x !== undefined && n.position.y !== undefined)).toBe(true)
    // Layer I 四节点同层：y 相同、x 互不重叠（dagre 水平排序不构成契约）
    expect(new Set(analysts.map((n) => n.position.y)).size).toBe(1)
    const xs = analysts.map((n) => n.position.x)
    expect(new Set(xs).size).toBe(4)
  })
})

describe('buildGraphModel: 迭代计数', () => {
  it('startCounts 驱动迭代徽标数', () => {
    const tree = runTree([start('trader'), complete('trader'), start('trader')])
    const { nodes } = buildGraphModel(tree, { trader: 2 })
    const trader = nodes.find((n) => n.id === 'trader')!
    expect(trader.iterations).toBe(2)
  })

  it('无重跑节点 iterations 为 1（已开始）且不显示徽标语义由渲染层判断', () => {
    const tree = runTree([start('trader')])
    const { nodes } = buildGraphModel(tree, { trader: 1 })
    expect(nodes.find((n) => n.id === 'trader')!.iterations).toBe(1)
  })
})

describe('buildGraphModel: 边', () => {
  it('flow 边齐全；return 边 iterations<2 时不动画、≥2 时动画', () => {
    const tree = buildLayerTree()
    const idle = buildGraphModel(tree, {})
    const retIdle = idle.edges.find((e) => e.kind === 'return')!
    expect(retIdle.animated).toBeFalsy()

    const rerun = buildGraphModel(tree, { trader: 2, fund_manager: 2 })
    const retRun = rerun.edges.find((e) => e.kind === 'return')!
    expect(retRun.animated).toBe(true)
  })

  it('边端点都能在 nodes 中找到（React Flow 契约）', () => {
    const { nodes, edges } = buildGraphModel(buildLayerTree(), {})
    const ids = new Set(nodes.map((n) => n.id))
    for (const e of edges) {
      expect(ids.has(e.source)).toBe(true)
      expect(ids.has(e.target)).toBe(true)
    }
  })
})
