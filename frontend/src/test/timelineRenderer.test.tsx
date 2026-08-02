import { describe, it, expect } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { TimelineRenderer, type TimelineBannerComponents } from '../TimelineRenderer'
import { timelineToolCallToEntry, nodeDisplayName } from '../timeline'
import { ThinkingBanner, ToolCallBanner } from '../App'
import { SearchBanner } from '../SearchBanner'
import type { TimelineItem } from '../types'

// 注入真实横幅组件（与 App.tsx 渲染层一致）
const components: TimelineBannerComponents = { ThinkingBanner, SearchBanner, ToolCallBanner }

// MessageRenderer chat 分支渲染分发（agent-turn-box-display Task 3）
// 覆盖：按 agentTimeline 数组顺序渲染、每个 item 独立横幅、response 在最后不框起。

describe('timelineToolCallToEntry - tool_call item 转 ToolCallEntry', () => {
  it('保留 name/args/result/done，生成展示用 label/icon/argText', () => {
    const entry = timelineToolCallToEntry({
      type: 'tool_call',
      name: 'search_stock',
      args: '茅台',
      result: '已识别：贵州茅台 (600519)',
      done: true,
    })
    expect(entry.name).toBe('search_stock')
    expect(entry.label).toBe('识别股票')
    expect(entry.icon).toBe('🔍')
    expect(entry.argText).toBe('茅台')
    expect(entry.resultText).toBe('已识别：贵州茅台 (600519)')
    expect(entry.done).toBe(true)
  })
})

describe('nodeDisplayName - 管线 node 角色名标题', () => {
  it('已知 node 映射为中文角色名', () => {
    expect(nodeDisplayName('bull_r1')).toBe('多头分析师')
    expect(nodeDisplayName('bear_r1')).toBe('空头分析师')
    expect(nodeDisplayName('trader')).toBe('Trader')
  })
  it('未知 node 原样返回', () => {
    expect(nodeDisplayName('unknown_node')).toBe('unknown_node')
  })
})

