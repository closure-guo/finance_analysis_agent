// Agent 时序渲染分发：遍历 agentTimeline，按 item.type 渲染为独立可折叠横幅。
// 组件通过 props 注入（ThinkingBanner / SearchBanner / ToolCallBanner 由 App.tsx 传入），
// 避免 TimelineRenderer -> App.tsx 的循环依赖。
// 设计见 agent-turn-box-display design.md 决策 3/4：每个 timeline item 一个横幅实例，
// ToolCallBanner 接收单条目数组（toolCalls={[entry]}）保持组件签名不变。
// Kimi 时间轴样式：所有 item 包在一个统一白色容器内，容器内用左侧竖线串联各条目。

import type { ComponentType, ReactNode } from 'react'
import type { TimelineItem, ToolCallEntry } from './types'
import { timelineToolCallToEntry } from './timeline'

// 注入的横幅组件签名（与 App.tsx 现有组件一致）
// embedded=true 表示横幅嵌入统一时间轴容器（去掉自身灰底框，融入白底容器）
export interface TimelineBannerComponents {
  ThinkingBanner: ComponentType<{ content: string; streaming: boolean; title?: string; embedded?: boolean }>
  SearchBanner: ComponentType<{ status: 'searching' | 'done' | 'error'; query?: string; results?: Array<{ title: string; url: string; content: string }>; embedded?: boolean }>
  ToolCallBanner: ComponentType<{ toolCalls: ToolCallEntry[]; streaming: boolean; embedded?: boolean }>
}

// 时间轴条目外壳：左侧时间轴节点图标 + 竖线（除最后一个条目外竖线向下延伸），
// 内容缩进在竖线右侧，形成 Kimi 风格的左侧时间轴串联效果。
// 节点图标按类型区分：active 时品牌色跳动圆点，完成态思考=圆点/搜索=放大镜/工具=扳手。
function TimelineEntry({ type, active, isLast, children }: { type: TimelineItem['type']; active: boolean; isLast: boolean; children: ReactNode }) {
  return (
    <div className="relative flex gap-3">
      {/* 左侧时间轴：节点图标 + 向下延伸的竖线（最后一个条目不画竖线） */}
      <div className="flex flex-col items-center flex-shrink-0" style={{ width: '16px' }}>
        <div className="flex-shrink-0 mt-2 flex items-center justify-center" style={{ width: '16px', height: '16px' }}>
          {active ? (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }}></span>
              <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }}></span>
            </span>
          ) : type === 'thinking' ? (
            <span className="block rounded-full" style={{ width: 7, height: 7, background: 'var(--text-brand)' }} />
          ) : type === 'search' ? (
            <i className="fas fa-search" style={{ fontSize: 9, color: 'var(--text-brand)' }}></i>
          ) : (
            <i className="fas fa-tools" style={{ fontSize: 9, color: 'var(--text-brand)' }}></i>
          )}
        </div>
        {!isLast && (
          <div className="flex-1 w-px" style={{ background: 'var(--border-neutral-l1)' }} />
        )}
      </div>
      {/* 条目内容：缩进在竖线右侧 */}
      <div className="flex-1 min-w-0 pb-3">{children}</div>
    </div>
  )
}

// 渲染一条 agentTimeline：所有 item 包在一个统一白色容器内（白底 + 浅灰边框 + 圆角），
// 容器内每个 item 用左侧竖线串联（时间轴效果），item 仍是独立可折叠横幅实例。
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
    // 统一白色容器：白底 + 1px 浅灰边框 + 圆角，包住所有 timeline 条目
    <div
      className="rounded-xl px-4 pt-3 pb-1 mb-3"
      style={{ background: 'var(--bg-base-default)', border: '1px solid var(--border-neutral-l1)' }}
    >
      {timeline.map((item, i) => {
        const isLast = i === timeline.length - 1
        if (item.type === 'thinking') {
          // 活动态判定：显式完成态（done=true）优先——已收口的横幅不再显示"思考中"；
          // 否则仅当消息流式中且该 thinking item 在 timeline 末尾（agent 正在思考）时显示"思考中"。
          const thinkingStreaming = item.done === true ? false : streaming && isLast
          return (
            <div key={i} data-timeline-index={i}>
              <TimelineEntry type={item.type} active={thinkingStreaming} isLast={isLast}>
              <ThinkingBanner content={item.content} streaming={thinkingStreaming} title={item.title} embedded />
              </TimelineEntry>
            </div>
          )
        }
        if (item.type === 'search') {
          return (
            <div key={i} data-timeline-index={i}>
              <TimelineEntry type={item.type} active={item.status === 'searching'} isLast={isLast}>
              <SearchBanner status={item.status} query={item.query} results={item.results} embedded />
              </TimelineEntry>
            </div>
          )
        }
        // tool_call：单条目数组传入 ToolCallBanner（组件签名不变）
        const toolStreaming = streaming && isLast && !item.done
        return (
          <div key={i} data-timeline-index={i}>
            <TimelineEntry type={item.type} active={toolStreaming} isLast={isLast}>
              <ToolCallBanner toolCalls={[timelineToolCallToEntry(item)]} streaming={toolStreaming} embedded />
            </TimelineEntry>
          </div>
        )
      })}
    </div>
  )
}
