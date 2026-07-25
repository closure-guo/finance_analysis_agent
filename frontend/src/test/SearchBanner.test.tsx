import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SearchBanner } from '../SearchBanner'

describe('SearchBanner', () => {
  it('搜索中状态显示"正在搜索：{query}"', () => {
    render(<SearchBanner status="searching" query="茅台 财报" />)
    expect(screen.getByText(/正在搜索/)).toBeInTheDocument()
    expect(screen.getByText(/茅台 财报/)).toBeInTheDocument()
  })

  it('搜索完成显示"搜索了 N 个网页"', () => {
    const results = [
      { title: '茅台年报', url: 'https://example.com/1', content: '摘要1' },
      { title: '茅台季报', url: 'https://example.com/2', content: '摘要2' },
    ]
    render(<SearchBanner status="done" results={results} />)
    expect(screen.getByText(/搜索了/)).toBeInTheDocument()
    // 使用 selector 精确匹配计数 span（class=font-medium），避免与结果列表索引 span（class=font-mono，渲染 {i+1}）冲突
    expect(screen.getByText('2', { selector: '.font-medium' })).toBeInTheDocument()
    expect(screen.getByText(/个网页/)).toBeInTheDocument()
  })

  it('搜索完成可展开查看结果列表', () => {
    const results = [
      { title: '茅台年报', url: 'https://example.com/1', content: '摘要内容' },
    ]
    render(<SearchBanner status="done" results={results} />)
    // 折叠状态下结果不可见
    expect(screen.getByText('茅台年报')).not.toBeVisible()
    // 点击展开
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText('茅台年报')).toBeVisible()
    expect(screen.getByText('摘要内容')).toBeVisible()
  })

  it('搜索失败显示错误状态', () => {
    render(<SearchBanner status="error" />)
    expect(screen.getByText(/搜索失败/)).toBeInTheDocument()
  })
})
