import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PipelineTimeline } from '../PipelineTimeline'
import { buildLayerTree, applyNodeEvent } from '../pipelineTree'

// PipelineTimeline 组件测试（redesign-pipeline-hierarchical-timeline Task 3.1）
// 覆盖：6 layer 渲染、子节点状态图标、耗时显示、展开折叠、当前高亮、
// layer 展开默认策略（运行层展开/完成层折叠）、用户偏好记忆。

const treeWith = (...events: Array<{ type: 'node_start' | 'node_complete'; node_id: string; t: number }>) => {
  let tree = buildLayerTree()
  for (const e of events) {
    tree = applyNodeEvent(tree, { type: e.type, node_id: e.node_id } as never, e.t)
  }
  return tree
}

describe('PipelineTimeline - 渲染结构', () => {
  it('渲染 6 个 layer 节点', () => {
    render(<PipelineTimeline tree={buildLayerTree()} nowMs={0} />)
    expect(screen.getByText('PREP')).toBeInTheDocument()
    expect(screen.getByText('Layer I')).toBeInTheDocument()
    expect(screen.getByText('Layer II')).toBeInTheDocument()
    expect(screen.getByText('Trader')).toBeInTheDocument()
    expect(screen.getByText('Risk')).toBeInTheDocument()
    expect(screen.getByText('Fund')).toBeInTheDocument()
  })

  it('运行中的 layer 默认展开显示子节点', () => {
    const tree = treeWith({ type: 'node_start', node_id: 'bull_r1', t: 1000 })
    render(<PipelineTimeline tree={tree} nowMs={2000} />)
    // Layer II 展开，子节点可见
    expect(screen.getByText('看多 R1')).toBeInTheDocument()
    expect(screen.getByText('看空 R1')).toBeInTheDocument()
    expect(screen.getByText('研究结论')).toBeInTheDocument()
  })

  it('未到的 layer 默认折叠（不显示子节点）', () => {
    const tree = treeWith({ type: 'node_start', node_id: 'check_cache', t: 1000 })
    render(<PipelineTimeline tree={tree} nowMs={2000} />)
    // Risk 未到，其子节点不可见
    expect(screen.queryByText('风控裁决')).not.toBeInTheDocument()
  })
})

describe('PipelineTimeline - 状态与耗时', () => {
  it('完成的子节点显示耗时', () => {
    const tree = treeWith(
      { type: 'node_start', node_id: 'trader', t: 1000 },
      { type: 'node_complete', node_id: 'trader', t: 3000 },
    )
    const { container } = render(<PipelineTimeline tree={tree} nowMs={3000} />)
    // trader 完成耗时 2s（子节点行内；层标题也显示层耗时，故限定子节点区域）
    const child = container.querySelector('[data-node-id="trader"]')
    expect(child?.textContent).toContain('0:02')
  })

  it('当前运行子节点显示已运行时长', () => {
    const tree = treeWith({ type: 'node_start', node_id: 'bull_r2', t: 1000 })
    const { container } = render(<PipelineTimeline tree={tree} nowMs={61_000} />)
    // bull_r2 已运行 60s = 1:00（节点行内，data-current 高亮区内）
    const current = container.querySelector('[data-current="true"]')
    expect(current?.textContent).toContain('1:00')
  })

  it('当前运行节点高亮（data-current=true）', () => {
    const tree = treeWith({ type: 'node_start', node_id: 'bull_r2', t: 1000 })
    const { container } = render(<PipelineTimeline tree={tree} nowMs={2000} />)
    const current = container.querySelector('[data-current="true"]')
    expect(current).not.toBeNull()
    expect(current?.textContent).toContain('看多 R2')
  })
})

describe('PipelineTimeline - 展开折叠交互', () => {
  it('已完成 layer 默认展开显示子节点（非 pending 层展开策略）', () => {
    const tree = treeWith(
      { type: 'node_start', node_id: 'trader', t: 1000 },
      { type: 'node_complete', node_id: 'trader', t: 2000 },
      { type: 'node_start', node_id: 'fund_manager', t: 3000 },
    )
    render(<PipelineTimeline tree={tree} nowMs={4000} />)
    // trader 层已完成，默认展开，子节点"交易决策"可见（无需点击）
    expect(screen.getByText('交易决策')).toBeInTheDocument()
  })

  it('用户点击已完成 layer 折叠（用户偏好覆盖默认展开）', () => {
    const tree = treeWith(
      { type: 'node_start', node_id: 'trader', t: 1000 },
      { type: 'node_complete', node_id: 'trader', t: 2000 },
      { type: 'node_start', node_id: 'fund_manager', t: 3000 },
    )
    render(<PipelineTimeline tree={tree} nowMs={4000} />)
    expect(screen.getByText('交易决策')).toBeInTheDocument()
    // 点击 Trader 层标题折叠
    fireEvent.click(screen.getByText('Trader'))
    expect(screen.queryByText('交易决策')).not.toBeInTheDocument()
  })
})
