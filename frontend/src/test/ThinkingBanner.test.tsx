import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThinkingBanner } from '../App'

describe('ThinkingBanner 思考横幅', () => {
  it('思考中态显示"思考中"并自动展开', () => {
    render(<ThinkingBanner content="分析中..." streaming={true} />)
    expect(screen.getByText('思考中')).toBeInTheDocument()
    // 流式时自动展开，内容区域可见
    expect(screen.getByText('分析中...')).toBeVisible()
  })

  it('完成态折叠 + 有标题 -> 横幅显示标题，不显示字数', () => {
    render(<ThinkingBanner content="## 茅台分析\n内容" streaming={false} title="茅台分析" />)
    // 默认展开，点击折叠
    fireEvent.click(screen.getByRole('button'))
    // 横幅标题在 span 中（下拉框置顶标题在 p.font-bold 中，折叠时不可见）
    expect(screen.getByText('茅台分析', { selector: 'span' })).toBeInTheDocument()
    // 不显示"· N 字"
    expect(screen.queryByText(/字/)).not.toBeInTheDocument()
  })

  it('完成态折叠 + 无标题 -> 横幅显示"思考已完成"', () => {
    render(<ThinkingBanner content="简短思考" streaming={false} />)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    expect(screen.queryByText(/字/)).not.toBeInTheDocument()
  })

  it('完成态展开 + 有标题 -> 横幅显示"思考已完成"，下拉框标题加粗置顶', () => {
    render(<ThinkingBanner content="## 茅台分析\n详细内容" streaming={false} title="茅台分析" />)
    // 展开态横幅固定显示"思考已完成"
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    // 下拉框内标题加粗置顶（font-bold）
    const titleEl = screen.getByText('茅台分析')
    expect(titleEl).toBeInTheDocument()
    expect(titleEl.className).toContain('font-bold')
  })

  it('完成态展开 + 无标题 -> 横幅显示"思考已完成"，下拉框无置顶标题', () => {
    render(<ThinkingBanner content="简短思考内容" streaming={false} />)
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    // 下拉框内不渲染置顶标题（思考正文直接显示）
    expect(screen.getByText('简短思考内容')).toBeVisible()
  })
})
