// polish-dark-mode-shortcuts Task 3.1：快捷键集中注册表。
// - 统一 keydown 分发；输入态（input/textarea/contentEditable 聚焦）抑制无修饰单键
// - HOTKEY_LIST 供命令面板底部清单展示
import { useEffect, useRef } from 'react'

export interface HotkeyEntry {
  /** 匹配主键（小写）；修饰键由 modifiers 描述 */
  key: string
  modifiers?: Array<'ctrl' | 'meta' | 'shift' | 'alt'>
  description: string
  handler: () => void
  /** 允许在输入态触发（默认 false：单键快捷键输入态抑制） */
  allowInInput?: boolean
}

// 快捷键清单（命令面板底部展示；Ctrl/B 项由 SidebarProvider 注册，此处一并列出供展示）
export const HOTKEY_LIST: Array<{ combo: string; description: string }> = [
  { combo: 'Ctrl / ⌘ + K', description: '打开命令面板' },
  { combo: 'Ctrl / ⌘ + ⇧ + N', description: '新建会话' },
  { combo: '/', description: '聚焦输入框' },
  { combo: 'Ctrl / ⌘ + B', description: '折叠/展开侧边栏' },
]

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  )
}

function matches(e: KeyboardEvent, entry: HotkeyEntry): boolean {
  if (e.key.toLowerCase() !== entry.key) return false
  const mods = entry.modifiers ?? []
  const hasCtrl = mods.includes('ctrl')
  const hasMeta = mods.includes('meta')
  // ctrl 与 meta 等价匹配（Windows Ctrl / macOS ⌘）
  if (hasCtrl !== e.ctrlKey && hasMeta !== e.metaKey) return false
  if (hasCtrl || hasMeta) {
    // 需要平台修饰键：Ctrl/Cmd 至少一个按下
    if (!(e.ctrlKey || e.metaKey)) return false
  } else if (e.ctrlKey || e.metaKey) {
    return false // 不要求修饰键时按下了修饰键 → 不匹配
  }
  if (mods.includes('shift') !== e.shiftKey) return false
  if (mods.includes('alt') !== e.altKey) return false
  return true
}

export function useHotkeys(entries: HotkeyEntry[]): void {
  // ref 持有最新 entries（避免 handler 闭包过期 & 重复订阅）
  const entriesRef = useRef(entries)
  entriesRef.current = entries

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const editable = isEditableTarget(e.target)
      for (const entry of entriesRef.current) {
        if (!entry.allowInInput && editable && !(e.ctrlKey || e.metaKey)) continue
        if (matches(e, entry)) {
          e.preventDefault()
          entry.handler()
          return
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
