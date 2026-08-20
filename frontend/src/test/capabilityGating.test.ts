import { describe, it, expect, beforeEach } from 'vitest'
import {
  canEnterMode,
  clearCapability,
  parseCapability,
  saveLlmConfigToStorage,
  loadLlmConfig,
  FA_LLM_CONFIG_KEY,
  addProfile,
  getActiveConfig,
  type CapabilityMatrix,
  type LLMConfig,
} from '../llmConfig'

// 能力矩阵门禁纯逻辑测试（harden-llm-gateway-governance Task 6）
// 规则：null/undefined capability → 放行（probe 未完成不误伤）；
// deep：tool_call=false 禁用并给原因；json_output=false 允许但 reason 标注管线 caveat；
// quick：stream 与 non_stream 均为 false 才禁用。

function fullMatrix(overrides: Partial<CapabilityMatrix> = {}): CapabilityMatrix {
  return {
    non_stream: true,
    stream: true,
    tool_call: true,
    tool_followup: true,
    json_output: true,
    ...overrides,
  }
}

describe('canEnterMode - 模式入口 capability 门禁', () => {
  it('capability 为 null → 放行（probe 未完成不误伤）', () => {
    expect(canEnterMode('deep', null)).toEqual({ allowed: true, reason: '' })
    expect(canEnterMode('quick', null)).toEqual({ allowed: true, reason: '' })
    expect(canEnterMode('deep', undefined)).toEqual({ allowed: true, reason: '' })
  })

  it('tool_call=false → deep 禁用，reason 提示可切换 provider 或快速模式', () => {
    const gate = canEnterMode('deep', fullMatrix({ tool_call: false }))
    expect(gate.allowed).toBe(false)
    expect(gate.reason).toContain('不支持工具调用')
    expect(gate.reason).toContain('快速模式')
  })

  it('json_output=false → deep 仍允许，reason 标注管线 caveat', () => {
    const gate = canEnterMode('deep', fullMatrix({ json_output: false }))
    expect(gate.allowed).toBe(true)
    expect(gate.reason).toContain('JSON')
  })

  it('stream 与 non_stream 均为 false → quick 禁用', () => {
    const gate = canEnterMode('quick', fullMatrix({ stream: false, non_stream: false }))
    expect(gate.allowed).toBe(false)
    expect(gate.reason).not.toBe('')
  })

  it('stream=false 但 non_stream=true → quick 允许', () => {
    expect(canEnterMode('quick', fullMatrix({ stream: false }))).toEqual({ allowed: true, reason: '' })
  })

  it('全项通过 → 两种模式均允许', () => {
    const cap = fullMatrix()
    expect(canEnterMode('deep', cap).allowed).toBe(true)
    expect(canEnterMode('quick', cap).allowed).toBe(true)
  })
})

describe('capability 持久化（store 层）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('saveLlmConfigToStorage 携带 capability 并可经 loadLlmConfig 读回', () => {
    const cap = fullMatrix({ tool_call: false })
    const cfg: LLMConfig = { apiKey: 'sk-1', model: 'm', baseUrl: 'b', thinking: '', capability: cap }
    saveLlmConfigToStorage(cfg)
    expect(loadLlmConfig().capability).toEqual(cap)
  })

  it('clearCapability 置空 capability（配置变更后旧 probe 事实失效）', () => {
    const cfg: LLMConfig = { apiKey: 'sk-1', model: 'm', baseUrl: 'b', thinking: '', capability: fullMatrix() }
    const cleared = clearCapability(cfg)
    expect(cleared.capability).toBeNull()
    // 清空持久化后读回亦为未探测
    saveLlmConfigToStorage(cleared)
    expect(loadLlmConfig().capability).toBeUndefined()
  })

  it('parseCapability 对非法/缺字段输入返回 null', () => {
    expect(parseCapability(null)).toBeNull()
    expect(parseCapability({})).toBeNull()
    expect(parseCapability({ non_stream: true, stream: true })).toBeNull()
    expect(parseCapability({ non_stream: 1, stream: true, tool_call: true, tool_followup: true, json_output: true })).toBeNull()
  })

  it('profile config 中的 capability 随 profiles 持久化保留', () => {
    const cfg: LLMConfig = { apiKey: 'sk-1', model: 'm', baseUrl: 'b', thinking: '', capability: fullMatrix({ json_output: false }) }
    const store = addProfile({ profiles: [], activeId: '' }, 'p1', cfg)
    saveLlmConfigToStorage(store.profiles[0].config)
    // 经 fa_llm_config 通道读回（与 profiles 通道结构一致，验证 JSON 往返不丢字段）
    const raw = JSON.parse(localStorage.getItem(FA_LLM_CONFIG_KEY)!)
    expect(raw.capability).toEqual(cfg.capability)
    expect(getActiveConfig(store).capability).toEqual(cfg.capability)
  })
})
