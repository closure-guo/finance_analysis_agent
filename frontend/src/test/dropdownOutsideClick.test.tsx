// delta fix-dropdown-outside-close：模式/LLM 切换下拉框「点击外部关闭 + 互斥展开」。
// 修复前：两处组件（EmptyState / ChatInputBar）的下拉框只靠触发按钮 onClick 切换开合，
// 点击页面其他位置不会关闭，展开后常驻覆盖页面。
import { render, fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChatInputBar, EmptyState } from '../App'
import type { CapabilityMatrix, LLMConfig, LLMProfile } from '../llmConfig'

function cfg(): LLMConfig {
  return { apiKey: 'sk-test', model: 'deepseek/deepseek-chat', baseUrl: 'https://api.deepseek.com/v1', thinking: 'enabled' }
}

function profiles(...names: string[]): LLMProfile[] {
  return names.map((name, i) => ({ id: `p${i + 1}`, name, config: cfg() }))
}

function fullMatrix(overrides: Partial<CapabilityMatrix> = {}): CapabilityMatrix {
  return { non_stream: true, stream: true, tool_call: true, tool_followup: true, json_output: true, ...overrides }
}

const DEEP_PLACEHOLDER = '输入股票名称或代码，如 茅台、300750'

describe('EmptyState 下拉框 dismiss（delta fix-dropdown-outside-close）', () => {
  function renderEmpty(over: { profiles?: LLMProfile[]; capability?: CapabilityMatrix } = {}) {
    const setMode = vi.fn()
    const onSwitchProfile = vi.fn()
    const onSend = vi.fn()
    const setShowSettings = vi.fn()
    const profs = over.profiles ?? profiles('DeepSeek 办公', '方舟 GLM')
    const view = render(
      <EmptyState
        onSend={onSend}
        apiKey="sk-test"
        capability={over.capability ?? null}
        setShowSettings={setShowSettings}
        mode="deep"
        setMode={setMode}
        profileName={profs.length ? profs[0].name : '默认配置'}
        profiles={profs}
        activeProfileId={profs[0]?.id ?? 'p1'}
        onSwitchProfile={onSwitchProfile}
      />,
    )
    return { view, setMode, onSwitchProfile, onSend, setShowSettings }
  }

  it('模式下拉框展开后点击外部区域关闭，不触发模式变更或发送', () => {
    const { setMode, onSend } = renderEmpty()
    // 展开：触发按钮可访问名含「模式：」
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    expect(screen.getByRole('button', { name: /快速模式/ })).toBeInTheDocument()

    // 点击输入框（下拉框外部）→ 关闭
    fireEvent.mouseDown(screen.getByPlaceholderText(DEEP_PLACEHOLDER))
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()
    expect(setMode).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('LLM 切换下拉框展开后点击外部区域关闭，不切换 profile', () => {
    const { onSwitchProfile } = renderEmpty()
    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek 办公' }))
    expect(screen.getByRole('button', { name: '方舟 GLM' })).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByPlaceholderText(DEEP_PLACEHOLDER))
    expect(screen.queryByRole('button', { name: '方舟 GLM' })).not.toBeInTheDocument()
    expect(onSwitchProfile).not.toHaveBeenCalled()
  })

  it('同一输入栏两个下拉框互斥展开（正反向）', () => {
    const { onSwitchProfile } = renderEmpty()
    // 模式展开时点 LLM 触发 → 模式关、LLM 开
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    expect(screen.getByRole('button', { name: /快速模式/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek 办公' }))
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '方舟 GLM' })).toBeInTheDocument()

    // LLM 展开时点模式触发 → LLM 关、模式开（此时 LLM 触发按钮与菜单项同名，取第一个为触发按钮）
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    expect(screen.queryByRole('button', { name: '方舟 GLM' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /快速模式/ })).toBeInTheDocument()
    expect(onSwitchProfile).not.toHaveBeenCalled()
  })

  it('再次点击触发按钮收起（toggle）', () => {
    const { onSwitchProfile } = renderEmpty()
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek 办公' }))
    // LLM 展开后触发按钮与菜单项同名，取第一个为触发按钮
    fireEvent.click(screen.getAllByRole('button', { name: 'DeepSeek 办公' })[0])
    expect(screen.queryByRole('button', { name: '方舟 GLM' })).not.toBeInTheDocument()
    expect(onSwitchProfile).not.toHaveBeenCalled()
  })

  it('点击选项执行对应动作并关闭；capability 门禁禁用项点击不生效', () => {
    const { setMode, onSwitchProfile } = renderEmpty()
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    fireEvent.click(screen.getByRole('button', { name: /快速模式/ }))
    expect(setMode).toHaveBeenCalledWith('quick')
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek 办公' }))
    fireEvent.click(screen.getByRole('button', { name: '方舟 GLM' }))
    expect(onSwitchProfile).toHaveBeenCalledWith('p2')
    expect(screen.queryByRole('button', { name: '方舟 GLM' })).not.toBeInTheDocument()
  })

  it('capability 门禁不回归：deep 被禁用时禁用项点击不生效、下拉框保持展开', () => {
    const { setMode } = renderEmpty({ capability: fullMatrix({ tool_call: false }) })
    fireEvent.click(screen.getByRole('button', { name: /模式：/ }))
    // 深度研究项因 tool_call=false 被禁用（描述文本仅存在于菜单项）
    const deepItem = screen.getByRole('button', { name: /5 层 Agent 流水线/ })
    expect(deepItem).toBeDisabled()
    fireEvent.click(deepItem)
    expect(setMode).not.toHaveBeenCalled()
    // 快速模式项仍可见（disabled 深度项的原因文案含「快速模式」字样，用其专属描述定位）
    expect(screen.getByRole('button', { name: /单次 LLM/ })).toBeInTheDocument()
  })

  it('无 LLM profile 时点击 LLM 切换引导打开设置面板，不展开下拉框', () => {
    const { setShowSettings } = renderEmpty({ profiles: [] })
    fireEvent.click(screen.getByRole('button', { name: '默认配置' }))
    expect(setShowSettings).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('方舟 GLM')).not.toBeInTheDocument()
  })
})

