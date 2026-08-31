// enhance-pipeline-progress 组件测试：完成折叠摘要条 + 计时源契约。
// - 管线完成后时间线折叠为单行摘要条（阶段数 + 总用时），点击可再展开（Task 2.2）
// - 刷新重建时计时源取快照 pipeline_start_ts，不归零（Task 1.3/3.1）
// - 完成时刻 completedAt 落在消息上（live 路径总用时数据源）
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { reduce } from '../stores/streamStore/reduce'
import { getStreamStore, resetStreamStore } from '../stores/streamStore'
import type { SessionDetail, SSEEvent } from '../types'
import type { SessionStreamState } from '../stores/streamStore/types'
import { IDLE_STATE } from '../stores/streamStore/types'
import { PipelineCard } from '../App'
import { buildLayerTree } from '../pipelineTree'

function completedDetail(over: Partial<SessionDetail> = {}): SessionDetail {
  return {
    session_id: 's1', stock_code: '600449', stock_name: '宁夏建材', display_name: '宁夏建材', status: 'completed',
    created_at: '2026-08-30T00:00:00Z', duration_ms: 65000, report_markdown: '', chart_data: null,
    analyst_reports: {}, agent_process: {}, analyst_summaries: {}, chat_history: [],
    pipeline_snapshot: JSON.stringify({
      layerTree: JSON.stringify(buildLayerTree()),
      currentNodeId: '',
      progress: 1,
      updatedAt: Date.now(),
      pipeline_start_ts: Date.now() - 65_000,
    }),
    ...over,
  } as SessionDetail
}

describe('完成折叠摘要条（enhance-pipeline-progress）', () => {
  it('node_complete progress=1 时消息记录 completedAt（live 总用时数据源）', () => {
    let state: SessionStreamState = IDLE_STATE
    state = reduce(state, { type: 'analysis_start', analysis_id: 'a1', stock_code: '600449', stock_name: '宁夏建材' } as never)
    const before = Date.now()
    state = reduce(state, {
      type: 'node_complete', node_id: 'fund_manager', layer: 'Fund', desc: '基金经理',
      completed: ['fund_manager'], progress: 1, output: {}, timestamp: '',
    } as never)
    const pipeline = state.messages.find((m) => m.type === 'pipeline')
    expect(pipeline).toBeDefined()
    expect((pipeline as { completedAt?: number }).completedAt).toBeGreaterThanOrEqual(before)
  })

  it('刷新重建：completed 管线消息携带 durationMs（报告 duration_ms）', () => {
    resetStreamStore()
    const store = getStreamStore()
    const messages = store.rebuildMessagesFromDetail(completedDetail())
    const pipeline = messages.find((m) => m.type === 'pipeline')
    expect(pipeline).toBeDefined()
    expect(pipeline!.progress).toBe(1)
    expect(pipeline!.durationMs).toBe(65000)
  })

  it('刷新重建后回放创建的管线已用时不归零（pipeline_start_ts 校正）', async () => {
    resetStreamStore()
    const startTs = Date.now() - 120_000
    const detail = completedDetail({
      status: 'running',
      pipeline_snapshot: JSON.stringify({
        layerTree: JSON.stringify(buildLayerTree()),
        currentNodeId: 'trader', progress: 0.5, updatedAt: Date.now(), pipeline_start_ts: startTs,
      }),
    })
    // resume 的 SSE 流：analysis_start 以 Date.now() 建管线（回放会重置计时），
    // store 依据快照 pipeline_start_ts 校正 startedAt → 已用时不归零
    const events = [{ type: 'analysis_start', analysis_id: 'a1', stock_code: '600449', stock_name: '宁夏建材', seq: 1 }]
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const ev of events) controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}

`))
        controller.close()
      },
    })
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.startsWith('/api/sessions/s1/stream')) {
        return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)
    afterEach(() => vi.unstubAllGlobals())

    const store = getStreamStore()
    store.rebuildSession('s1', detail)
    await store.resume('s1')
    const state = store.getSnapshot('s1')
    const pipeline = state.messages.find((m) => m.type === 'pipeline') as { startedAt?: number } | undefined
    expect(pipeline).toBeDefined()
    expect(pipeline!.startedAt).toBe(startTs)
    expect(Date.now() - pipeline!.startedAt!).toBeGreaterThan(100_000)
  })

  it('完成态 PipelineCard：默认折叠为摘要条（阶段数+总用时），点击展开时间线', () => {
    const now = Date.now()
    const msg = {
      id: 'p1', type: 'pipeline' as const, content: '',
      completedNodes: ['check_cache', 'fetch_data', 'fund_manager'],
      currentNode: '', nodeOutputs: {}, progress: 1,
      startedAt: now - 65_000, completedAt: now - 1000,
      layerTree: buildLayerTree(),
    }
    render(<PipelineCard msg={msg} />)
    // 摘要条可见：阶段数 + 总用时
    const summary = screen.getByTestId('pipeline-summary')
    expect(summary.textContent).toContain('3 个阶段')
    expect(summary.textContent).toContain('总耗时')
    expect(summary.textContent).toContain('1:04')
    // 时间线默认折叠
    expect(screen.queryByTestId('pipeline-timeline')).toBeNull()
    // 点击展开
    fireEvent.click(summary)
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()
    // 再点击收起
    fireEvent.click(screen.getByTestId('pipeline-summary'))
    expect(screen.queryByTestId('pipeline-timeline')).toBeNull()
  })

  it('重建会话 completedNodes 为空时从 layerTree 统计阶段数', () => {
    const tree = buildLayerTree()
    // 标记 2 个节点完成
    tree[0].children[0].status = 'completed'
    tree[0].children[1].status = 'completed'
    const msg = {
      id: 'p4', type: 'pipeline' as const, content: '',
      completedNodes: [], currentNode: '', nodeOutputs: {}, progress: 1,
      durationMs: 60_000, layerTree: tree,
    }
    render(<PipelineCard msg={msg} />)
    expect(screen.getByTestId('pipeline-summary').textContent).toContain('2 个阶段')
  })

  it('运行态 PipelineCard：不显示摘要条，时间线直接渲染', () => {
    const msg = {
      id: 'p2', type: 'pipeline' as const, content: '深度分析进行中...',
      completedNodes: ['check_cache'], currentNode: 'fetch_data', nodeOutputs: {}, progress: 0.3,
      startedAt: Date.now() - 5000,
      layerTree: buildLayerTree(),
    }
    render(<PipelineCard msg={msg} />)
    expect(screen.queryByTestId('pipeline-summary')).toBeNull()
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()
  })

  it('完成态 durationMs 优先于 completedAt-startedAt', () => {
    const now = Date.now()
    const msg = {
      id: 'p3', type: 'pipeline' as const, content: '',
      completedNodes: ['fund_manager'], currentNode: '', nodeOutputs: {}, progress: 1,
      startedAt: now - 100_000, completedAt: now - 1000, durationMs: 65_000,
      layerTree: buildLayerTree(),
    }
    render(<PipelineCard msg={msg} />)
    expect(screen.getByTestId('pipeline-summary').textContent).toContain('1:05')
  })
})
