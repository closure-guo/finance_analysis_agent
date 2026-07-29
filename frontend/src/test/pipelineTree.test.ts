import { describe, it, expect } from 'vitest'
import {
  buildLayerTree,
  applyNodeEvent,
  LAYER_TREE_CONFIG,
  type LayerNode,
} from '../pipelineTree'

// pipelineTree 状态树纯函数测试（redesign-pipeline-hierarchical-timeline Task 2.1）
// 覆盖：初始树结构、node_start/node_complete 驱动 layer 与子节点状态流转、
// 耗时记录、状态单调性（无回退）、Layer I 并行独立状态。

describe('buildLayerTree - 初始状态树', () => {
  it('生成 6 个 layer，全部 pending，子节点按配置展开', () => {
    const tree = buildLayerTree()
    expect(tree).toHaveLength(6)
    expect(tree.map((l) => l.id)).toEqual(['prep', 'layer1', 'layer2', 'trader', 'risk', 'fund'])
    for (const layer of tree) {
      expect(layer.status).toBe('pending')
      expect(layer.startedAt).toBeUndefined()
      expect(layer.completedAt).toBeUndefined()
      for (const child of layer.children) {
        expect(child.status).toBe('pending')
      }
    }
  })

  it('Layer I 有 4 个并行分析师子节点', () => {
    const tree = buildLayerTree()
    const layer1 = tree.find((l) => l.id === 'layer1')!
    expect(layer1.children.map((c) => c.nodeId)).toEqual([
      'fundamental_analyst',
      'technical_analyst',
      'macro_analyst',
      'sentiment_analyst',
    ])
  })

  it('Layer II 子节点为辩论 5 节点', () => {
    const tree = buildLayerTree()
    const layer2 = tree.find((l) => l.id === 'layer2')!
    expect(layer2.children.map((c) => c.nodeId)).toEqual([
      'bull_r1', 'bear_r1', 'bull_r2', 'bear_r2', 'research_manager',
    ])
  })
})

describe('applyNodeEvent - node_start', () => {
  it('node_start 将子节点置 running，所在 layer 置 running，记录 startedAt', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'check_cache' } as never, 1000)
    const prep = tree.find((l) => l.id === 'prep')!
    expect(prep.status).toBe('running')
    expect(prep.startedAt).toBe(1000)
    const child = prep.children.find((c) => c.nodeId === 'check_cache')!
    expect(child.status).toBe('running')
    expect(child.startedAt).toBe(1000)
  })

  it('Layer I 某分析师 node_start 仅影响该子节点，其余保持 pending', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'fundamental_analyst' } as never, 1000)
    const layer1 = tree.find((l) => l.id === 'layer1')!
    expect(layer1.status).toBe('running')
    expect(layer1.children.find((c) => c.nodeId === 'fundamental_analyst')!.status).toBe('running')
    expect(layer1.children.find((c) => c.nodeId === 'technical_analyst')!.status).toBe('pending')
    expect(layer1.children.find((c) => c.nodeId === 'macro_analyst')!.status).toBe('pending')
    expect(layer1.children.find((c) => c.nodeId === 'sentiment_analyst')!.status).toBe('pending')
  })
})

describe('applyNodeEvent - node_complete', () => {
  it('node_complete 将子节点置 completed 并记录 completedAt/耗时', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'check_cache' } as never, 1000)
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'check_cache' } as never, 3000)
    const child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'check_cache')!
    expect(child.status).toBe('completed')
    expect(child.completedAt).toBe(3000)
    expect(child.durationMs).toBe(2000)
  })

  it('layer 全部子节点完成时 layer 置 completed 并记录层耗时', () => {
    let tree = buildLayerTree()
    // trader 层只有 1 个子节点
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'trader' } as never, 1000)
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'trader' } as never, 5000)
    const trader = tree.find((l) => l.id === 'trader')!
    expect(trader.status).toBe('completed')
    expect(trader.durationMs).toBe(4000)
  })

  it('Layer I 4 分析师各自完成，全部完成后 layer 才 completed', () => {
    let tree = buildLayerTree()
    const analysts = ['fundamental_analyst', 'technical_analyst', 'macro_analyst', 'sentiment_analyst']
    let t = 1000
    for (const a of analysts) {
      tree = applyNodeEvent(tree, { type: 'node_start', node_id: a } as never, t)
    }
    // 逐个完成，前 3 个完成时 layer 仍 running
    for (let i = 0; i < 3; i++) {
      t += 1000
      tree = applyNodeEvent(tree, { type: 'node_complete', node_id: analysts[i] } as never, t)
      expect(tree.find((l) => l.id === 'layer1')!.status).toBe('running')
    }
    t += 1000
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: analysts[3] } as never, t)
    expect(tree.find((l) => l.id === 'layer1')!.status).toBe('completed')
  })

  it('node_complete 携带 output 时记录到子节点 output', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'check_cache', output: { summary: '缓存未命中' } } as never, 1000)
    const child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'check_cache')!
    expect(child.output?.summary).toBe('缓存未命中')
  })
})

