// SettingsCenterPage 设置中心页壳（add-agent-settings-center Task 7）
// 左侧垂直导航六分区 + 右侧内容区；initialModule 定位激活分区。
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SettingsCenterPage } from '../../pages/settings/SettingsCenterPage'
import { emptyLlmConfig } from '../../llmConfig'


const baseProps = {
  config: emptyLlmConfig(),
  backendDefaults: { model: 'deepseek/deepseek-chat', baseUrl: '', thinking: 'enabled' },
  profileStore: { profiles: [], activeId: '' },
  capability: null,
  onProbeCapability: vi.fn(),
  onSave: vi.fn(),
  onSaveAs: vi.fn(),
  onSwitchProfile: vi.fn(),
  onDeleteProfile: vi.fn(),
  onBack: vi.fn(),
}

describe('SettingsCenterPage', () => {
  it('默认激活 LLM 配置分区并显示其内容', () => {
    render(<SettingsCenterPage {...baseProps} />)
    // 左侧导航含六大分区
    expect(screen.getByText('缓存管理')).toBeInTheDocument()
    expect(screen.getByText('会话管理')).toBeInTheDocument()
    expect(screen.getByText('运行信息')).toBeInTheDocument()
    expect(screen.getByText('数据监控')).toBeInTheDocument()
    expect(screen.getByText('战绩展示偏好')).toBeInTheDocument()
  })

  it('点击左侧导航切换右侧内容区', () => {
    render(<SettingsCenterPage {...baseProps} />)
    fireEvent.click(screen.getByText('缓存管理'))
    expect(screen.getByText(/缓存管理/)).toBeInTheDocument()
  })

  it('initialModule=llm 时定位到 LLM 配置分区', () => {
    render(<SettingsCenterPage {...baseProps} initialModule="llm" />)
    // 出现 LLM 配置表单字段（如 Provider 预设）
    expect(screen.getByText(/Provider/)).toBeInTheDocument()
  })
})