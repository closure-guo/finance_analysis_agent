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

  it('完成态默认折叠 + 有标题 -> 横幅直接显示标题，不显示字数', () => {
    render(<ThinkingBanner content="## 茅台分析\n内容" streaming={false} title="茅台分析" />)
    // 完成后默认折叠：横幅标题在 span 中直接可见，无需先点击
    expect(screen.getByText('茅台分析', { selector: 'span' })).toBeInTheDocument()
    // 折叠态展开内容容器不可见（maxHeight 0 + opacity 0）
    const titleInDropdown = screen.getByText('茅台分析', { selector: 'p' })
    expect(titleInDropdown).not.toBeVisible()
    // 不显示"· N 字"
    expect(screen.queryByText(/字/)).not.toBeInTheDocument()
  })

  it('完成态折叠 + 无标题 -> 横幅显示"思考已完成"', () => {
    render(<ThinkingBanner content="简短思考" streaming={false} />)
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    expect(screen.queryByText(/字/)).not.toBeInTheDocument()
  })

  it('完成态点击展开 + 有标题 -> 横幅显示"思考已完成"，下拉框标题加粗置顶', () => {
    render(<ThinkingBanner content="## 茅台分析\n详细内容" streaming={false} title="茅台分析" />)
    // 默认折叠，点击展开
    fireEvent.click(screen.getByRole('button'))
    // 展开态横幅固定显示"思考已完成"
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    // 下拉框内标题加粗置顶（font-bold）
    const titleEl = screen.getByText('茅台分析', { selector: 'p' })
    expect(titleEl).toBeInTheDocument()
    expect(titleEl.className).toContain('font-bold')
  })

  it('完成态点击展开 + 无标题 -> 横幅显示"思考已完成"，下拉框无置顶标题', () => {
    render(<ThinkingBanner content="简短思考内容" streaming={false} />)
    expect(screen.getByText('思考已完成')).toBeInTheDocument()
    // 默认折叠时内容不可见，点击展开后可见
    expect(screen.getByText('简短思考内容')).not.toBeVisible()
    fireEvent.click(screen.getByRole('button'))
    // 下拉框内不渲染置顶标题（思考正文直接显示）
    expect(screen.getByText('简短思考内容')).toBeVisible()
  })
})
