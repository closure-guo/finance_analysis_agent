// 切换已存 profile 时 LLM 配置分区表单应整体切换（设计档案 §15 原子切换；
// 修复前：本地 useState 只在挂载取初值，切 profile 后表单不刷新）。
// Task 7 后该逻辑由弹窗抽取为 LlmConfigPane，由设置中心页内嵌渲染。
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LlmConfigPane } from '../pages/settings/panes/LlmConfigPane'
import type { LLMConfig, ProfileStore } from '../llmConfig'

function cfg(over: Partial<LLMConfig>): LLMConfig {
  return { apiKey: '', model: '', baseUrl: '', thinking: '', ...over }
}

function storeOf(...profiles: { id: string; name: string; config: LLMConfig }[]): ProfileStore {
  return { profiles: profiles as ProfileStore['profiles'], activeId: profiles[0].id }
}

const noop = vi.fn()

function renderModal(store: ProfileStore, onSwitchProfile: (id: string) => void) {
  const active = store.profiles.find(p => p.id === store.activeId)!
  return render(
    <LlmConfigPane
      config={active.config}
      backendDefaults={{ model: 'deepseek/deepseek-chat', baseUrl: '', thinking: 'enabled' }}
      profileStore={store}
      capability={null}
      onProbeCapability={noop}
      onSave={noop}
      onSaveAs={noop}
      onSwitchProfile={onSwitchProfile}
      onDeleteProfile={noop}
    />,
  )
}

describe('LlmConfigPane profile 切换（ZCode 式整体切换）', () => {
  it('点击 profile 后表单字段立即切换为目标配置', () => {
    const store = storeOf(
      { id: 'a', name: '办公 DeepSeek', config: cfg({ model: 'deepseek/deepseek-chat', baseUrl: 'https://api.deepseek.com/v1', apiKey: 'sk-a', thinking: 'enabled' }) },
      { id: 'b', name: '方舟 GLM', config: cfg({ model: 'openai/glm-5.3', baseUrl: 'https://ark/v1', apiKey: 'ark-b', thinking: '' }) },
    )
    // 父级语义：switchProfile 更新 store（activeId=b）后传入新 config
    let current = store
    const onSwitch = (id: string) => {
      current = { ...current, activeId: id }
      rerenderWith(current)
    }
    const view = renderModal(current, onSwitch)
    const rerenderWith = (s: ProfileStore) => {
      const active = s.profiles.find(p => p.id === s.activeId)!
      view.rerender(
        <LlmConfigPane
          config={active.config}
          backendDefaults={{ model: 'deepseek/deepseek-chat', baseUrl: '', thinking: 'enabled' }}
          profileStore={s}
          capability={null}
          onProbeCapability={noop}
          onSave={noop}
          onSaveAs={noop}
          onSwitchProfile={onSwitch}
          onDeleteProfile={noop}
        />,
      )
    }

    // 初始展示 profile a
    expect((screen.getByPlaceholderText('deepseek/deepseek-chat') as HTMLInputElement).value).toBe('deepseek/deepseek-chat')
    expect((screen.getByPlaceholderText('sk-...') as HTMLInputElement).value).toBe('sk-a')

    // 点击 profile b
    fireEvent.click(screen.getByText('方舟 GLM'))

    // 表单应整体切换为 b 的配置（修复点）
    expect((screen.getByPlaceholderText('deepseek/deepseek-chat') as HTMLInputElement).value).toBe('openai/glm-5.3')
    expect((screen.getByPlaceholderText('sk-...') as HTMLInputElement).value).toBe('ark-b')
  })
})