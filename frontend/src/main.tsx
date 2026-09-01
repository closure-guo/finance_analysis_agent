import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { loadThemeChoice, applyTheme, watchSystemTheme } from './theme'

// 首帧前应用持久化主题（polish-dark-mode-shortcuts）：避免深色用户闪浅色；
// 「跟随系统」注册实时切换
applyTheme(loadThemeChoice())
watchSystemTheme(() => applyTheme(loadThemeChoice()))

ReactDOM.createRoot(document.getElementById('root')!).render(
  <>
    <App />
  </>,
)
