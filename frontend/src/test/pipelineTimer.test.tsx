// PipelineCard 计时器生命周期测试（fix-pipeline-timer，TDD 先行）
// 根因：停止判据用「completedNodes 含 fund_manager/generate_file」节点代理，
// 中断/恢复/退回三场景失真。修复后以 terminated/progress===1 为准。
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import { PipelineCard } from '../App'
import type { UIMessage } from '../types'

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('fa_pipeline_view', 'list') // 本文件测计时器文本，列表视图便于断言
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-12T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

function pipelineMsg(over: Partial<UIMessage>): UIMessage {
  return {
    id: 'msg-t',
    type: 'pipeline',
    content: '',
    completedNodes: [],
    currentNode: '',
    nodeOutputs: {},
    progress: 0.5,
    startedAt: Date.now(),
    ...over,
  }
}

function etaText(): string | null {
  return document.querySelector('[data-testid="pipeline-eta"]')?.textContent ?? null
}

function expandSummaryIfPresent() {
  const summary = screen.queryByTestId('pipeline-summary')
  if (summary && summary.getAttribute('aria-expanded') === 'false') {
    fireEvent.click(summary)
  }
}

describe('PipelineCard 计时器生命周期（fix-pipeline-timer）', () => {
  it('恢复的已完成会话（progress=1、completedNodes 空）：显示总耗时而非已用时，且推进时间后文本不变', () => {
    // restore 路径合成消息：completedNodes 为空 → 旧判据（节点代理）永不停止，
    // 且 startedAt undefined → 旧显示为「已用时 0:00 · 预计剩余 ~0:00」
    const msg = pipelineMsg({
      progress: 1,
      completedNodes: [],
      durationMs: 174_000,
      startedAt: undefined,
    })
    render(<PipelineCard msg={msg} />)
    expandSummaryIfPresent()
    const before = etaText()
    expect(before).toContain('总耗时')
    expect(before).toContain('2:54')
    expect(before).not.toContain('已用时')
    // 推进 5 秒：计时器应已停止，文本不变
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(etaText()).toBe(before)
  })

  it('收到终态（terminated=true）的运行中消息：计时器停止，显示总耗时', () => {
    const msg = pipelineMsg({ terminated: true, startedAt: Date.now() - 60_000 })
    render(<PipelineCard msg={msg} />)
    const before = etaText()
    expect(before).toContain('总耗时')
    expect(before).toContain('1:00')
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(etaText()).toBe(before)
  })

  it('运行中消息（无终态）：计时器继续走（回归保护，不能误停）', () => {
    const msg = pipelineMsg({ startedAt: Date.now() - 10_000 })
    render(<PipelineCard msg={msg} />)
    expect(etaText()).toContain('已用时 0:10')
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(etaText()).toContain('已用时 0:13')
  })
})
