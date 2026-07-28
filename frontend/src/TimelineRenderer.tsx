// Agent 时序渲染分发：遍历 agentTimeline，按 item.type 渲染为独立可折叠横幅。
// 组件通过 props 注入（ThinkingBanner / SearchBanner / ToolCallBanner 由 App.tsx 传入），
// 避免 TimelineRenderer -> App.tsx 的循环依赖。
// 设计见 agent-turn-box-display design.md 决策 3/4：每个 timeline item 一个横幅实例，
// ToolCallBanner 接收单条目数组（toolCalls={[entry]}）保持组件签名不变。

import type { ComponentType } from 'react'
import type { TimelineItem, ToolCallEntry } from './types'
import { timelineToolCallToEntry } from './timeline'

// 注入的横幅组件签名（与 App.tsx 现有组件一致）
export interface TimelineBannerComponents {
  ThinkingBanner: ComponentType<{ content: string; streaming: boolean; title?: string }>
  SearchBanner: ComponentType<{ status: 'searching' | 'done' | 'error'; query?: string; results?: Array<{ title: string; url: string; content: string }> }>
  ToolCallBanner: ComponentType<{ toolCalls: ToolCallEntry[]; streaming: boolean }>
}

// 渲染一条 agentTimeline：每个 item 一个独立横幅，顺序即数组顺序。
// streaming 为整条消息的流式标记；仅当"消息流式中 且 末尾 item 未完成"时，
// 对应末尾横幅显示进行中动画（思考中/搜索中/调用工具中），其余已完成横幅不显示"思考中"。
export function TimelineRenderer({
  timeline,
  streaming,
  components,
}: {
  timeline: TimelineItem[]
  streaming: boolean
  components: TimelineBannerComponents
}) {
  const { ThinkingBanner, SearchBanner, ToolCallBanner } = components
  return (
    <>
      {timeline.map((item, i) => {
        const isLast = i === timeline.length - 1
        if (item.type === 'thinking') {
          // 仅当消息流式中且该 thinking item 在 timeline 末尾（agent 正在思考）时显示"思考中"；
          // agent 转去执行搜索/工具调用后（末尾变为 search/tool_call item），该横幅不再显示"思考中"
          const thinkingStreaming = streaming && isLast
          return (
            <div key={i} data-timeline-index={i}>
              <ThinkingBanner content={item.content} streaming={thinkingStreaming} title={item.title} />
            </div>
          )
        }
        if (item.type === 'search') {
          return (
            <div key={i} data-timeline-index={i}>
              <SearchBanner status={item.status} query={item.query} results={item.results} />
            </div>
          )
        }
        // tool_call：单条目数组传入 ToolCallBanner（组件签名不变）
        const toolStreaming = streaming && isLast && !item.done
        return (
          <div key={i} data-timeline-index={i}>
            <ToolCallBanner toolCalls={[timelineToolCallToEntry(item)]} streaming={toolStreaming} />
          </div>
        )
      })}
    </>
  )
}