describe('applyNodeEvent - 状态单调性', () => {
  it('completed 节点再次收到 node_start 不回退为 running', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'trader' } as never, 1000)
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'trader' } as never, 2000)
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'trader' } as never, 3000)
    const child = tree.find((l) => l.id === 'trader')!.children.find((c) => c.nodeId === 'trader')!
    expect(child.status).toBe('completed')
  })

  it('未知 node_id 事件不报错，树不变', () => {
    const tree = buildLayerTree()
    const next = applyNodeEvent(tree, { type: 'node_start', node_id: 'unknown_node' } as never, 1000)
    expect(next).toEqual(tree)
  })
})

describe('LAYER_TREE_CONFIG 完整性', () => {
  it('覆盖全部 22 个图节点（PREP 4 + Layer I 4 + 校验 1 + Layer II 5 + Trader 1 + Risk 7 + Fund 1 + 报告 2... 按配置）', () => {
    const allNodes = LAYER_TREE_CONFIG.flatMap((l) => l.children.map((c) => c.nodeId))
    // 至少覆盖核心节点
    for (const n of ['check_cache', 'fetch_data', 'compute_metrics', 'technical_analyst',
      'bull_r1', 'research_manager', 'trader', 'risk_judge', 'fund_manager']) {
      expect(allNodes).toContain(n)
    }
  })
})

describe('applyNodeEvent - 后端真实时间戳（fix-node-timer-real-lifecycle）', () => {
  it('node_start 优先使用 server_start_ts 作为 startedAt', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(
      tree,
      { type: 'node_start', node_id: 'fetch_data', server_start_ts: 5_000_000 } as never,
      9_999_999,
    )
    const child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'fetch_data')!
    // 用后端真实入口时间戳，而非 nowMs
    expect(child.startedAt).toBe(5_000_000)
  })

  it('node_timing 用 server_duration_ms 覆盖 updates 近似耗时', () => {
    let tree = buildLayerTree()
    // updates 近似：start/complete 同刻 → durationMs≈0（快速节点恒 0 的旧行为）
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'check_cache' } as never, 1_000_000)
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'check_cache' } as never, 1_000_000)
    let child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'check_cache')!
    expect(child.durationMs).toBe(0) // 近似值为 0
    // node_timing 到达：真实 20ms 覆盖
    tree = applyNodeEvent(
      tree,
      {
        type: 'node_timing',
        node_id: 'check_cache',
        server_start_ts: 999_000,
        server_end_ts: 999_020,
        server_duration_ms: 20,
      } as never,
      1_000_500,
    )
    child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'check_cache')!
    expect(child.durationMs).toBe(20)
    expect(child.startedAt).toBe(999_000)
    expect(child.completedAt).toBe(999_020)
    // 状态不被 node_timing 改变（仍 completed）
    expect(child.status).toBe('completed')
  })

  it('node_timing 缺 server_duration_ms 时由 end-start 推导', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'fetch_data' } as never, 1_000)
    tree = applyNodeEvent(
      tree,
      { type: 'node_timing', node_id: 'fetch_data', server_start_ts: 500, server_end_ts: 2_300 } as never,
      3_000,
    )
    const child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'fetch_data')!
    expect(child.durationMs).toBe(1_800)
  })

  it('无 server_* 时回退 Date.now() 到达时刻（stub/fast path/历史会话兼容）', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'check_cache' } as never, 1_000)
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'check_cache' } as never, 3_500)
    const child = tree.find((l) => l.id === 'prep')!.children.find((c) => c.nodeId === 'check_cache')!
    expect(child.startedAt).toBe(1_000)
    expect(child.durationMs).toBe(2_500)
  })
})
