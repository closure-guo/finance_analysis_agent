import type * as React from "react"
import { Toaster as Sonner } from "sonner"
import type { ToasterProps } from "sonner"

// shadcn/ui sonner 封装（next-themes-free 版本）：
// 颜色直接走 Task 1 语义令牌（--popover / --border），无暗色主题切换依赖。
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      position="top-center"
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
