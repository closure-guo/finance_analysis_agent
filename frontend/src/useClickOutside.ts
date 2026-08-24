import { useEffect, useRef, type RefObject } from 'react'

// 点击容器外部时触发的通用 dismiss 钩子（delta fix-dropdown-outside-close）。
// enabled 时挂 document 级 mousedown 监听：事件目标不在 ref 容器内则调用 onOutside。
// 约束：ref 容器必须同时包裹触发按钮与弹层，否则点击触发按钮会先命中「外部关闭」
// 再被按钮 onClick 重新打开（开合竞态），下拉框将永远关不掉。
export function useClickOutside(
  ref: RefObject<HTMLElement | null>,
  enabled: boolean,
  onOutside: () => void,
): void {
  const onOutsideRef = useRef(onOutside)
  useEffect(() => {
    onOutsideRef.current = onOutside
  })

  useEffect(() => {
    if (!enabled) return
    const handler = (e: MouseEvent) => {
      const el = ref.current
      if (el && e.target instanceof Node && !el.contains(e.target)) {
        onOutsideRef.current()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [ref, enabled])
}