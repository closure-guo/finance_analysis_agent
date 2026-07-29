import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import App from '../App'
import { buildLayerTree, applyNodeEvent, serializeLayerTree, type LayerNode } from '../pipelineTree'
import type { SessionDetail } from '../types'

// selectSession 按会话 status 恢复管线 UI（resume-pipeline-across-sessions Task 5）：
// - running + pipeline_snapshot → 恢复分层时间轴 + 进入 analyzing + 启动 2s 轮询
// - completed + pipeline_snapshot → 报告消息 + 静态完成时间轴（插在报告消息之前）
// - 无快照 → 走现有 report/chat_history 恢复逻辑
// 交互入口：渲染 App（sidebar 打开）→ 点击会话列表项触发 selectSession。

// 构造指定 running 节点的快照树：沿途节点按序列 node_start，目标节点保持 running
function treeWithRunningNode(targetNodeId: string, path: string[]): LayerNode[] {
  let tree = buildLayerTree()
  let ts = 1_000
  for (const nodeId of path) {
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: nodeId } as never, ts)
    if (nodeId !== targetNodeId) {
      tree = applyNodeEvent(tree, { type: 'node_complete', node_id: nodeId } as never, ts + 100)
    }
    ts += 1_000
  }
  return tree
}

// 构造全完成树：所有配置节点依次 start + complete
function treeAllCompleted(): LayerNode[] {
  let tree = buildLayerTree()
  let ts = 1_000
  for (const layer of tree) {
    for (const child of layer.children) {
      tree = applyNodeEvent(tree, { type: 'node_start', node_id: child.nodeId } as never, ts)
      tree = applyNodeEvent(tree, { type: 'node_complete', node_id: child.nodeId } as never, ts + 100)
      ts += 1_000
    }
  }
  return tree
}

function makeSnapshot(tree: LayerNode[], currentNodeId: string, progress: number): string {
  // layerTree 为内嵌的序列化 JSON 字符串（snapshot 整体 JSON 内的字符串字段）
  return JSON.stringify({
    layerTree: serializeLayerTree(tree),
    currentNodeId,
    progress,
    updatedAt: 1_700_000_000_000,
  })
}

function makeSessionDetail(overrides: Partial<SessionDetail>): SessionDetail {
  return {
    session_id: 's1',
    stock_code: '600519',
    stock_name: '贵州茅台',
    display_name: '贵州茅台分析',
    status: 'completed',
    created_at: '2026-07-01T00:00:00Z',
    duration_ms: 60_000,
    session_type: 'analysis',
    report_markdown: '',
    chart_data: {} as SessionDetail['chart_data'],
    analyst_reports: {},
    agent_process: {},
    analyst_summaries: {},
    chat_history: [],
    pipeline_snapshot: null,
    ...overrides,
  }
}

