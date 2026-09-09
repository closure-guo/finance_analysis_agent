import { describe, it, expect } from 'vitest'
import css from '../index.css?raw'

// 明日方舟 UI 色卡为设计令牌主取值来源（update-arknights-ui-theme）：
// 主色 #2F3132 深灰面板 / #FCFBFB 纯白 / #228EBF 强调蓝 / #CBB54C 点缀金；
// 罗德岛阵营色点缀：#0A0B0D 黑 / #2A5BA8 蓝 / #3FC6E0 亮青 / #888A8C 工业灰。
// 本测试冻结调色板契约，防止历史品牌紫回流。
const light = css.slice(0, css.indexOf('.dark'))
const dark = css.slice(css.indexOf('.dark'))

function tokens(block: string, names: string[]): string[] {
  return names.map((n) => {
    const m = block.match(new RegExp(`${n}:\\s*([^;]+);`))
    return m ? m[1].trim() : ''
  })
}

describe('明日方舟 UI 主题调色板（index.css 设计令牌冻结）', () => {
  it('浅色主题：强调蓝主色 + 点缀金标签 + 罗德岛黑正文', () => {
    const [brand, primary, ring, warning, textDefault] = tokens(light, [
      '--bg-brand',
      '--primary',
      '--ring',
      '--status-warning-default',
      '--text-default',
    ])
    expect(brand).toBe('#228EBF')
    expect(primary).toBe('#228EBF')
    expect(ring).toBe('#228EBF')
    expect(warning).toBe('#CBB54C')
    expect(textDefault).toBe('#0A0B0D')
  })

  it('深色主题：深灰面板底色 + 纯白文字 + 亮青蓝运行态点缀', () => {
    const [base, textDefault, statusPrimary] = tokens(dark, [
      '--bg-base-default',
      '--text-default',
      '--status-primary-default',
    ])
    expect(base).toBe('#2F3132')
    expect(textDefault).toBe('#FCFBFB')
    expect(statusPrimary).toBe('#3FC6E0')
  })

  it('图表系列色对齐色卡（强调蓝/点缀金/罗德岛蓝/亮青蓝）', () => {
    const [sky, amber, violet, teal] = tokens(light, [
      '--chart-sky',
      '--chart-amber',
      '--chart-violet',
      '--chart-teal',
    ])
    expect(sky).toBe('#228EBF')
    expect(amber).toBe('#CBB54C')
    expect(violet).toBe('#2A5BA8')
    expect(teal).toBe('#3FC6E0')
  })

  it('历史 TRAE 品牌紫不再出现', () => {
    expect(css).not.toMatch(/#4B3FE3|#6C5FF0|#8F84F5/i)
  })
})
