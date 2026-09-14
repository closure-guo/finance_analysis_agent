// PipelineCard 图/列表切换接线测试（add-pipeline-graph-view Task 4，TDD 先行）
// 覆盖：默认图视图、切换持久化 localStorage、预置偏好生效、查看详情切列表并展开、窄屏降级
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PipelineCard } from '../App'
import { buildLayerTree, applyNodeEvent, type LayerNode } from '../pipelineTree'
import type { UIMessage } from '../types'

beforeEach(() => {
  localStorage.clear()
  const g = globalThis as { ResizeObserver?: unknown }
  if (!g.ResizeObserver) {
    g.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
  // jsdom 无 matchMedia（PipelineCard 窄屏监听用）
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
  }
})

function runTree(events: Parameters<typeof applyNodeEvent>[1][]): LayerNode[] {
  let tree = buildLayerTree()
  for (const e of events) tree = applyNodeEvent(tree, e, 1000)
  return tree
}

function pipelineMsg(tree: LayerNode[]): UIMessage {
  return {
    id: 'msg-1',
    type: 'pipeline',
    content: '分析进度',
    completedNodes: [],
    currentNode: '',
    nodeOutputs: {},
    progress: 0.3,
    startedAt: Date.now(),
    layerTree: tree,
    nodeStartCounts: {},
  }
}

describe('PipelineCard 图/列表视图切换', () => {
  it('默认显示图视图（≥768px 且无偏好）', () => {
    render(<PipelineCard msg={pipelineMsg(buildLayerTree())} />)
    expect(screen.getByTestId('pipeline-view-toggle')).toBeDefined()
    expect(screen.getByTestId('pipeline-graph')).toBeDefined()
    expect(screen.queryByTestId('pipeline-timeline')).toBeNull()
  })

  it('点击「列表」切换视图并写 localStorage', () => {
    render(<PipelineCard msg={pipelineMsg(buildLayerTree())} />)
    fireEvent.click(screen.getByTestId('pipeline-view-list'))
    expect(screen.getByTestId('pipeline-timeline')).toBeDefined()
    expect(screen.queryByTestId('pipeline-graph')).toBeNull()
    expect(localStorage.getItem('fa_pipeline_view')).toBe('list')
  })

  it('预置偏好 list 时直接显示列表', () => {
    localStorage.setItem('fa_pipeline_view', 'list')
    render(<PipelineCard msg={pipelineMsg(buildLayerTree())} />)
    expect(screen.getByTestId('pipeline-timeline')).toBeDefined()
    expect(screen.queryByTestId('pipeline-graph')).toBeNull()
  })

  it('查看详情：切到列表且对应 layer 展开（子节点可见）', () => {
    const tree = runTree([
      { type: 'node_start', node_id: 'fundamental_analyst' },
      { type: 'node_complete', node_id: 'fundamental_analyst', output: { summary: '基本面：中性' } },
    ])
    render(<PipelineCard msg={pipelineMsg(tree)} />)
    fireEvent.click(screen.getByTestId('graph-node-fundamental_analyst'))
    fireEvent.click(screen.getByTestId('graph-details-view'))
    expect(screen.getByTestId('pipeline-timeline')).toBeDefined()
    expect(localStorage.getItem('fa_pipeline_view')).toBe('list')
    // 目标 layer 展开状态：子节点「基本面」文本可见
    expect(screen.getAllByText('基本面').length).toBeGreaterThan(0)
  })

  it('窄屏（<768px）隐藏 toggle 仅列表', () => {
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(640)
    render(<PipelineCard msg={pipelineMsg(buildLayerTree())} />)
    expect(screen.queryByTestId('pipeline-view-toggle')).toBeNull()
    expect(screen.getByTestId('pipeline-timeline')).toBeDefined()
    vi.restoreAllMocks()
  })
})