// fetch stub：/api/sessions 列表 + 按 id 的会话详情（detailResponses 支持按调用次数出队）
function stubFetch(detailResponses: Array<{ ok: boolean; body: unknown }>) {
  let detailCallCount = 0
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/sessions' && (!init || !init.method || init.method === 'GET')) {
      return new Response(JSON.stringify({ sessions: [] }), { status: 200 })
    }
    if (url.startsWith('/api/sessions/')) {
      const idx = Math.min(detailCallCount, detailResponses.length - 1)
      detailCallCount += 1
      const item = detailResponses[idx]
      return new Response(JSON.stringify(item.body), { status: item.ok ? 200 : 500 })
    }
    return new Response('{}', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// 渲染 App 并点击会话项触发 selectSession（sidebar 默认打开，列表空时点击无效，
// 所以直接通过列表 sessions 为空则改走：把会话塞进 loadSessions 响应不灵活，
// 这里直接渲染后通过 props 内部点击不可行——改为 mock /api/sessions 返回目标会话并点击）
async function renderAndSelect(sessionId: string, displayName: string) {
  render(<App />)
  await waitFor(() => expect(screen.getByText(displayName)).toBeInTheDocument())
  await act(async () => {
    fireEvent.click(screen.getByText(displayName))
  })
  await act(async () => {})
}

function stubFetchWithSessionList(sessionId: string, displayName: string, detailResponses: Array<{ ok: boolean; body: unknown }>) {
  let detailCallCount = 0
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/sessions' && (!init || !init.method)) {
      return new Response(
        JSON.stringify({
          sessions: [{
            session_id: sessionId,
            stock_code: '600519',
            stock_name: '贵州茅台',
            display_name: displayName,
            status: 'completed',
            created_at: '2026-07-01T00:00:00Z',
            duration_ms: 60_000,
          }],
        }),
        { status: 200 },
      )
    }
    if (url.startsWith(`/api/sessions/${sessionId}`)) {
      const idx = Math.min(detailCallCount, detailResponses.length - 1)
      detailCallCount += 1
      const item = detailResponses[idx]
      return new Response(JSON.stringify(item.body), { status: item.ok ? 200 : 500 })
    }
    return new Response('{}', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('selectSession 按会话状态恢复管线', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('running 会话恢复快照时间轴并进入 analyzing（渲染 pipeline-timeline）', async () => {
    const tree = treeWithRunningNode('trader', ['check_cache', 'trader'])
    const snapshot = makeSnapshot(tree, 'trader', 0.5)
    const detail = makeSessionDetail({ status: 'running', pipeline_snapshot: snapshot })
    stubFetchWithSessionList('s1', '运行中会话', [{ ok: true, body: detail }])

    await renderAndSelect('s1', '运行中会话')

    // appState === 'analyzing' → pipeline 消息渲染出分层时间轴
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()
  })

  it('completed 会话恢复报告消息 + 静态时间轴（时间轴在报告之前）', async () => {
    const tree = treeAllCompleted()
    const snapshot = makeSnapshot(tree, '', 1)
    const detail = makeSessionDetail({
      status: 'completed',
      pipeline_snapshot: snapshot,
      report_markdown: '# 交易决策报告\n买入',
      chat_history: [{ role: 'user', content: '分析贵州茅台', ts: '2026-07-01T00:00:00Z' }],
    })
    stubFetchWithSessionList('s1', '已完成会话', [{ ok: true, body: detail }])

    await renderAndSelect('s1', '已完成会话')

    // 报告消息渲染（ReactMarkdown 渲染 markdown 内容）
    expect(screen.getByText('交易决策报告')).toBeInTheDocument()
    // 静态时间轴与报告并存，且时间轴 DOM 在报告之前
    // （completed 态时间轴为静态快照，渲染过滤器需放行已完成时间轴）
    const timeline = screen.getByTestId('pipeline-timeline')
    const report = screen.getByText('交易决策报告')
    expect(timeline.compareDocumentPosition(report) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('无快照 completed 会话走现有逻辑（报告恢复、无时间轴）', async () => {
    const detail = makeSessionDetail({
      status: 'completed',
      pipeline_snapshot: null,
      report_markdown: '# 历史报告',
    })
    stubFetchWithSessionList('s1', '历史会话', [{ ok: true, body: detail }])

    await renderAndSelect('s1', '历史会话')

    expect(screen.getByText('历史报告')).toBeInTheDocument()
    expect(screen.queryByTestId('pipeline-timeline')).not.toBeInTheDocument()
  })

  it('running 会话在无活跃 SSE 时每 2s 轮询快照并更新进度，completed 后停止并恢复报告', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const treeRunning = treeWithRunningNode('trader', ['check_cache', 'trader'])
    const snapshotRunning = makeSnapshot(treeRunning, 'trader', 0.5)
    const detailRunning = makeSessionDetail({ status: 'running', pipeline_snapshot: snapshotRunning })

    const treeDone = treeAllCompleted()
    const snapshotDone = makeSnapshot(treeDone, '', 1)
    const detailCompleted = makeSessionDetail({
      status: 'completed',
      pipeline_snapshot: snapshotDone,
      report_markdown: '# 最终报告',
    })

    const fetchMock = stubFetchWithSessionList('s1', '轮询会话', [
      { ok: true, body: detailRunning },   // selectSession 首次加载
      { ok: true, body: detailRunning },   // 第 1 次轮询：仍 running
      { ok: true, body: detailCompleted }, // 第 2 次轮询：completed → selectSession 完整恢复
      { ok: true, body: detailCompleted }, // selectSession 恢复报告的详情请求
    ])

    render(<App />)
    await waitFor(() => expect(screen.getByText('轮询会话')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByText('轮询会话'))
    })
    // 恢复 running 时间轴
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()

    const detailCallsBefore = fetchMock.mock.calls.filter(([u]) => String(u).startsWith('/api/sessions/s1')).length

    // 推进 2s：触发第 1 次轮询（running，仅更新快照）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_100)
    })
    const detailCallsMid = fetchMock.mock.calls.filter(([u]) => String(u).startsWith('/api/sessions/s1')).length
    expect(detailCallsMid).toBeGreaterThan(detailCallsBefore)

    // 再推进 2s：轮询得到 completed → selectSession 恢复报告，轮询停止
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_100)
    })
    expect(await screen.findByText('最终报告')).toBeInTheDocument()

    const detailCallsDone = fetchMock.mock.calls.filter(([u]) => String(u).startsWith('/api/sessions/s1')).length
    // 再推进 4s：轮询已停止，不再有新的详情请求
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_200)
    })
    const detailCallsAfter = fetchMock.mock.calls.filter(([u]) => String(u).startsWith('/api/sessions/s1')).length
    expect(detailCallsAfter).toBe(detailCallsDone)
  })

  it('恢复态轮询期间用户发起新分析：轮询让位，不写消息、不调 selectSession', async () => {
    // 竞态场景（Task 5 review）：startAnalysis 设置 abortRef 前无 setState、effect 不重跑、
    // interval 不清理；若轮询读到 completed 会调 selectSession → abortStreaming() 掐断新 SSE。
    // 修复后 interval 回调开头复查 abortRef，SSE 在线时轮询直接返回。
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.setItem('fa_api_key', 'test-key')

    const treeRunning = treeWithRunningNode('trader', ['check_cache', 'trader'])
    const snapshotRunning = makeSnapshot(treeRunning, 'trader', 0.5)
    const detailRunning = makeSessionDetail({ status: 'running', pipeline_snapshot: snapshotRunning })

    // 关键陷阱：新分析 SSE 建立后，恢复态的 currentSessionId（s1）仍指向旧会话，
    // 而旧会话恰在此刻 completed → 若轮询不让位，必然触发 selectSession → abortStreaming。
    const treeDone = treeAllCompleted()
    const snapshotDone = makeSnapshot(treeDone, '', 1)
    const detailCompleted = makeSessionDetail({
      status: 'completed',
      pipeline_snapshot: snapshotDone,
      report_markdown: '# 旧会话报告',
    })

    // 永不结束的 SSE 流：模拟新分析已建立订阅、正在流式产出（SSE 在线期间）
    const sseStream = new ReadableStream<Uint8Array>({
      start() { /* 保持打开，不推送、不关闭 */ },
    })
    let detailCallCount = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sessions' && (!init || !init.method)) {
        return new Response(
          JSON.stringify({
            sessions: [{
              session_id: 's1',
              stock_code: '600519',
              stock_name: '贵州茅台',
              display_name: '轮询让位会话',
              status: 'completed',
              created_at: '2026-07-01T00:00:00Z',
              duration_ms: 60_000,
            }],
          }),
          { status: 200 },
        )
      }
      if (url === '/api/analyze') {
        return new Response(sseStream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        })
      }
      if (url.startsWith('/api/sessions/')) {
        detailCallCount += 1
        // 首次为 selectSession 恢复（running + 快照）；此后若轮询未让位则命中 completed，
        // 走 selectSession → abortStreaming()，放大竞态后果便于断言
        const body = detailCallCount === 1 ? detailRunning : detailCompleted
        return new Response(JSON.stringify(body), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText('轮询让位会话')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByText('轮询让位会话'))
    })
    // 恢复 running 时间轴，进入 analyzing + 轮询启动
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()

    // 模拟用户在恢复态发起新分析：ChatInput 输入 → 点击发送 → startAnalysis 设置 abortRef 并建立 SSE。
    // 注意：此过程无 setState 改变 appState/currentSessionId（仅 session_created 事件才会），
    // 轮询 effect 不重跑、interval 不清理——正是竞态窗口。
    const input = screen.getByPlaceholderText(/输入股票名称或代码|输入问题/)
    await act(async () => {
      fireEvent.change(input, { target: { value: '分析宁德时代' } })
      fireEvent.click(screen.getByTestId('send-button'))
    })
    // 等待 /api/analyze 请求发出（abortRef 已设置、SSE 已建立）
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u) === '/api/analyze')).toBe(true))

    const callsBefore = fetchMock.mock.calls.length

    // 推进 6s（3 个轮询周期）：轮询应让位——零网络请求、零消息写入、零 selectSession 调用
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_300)
    })
    expect(fetchMock.mock.calls.length).toBe(callsBefore)
    // selectSession 未被误调：旧会话报告未插入、未被 abortStreaming 掐断（时间轴仍在 analyzing 渲染）
    expect(screen.queryByText('旧会话报告')).not.toBeInTheDocument()
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()
    // 用户刚发起的分析输入仍在消息流中
    expect(screen.getByText('分析宁德时代')).toBeInTheDocument()
  })

  it('running 会话轮询超过 5 分钟后停止并提示管线可能已中断', async () => {
    // 超时保护（Final Review Fix 2）：ReAct 路径切走后 status 可能永久 running，
    // 轮询无限进行会泄漏资源。超过 MAX_POLLING_MS（5 分钟）后停止轮询并提示用户。
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const treeRunning = treeWithRunningNode('trader', ['check_cache', 'trader'])
    const snapshotRunning = makeSnapshot(treeRunning, 'trader', 0.5)
    const detailRunning = makeSessionDetail({ status: 'running', pipeline_snapshot: snapshotRunning })

    // 永远返回 running（管线卡住不完成，模拟 ReAct 路径切走后台未续跑）
    const fetchMock = stubFetchWithSessionList('s1', '卡住会话', [
      { ok: true, body: detailRunning },
    ])

    render(<App />)
    await waitFor(() => expect(screen.getByText('卡住会话')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByText('卡住会话'))
    })
    expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument()

    // 推进超过 5 分钟（MAX_POLLING_MS = 300_000，每 2s 一次轮询）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(305_000)
    })

    // 轮询已停止：再推进 10s 不应有新的详情请求
    const callsAtTimeout = fetchMock.mock.calls.filter(([u]) => String(u).startsWith('/api/sessions/s1')).length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    const callsAfterWait = fetchMock.mock.calls.filter(([u]) => String(u).startsWith('/api/sessions/s1')).length
    expect(callsAfterWait).toBe(callsAtTimeout)

    // 提示消息出现
    expect(screen.getByText(/管线可能已中断/)).toBeInTheDocument()
  })
})
