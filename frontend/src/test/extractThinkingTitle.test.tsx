import { describe, it, expect } from 'vitest'
import { extractThinkingTitle } from '../App'

describe('extractThinkingTitle 思考标题提取', () => {
  it('含 ## 标题行时提取首个标题文本', () => {
    const content = '## 茅台财务分析\n\n营收增长稳定...\n净利润率提升'
    expect(extractThinkingTitle(content)).toBe('茅台财务分析')
  })

  it('多个 ## 标题仅取首个', () => {
    const content = '## 基本面分析\n营收数据\n\n## 技术面分析\n趋势向上'
    expect(extractThinkingTitle(content)).toBe('基本面分析')
  })

  it('## 标题前后有空白时仍能提取', () => {
    const content = '\n  ## 行业对比  \n\n多维度对比'
    expect(extractThinkingTitle(content)).toBe('行业对比')
  })

  it('仅含 **加粗** 不提取标题', () => {
    const content = '**营收分析**\n营收增长15%...'
    expect(extractThinkingTitle(content)).toBeUndefined()
  })

  it('无格式纯文本不提取标题', () => {
    const content = '这是一段简短的思考内容，没有标题格式。'
    expect(extractThinkingTitle(content)).toBeUndefined()
  })

  it('空字符串不提取标题', () => {
    expect(extractThinkingTitle('')).toBeUndefined()
  })

  it('### 三级标题不提取（仅识别 ## 二级标题）', () => {
    const content = '### 子标题\n内容'
    expect(extractThinkingTitle(content)).toBeUndefined()
  })

  it('## 后无空格不识别为标题（严格 ## + 空格）', () => {
    const content = '##无空格标题\n内容'
    expect(extractThinkingTitle(content)).toBeUndefined()
  })
})
