import { HttpAgent } from '@ag-ui/client'
import type { RunAgentParameters } from '@ag-ui/client'
import type { LLMConfigPayload } from '../llmConfig'

// add-assistant-ui-thread Task 3a：AG-UI quick 通道 HttpAgent 工厂。
//
// 后端端点 POST /api/agui/quick（AG-UI RunAgentInput → SSE 事件流）。
// LLM 配置经两条路径透传（调研 §3.1 / 实施计划 Task 3）：
//   - headers: X-Api-Key（HTTP 层可见性）
//   - forwardedProps: { apiKey, llmConfig }（后端实际读取的注入路径，
//     与现有通道 api_key/llm_config 语义对齐）
// forwardedProps 注入通过官方受保护钩子 prepareRunAgentInput 实现——
// useAgUiRuntime 内部调用 agent.runAgent() 时不携带业务参数，子类覆写
// 是唯一不改运行时的注入点。

export const AGUI_QUICK_URL = '/api/agui/quick'

export interface QuickAgentConfig {
  apiKey?: string
  llmConfig?: LLMConfigPayload | null
  /** 当前会话 id 获取器：非空 → threadId 用之（追问/恢复会话）；null → ''（服务端新建会话） */
  getSessionId?: () => string | null
}

export function createQuickAgent(config: QuickAgentConfig): HttpAgent {
  // 子类在工厂闭包内声明（捕获 config，不在类上挂私有字段——避免与
  // HttpAgent 内部私有字段的 nominal 声明冲突）
  class QuickAgent extends HttpAgent {
    protected prepareRunAgentInput(parameters?: RunAgentParameters) {
      const forwardedProps: Record<string, unknown> = {}
      if (config.apiKey) forwardedProps.apiKey = config.apiKey
      if (config.llmConfig) forwardedProps.llmConfig = config.llmConfig
      const input = super.prepareRunAgentInput({
        ...parameters,
        forwardedProps: { ...forwardedProps, ...parameters?.forwardedProps },
      })
      // thread_id 生命周期（后端契约：为空 → 服务端 create_chat_session 新建，
      // 真 id 经 RUN_STARTED 回传）。HttpAgent 构造时自动生成随机 UUID threadId，
      // 不覆写的话新会话首条消息会被后端 404（Session not found）——E2E 发现。
      return { ...input, threadId: config.getSessionId?.() ?? '' }
    }
  }
  return new QuickAgent({
    url: AGUI_QUICK_URL,
    headers: config.apiKey ? { 'X-Api-Key': config.apiKey } : undefined,
  })
}
