import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MessageActions, isLastAssistantMessageId } from '../../chat/AnalysisThread'

function actionLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('button')).map((b) => b.getAttribute('aria-label') ?? '')
}

describe('MessageActions 操作条（bug 复现 + 设计要求）', () => {
  it('固定高度行恒渲染(未 hover 也占位)——按钮出现不引起布局位移', () => {
    const { container, rerender } = render(
      <MessageActions text="t" onRegenerate={vi.fn()} visible={false} showRetry={false} />,
    )
    // 未 hover:操作行仍在 DOM(固定高度),但无按钮
    const row = screen.getByTestId('message-actions')
    expect(row.className).toContain('h-7')
    expect(row.querySelectorAll('button')).toHaveLength(0)
    // hover 后:同一行元素存在,按钮挂载(行高不变 → 文本块不位移)
    rerender(<MessageActions text="t" onRegenerate={vi.fn()} visible showRetry={false} />)
    const row2 = screen.getByTestId('message-actions')
    expect(row2.className).toContain('h-7')
    expect(row2.querySelectorAll('button').length).toBeGreaterThan(0)
  })

  it('按钮顺序:复制 → 重试 → 点赞 → 点踩,图标化(aria-label,无文字)', () => {
    const { container } = render(
      <MessageActions text="t" onRegenerate={vi.fn()} visible showRetry />,
    )
    const labels = actionLabels(container)
    expect(labels).toEqual(['复制', '重试', '点赞', '点踩'])
    // 图标来自项目图标库(FontAwesome),非纯文字
    expect(container.querySelector('i.fa-copy')).not.toBeNull()
    expect(container.querySelector('i.fa-redo')).not.toBeNull()
    expect(container.querySelector('i.fa-thumbs-up')).not.toBeNull()
    expect(container.querySelector('i.fa-thumbs-down')).not.toBeNull()
    // 无可见文字标签
    expect(container.textContent).not.toContain('重新生成')
    expect(container.textContent).not.toContain('复制')
  })

  it('showRetry=false 时不渲染重试按钮', () => {
    const { container } = render(
      <MessageActions text="t" onRegenerate={vi.fn()} visible showRetry={false} />,
    )
    expect(actionLabels(container)).toEqual(['复制', '点赞', '点踩'])
  })

  it('点赞/点踩本地 toggle,点击高亮再点取消', () => {
    const { container } = render(
      <MessageActions text="t" onRegenerate={vi.fn()} visible showRetry={false} />,
    )
    const like = screen.getByRole('button', { name: '点赞' })
    fireEvent.click(like)
    expect(like.style.color).toBe('var(--bg-brand)') // 选中高亮
    fireEvent.click(like)
    expect(like.style.color).not.toBe('var(--bg-brand)') // 再点取消
  })

  it('复制点击触发 clipboard 并短暂显示「已复制」反馈', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    render(<MessageActions text="正文内容" onRegenerate={vi.fn()} visible showRetry={false} />)
    fireEvent.click(screen.getByRole('button', { name: '复制' }))
    expect(writeText).toHaveBeenCalledWith('正文内容')
    vi.unstubAllGlobals()
  })

  it('点赞/点踩触发 onFeedback 上报(add-user-feedback)', () => {
    const onFeedback = vi.fn()
    render(
      <MessageActions text="t" onRegenerate={vi.fn()} visible showRetry={false} onFeedback={onFeedback} />,
    )
    fireEvent.click(screen.getByRole('button', { name: '点赞' }))
    expect(onFeedback).toHaveBeenCalledWith('like')
    fireEvent.click(screen.getByRole('button', { name: '点踩' }))
    expect(onFeedback).toHaveBeenCalledWith('dislike')
  })

  it('再点同一切换按钮取消(不上报)', () => {
    const onFeedback = vi.fn()
    render(
      <MessageActions text="t" onRegenerate={vi.fn()} visible showRetry={false} onFeedback={onFeedback} />,
    )
    const like = screen.getByRole('button', { name: '点赞' })
    fireEvent.click(like)
    fireEvent.click(like) // 取消
    expect(onFeedback).toHaveBeenCalledTimes(1) // 仅首次上报
  })
})

describe('isLastAssistantMessageId（重试只出现在最后一段 agent 输出）', () => {
  const msgs = (roles: string[]) => roles.map((r, i) => ({ role: r, id: `m${i}` }))

  it('最后一条 assistant 返回 true', () => {
    expect(isLastAssistantMessageId(msgs(['user', 'assistant', 'user', 'assistant']), 'm3')).toBe(true)
  })

  it('历史 assistant 输出返回 false（中间那条不可重试）', () => {
    expect(isLastAssistantMessageId(msgs(['user', 'assistant', 'user', 'assistant']), 'm1')).toBe(false)
  })

  it('末尾是 user 消息时,最后的 assistant 仍是可重试目标', () => {
    expect(isLastAssistantMessageId(msgs(['user', 'assistant', 'user']), 'm1')).toBe(true)
  })

  it('无 assistant 消息返回 false', () => {
    expect(isLastAssistantMessageId(msgs(['user']), 'm0')).toBe(false)
  })
})
