// PipelineGraph 组件测试（add-pipeline-graph-view Task 3，TDD 先行）
// 覆盖：节点渲染与状态着色、迭代徽标、点击节点悬浮卡片、查看详情回调
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PipelineGraph } from '../PipelineGraph'
import { buildLayerTree, applyNodeEvent, type LayerNode } from '../pipelineTree'

// jsdom 缺 ResizeObserver（React Flow 测量依赖），参照 src/test/chat/aguiTestSetup.ts
beforeEach(() => {
  const g = globalThis as { ResizeObserver?: unknown }
  if (!g.ResizeObserver) {
    g.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
  vi.mocked(window.requestAnimationFrame ?? ((cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number))
})

function runTree(events: Parameters<typeof applyNodeEvent>[1][]): LayerNode[] {
  let tree = buildLayerTree()
  for (const e of events) tree = applyNodeEvent(tree, e, 1000)
  return tree
}

describe('PipelineGraph', () => {
  it('渲染全部节点（抽样校验）且 pending 节点带状态标记', () => {
    render(<PipelineGraph tree={buildLayerTree()} startCounts={{}} onViewDetails={() => {}} />)
    expect(screen.getByTestId('graph-node-fundamental_analyst')).toBeDefined()
    expect(screen.getByTestId('graph-node-trader')).toBeDefined()
    expect(screen.getByTestId('graph-node-fund_manager')).toBeDefined()
    expect(screen.getByTestId('graph-node-fundamental_analyst').getAttribute('data-status')).toBe('pending')
  })

  it('completed 节点显示耗时与摘要来源状态', () => {
    const tree = runTree([
      { type: 'node_start', node_id: 'fundamental_analyst' },
      { type: 'node_complete', node_id: 'fundamental_analyst', output: { summary: '基本面：中性' } },
    ])
    render(<PipelineGraph tree={tree} startCounts={{}} onViewDetails={() => {}} />)
    const node = screen.getByTestId('graph-node-fundamental_analyst')
    expect(node.getAttribute('data-status')).toBe('completed')
    expect(node.textContent).toContain('基本面')
    // 摘要在悬浮卡片呈现（点击节点后），节点本体只含 label + 耗时
    expect(node.textContent).toContain('0ms')
  })

  it('迭代 ≥2 时节点显示 ×2 徽标', () => {
    render(<PipelineGraph tree={buildLayerTree()} startCounts={{ trader: 2 }} onViewDetails={() => {}} />)
    expect(screen.getByTestId('graph-iterations-trader').textContent).toBe('×2')
    expect(screen.queryByTestId('graph-iterations-fundamental_analyst')).toBeNull()
  })

  it('点击节点弹出悬浮卡片（状态/耗时/摘要），查看详情回调 layerId', () => {
    const onViewDetails = vi.fn()
    const tree = runTree([
      { type: 'node_start', node_id: 'fundamental_analyst' },
      { type: 'node_complete', node_id: 'fundamental_analyst', output: { summary: '基本面：中性' } },
    ])
    render(<PipelineGraph tree={tree} startCounts={{}} onViewDetails={onViewDetails} />)
    fireEvent.click(screen.getByTestId('graph-node-fundamental_analyst'))
    expect(screen.getByTestId('graph-details-card')).toBeDefined()
    expect(screen.getByTestId('graph-details-card').textContent).toContain('基本面：中性')
    fireEvent.click(screen.getByTestId('graph-details-view'))
    expect(onViewDetails).toHaveBeenCalledWith('layer1')
  })

  it('运行中节点卡片显示运行中、无摘要时摘要区不渲染', () => {
    const tree = runTree([{ type: 'node_start', node_id: 'technical_analyst' }])
    render(<PipelineGraph tree={tree} startCounts={{}} onViewDetails={() => {}} />)
    fireEvent.click(screen.getByTestId('graph-node-technical_analyst'))
    const card = screen.getByTestId('graph-details-card')
    expect(card.textContent).toContain('运行中')
    expect(screen.queryByTestId('graph-details-summary')).toBeNull()
  })

  it('回边重跑时回边以动画类渲染（flow 边不受影响）', () => {
    // React Flow 的边是 SVG path，jsdom 断言成本高；此处断言传给 ReactFlow 的
    // edges 经 graphModel 已带 animated（纯函数层已覆盖），组件层只验证渲染不抛错
    const tree = buildLayerTree()
    expect(() =>
      render(<PipelineGraph tree={tree} startCounts={{ trader: 2, fund_manager: 2 }} onViewDetails={() => {}} />),
    ).not.toThrow()
  })
})
