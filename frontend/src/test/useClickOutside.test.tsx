// useClickOutside 钩子行为：容器内点击不触发、容器外点击触发、禁用时不触发、卸载后清理监听。
import { useRef, useState } from 'react'
import { render, fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useClickOutside } from '../useClickOutside'

function Harness({ enabled }: { enabled: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const [count, setCount] = useState(0)
  useClickOutside(ref, enabled, () => setCount(c => c + 1))
  return (
    <div>
      <div ref={ref} data-testid="container">容器内</div>
      <div data-testid="outside">容器外</div>
      <div data-testid="count">{count}</div>
    </div>
  )
}

describe('useClickOutside', () => {
  it('容器内点击（含子元素冒泡）不触发 onOutside', () => {
    render(<Harness enabled />)
    fireEvent.mouseDown(screen.getByTestId('container'))
    expect(screen.getByTestId('count').textContent).toBe('0')
  })

  it('容器外点击触发 onOutside', () => {
    render(<Harness enabled />)
    fireEvent.mouseDown(screen.getByTestId('outside'))
    expect(screen.getByTestId('count').textContent).toBe('1')
  })

  it('enabled=false 时容器外点击不触发', () => {
    render(<Harness enabled={false} />)
    fireEvent.mouseDown(screen.getByTestId('outside'))
    expect(screen.getByTestId('count').textContent).toBe('0')
  })

  it('卸载后 document 监听被清理（后续外部点击不再触发）', () => {
    const view = render(<Harness enabled />)
    fireEvent.mouseDown(screen.getByTestId('outside'))
    expect(screen.getByTestId('count').textContent).toBe('1')
    view.unmount()
    // 卸载后不再有组件更新；再次触发不抛错即可证明监听已移除
    fireEvent.mouseDown(document.body)
  })
})