describe('ChatInputBar 下拉框 dismiss（delta fix-dropdown-outside-close）', () => {
  function renderBar(over: { profiles?: LLMProfile[] } = {}) {
    const setMode = vi.fn()
    const onSwitchProfile = vi.fn()
    const onSend = vi.fn()
    const onNewAnalysis = vi.fn()
    const setShowSettings = vi.fn()
    const profs = over.profiles ?? profiles('DeepSeek 办公', '方舟 GLM')
    const view = render(
      <ChatInputBar
        onSend={onSend}
        leftInset={0}
        mode="deep"
        setMode={setMode}
        capability={null}
        onNewAnalysis={onNewAnalysis}
        apiKey="sk-test"
        setShowSettings={setShowSettings}
        profileName={profs.length ? profs[0].name : '默认配置'}
        profiles={profs}
        activeProfileId={profs[0]?.id ?? 'p1'}
        onSwitchProfile={onSwitchProfile}
      />,
    )
    return { view, setMode, onSwitchProfile, onSend, onNewAnalysis, setShowSettings }
  }

  it('模式下拉框展开后点击外部区域关闭，当前模式与会话不变', () => {
    const { setMode, onNewAnalysis, onSend } = renderBar()
    // 会话视图模式触发按钮可访问名恰为当前模式名「深度研究」
    fireEvent.click(screen.getByRole('button', { name: '深度研究' }))
    expect(screen.getByRole('button', { name: /快速模式/ })).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByPlaceholderText(DEEP_PLACEHOLDER))
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()
    expect(setMode).not.toHaveBeenCalled()
    expect(onNewAnalysis).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('LLM 切换下拉框展开后点击外部区域关闭，不切换 profile', () => {
    const { onSwitchProfile } = renderBar()
    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek 办公' }))
    expect(screen.getByRole('button', { name: '方舟 GLM' })).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByPlaceholderText(DEEP_PLACEHOLDER))
    expect(screen.queryByRole('button', { name: '方舟 GLM' })).not.toBeInTheDocument()
    expect(onSwitchProfile).not.toHaveBeenCalled()
  })

  it('模式与 LLM 下拉框互斥展开 + 触发按钮 toggle', () => {
    const { onSwitchProfile, setMode } = renderBar()
    // 模式展开 → 点 LLM 触发 → 互斥切换
    fireEvent.click(screen.getByRole('button', { name: '深度研究' }))
    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek 办公' }))
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '方舟 GLM' })).toBeInTheDocument()

    // LLM 展开 → 点模式触发 → 互斥切回；再次点击模式触发验证 toggle 收起
    fireEvent.click(screen.getByRole('button', { name: '深度研究' }))
    expect(screen.queryByRole('button', { name: '方舟 GLM' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /快速模式/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '深度研究' }))
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()
    expect(setMode).not.toHaveBeenCalled()
    expect(onSwitchProfile).not.toHaveBeenCalled()
  })

  it('点击模式选项执行动作（切模式并开新会话）并关闭', () => {
    const { setMode, onNewAnalysis } = renderBar()
    fireEvent.click(screen.getByRole('button', { name: '深度研究' }))
    fireEvent.click(screen.getByRole('button', { name: /快速模式/ }))
    expect(setMode).toHaveBeenCalledWith('quick')
    expect(onNewAnalysis).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /快速模式/ })).not.toBeInTheDocument()
  })

  it('无 LLM profile 时点击 LLM 切换引导打开设置面板，不展开下拉框', () => {
    const { setShowSettings } = renderBar({ profiles: [] })
    fireEvent.click(screen.getByRole('button', { name: '默认配置' }))
    expect(setShowSettings).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('方舟 GLM')).not.toBeInTheDocument()
  })
})