describe('TimelineRenderer - 按 agentTimeline 数组顺序渲染', () => {
  const timeline: TimelineItem[] = [
    { type: 'thinking', content: '思考1 内容', title: '初步判断' },
    { type: 'search', query: '茅台', status: 'done', results: [{ title: 't', url: 'https://a.com', content: 'c' }] },
    { type: 'thinking', content: '思考2 内容' },
    { type: 'tool_call', name: 'search_stock', args: '茅台', result: '已识别', done: true },
  ]

  it('渲染顺序与 timeline 数组顺序一致（思考1 -> 搜索 -> 思考2 -> 工具调用）', () => {
    const { container } = render(<TimelineRenderer timeline={timeline} streaming={false} components={components} />)
    const banners = container.querySelectorAll('[data-timeline-index]')
    expect(banners).toHaveLength(4)
    // 每个横幅携带 timeline 下标，DOM 顺序即数组顺序
    expect([...banners].map(b => b.getAttribute('data-timeline-index'))).toEqual(['0', '1', '2', '3'])
  })

  it('每个 thinking item 渲染为独立 ThinkingBanner（独立折叠状态）', () => {
    render(<TimelineRenderer timeline={timeline} streaming={false} components={components} />)
    // 完成后默认折叠：思考1有标题（横幅直接显示标题），
    // 思考2无标题 -> 横幅显示"思考已完成"；两个独立横幅互不影响
    expect(screen.getByText('初步判断', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
  })

  it('所有 timeline item 包在一个统一白色容器内（Kimi 时间轴样式）', () => {
    const { container } = render(<TimelineRenderer timeline={timeline} streaming={false} components={components} />)
    // 统一容器：白底 + 边框 + 圆角，包住所有 data-timeline-index 条目
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.style.background).toContain('var(--bg-base-default)')
    expect(wrapper.style.border).toContain('var(--border-neutral-l1)')
    expect(wrapper.querySelectorAll('[data-timeline-index]')).toHaveLength(4)
  })

  it('search item 渲染为独立 SearchBanner', () => {
    render(<TimelineRenderer timeline={timeline} streaming={false} components={components} />)
    expect(screen.getByText(/搜索了/)).toBeInTheDocument()
  })

  it('tool_call item 渲染为独立 ToolCallBanner（单条目）', () => {
    render(<TimelineRenderer timeline={timeline} streaming={false} components={components} />)
    expect(screen.getByText(/识别股票/)).toBeInTheDocument()
  })

  it('搜索执行期间（末尾为 searching search item），思考横幅不显示"思考中"', () => {
    const searching: TimelineItem[] = [
      { type: 'thinking', content: '思考1 内容' },
      { type: 'search', query: '茅台', status: 'searching' },
    ]
    render(<TimelineRenderer timeline={searching} streaming={true} components={components} />)
    // 思考1 已完成（agent 转去执行搜索），显示"思考已完成"而非"思考中"
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    expect(screen.queryByText('思考中')).not.toBeInTheDocument()
    // 搜索横幅显示搜索中
    expect(screen.getByText(/正在搜索/)).toBeInTheDocument()
  })

  it('agent 实际思考中（末尾为 thinking item），该横幅显示"思考中"', () => {
    const thinking: TimelineItem[] = [
      { type: 'thinking', content: '思考1 内容' },
      { type: 'search', query: '茅台', status: 'done', results: [] },
      { type: 'thinking', content: '思考2 流式中' },
    ]
    render(<TimelineRenderer timeline={thinking} streaming={true} components={components} />)
    // 末尾 thinking item 流式中显示"思考中"；思考1 已完成
    expect(screen.getByText('思考中')).toBeInTheDocument()
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
  })
})

describe('ToolCallBanner - 完成后自动折叠（深度模式工具调用横幅不关闭 bug 复现）', () => {
  it('工具完成（done=true）且不再 streaming 时，横幅内容自动折叠', () => {
    // 深度模式澄清阶段：tool_result 已置 done=true，但 run_deep_analysis 事件
    // 不进 chat timeline，该 tool_call item 停留末尾 → streaming 曾一直为 true。
    // 修复后期望：streaming 变 false（或 done=true 且无 pending）时横幅自动折叠，
    // 不再停留在"调用工具中"展开态。
    const timeline: TimelineItem[] = [
      { type: 'tool_call', name: 'search_stock', args: '中际旭创', result: '已识别：中际旭创 (300308)', done: true },
    ]
    const { container } = render(<TimelineRenderer timeline={timeline} streaming={false} components={components} />)
    // 完成态：标题显示"已调用工具"或"工具调用"（非"调用工具中"）
    expect(screen.queryByText(/调用工具中/)).not.toBeInTheDocument()
    // 折叠：工具详情内容 maxHeight 应为 0px（折叠态）
    const collapsible = container.querySelector('[data-timeline-index="0"] .overflow-hidden') as HTMLElement
    expect(collapsible).not.toBeNull()
    expect(collapsible.style.maxHeight).toBe('0px')
  })

  it('深度模式根因场景：工具停留末尾，tool_result 翻转 done 后横幅从展开转为折叠', () => {
    // 深度模式：run_deep_analysis 不进 timeline，search_stock 的 tool_call item 停留末尾。
    // tool_result 前 done=false → toolStreaming=true → 展开"调用工具中"；
    // tool_result 后 done=true → toolStreaming=false → 应自动折叠（修复前停留展开）。
    const pending: TimelineItem[] = [
      { type: 'tool_call', name: 'search_stock', args: '中际旭创', done: false },
    ]
    const { container, rerender } = render(<TimelineRenderer timeline={pending} streaming={true} components={components} />)
    // 展开态（调用中）
    const before = container.querySelector('[data-timeline-index="0"] .overflow-hidden') as HTMLElement
    expect(before.style.maxHeight).toBe('240px')

    // tool_result 到达：done 翻转（item 仍末尾）
    const doneTimeline: TimelineItem[] = [
      { type: 'tool_call', name: 'search_stock', args: '中际旭创', result: '已识别：中际旭创 (300308)', done: true },
    ]
    act(() => {
      rerender(<TimelineRenderer timeline={doneTimeline} streaming={true} components={components} />)
    })
    const after = container.querySelector('[data-timeline-index="0"] .overflow-hidden') as HTMLElement
    expect(after.style.maxHeight).toBe('0px')
    expect(screen.queryByText(/调用工具中/)).not.toBeInTheDocument()
  })
})
