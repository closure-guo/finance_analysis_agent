import { describe, it, expect } from 'vitest'
import { SEARCH_TOOL_NAMES, isSearchTool } from '../App'

describe('搜索类工具过滤', () => {
  it('SEARCH_TOOL_NAMES 包含 web_search 与 batch_web_search', () => {
    expect(SEARCH_TOOL_NAMES.has('web_search')).toBe(true)
    expect(SEARCH_TOOL_NAMES.has('batch_web_search')).toBe(true)
    // 仅这两个工具，避免误扩
    expect(SEARCH_TOOL_NAMES.size).toBe(2)
  })

  it('isSearchTool 对搜索类工具返回 true', () => {
    expect(isSearchTool('web_search')).toBe(true)
    expect(isSearchTool('batch_web_search')).toBe(true)
  })

  it('isSearchTool 对非搜索类工具返回 false', () => {
    // 股票识别工具仍走工具调用横幅
    expect(isSearchTool('search_stock')).toBe(false)
    // 深度分析管线工具，由分流逻辑单独处理
    expect(isSearchTool('run_deep_analysis')).toBe(false)
    // 未知工具不误判
    expect(isSearchTool('unknown')).toBe(false)
  })
})
