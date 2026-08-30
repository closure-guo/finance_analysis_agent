import { useEffect, useState } from 'react'

// 轻量 pathname 路由（add-download-center）：不引入 react-router，
// pushState + popstate 即可满足 /downloads 直达/刷新（nginx try_files 已配 SPA fallback）。
export function usePathname(): string {
  const [pathname, setPathname] = useState(() => window.location.pathname)
  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  return pathname
}

export function navigate(to: string): void {
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
