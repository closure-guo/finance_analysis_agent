// polish-dark-mode-shortcuts Task 1.1：主题状态管理。
// 三态选择（浅色/深色/跟随系统）持久化到 localStorage（fa_theme）；
// 应用方式为 documentElement.classList.toggle('dark')（index.css .dark 变量覆盖）。
// 「跟随系统」监听 prefers-color-system 变化实时切换。

export type ThemeChoice = 'light' | 'dark' | 'system'

const THEME_KEY = 'fa_theme'

export function loadThemeChoice(): ThemeChoice {
  const raw = localStorage.getItem(THEME_KEY)
  return raw === 'dark' || raw === 'light' || raw === 'system' ? raw : 'system'
}

export function saveThemeChoice(choice: ThemeChoice): void {
  localStorage.setItem(THEME_KEY, choice)
}

// 系统当前是否偏好深色（无 matchMedia 环境——jsdom——回退浅色）
export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

// 依据选择解析实际生效主题
export function resolveTheme(choice: ThemeChoice): 'light' | 'dark' {
  return choice === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : choice
}

// 应用主题到 documentElement；返回实际生效主题
export function applyTheme(choice: ThemeChoice): 'light' | 'dark' {
  const resolved = resolveTheme(choice)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
  return resolved
}

// 订阅系统主题变化（跟随系统模式下实时切换）；返回退订函数
export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => {}
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener('change', onChange)
  return () => mq.removeEventListener('change', onChange)
}
