// 回归测试：深度分析消息区渲染缺陷（用户报告，2026-09-07）。
// 缺陷 1：pipeline/report 消息整行出现并列双机器人头像——
//   AssistantMessage 外层渲染 AssistantAvatar，而 PipelineCard/ReportCard 卡内又自带头像。
// 缺陷 2：chat 消息下方恒渲染 h-7 固定高度操作条（未 hover 也占 28px），
//   在动作横幅之间形成「间隙」，hover 时间隙里浮现复制/点赞/点踩按钮行。
// 修复契约：
//   - pipeline/report 消息整行恰好 1 个机器人头像（卡自带头像，外层不再重复）。
//   - 未 hover 时消息区不出现任何 message-actions 占位（无间隙）。
//   - hover 才挂载操作按钮行，且按钮行悬浮（absolute）不占用布局高度（无位移、无空洞）。
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AnalysisRuntimeProvider, ThreadMessages } from '../../chat/AnalysisThread'
import { installJsdomPolyfills } from './aguiTestSetup'
import type { UIMessage } from '../../types'

installJsdomPolyfills()

function renderThread(messages: UIMessage[]) {
  return render(
    <AnalysisRuntimeProvider messages={messages} isRunning={false} onSubmit={() => {}} onCancel={() => {}}>
      <ThreadMessages />
    </AnalysisRuntimeProvider>,
  )
}

const robotCount = (el: HTMLElement): number => el.querySelectorAll('i.fa-robot').length

describe('深度分析消息区布局（单头像 + 无间隙操作条）', () => {
  const pipelineMsg: UIMessage = {
    id: 'p1', type: 'pipeline', content: '',
    completedNodes: ['check_cache'], currentNode: '', nodeOutputs: {}, progress: 1,
    startedAt: Date.now() - 1000, completedAt: Date.now(),
  }
  const reportMsg: UIMessage = {
    id: 'r1', type: 'report', content: '', reportMarkdown: '# 拓荆科技 投资分析报告',
    streaming: false, stockName: '拓荆科技', stockCode: '688072',
  }
  const chatMsg: UIMessage = {
    id: 'c1', type: 'chat', content: '', chatResponse: '',
    streaming: false,
    agentTimeline: [
      { type: 'thinking', content: '正在分析标的...', done: true },
      { type: 'tool_call', name: 'search_stock', args: '{}', result: '找到股票', done: true },
    ],
  }

  it('pipeline 卡整行只渲染一个机器人头像（修复并列双头像）', () => {
    const { container } = renderThread([pipelineMsg])
    const rows = Array.from(container.querySelectorAll('.max-w-3xl > *'))
    const pipelineRow = rows.find((el) => el.querySelector('[data-testid="pipeline-summary"]'))
    expect(pipelineRow).toBeTruthy()
    expect(robotCount(pipelineRow as HTMLElement)).toBe(1)
  })

  it('report 卡整行只渲染一个机器人头像（修复并列双头像）', () => {
    const { container } = renderThread([reportMsg])
    const rows = Array.from(container.querySelectorAll('.max-w-3xl > *'))
    const reportRow = rows.find((el) => el.querySelector('[data-testid="report-summary-card"]'))
    expect(reportRow).toBeTruthy()
    expect(robotCount(reportRow as HTMLElement)).toBe(1)
  })

  it('未 hover 时消息区不残留操作条占位（无间隙，不出现按钮行）', () => {
    const { container } = renderThread([chatMsg])
    expect(container.querySelectorAll('[data-testid="message-actions"]')).toHaveLength(0)
  })

  it('hover 消息才挂载操作按钮行，且悬浮不占布局高度', () => {
    const { container } = renderThread([chatMsg])
    fireEvent.mouseEnter(screen.getByTestId('stream-output'))
    const actions = container.querySelector('[data-testid="message-actions"]')
    expect(actions).not.toBeNull()
    // 按钮行悬浮在消息底部间隙内：absolute 定位，不参与兄弟布局（无位移/无永久空洞）
    expect(actions!.className).toContain('absolute')
    const labels = Array.from(actions!.querySelectorAll('button')).map((b) => b.getAttribute('aria-label'))
    // 最后一段 assistant 输出下含「重试」；复制/点赞/点踩恒在
    expect(labels).toEqual(['复制', '重试', '点赞', '点踩'])
    // 移出消息后按钮行卸载
    fireEvent.mouseLeave(screen.getByTestId('stream-output'))
    expect(container.querySelectorAll('[data-testid="message-actions"]')).toHaveLength(0)
  })

  it('流式运行中 hover 不挂载操作条', () => {
    const { container } = render(
      <AnalysisRuntimeProvider messages={[chatMsg]} isRunning onSubmit={() => {}} onCancel={() => {}}>
        <ThreadMessages />
      </AnalysisRuntimeProvider>,
    )
    fireEvent.mouseEnter(screen.getByTestId('stream-output'))
    expect(container.querySelectorAll('[data-testid="message-actions"]')).toHaveLength(0)
  })
})