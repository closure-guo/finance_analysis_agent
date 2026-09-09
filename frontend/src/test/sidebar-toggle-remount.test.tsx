// 复现测试（fix-sidebar-toggle-freeze）：反复展开/收起侧边栏时，历史会话列表不得被
// 反复重挂载。
//
// 根因：旧实现下 Sidebar 只渲染「当前态」那一侧 rail（{collapsed ? collapsedRail :
// expandedRail}）。每次展开都把整棵会话列表（219 会话 ≈ 657 DOM 节点）重新挂载并
// 重放 framer-motion 入场动画，阻塞主线程 ~75-145ms/次，快速连点即表现为卡顿。
//
// 断言：展开态内容跨多次 toggle 只挂载一次（保持挂载、display 切换隐藏，而非重挂载）。
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useEffect } from 'react'
import { render, fireEvent, cleanup } from '@testing-library/react'
import { SidebarProvider, Sidebar, useSidebar } from '../components/ui/sidebar'

let mountCount = 0

function MountProbe() {
  // 记录本组件被挂载的次数：每次重挂载都会再次执行此 effect
  useEffect(() => { mountCount += 1 }, [])
  return <div>expanded-rail-content</div>
}

function Harness() {
  const { toggleSidebar } = useSidebar()
  return (
    <>
      <button data-testid="toggle" onClick={toggleSidebar}>toggle</button>
      <Sidebar expandedRail={<MountProbe />} collapsedRail={<div>collapsed-icons</div>} />
    </>
  )
}

describe('侧边栏展开不重挂载会话列表', () => {
  beforeEach(() => {
    localStorage.clear()
    mountCount = 0
  })
  afterEach(() => cleanup())

  it('多次展开/收起后展开态内容只挂载一次（不随每次展开重挂载）', () => {
    render(
      <SidebarProvider>
        <Harness />
      </SidebarProvider>,
    )
    // 默认展开态：挂载一次
    expect(mountCount).toBe(1)
    const toggle = document.querySelector('[data-testid="toggle"]') as HTMLElement
    // 收起 → 展开 → 收起 → 展开：展开态内容应保持挂载，不得被重挂载
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    expect(mountCount).toBe(1)
  })
})
